import { createContext, useCallback, useContext, useState } from "react";

interface AuthState {
  token: string | null;
}

interface AuthContextValue extends AuthState {
  setToken: (token: string) => void;
  clearToken: () => void;
}

const AuthContext = createContext<AuthContextValue>({
  token: null,
  setToken: () => {},
  clearToken: () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setTokenState] = useState<string | null>(null);

  const setToken = useCallback((t: string) => setTokenState(t), []);
  const clearToken = useCallback(() => setTokenState(null), []);

  return (
    <AuthContext.Provider value={{ token, setToken, clearToken }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
