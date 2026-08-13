import { Button, Container, Nav, Navbar } from "react-bootstrap";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function NavBar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    // /community now requires login (ProtectedRoute), so sending a
    // logged-out user there would just bounce them straight to /login
    // anyway -- skip the pointless extra redirect.
    navigate("/login");
  }

  return (
    <Navbar expand="md" data-bs-theme="dark" className="navbar-eggplant mb-4" collapseOnSelect>
      <Container>
        <Navbar.Brand as={Link} to="/community" className="fw-bold">
          Yarnboard
        </Navbar.Brand>
        <Navbar.Toggle aria-controls="main-nav" />
        <Navbar.Collapse id="main-nav">
          <Nav className="me-auto">
            <Nav.Link as={Link} to="/community">
              Community
            </Nav.Link>
            {user && (
              <>
                <Nav.Link as={Link} to="/submit">
                  Submit a Pattern
                </Nav.Link>
                <Nav.Link as={Link} to="/mine">
                  My Uploads
                </Nav.Link>
                <Nav.Link as={Link} to="/saved">
                  My Saved
                </Nav.Link>
                <Nav.Link as={Link} to="/stitch-fiddle">
                  Stitch Fiddle
                </Nav.Link>
              </>
            )}
          </Nav>
          {user ? (
            <Nav className="align-items-md-center gap-2">
              <Navbar.Text>
                Hi, <strong>{user.username}</strong>
              </Navbar.Text>
              <Button variant="outline-light" size="sm" onClick={handleLogout}>
                Log out
              </Button>
            </Nav>
          ) : (
            <Nav className="align-items-md-center gap-2">
              <Nav.Link as={Link} to="/login">
                Log in
              </Nav.Link>
              <Link to="/register" className="btn btn-light btn-sm">
                Sign up
              </Link>
            </Nav>
          )}
        </Navbar.Collapse>
      </Container>
    </Navbar>
  );
}
