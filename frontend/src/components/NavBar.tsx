import { Button, Container, Nav, Navbar } from "react-bootstrap";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function NavBar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { t, i18n } = useTranslation();

  async function handleLogout() {
    await logout();
    navigate("/community");
  }

  /** Only two languages exist (see i18n/index.ts's SUPPORTED_LANGUAGES),
   * so this is a toggle, not a picker -- switching to "the other one" is
   * unambiguous. The button's own label is the *other* language's name
   * (nav.language), not the current one -- "עברית" while in English,
   * "English" while in Hebrew -- so it reads as "switch to X" rather
   * than "you are currently in X". */
  function toggleLanguage() {
    i18n.changeLanguage(i18n.language === "he" ? "en" : "he");
  }

  return (
    <Navbar expand="md" data-bs-theme="dark" className="navbar-eggplant mb-4" collapseOnSelect>
      <Container>
        <Navbar.Brand as={Link} to="/" className="fw-bold">
          {t("nav.brand")}
        </Navbar.Brand>
        <Navbar.Toggle aria-controls="main-nav" />
        <Navbar.Collapse id="main-nav">
          <Nav className="me-auto">
            <Nav.Link as={Link} to="/community">
              {t("nav.community")}
            </Nav.Link>
            <Nav.Link as={Link} to="/submit">
              {t("nav.submit")}
            </Nav.Link>
            {user && (
              <>
                <Nav.Link as={Link} to="/mine">
                  {t("nav.myUploads")}
                </Nav.Link>
                <Nav.Link as={Link} to="/saved">
                  {t("nav.mySaved")}
                </Nav.Link>
                <Nav.Link as={Link} to="/stitch-fiddle">
                  {t("nav.stitchFiddle")}
                </Nav.Link>
              </>
            )}
          </Nav>
          <Nav className="align-items-md-center gap-2">
            <Button variant="outline-light" size="sm" onClick={toggleLanguage}>
              {t("nav.language")}
            </Button>
            {user ? (
              <>
                <Navbar.Text>{t("nav.greeting", { username: user.username })}</Navbar.Text>
                <Button variant="outline-light" size="sm" onClick={handleLogout}>
                  {t("nav.logout")}
                </Button>
              </>
            ) : (
              <>
                <Nav.Link as={Link} to="/login">
                  {t("nav.login")}
                </Nav.Link>
                <Link to="/register" className="btn btn-light btn-sm">
                  {t("nav.signup")}
                </Link>
              </>
            )}
          </Nav>
        </Navbar.Collapse>
      </Container>
    </Navbar>
  );
}
