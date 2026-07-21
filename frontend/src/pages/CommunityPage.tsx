/** All published patterns, from every user. Public -- no login required to
 * browse, matching the backend's GET /api/patterns/community. */
import { useEffect, useState } from "react";
import { Col, Row, Spinner } from "react-bootstrap";
import { fetchCommunityPatterns, fetchMySaved, savePattern, unsavePattern } from "../api/client";
import PatternCard from "../components/PatternCard";
import { useAuth } from "../context/AuthContext";
import type { Pattern } from "../types/models";

export default function CommunityPage() {
  const { user } = useAuth();
  const [patterns, setPatterns] = useState<Pattern[]>([]);
  const [savedIds, setSavedIds] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchCommunityPatterns()
      .then(setPatterns)
      .finally(() => setLoading(false));
    if (user) {
      fetchMySaved().then((saved) => setSavedIds(new Set(saved.map((p) => p.id))));
    }
  }, [user]);

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
              onToggleSave={user ? handleToggleSave : undefined}
              isSaved={savedIds.has(pattern.id)}
            />
          </Col>
        ))}
      </Row>
    </div>
  );
}
