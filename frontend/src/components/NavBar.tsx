import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function NavBar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate("/community");
  }

  return (
    <nav className="navbar">
      <Link to="/community" className="brand">
        Yarnboard
      </Link>
      <Link to="/community">Community</Link>
      {user && (
        <>
          <Link to="/submit">Submit a Pattern</Link>
          <Link to="/mine">My Uploads</Link>
          <Link to="/saved">My Saved</Link>
        </>
      )}
      <span className="navbar-spacer" />
      {user ? (
        <>
          <span>Hi, {user.username}</span>
          <button type="button" onClick={handleLogout}>
            Log out
          </button>
        </>
      ) : (
        <>
          <Link to="/login">Log in</Link>
          <Link to="/register">Sign up</Link>
        </>
      )}
    </nav>
  );
}
