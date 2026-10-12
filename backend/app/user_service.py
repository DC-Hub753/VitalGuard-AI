"""User authentication, credential hashing (PBKDF2-HMAC-SHA256), and account service."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
from typing import Any

from sqlalchemy import func, insert, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from .storage import _engine
from .storage_schema import users


PBKDF2_ITERATIONS = 120_000


def hash_password(password: str) -> str:
    """Hash password using PBKDF2-HMAC-SHA256 with 16-byte cryptographically secure salt."""
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    salt_b64 = base64.b64encode(salt).decode("ascii")
    key_b64 = base64.b64encode(key).decode("ascii")
    return f"pbkdf2:sha256:{PBKDF2_ITERATIONS}${salt_b64}${key_b64}"


def verify_password(password: str, hashed: str) -> bool:
    """Verify password against stored PBKDF2-HMAC-SHA256 hash using constant-time comparison."""
    try:
        scheme, salt_b64, key_b64 = hashed.split("$")
        parts = scheme.split(":")
        iterations = int(parts[2])
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expected_key = base64.b64decode(key_b64.encode("ascii"))
        derived_key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(derived_key, expected_key)
    except Exception:
        return False


def _serialize_user(row: Any) -> dict[str, Any]:
    item = dict(row)
    item.pop("password_hash", None)
    for key in ("created_at", "updated_at"):
        if item.get(key) is not None and hasattr(item[key], "isoformat"):
            item[key] = item[key].isoformat()
    return item


def get_user_by_username(username: str) -> dict[str, Any] | None:
    """Fetch user record including password_hash by username."""
    engine = _engine()
    try:
        with engine.connect() as connection:
            row = connection.execute(
                select(users).where(users.c.username == username)
            ).mappings().first()
        return dict(row) if row else None
    finally:
        engine.dispose()


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    """Fetch user record by ID (excluding password hash)."""
    engine = _engine()
    try:
        with engine.connect() as connection:
            row = connection.execute(
                select(users).where(users.c.id == user_id)
            ).mappings().first()
        return _serialize_user(row) if row else None
    finally:
        engine.dispose()


def list_users() -> list[dict[str, Any]]:
    """List all user accounts."""
    engine = _engine()
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                select(users).order_by(users.c.id)
            ).mappings().all()
        return [_serialize_user(row) for row in rows]
    finally:
        engine.dispose()


def create_user(
    *,
    username: str,
    password: str,
    role: str,
    full_name: str = "",
) -> dict[str, Any]:
    """Create a new user account with hashed password. Raises IntegrityError on duplicate."""
    pw_hash = hash_password(password)
    engine = _engine()
    try:
        with engine.begin() as connection:
            result = connection.execute(insert(users).values(
                username=username,
                password_hash=pw_hash,
                role=role,
                full_name=full_name,
                active=True,
            ))
            row = connection.execute(
                select(users).where(users.c.id == result.inserted_primary_key[0])
            ).mappings().one()
        return _serialize_user(row)
    finally:
        engine.dispose()


def update_user_status(user_id: int, *, active: bool) -> dict[str, Any] | None:
    """Enable or disable a user account."""
    engine = _engine()
    try:
        with engine.begin() as connection:
            existing = connection.execute(
                select(users).where(users.c.id == user_id)
            ).mappings().first()
            if not existing:
                return None
            connection.execute(
                update(users).where(users.c.id == user_id).values(active=active)
            )
            row = connection.execute(
                select(users).where(users.c.id == user_id)
            ).mappings().one()
        return _serialize_user(row)
    finally:
        engine.dispose()


def update_user_role(user_id: int, *, role: str) -> dict[str, Any] | None:
    """Update role for a user account."""
    engine = _engine()
    try:
        with engine.begin() as connection:
            existing = connection.execute(
                select(users).where(users.c.id == user_id)
            ).mappings().first()
            if not existing:
                return None
            connection.execute(
                update(users).where(users.c.id == user_id).values(role=role)
            )
            row = connection.execute(
                select(users).where(users.c.id == user_id)
            ).mappings().one()
        return _serialize_user(row)
    finally:
        engine.dispose()


def seed_initial_users(engine: Engine) -> None:
    """Seed initial role accounts if the users table is completely empty."""
    with engine.begin() as connection:
        count = connection.execute(select(func.count()).select_from(users)).scalar()
        if count and count > 0:
            return

        demo_accounts = [
            ("admin", "AdminPass123!", "admin", "System Administrator"),
            ("clinician", "ClinicianPass123!", "clinician", "Dr. Jane Wilson"),
            ("nurse", "NursePass123!", "nurse", "Nurse Robert Taylor"),
        ]
        for uname, pwd, role, fname in demo_accounts:
            connection.execute(insert(users).values(
                username=uname,
                password_hash=hash_password(pwd),
                role=role,
                full_name=fname,
                active=True,
            ))
