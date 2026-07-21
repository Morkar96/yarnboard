/** Full pattern view: materials, abbreviations, attribution, and the
 * interactive per-user checklist (PatternChecklist). Public to view; the
 * checklist itself only accepts input from logged-in users. */
import { useEffect, useState } from "react";
import { Card, Spinner } from "react-bootstrap";
import { useParams } from "react-router-dom";
import { fetchPattern } from "../api/client";
import AttributionTag from "../components/AttributionTag";
import PatternChecklist from "../components/PatternChecklist";
import type { Pattern } from "../types/models";

export default function PatternDetailPage() {
  const { id } = useParams<{ id: string }>();
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

  return (
    <div>
      <h1 className="mb-2">{pattern.title}</h1>
      <AttributionTag pattern={pattern} />

      {pattern.materials && (
        <Card className="shadow-sm mb-3">
          <Card.Header className="bg-white fw-semibold">Materials</Card.Header>
          <Card.Body>
            <pre className="mb-0" style={{ whiteSpace: "pre-wrap" }}>
              {pattern.materials}
            </pre>
          </Card.Body>
        </Card>
      )}

      {pattern.abbreviations && (
        <Card className="shadow-sm mb-3">
          <Card.Header className="bg-white fw-semibold">Abbreviations</Card.Header>
          <Card.Body>
            <pre className="mb-0" style={{ whiteSpace: "pre-wrap" }}>
              {pattern.abbreviations}
            </pre>
          </Card.Body>
        </Card>
      )}

      <h2 className="h4 mt-4 mb-3">Instructions</h2>
      <PatternChecklist patternId={pattern.id} instructions={pattern.instructions} />
    </div>
  );
}
