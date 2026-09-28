/** All published patterns, from every user. Requires login -- gated behind
 * ProtectedRoute in App.tsx and behind login server-side (see GET
 * /api/patterns/community), so unregistered visitors can't browse the
 * community library at all. */
import { useEffect, useState } from "react";
import { Col, Row, Spinner } from "react-bootstrap";
import { fetchCommunityPatterns, fetchMySaved, savePattern, unsavePattern } from "../api/client";
import PatternCard from "../components/PatternCard";
import type { Pattern } from "../types/models";

export default function CommunityPage() {
  const [patterns, setPatterns] = useState<Pattern[]>([]);
  const [savedIds, setSavedIds] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchCommunityPatterns()
      .then(setPatterns)
      .finally(() => setLoading(false));
    fetchMySaved().then((saved) => setSavedIds(new Set(saved.map((p) => p.id))));
  }, []);

  async function handleToggleSave(pattern: Pattern) {
    if (savedIds.has(pattern.id)) {
      await unsavePattern(pattern.id);
      setSavedIds((prev) => {
        const next = new Set(prev);
        next.delete(pattern.id);
        return next;
      });
    } else {
      await savePattern(pattern.id);
      setSavedIds((prev) => new Set(prev).add(pattern.id));
    }
  }

  if (loading) return <Spinner animation="border" variant="primary" />;

  return (
    <div>
      <h1 className="mb-4">Community Patterns</h1>
      {patterns.length === 0 && <p className="text-muted">No patterns have been published yet.</p>}
      <Row xs={1} sm={2} lg={3} className="g-3">
        {patterns.map((pattern) => (
          <Col key={pattern.id}>
            <PatternCard
              pattern={pattern}
              onToggleSave={handleToggleSave}
              isSaved={savedIds.has(pattern.id)}
            />
          </Col>
        ))}
      </Row>
    </div>
  );
}
