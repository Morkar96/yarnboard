/** Step 2 of submitting a pattern: edit the scraped draft, then save it.
 * Receives its draft via router state from SubmitPatternPage rather than
 * a URL param, since a draft is never persisted anywhere until Save is
 * clicked.
 *
 * Saving here only ever creates a *private* Pattern row (see Pattern.
 * is_public's docstring in backend/app/models.py) -- it doesn't publish
 * to the community, so there's no consent gate here the way there used
 * to be. That gate now lives on PatternVisibilityPanel, shown at the
 * point a pattern actually does become public. */
import { useState } from "react";
import { Alert, Button } from "react-bootstrap";
import { useTranslation } from "react-i18next";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { submitPattern } from "../api/client";
import PatternReviewForm from "../components/PatternReviewForm";
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
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  if (!state || !draft) {
    // Reached directly (e.g. page refresh) without a draft in memory --
    // send the user back to start over, since we never persist drafts.
    return <Navigate to="/submit" replace />;
  }

  async function handleSave() {
    if (!draft) return;
    setError(null);
    setSaving(true);
    try {
      const result = await submitPattern({ ...draft, original_url: state!.originalUrl });
      navigate(`/pattern/${result.pattern.id}`);
    } catch (err) {
      setError(getErrorMessage(err, t("review.saveFailed")));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <h1 className="mb-2">{t("review.title")}</h1>
      <p className="text-muted">{t("review.sourceLabel", { url: state.originalUrl })}</p>
      <PatternReviewForm draft={draft} onChange={setDraft} />
      <Alert variant="light" className="my-4">
        {t("review.saveNotice")}
      </Alert>
      {error && <Alert variant="danger">{error}</Alert>}
      <Button variant="primary" disabled={saving} onClick={handleSave}>
        {saving ? t("review.saving") : t("review.saveButton")}
      </Button>
    </div>
  );
}
