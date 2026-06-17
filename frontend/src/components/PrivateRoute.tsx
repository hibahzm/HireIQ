import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import SplashScreen from "./ui/SplashScreen";

export default function PrivateRoute({ children }: { children: React.ReactNode }) {
  const { status, kind } = useAuth();

  if (status === "loading") {
    return <SplashScreen label="Restoring your session…" />;
  }

  if (status === "anonymous") return <Navigate to="/login" replace />;
  // Candidates have their own portal; never render the company shell for them.
  if (kind === "candidate") return <Navigate to="/candidate" replace />;

  return <>{children}</>;
}
