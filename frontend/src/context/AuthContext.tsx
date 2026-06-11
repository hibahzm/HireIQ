import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { api } from "../services/api";

export type AuthStatus = "loading" | "authenticated" | "anonymous";

export interface AuthUser {
  id: string;
  company_id: string;
  email: string;
  role: string;
  is_active: boolean;
}

interface AuthContextValue {
  token: string | null;
  user: AuthUser | null;
  status: AuthStatus;
  setToken: (token: string) => void;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue>({
  token: null,
  user: null,
  status: "loading",
  setToken: () => {},
  logout: async () => {},
});

/** Seconds until a JWT expires, or null if it can't be parsed. */
function secondsUntilExpiry(token: string): number | null {
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    if (typeof payload.exp !== "number") return null;
    return payload.exp - Math.floor(Date.now() / 1000);
  } catch {
    return null;
  }
}

function userFromToken(token: string): AuthUser | null {
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    if (!payload.sub || !payload.company_id || !payload.role) return null;
    return {
      id: payload.sub,
      company_id: payload.company_id,
      email: "",
      role: payload.role,
      is_active: true,
    };
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setTokenState] = useState<string | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Holds the latest silentRefresh so the scheduled timer can call it without
  // creating a circular useCallback dependency.
  const silentRefreshRef = useRef<() => void>(() => {});

  const loadUser = useCallback(async (accessToken: string) => {
    try {
      const me = await api.auth.me(accessToken);
      setUser(me);
    } catch {
      // Non-fatal: the identity chip just stays empty.
    }
  }, []);

  // Apply a fresh access token: store it, load the profile, and schedule the
  // next silent refresh shortly before it expires.
  const applyToken = useCallback(
    (accessToken: string) => {
      setTokenState(accessToken);
      setUser(userFromToken(accessToken));
      setStatus("authenticated");
      void loadUser(accessToken);

      if (refreshTimer.current) clearTimeout(refreshTimer.current);
      const ttl = secondsUntilExpiry(accessToken);
      const delayMs = ttl !== null ? Math.max(ttl - 60, 30) * 1000 : 10 * 60 * 1000;
      refreshTimer.current = setTimeout(() => silentRefreshRef.current(), delayMs);
    },
    [loadUser]
  );

  // Exchange the httpOnly refresh cookie for a fresh access token.
  const silentRefresh = useCallback(async () => {
    try {
      const res = await api.auth.refresh();
      applyToken(res.access_token);
    } catch {
      setTokenState(null);
      setUser(null);
      setStatus("anonymous");
    }
  }, [applyToken]);

  useEffect(() => {
    silentRefreshRef.current = () => void silentRefresh();
  }, [silentRefresh]);

  const setToken = useCallback((t: string) => applyToken(t), [applyToken]);

  const logout = useCallback(async () => {
    if (refreshTimer.current) clearTimeout(refreshTimer.current);
    try {
      if (token) await api.auth.logout(token);
    } catch {
      // Ignore — clear local state regardless.
    }
    setTokenState(null);
    setUser(null);
    setStatus("anonymous");
  }, [token]);

  // On first load, try to restore the session from the refresh cookie.
  useEffect(() => {
    void silentRefresh();
    return () => {
      if (refreshTimer.current) clearTimeout(refreshTimer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <AuthContext.Provider value={{ token, user, status, setToken, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
