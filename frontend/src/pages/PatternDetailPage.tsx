/** Full pattern view: materials, abbreviations, attribution, and the
 * interactive per-user checklist (PatternChecklist). Fully public --
 * anonymous viewers can use the checklist too, just cached to their own
 * browser instead of synced to an account (see PatternChecklist). */
import { useEffect, useState } from "react";
import { Spinner } from "react-bootstrap";
import { Link, useParams } from "react-router-dom";
import { fetchPattern, resolvePhotoUrl } from "../api/client";
import AttributionTag from "../components/AttributionTag";
import CollapsibleCard from "../components/CollapsibleCard";
import PatternChartGrid from "../components/PatternChartGrid";
import PatternChecklist from "../components/PatternChecklist";
import { useAuth } from "../context/AuthContext";
import type { Pattern } from "../types/models";

export default function PatternDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const [pattern, setPattern] = useState<Pattern | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (!id) return;
    fetchPattern(Number(id))
      .then(setPattern)
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <Spinner animation="border" variant="primary" />;
  if (notFound || !pattern) return <p className="text-muted">Pattern not found.</p>;

  const canEdit = !!user && (user.is_admin || user.id === pattern.uploader_id);

  return (
    <div>
      <div className="d-flex justify-content-between align-items-start">
        <h1 className="mb-2">{pattern.title}</h1>
        {canEdit && (
          <Link to={`/pattern/${pattern.id}/edit`} className="btn btn-outline-primary btn-sm">
            Edit
          </Link>
        )}
      </div>
      <AttributionTag pattern={pattern} />

      {pattern.chart_grid ? (
        <PatternChartGrid grid={pattern.chart_grid} />
      ) : (
        pattern.has_photo && (
          <img
            src={resolvePhotoUrl(pattern.photo_url)}
            alt={pattern.title}
            className="mb-3"
            style={{ maxWidth: "100%", maxHeight: "400px", objectFit: "cover" }}
            onError={(e) => {
              e.currentTarget.style.display = "none";
            }}
          />
        )
      )}

      {pattern.materials && (
        <CollapsibleCard title="Materials">
          <pre className="mb-0" style={{ whiteSpace: "pre-wrap" }}>
            {pattern.materials}
          </pre>
        </CollapsibleCard>
      )}

      {pattern.abbreviations && (
        <CollapsibleCard title="Abbreviations">
          <pre className="mb-0" style={{ whiteSpace: "pre-wrap" }}>
            {pattern.abbreviations}
          </pre>
        </CollapsibleCard>
      )}

      <h2 className="h4 mt-4 mb-3">Instructions</h2>
      <PatternChecklist patternId={pattern.id} instructions={pattern.instructions} />
    </div>
  );
}
