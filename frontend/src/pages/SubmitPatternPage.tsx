/** Step 1 of submitting a pattern: either paste a URL to scrape, or
 * upload a file directly -- two explicit, always-available choices (see
 * `mode` below), not one hidden behind the other failing. Either way,
 * this hands off a preview draft to ReviewPatternPage for editing + the
 * publish-consent gate. See PublishConsentNotice for why the review step
 * isn't skippable.
 *
 * "Upload a file" exists for two different reasons that both land on the
 * same form: a PDF (e.g. a paid Etsy/Ravelry pattern that only exists as
 * a PDF in the first place -- there's nothing to "fetch" for those at
 * all) always needs this path, while a normal webpage only needs it when
 * automatic fetching is blocked (e.g. Cloudflare's bot-detection
 * challenge -- see backend/app/scraper.py); the URL field stays required
 * in both cases since it's still what dedup and attribution are based on.
 * A URL-fetch failure also auto-switches to this tab, pre-filled, so the
 * fallback case doesn't need to be discovered separately.
 *
 * This page itself is public (unregistered visitors can read how
 * uploading works), but the actual scrape/submit endpoints all require
 * login server-side -- so anonymous visitors see the explanation plus a
 * login/register prompt instead of the live form, rather than being able
 * to fill it out and only find out it's blocked at the end. */
import { useState, type FormEvent } from "react";
import { Alert, Button, ButtonGroup, Form } from "react-bootstrap";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import { previewPattern, previewPatternFromUpload } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { useApiErrorMessage } from "../i18n/useApiErrorMessage";

type Mode = "link" | "upload";

interface PreviewResult {
  duplicate: boolean;
  existing_pattern_id: number | null;
  already_shared_with_you: number | null;
  draft: unknown;
}

export default function SubmitPatternPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const getErrorMessage = useApiErrorMessage();
  const [mode, setMode] = useState<Mode>("link");
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  // Set instead of navigating straight to review when the preview came
  // back with already_shared_with_you -- the warning has to actually be
  // seen and give the user a real choice (view the shared pattern
  // instead, or continue with their own copy), not just flash by while
  // the page navigates on regardless (see handleContinueAnyway).
  const [pendingSharedResult, setPendingSharedResult] = useState<PreviewResult | null>(null);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadLoading, setUploadLoading] = useState(false);

  function goToReview(result: PreviewResult) {
    if (result.duplicate) {
      navigate(`/pattern/${result.existing_pattern_id}`);
      return;
    }
    if (result.already_shared_with_you) {
      setPendingSharedResult(result);
      return;
    }
    navigate("/submit/review", { state: { draft: result.draft, originalUrl: url } });
  }

  function handleContinueAnyway() {
    if (!pendingSharedResult) return;
    navigate("/submit/review", { state: { draft: pendingSharedResult.draft, originalUrl: url } });
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setPendingSharedResult(null);
    setLoading(true);
    try {
      goToReview(await previewPattern(url));
    } catch (err) {
      setError(getErrorMessage(err, t("submit.genericFetchError")));
      // Any preview failure (blocked by bot-detection, timed out, DNS
      // error, etc.) can potentially be worked around by uploading the
      // page's HTML yourself instead, so switch to that tab (URL
      // preserved) rather than trying to sniff out which failure this was.
      setMode("upload");
    } finally {
      setLoading(false);
    }
  }

  async function handleUploadPreview(e: FormEvent) {
    e.preventDefault();
    if (!uploadFile) return;
    setUploadError(null);
    setPendingSharedResult(null);
    setUploadLoading(true);
    try {
      goToReview(await previewPatternFromUpload(url, uploadFile));
    } catch (err) {
      setUploadError(getErrorMessage(err, t("submit.genericUploadError")));
    } finally {
      setUploadLoading(false);
    }
  }

  return (
    <div>
      <h1 className="mb-3">{t("submit.title")}</h1>
      <p className="text-muted">{t("submit.intro")}</p>

      {!user ? (
        <Alert variant="light" style={{ maxWidth: "32rem" }}>
          <Link to="/login">{t("submit.guestPromptLogin")}</Link> {t("common.or")}{" "}
          <Link to="/register">{t("submit.guestPromptSignup")}</Link> {t("submit.guestPromptTail")}
        </Alert>
      ) : (
        <>
          <ButtonGroup className="mb-3">
            <Button
              variant={mode === "link" ? "primary" : "outline-primary"}
              onClick={() => setMode("link")}
            >
              {t("submit.modeLink")}
            </Button>
            <Button
              variant={mode === "upload" ? "primary" : "outline-primary"}
              onClick={() => setMode("upload")}
            >
              {t("submit.modeUpload")}
            </Button>
          </ButtonGroup>

          {pendingSharedResult?.already_shared_with_you && (
            <Alert variant="warning" style={{ maxWidth: "32rem" }}>
              <p className="mb-2">{t("sharedWithMe.alreadySharedWarning")}</p>
              <div className="d-flex gap-2">
                <Link
                  to={`/pattern/${pendingSharedResult.already_shared_with_you}`}
                  className="btn btn-outline-primary btn-sm"
                >
                  {t("submit.viewSharedPattern")}
                </Link>
                <Button variant="outline-secondary" size="sm" onClick={handleContinueAnyway}>
                  {t("submit.continueAnyway")}
                </Button>
              </div>
            </Alert>
          )}

          {mode === "link" ? (
            <Form onSubmit={handleSubmit} className="mb-2" style={{ maxWidth: "32rem" }}>
              <Form.Group className="mb-3" controlId="submit-url">
                <Form.Label>{t("submit.urlLabel")}</Form.Label>
                <Form.Control
                  type="url"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder={t("submit.urlPlaceholder")}
                  required
                />
              </Form.Group>
              {error && <Alert variant="danger">{error}</Alert>}
              <Button type="submit" variant="primary" disabled={loading}>
                {loading ? t("submit.fetching") : t("submit.previewButton")}
              </Button>
            </Form>
          ) : (
            <div className="mb-2" style={{ maxWidth: "32rem" }}>
              <p className="text-muted">{t("submit.uploadIntro")}</p>
              <Form onSubmit={handleUploadPreview}>
                <Form.Group className="mb-3" controlId="submit-upload-url">
                  <Form.Label>{t("submit.urlLabel")}</Form.Label>
                  <Form.Control
                    type="url"
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    placeholder={t("submit.urlPlaceholder")}
                    required
                  />
                  <Form.Text>{t("submit.uploadUrlHint")}</Form.Text>
                </Form.Group>
                <Form.Group className="mb-3" controlId="submit-upload-file">
                  <Form.Label>{t("submit.uploadFileLabel")}</Form.Label>
                  <Form.Control
                    type="file"
                    accept=".html,.htm,text/html,.pdf,application/pdf"
                    onChange={(e) =>
                      setUploadFile((e.target as HTMLInputElement).files?.[0] ?? null)
                    }
                    required
                  />
                </Form.Group>
                {uploadError && <Alert variant="danger">{uploadError}</Alert>}
                <Button type="submit" variant="primary" disabled={uploadLoading || !uploadFile}>
                  {uploadLoading ? t("submit.processing") : t("submit.uploadButton")}
                </Button>
              </Form>
            </div>
          )}

          <p className="text-muted">
            {t("submit.alreadyHaveIntro")} <Link to="/community">{t("submit.communityPage")}</Link>{" "}
            {t("submit.alreadyHaveTail")}
          </p>
        </>
      )}
    </div>
  );
}
