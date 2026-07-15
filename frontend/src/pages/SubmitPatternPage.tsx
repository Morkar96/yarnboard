/** Step 1 of submitting a pattern: paste a URL, scrape a preview draft,
 * then hand off to ReviewPatternPage for editing + the publish-consent
 * gate. See PublishConsentNotice for why the review step isn't skippable. */
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError, previewPattern } from "../api/client";

export default function SubmitPatternPage() {
  const navigate = useNavigate();
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const result = await previewPattern(url);
      if (result.duplicate) {
        navigate(`/pattern/${result.existing_pattern_id}`);
        return;
      }
      navigate("/submit/review", { state: { draft: result.draft, originalUrl: url } });
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not fetch that page. Check the URL and try again.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="submit-page">
      <h1>Submit a Pattern</h1>
      <p>
        Paste a link to a knitting or crochet pattern webpage. We'll pull out the title,
        materials, abbreviations, and instructions for you to review before publishing.
      </p>
      <form onSubmit={handleSubmit}>
        <label>
          Pattern URL
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://example.com/my-pattern"
            required
          />
        </label>
        {error && <p className="form-error">{error}</p>}
        <button type="submit" disabled={loading}>
          {loading ? "Fetching..." : "Preview"}
        </button>
      </form>
      <p>
        Already have this pattern saved? Check the <Link to="/community">Community</Link> page
        first -- Yarnboard avoids storing the same source URL twice.
      </p>
    </div>
  );
}
