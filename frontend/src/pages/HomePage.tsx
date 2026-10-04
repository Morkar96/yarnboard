/**
 * Landing page once logged in (see App.tsx's "/" route and LoginPage's
 * post-login navigate) -- a short how-to for the four things there are to
 * do here, each linking straight to the page that does it. Not a feature
 * in itself, just onboarding; nothing here is fetched from the API.
 */
import { Card, Col, Row } from "react-bootstrap";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

interface Guide {
  titleKey: string;
  descriptionKey: string;
  linkTo: string;
  ctaKey: string;
}

const GUIDES: Guide[] = [
  {
    titleKey: "home.stitchFiddleTitle",
    descriptionKey: "home.stitchFiddleDescription",
    linkTo: "/stitch-fiddle",
    ctaKey: "home.stitchFiddleCta",
  },
  {
    titleKey: "home.submitTitle",
    descriptionKey: "home.submitDescription",
    linkTo: "/submit",
    ctaKey: "home.submitCta",
  },
  {
    titleKey: "home.useTitle",
    descriptionKey: "home.useDescription",
    linkTo: "/community",
    ctaKey: "home.useCta",
  },
  {
    titleKey: "home.editTitle",
    descriptionKey: "home.editDescription",
    linkTo: "/mine",
    ctaKey: "home.editCta",
  },
];

export default function HomePage() {
  const { user } = useAuth();
  const { t } = useTranslation();

  return (
    <>
      <h1 className="mb-1">{user ? t("home.welcomeNamed", { username: user.username }) : t("home.welcome")}</h1>
      <p className="text-muted mb-4">{t("home.subtitle")}</p>
      <Row className="g-3">
        {GUIDES.map((guide) => (
          <Col xs={12} md={6} key={guide.titleKey}>
            <Card className="h-100 shadow-sm">
              <Card.Body className="d-flex flex-column">
                <Card.Title as="h2" className="h5">
                  {t(guide.titleKey)}
                </Card.Title>
                <Card.Text className="flex-grow-1">{t(guide.descriptionKey)}</Card.Text>
                <Link to={guide.linkTo} className="btn btn-outline-primary align-self-start">
                  {t(guide.ctaKey)}
                </Link>
              </Card.Body>
            </Card>
          </Col>
        ))}
      </Row>
    </>
  );
}
