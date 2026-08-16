import { useEffect, useState } from "react";
import { Alert, Card, Col, Row, Spinner } from "react-bootstrap";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import { verifyEmail } from "../api/client";
import { useApiErrorMessage } from "../i18n/useApiErrorMessage";

type Status = "verifying" | "success" | "error";

/**
 * Landing page for the link mailed by send_verification_email
 * (backend/app/email.py): /verify-email?token=... . Calls POST
 * /api/verify-email itself on mount rather than the email linking to the
 * API endpoint directly -- keeps the state-changing call same-origin to
 * the frontend and gives us a page to show a result on either outcome.
 */
export default function VerifyEmailPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token");
  const { t } = useTranslation();
  const getErrorMessage = useApiErrorMessage();
  const [status, setStatus] = useState<Status>("verifying");
  const [message, setMessage] = useState<string>("");

  useEffect(() => {
    if (!token) {
      setStatus("error");
      setMessage(t("auth.verify.missingToken"));
      return;
    }
    verifyEmail(token)
      .then((res) => {
        setStatus("success");
        setMessage(res.message);
      })
      .catch((err) => {
        setStatus("error");
        setMessage(getErrorMessage(err, t("auth.verify.failed")));
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  return (
    <Row className="justify-content-center">
      <Col xs={12} sm={8} md={6} lg={5}>
        <Card className="shadow-sm">
          <Card.Body>
            <Card.Title as="h1" className="h3 mb-4">
              {t("auth.verify.title")}
            </Card.Title>
            {status === "verifying" && (
              <div className="d-flex align-items-center gap-2">
                <Spinner animation="border" size="sm" />
                <span>{t("auth.verify.verifying")}</span>
              </div>
            )}
            {status === "success" && (
              <>
                <Alert variant="success">{message}</Alert>
                <Link to="/login">{t("auth.verify.goToLogin")}</Link>
              </>
            )}
            {status === "error" && (
              <>
                <Alert variant="danger">{message}</Alert>
                <Link to="/login">{t("auth.verify.backToLogin")}</Link>
              </>
            )}
          </Card.Body>
        </Card>
      </Col>
    </Row>
  );
}
