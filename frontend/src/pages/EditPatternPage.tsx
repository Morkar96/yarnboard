/** Edit an already-published pattern. Reuses PatternReviewForm (the same
 * component used pre-publish in the submit flow) -- no PublishConsentNotice
 * here, since this isn't a first-time publish.
 *
 * The client-side gate on who can edit (admin or the original uploader)
 * is UX only -- the backend is the real authority (PATCH /api/patterns/<id>
 * 403s otherwise), so a direct navigation to this URL for a pattern you
 * can't edit still safely fails, just with a plain error message instead
 * of hiding the page entirely. */
import { useEffect, useState } from "react";
import { Alert, Button, Spinner } from "react-bootstrap";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError, fetchPattern, updatePattern } from "../api/client";
import PatternReviewForm from "../components/PatternReviewForm";
import { useAuth } from "../context/AuthContext";
import type { Pattern, PatternDraft } from "../types/models";

/** Pattern.instructions is {part: [{step, completed}]} (viewer-specific
 * progress merged in); PatternReviewForm expects the plain-string draft
 * shape {part: [step]} it already uses pre-publish -- strip `completed`. */
function patternToDraft(pattern: Pattern): PatternDraft {
  const instructions: Record<string, string[]> = {};
  for (const [part, steps] of Object.entries(pattern.instructions)) {
    instructions[part] = steps.map((s) => s.step);
  }
  return {
    title: pattern.title,
    author: pattern.author,
    materials: pattern.materials ?? "",
    abbreviations: pattern.abbreviations ?? "",
    instructions,
    source_site_name: pattern.source_site_name ?? "",
    source_domain: pattern.source_domain ?? "",
  };
}

export default function EditPatternPage() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const navigate = useNavigate();

  const [pattern, setPattern] = useState<Pattern | null>(null);
  const [draft, setDraft] = useState<PatternDraft | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!id) return;
    fetchPattern(Number(id))
      .then((p) => {
        setPattern(p);
        setDraft(patternToDraft(p));
      })
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <Spinner animation="border" variant="primary" />;
  if (notFound || !pattern || !draft) return <p className="text-muted">Pattern not found.</p>;

  const canEdit = !!user && (user.is_admin || user.id === pattern.uploader_id);
  if (!canEdit) {
    return <Alert variant="danger">You don't have permission to edit this pattern.</Alert>;
  }

  async function handleSave() {
    if (!draft || !pattern) return;
    setError(null);
    setSaving(true);
    try {
      await updatePattern(pattern.id, draft);
      navigate(`/pattern/${pattern.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save changes.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <h1 className="mb-3">Edit Pattern</h1>
      <PatternReviewForm draft={draft} onChange={setDraft} />
      {error && (
        <Alert variant="danger" className="mt-3">
          {error}
        </Alert>
      )}
      <Button variant="primary" className="mt-3" disabled={saving} onClick={handleSave}>
        {saving ? "Saving..." : "Save Changes"}
      </Button>
    </div>
  );
}
