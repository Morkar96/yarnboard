/** Redirects to /login if there's no logged-in user once the initial
 * session-restore check (AuthContext's `loading`) has finished. */
import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();

  if (loading) return <p>Loading...</p>;
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}
