import { useState, type FormEvent } from "react";
import { Alert, Button, Card, Col, Form, Row } from "react-bootstrap";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { ApiError, resendVerification } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { useApiErrorMessage } from "../i18n/useApiErrorMessage";

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const getErrorMessage = useApiErrorMessage();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  // Only login's 403 ("verify your email first") means resending helps --
  // a plain 401 (wrong credentials) shouldn't offer it.
  const [showResend, setShowResend] = useState(false);
  const [resendStatus, setResendStatus] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setShowResend(false);
    setResendStatus(null);
    setSubmitting(true);
    try {
      await login(email, password);
      navigate("/");
    } catch (err) {
      setError(getErrorMessage(err, t("auth.login.failed")));
      setShowResend(err instanceof ApiError && err.status === 403);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleResend() {
    setResendStatus(null);
    try {
      await resendVerification(email);
      setResendStatus(t("auth.login.resendSent"));
    } catch {
      setResendStatus(t("auth.login.resendFailed"));
    }
  }

  return (
    <Row className="justify-content-center">
      <Col xs={12} sm={8} md={5} lg={4}>
        <Card className="shadow-sm">
          <Card.Body>
            <Card.Title as="h1" className="h3 mb-4">
              {t("auth.login.title")}
            </Card.Title>
            <Form onSubmit={handleSubmit}>
              <Form.Group className="mb-3" controlId="login-email">
                <Form.Label>{t("auth.login.emailLabel")}</Form.Label>
                <Form.Control
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </Form.Group>
              <Form.Group className="mb-3" controlId="login-password">
                <Form.Label>{t("auth.login.passwordLabel")}</Form.Label>
                <Form.Control
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </Form.Group>
              {error && (
                <Alert variant="danger">
                  {error}
                  {showResend && (
                    <>
                      {" "}
                      <Alert.Link as="button" type="button" onClick={handleResend}>
                        {t("auth.login.resendLink")}
                      </Alert.Link>
                    </>
                  )}
                </Alert>
              )}
              {resendStatus && <Alert variant="info">{resendStatus}</Alert>}
              <Button type="submit" variant="primary" className="w-100" disabled={submitting}>
                {submitting ? t("auth.login.submitting") : t("auth.login.submit")}
              </Button>
            </Form>
          </Card.Body>
        </Card>
      </Col>
    </Row>
  );
}
