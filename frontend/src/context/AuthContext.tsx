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
export type AuthKind = "company" | "candidate";

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
  kind: AuthKind | null;
  status: AuthStatus;
  setToken: (token: string) => void;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue>({
  token: null,
  user: null,
  kind: null,
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

/** Candidate tokens carry typ="candidate" and no company_id; company tokens don't. */
function kindFromToken(token: string): AuthKind {
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    return payload.typ === "candidate" ? "candidate" : "company";
  } catch {
    return "company";
  }
}

function userFromToken(token: string): AuthUser | null {
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    if (payload.typ === "candidate") {
      if (!payload.sub) return null;
      return { id: payload.sub, company_id: "", email: "", role: "candidate", is_active: true };
    }
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
  const [kind, setKind] = useState<AuthKind | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Holds the latest silentRefresh so the scheduled timer can call it without
  // creating a circular useCallback dependency.
  const silentRefreshRef = useRef<() => void>(() => {});
  // The known principal kind, so a scheduled refresh hits the right endpoint.
  const kindRef = useRef<AuthKind | null>(null);

  const loadUser = useCallback(async (accessToken: string, principalKind: AuthKind) => {
    try {
      if (principalKind === "candidate") {
        const me = await api.candidateAuth.me(accessToken);
        setUser({
          id: me.id,
          company_id: "",
          email: me.email,
          role: "candidate",
          is_active: me.is_active,
        });
      } else {
        const me = await api.auth.me(accessToken);
        setUser(me);
      }
    } catch {
      // Non-fatal: the identity chip just stays empty.
    }
  }, []);

  // Apply a fresh access token: store it, load the profile, and schedule the
  // next silent refresh shortly before it expires.
  const applyToken = useCallback(
    (accessToken: string) => {
      const principalKind = kindFromToken(accessToken);
      kindRef.current = principalKind;
      setTokenState(accessToken);
      setKind(principalKind);
      setUser(userFromToken(accessToken));
      setStatus("authenticated");
      void loadUser(accessToken, principalKind);

      if (refreshTimer.current) clearTimeout(refreshTimer.current);
      const ttl = secondsUntilExpiry(accessToken);
      const delayMs = ttl !== null ? Math.max(ttl - 60, 30) * 1000 : 10 * 60 * 1000;
      refreshTimer.current = setTimeout(() => silentRefreshRef.current(), delayMs);
    },
    [loadUser]
  );

  // Exchange the httpOnly refresh cookie for a fresh access token. The refresh
  // cookie is shared, so when the kind is unknown (first load) we try the
  // company endpoint first, then fall back to the candidate endpoint.
  const silentRefresh = useCallback(async () => {
    const tryRefresh = async () => {
      const known = kindRef.current;
      if (known === "candidate") return api.candidateAuth.refresh();
      if (known === "company") return api.auth.refresh();
      try {
        return await api.auth.refresh();
      } catch {
        return api.candidateAuth.refresh();
      }
    };
    try {
      const res = await tryRefresh();
      applyToken(res.access_token);
    } catch {
      kindRef.current = null;
      setTokenState(null);
      setUser(null);
      setKind(null);
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
    kindRef.current = null;
    setTokenState(null);
    setUser(null);
    setKind(null);
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

  // Any 401 from the API (expired, deactivated, or revoked session) clears the
  // session so protected routes redirect to login instead of showing a stale UI.
  useEffect(() => {
    const onUnauthorized = () => {
      if (refreshTimer.current) clearTimeout(refreshTimer.current);
      kindRef.current = null;
      setTokenState(null);
      setUser(null);
      setKind(null);
      setStatus("anonymous");
    };
    window.addEventListener("auth:unauthorized", onUnauthorized);
    return () => window.removeEventListener("auth:unauthorized", onUnauthorized);
  }, []);

  return (
    <AuthContext.Provider value={{ token, user, kind, status, setToken, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
