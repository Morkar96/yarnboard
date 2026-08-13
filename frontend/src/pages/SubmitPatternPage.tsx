/** Step 1 of submitting a pattern: paste a URL, scrape a preview draft,
 * then hand off to ReviewPatternPage for editing + the publish-consent
 * gate. See PublishConsentNotice for why the review step isn't skippable.
 *
 * Some sites block automatic fetching entirely (e.g. Cloudflare's
 * bot-detection challenge -- see backend/app/scraper.py). When that
 * happens this page offers a fallback: upload the page's saved HTML, or a
 * PDF (e.g. a paid Etsy/Ravelry pattern that only exists as a PDF in the
 * first place -- there's nothing to "fetch" for those at all), and the
 * same extraction heuristics run against that instead. */
import { useState, type FormEvent } from "react";
import { Alert, Button, Card, Form } from "react-bootstrap";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import { previewPattern, previewPatternFromUpload } from "../api/client";
import { useApiErrorMessage } from "../i18n/useApiErrorMessage";

export default function SubmitPatternPage() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const getErrorMessage = useApiErrorMessage();
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [offerUpload, setOfferUpload] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadLoading, setUploadLoading] = useState(false);

  function goToReview(result: { duplicate: boolean; existing_pattern_id: number | null; draft: unknown }) {
    if (result.duplicate) {
      navigate(`/pattern/${result.existing_pattern_id}`);
      return;
    }
    navigate("/submit/review", { state: { draft: result.draft, originalUrl: url } });
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setOfferUpload(false);
    setLoading(true);
    try {
      goToReview(await previewPattern(url));
    } catch (err) {
      setError(getErrorMessage(err, t("submit.genericFetchError")));
      // Any preview failure (blocked by bot-detection, timed out, DNS
      // error, etc.) can potentially be worked around by uploading the
      // page's HTML yourself instead, so always offer it here rather than
      // trying to sniff out which specific failure this was.
      setOfferUpload(true);
    } finally {
      setLoading(false);
    }
  }

  async function handleUploadPreview(e: FormEvent) {
    e.preventDefault();
    if (!uploadFile) return;
    setUploadError(null);
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

      {offerUpload && (
        <Card className="shadow-sm my-4" style={{ maxWidth: "32rem" }}>
          <Card.Body>
            <p>{t("submit.uploadFallbackIntro")}</p>
            <Form onSubmit={handleUploadPreview}>
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
              <Button type="submit" variant="outline-primary" disabled={uploadLoading || !uploadFile}>
                {uploadLoading ? t("submit.processing") : t("submit.uploadButton")}
              </Button>
            </Form>
          </Card.Body>
        </Card>
      )}

      <p className="text-muted">
        {t("submit.alreadyHaveIntro")} <Link to="/community">{t("submit.communityPage")}</Link>{" "}
        {t("submit.alreadyHaveTail")}
      </p>
    </div>
  );
}
