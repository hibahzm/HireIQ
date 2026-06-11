import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import SplashScreen from "./ui/SplashScreen";

export default function PrivateRoute({ children }: { children: React.ReactNode }) {
  const { status } = useAuth();

  if (status === "loading") {
    return <SplashScreen label="Restoring your session…" />;
  }

  if (status === "anonymous") return <Navigate to="/login" replace />;

  return <>{children}</>;
}
