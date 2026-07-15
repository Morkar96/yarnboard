/** Full pattern view: materials, abbreviations, attribution, and the
 * interactive per-user checklist (PatternChecklist). Public to view; the
 * checklist itself only accepts input from logged-in users. */
import { useEffect, useState } from "react";
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

  if (loading) return <p>Loading...</p>;
  if (notFound || !pattern) return <p>Pattern not found.</p>;

  return (
    <div className="pattern-detail-page">
      <h1>{pattern.title}</h1>
      <AttributionTag pattern={pattern} />

      {pattern.materials && (
        <section>
          <h2>Materials</h2>
          <pre>{pattern.materials}</pre>
        </section>
      )}

      {pattern.abbreviations && (
        <section>
          <h2>Abbreviations</h2>
          <pre>{pattern.abbreviations}</pre>
        </section>
      )}

      <section>
        <h2>Instructions</h2>
        <PatternChecklist patternId={pattern.id} instructions={pattern.instructions} />
      </section>
    </div>
  );
}
