/** Step 2 of submitting a pattern: edit the scraped draft, acknowledge the
 * publish-consent notice, then publish. Receives its draft via router
 * state from SubmitPatternPage rather than a URL param, since a draft is
 * never persisted anywhere until Publish is clicked. */
import { useState } from "react";
import { Alert, Button } from "react-bootstrap";
import { useTranslation } from "react-i18next";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { submitPattern } from "../api/client";
import PatternReviewForm from "../components/PatternReviewForm";
import PublishConsentNotice from "../components/PublishConsentNotice";
import { useApiErrorMessage } from "../i18n/useApiErrorMessage";
import type { PatternDraft } from "../types/models";

interface LocationState {
  draft: PatternDraft;
  originalUrl: string;
}

export default function ReviewPatternPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const getErrorMessage = useApiErrorMessage();
  const state = location.state as LocationState | null;

  const [draft, setDraft] = useState<PatternDraft | null>(state?.draft ?? null);
  const [acknowledged, setAcknowledged] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [publishing, setPublishing] = useState(false);

  if (!state || !draft) {
    // Reached directly (e.g. page refresh) without a draft in memory --
    // send the user back to start over, since we never persist drafts.
    return <Navigate to="/submit" replace />;
  }

  async function handlePublish() {
    if (!draft) return;
    setError(null);
    setPublishing(true);
    try {
      const result = await submitPattern({ ...draft, original_url: state!.originalUrl });
      navigate(`/pattern/${result.pattern.id}`);
    } catch (err) {
      setError(getErrorMessage(err, t("review.publishFailed")));
    } finally {
      setPublishing(false);
    }
  }

  return (
    <div>
      <h1 className="mb-2">{t("review.title")}</h1>
      <p className="text-muted">{t("review.sourceLabel", { url: state.originalUrl })}</p>
      <PatternReviewForm draft={draft} onChange={setDraft} />
      <PublishConsentNotice acknowledged={acknowledged} onAcknowledgeChange={setAcknowledged} />
      {error && <Alert variant="danger">{error}</Alert>}
      <Button variant="primary" disabled={!acknowledged || publishing} onClick={handlePublish}>
        {publishing ? t("review.publishing") : t("review.publishButton")}
      </Button>
    </div>
  );
}
