/** All published patterns, from every user. Public -- anyone can browse
 * the community library (see GET /api/patterns/community), but saving a
 * pattern to your own list is still login-only, so the Save button and
 * the saved-lookup fetch are both skipped entirely for anonymous
 * visitors rather than shown disabled. */
import { useEffect, useState } from "react";
import { Alert, Col, Row, Spinner } from "react-bootstrap";
import { Link } from "react-router-dom";
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
      {!user && (
        <Alert variant="light">
          Browsing as a guest -- you can view every pattern and check off steps as you go. Want to
          save patterns or upload your own? <Link to="/submit">See how uploading works</Link>, or{" "}
          <Link to="/register">sign up</Link>.
        </Alert>
      )}
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
