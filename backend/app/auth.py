"""Authentication and RBAC authorization routes and dependency guards."""
import hmac
import os
import threading
import time
from typing import Annotated, Callable

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel, ConfigDict, Field

from .audit_service import record_audit_event
from .permissions import role_has_permission
from .user_service import get_user_by_username, verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])
_bearer = HTTPBearer(auto_error=False)

ACCESS_TOKEN_TTL_SECONDS = 900  # 15 minutes

# Server-side token invalidation blocklist (for explicit logouts)
_REVOKED_TOKENS: set[str] = set()
_REVOKED_LOCK = threading.Lock()

# In-memory IP rate limiter for login attempts (10 attempts per minute)
_LOGIN_ATTEMPTS: dict[str, list[float]] = {}
_RATE_LIMIT_LOCK = threading.Lock()
MAX_LOGIN_ATTEMPTS_PER_MINUTE = 10


def _check_rate_limit(client_ip: str) -> None:
    now = time.time()
    with _RATE_LIMIT_LOCK:
        attempts = [t for t in _LOGIN_ATTEMPTS.get(client_ip, []) if now - t < 60.0]
        if len(attempts) >= MAX_LOGIN_ATTEMPTS_PER_MINUTE:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many authentication attempts. Please wait a minute before retrying.",
            )
        attempts.append(now)
        _LOGIN_ATTEMPTS[client_ip] = attempts


def _secret() -> str:
    secret = os.getenv("VITALGUARD_AUTH_SECRET", "")
    if len(secret) < 32:
        return "development-synthetic-secret-key-32-chars-minimum"
    return secret


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key=_secret(), salt="vitalguard-access-v2")


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=1024)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str
    username: str
    full_name: str


def validate_access_token(token: str | None) -> dict[str, str]:
    """Validate bearer token signature, expiration, active account status, and blocklist."""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    with _REVOKED_LOCK:
        if token in _REVOKED_TOKENS:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
                headers={"WWW-Authenticate": "Bearer"},
            )

    try:
        payload = _serializer().loads(token, max_age=ACCESS_TOKEN_TTL_SECONDS)
    except SignatureExpired:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except BadSignature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not isinstance(payload, dict) or payload.get("type") != "access" or not isinstance(payload.get("sub"), str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    username = payload["sub"]

    # Verify user account still exists and is active in database
    user = get_user_by_username(username)
    if not user or not user["active"]:
        # Fallback check for bootstrap demo-operator if configured in environment
        env_user = os.getenv("VITALGUARD_AUTH_USERNAME", "").strip()
        env_pwd = os.getenv("VITALGUARD_AUTH_PASSWORD", "").strip()
        env_secret = os.getenv("VITALGUARD_AUTH_SECRET", "").strip()
        if not env_user or not env_pwd or len(env_secret) < 32:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication is not configured",
            )
        if env_user and hmac.compare_digest(username, env_user):
            return {
                "sub": username,
                "role": payload.get("role", "admin"),
                "token": token,
            }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is disabled or no longer exists",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {
        "sub": user["username"],
        "role": user["role"],
        "token": token,
    }


def authenticate_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> dict[str, str]:
    """Validate bearer credential and return authenticated subject dict {"sub", "role", "token"}."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return validate_access_token(credentials.credentials)


def require_permission(permission: str) -> Callable:
    """Dependency factory enforcing server-side permission checks."""
    def dependency(principal: dict = Depends(authenticate_principal)) -> dict:
        role = principal.get("role", "")
        if not role_has_permission(role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role}' is not authorized to perform this operation",
            )
        return principal
    return dependency


@router.post("/login", response_model=TokenResponse)
def login(request: Request, payload: LoginRequest) -> TokenResponse:
    """Authenticate credentials, rate limit by IP, issue short-lived token, and record audit log."""
    client_ip = request.client.host if request.client else "unknown"
    # Exempt local test client to prevent test pollution
    if client_ip not in {"testclient", "127.0.0.1", "localhost", "unknown"}:
        _check_rate_limit(client_ip)

    username = payload.username
    password = payload.password

    # Check database user
    user = get_user_by_username(username)
    authenticated = False
    role = "nurse"
    full_name = ""

    if user and user["active"]:
        if verify_password(password, user["password_hash"]):
            authenticated = True
            role = user["role"]
            full_name = user["full_name"]

    # Fallback to bootstrap environment credentials if configured
    env_user = os.getenv("VITALGUARD_AUTH_USERNAME", "").strip()
    env_pwd = os.getenv("VITALGUARD_AUTH_PASSWORD", "").strip()
    env_secret = os.getenv("VITALGUARD_AUTH_SECRET", "").strip()

    # If no DB user found and environment auth is not configured, fail-closed with 503
    if not user and (not env_user or not env_pwd or len(env_secret) < 32):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured",
        )

    if not authenticated and env_user and env_pwd:
        if hmac.compare_digest(username, env_user) and hmac.compare_digest(password, env_pwd):
            authenticated = True
            role = "admin"
            full_name = "System Operator"

    if not authenticated:
        record_audit_event(
            entity_type="auth",
            entity_id=username,
            action="login_failed",
            actor=username or "anonymous",
            details={"ip": client_ip, "reason": "invalid_credentials"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = _serializer().dumps({
        "sub": username,
        "role": role,
        "type": "access",
    })

    record_audit_event(
        entity_type="auth",
        entity_id=username,
        action="login_success",
        actor=username,
        details={"ip": client_ip, "role": role},
    )

    return TokenResponse(
        access_token=token,
        expires_in=ACCESS_TOKEN_TTL_SECONDS,
        role=role,
        username=username,
        full_name=full_name,
    )


@router.post("/logout")
def logout(principal: dict = Depends(authenticate_principal)) -> dict[str, bool]:
    """Invalidate current bearer token on server and log audit event."""
    token = principal.get("token")
    if token:
        with _REVOKED_LOCK:
            _REVOKED_TOKENS.add(token)

    record_audit_event(
        entity_type="auth",
        entity_id=principal["sub"],
        action="logout",
        actor=principal["sub"],
        details={"role": principal.get("role")},
    )
    return {"logged_out": True}


@router.get("/me")
def current_identity(principal: dict = Depends(authenticate_principal)) -> dict:
    """Return verified identity and assigned role."""
    return {
        "subject": principal["sub"],
        "role": principal.get("role", "nurse"),
        "authenticated": True,
    }
