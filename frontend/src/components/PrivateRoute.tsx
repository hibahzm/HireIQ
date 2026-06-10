import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import Spinner from "./ui/Spinner";

export default function PrivateRoute({ children }: { children: React.ReactNode }) {
  const { status } = useAuth();

  if (status === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-canvas">
        <Spinner label="Restoring your session…" />
      </div>
    );
  }

  if (status === "anonymous") return <Navigate to="/login" replace />;

  return <>{children}</>;
}
