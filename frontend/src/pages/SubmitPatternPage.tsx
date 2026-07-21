/** Step 1 of submitting a pattern: paste a URL, scrape a preview draft,
 * then hand off to ReviewPatternPage for editing + the publish-consent
 * gate. See PublishConsentNotice for why the review step isn't skippable.
 *
 * Some sites block automatic fetching entirely (e.g. Cloudflare's
 * bot-detection challenge -- see backend/app/scraper.py). When that
 * happens this page offers a fallback: save the page's HTML yourself and
 * upload it, and the same extraction heuristics run against that instead. */
import { useState, type FormEvent } from "react";
import { Alert, Button, Card, Form } from "react-bootstrap";
import { Link, useNavigate } from "react-router-dom";
import { ApiError, previewPattern, previewPatternFromUpload } from "../api/client";

export default function SubmitPatternPage() {
  const navigate = useNavigate();
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
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not fetch that page. Check the URL and try again.",
      );
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
      setUploadError(err instanceof ApiError ? err.message : "Could not process that file.");
    } finally {
      setUploadLoading(false);
    }
  }

  return (
    <div>
      <h1 className="mb-3">Submit a Pattern</h1>
      <p className="text-muted">
        Paste a link to a knitting or crochet pattern webpage. We'll pull out the title,
        materials, abbreviations, and instructions for you to review before publishing.
      </p>
      <Form onSubmit={handleSubmit} className="mb-2" style={{ maxWidth: "32rem" }}>
        <Form.Group className="mb-3" controlId="submit-url">
          <Form.Label>Pattern URL</Form.Label>
          <Form.Control
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://example.com/my-pattern"
            required
          />
        </Form.Group>
        {error && <Alert variant="danger">{error}</Alert>}
        <Button type="submit" variant="primary" disabled={loading}>
          {loading ? "Fetching..." : "Preview"}
        </Button>
      </Form>

      {offerUpload && (
        <Card className="shadow-sm my-4" style={{ maxWidth: "32rem" }}>
          <Card.Body>
            <p>
              Couldn't fetch that page automatically -- some sites block automated requests. If
              you have the page saved as an HTML file (open it in your browser, then "Save Page
              As..." / "Save As" and choose "Webpage, HTML only"), you can upload it here
              instead. The URL above is still used to credit the original source and to avoid
              duplicates.
            </p>
            <Form onSubmit={handleUploadPreview}>
              <Form.Group className="mb-3" controlId="submit-upload-file">
                <Form.Label>Saved HTML file</Form.Label>
                <Form.Control
                  type="file"
                  accept=".html,.htm,text/html"
                  onChange={(e) =>
                    setUploadFile((e.target as HTMLInputElement).files?.[0] ?? null)
                  }
                  required
                />
              </Form.Group>
              {uploadError && <Alert variant="danger">{uploadError}</Alert>}
              <Button type="submit" variant="outline-primary" disabled={uploadLoading || !uploadFile}>
                {uploadLoading ? "Processing..." : "Preview from file"}
              </Button>
            </Form>
          </Card.Body>
        </Card>
      )}

      <p className="text-muted">
        Already have this pattern saved? Check the <Link to="/community">Community</Link> page
        first -- Yarnboard avoids storing the same source URL twice.
      </p>
    </div>
  );
}
