import { useState, type FormEvent } from "react";
import { Alert, Button, Card, Col, Form, Row } from "react-bootstrap";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useApiErrorMessage } from "../i18n/useApiErrorMessage";

export default function RegisterPage() {
  const { register } = useAuth();
  const { t } = useTranslation();
  const getErrorMessage = useApiErrorMessage();
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  // Set once registration succeeds -- there's no session to navigate into
  // (the account starts unverified), so this page shows a confirmation
  // instead of redirecting to /community.
  const [registeredEmail, setRegisteredEmail] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await register(username, email, password);
      setRegisteredEmail(email);
    } catch (err) {
      setError(getErrorMessage(err, t("auth.register.failed")));
    } finally {
      setSubmitting(false);
    }
  }

  if (registeredEmail) {
    return (
      <Row className="justify-content-center">
        <Col xs={12} sm={8} md={5} lg={4}>
          <Card className="shadow-sm">
            <Card.Body>
              <Card.Title as="h1" className="h3 mb-4">
                {t("auth.register.checkEmailTitle")}
              </Card.Title>
              <p>{t("auth.register.checkEmailBody", { email: registeredEmail })}</p>
              <Link to="/login">{t("auth.register.goToLogin")}</Link>
            </Card.Body>
          </Card>
        </Col>
      </Row>
    );
  }

  return (
    <Row className="justify-content-center">
      <Col xs={12} sm={8} md={5} lg={4}>
        <Card className="shadow-sm">
          <Card.Body>
            <Card.Title as="h1" className="h3 mb-4">
              {t("auth.register.title")}
            </Card.Title>
            <Form onSubmit={handleSubmit}>
              <Form.Group className="mb-3" controlId="register-username">
                <Form.Label>{t("auth.register.usernameLabel")}</Form.Label>
                <Form.Control value={username} onChange={(e) => setUsername(e.target.value)} required />
              </Form.Group>
              <Form.Group className="mb-3" controlId="register-email">
                <Form.Label>{t("auth.register.emailLabel")}</Form.Label>
                <Form.Control
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </Form.Group>
              <Form.Group className="mb-3" controlId="register-password">
                <Form.Label>{t("auth.register.passwordLabel")}</Form.Label>
                <Form.Control
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={6}
                />
              </Form.Group>
              {error && <Alert variant="danger">{error}</Alert>}
              <Button type="submit" variant="primary" className="w-100" disabled={submitting}>
                {submitting ? t("auth.register.submitting") : t("auth.register.submit")}
              </Button>
            </Form>
          </Card.Body>
        </Card>
      </Col>
    </Row>
  );
}
