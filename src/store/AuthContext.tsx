import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import { APP_CONFIG } from '../services/config.ts';

export type UserRole = 'admin' | 'clinician' | 'nurse';

type AuthState = {
  token: string;
  username: string;
  role: UserRole;
  fullName: string;
  expiresAt: number;
};

type AuthContextValue = {
  token: string | null;
  username: string | null;
  role: UserRole | null;
  fullName: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  hasRole: (roles: UserRole[]) => boolean;
};

const STORAGE_KEY = 'vitalguard.operator.session';

const AuthContext = createContext<AuthContextValue | null>(null);

function readSession(): AuthState | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const value = JSON.parse(raw) as AuthState;
    if (!value.token || !value.username || value.expiresAt <= Date.now()) {
      sessionStorage.removeItem(STORAGE_KEY);
      return null;
    }
    return value;
  } catch {
    sessionStorage.removeItem(STORAGE_KEY);
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<AuthState | null>(() => readSession());

  const logout = useCallback(async () => {
    const currentToken = session?.token;
    if (currentToken) {
      try {
        await fetch(`${APP_CONFIG.apiBaseUrl}/api/v1/auth/logout`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${currentToken}`,
          },
          signal: AbortSignal.timeout(3000),
        });
      } catch {
        // Silently continue with local cleanup
      }
    }
    sessionStorage.removeItem(STORAGE_KEY);
    setSession(null);
  }, [session]);

  const login = useCallback(async (username: string, password: string) => {
    const response = await fetch(`${APP_CONFIG.apiBaseUrl}/api/v1/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
      signal: AbortSignal.timeout(30000),
    });

    if (!response.ok) {
      if (response.status === 429) {
        throw new Error('Too many login attempts. Please wait a minute and try again.');
      }
      if (response.status === 503) {
        throw new Error('Authentication is not configured on the server. Please contact system administrator.');
      }
      if (response.status === 401) {
        throw new Error('Invalid username or password.');
      }
      throw new Error(`Login failed (${response.status}). Please try again.`);
    }

    const result = await response.json() as {
      access_token: string;
      expires_in: number;
      role: UserRole;
      username: string;
      full_name?: string;
    };

    const next: AuthState = {
      token: result.access_token,
      username: result.username,
      role: result.role || 'nurse',
      fullName: result.full_name || result.username,
      expiresAt: Date.now() + result.expires_in * 1000,
    };

    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    setSession(next);
  }, []);

  const hasRole = useCallback((roles: UserRole[]): boolean => {
    if (!session || session.expiresAt <= Date.now()) return false;
    return roles.includes(session.role);
  }, [session]);

  const value = useMemo(() => {
    const active = session && session.expiresAt > Date.now();
    return {
      token: active ? session.token : null,
      username: active ? session.username : null,
      role: active ? session.role : null,
      fullName: active ? session.fullName : null,
      login,
      logout,
      hasRole,
    };
  }, [session, login, logout, hasRole]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within AuthProvider');
  return context;
}

export function useOptionalAuth() {
  return useContext(AuthContext);
}
