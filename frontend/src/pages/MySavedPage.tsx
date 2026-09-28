/** Community patterns this account has bookmarked -- may or may not have
 * been uploaded by this same account (see MyUploadsPage for that list). */
import { useEffect, useState } from "react";
import { Col, Row, Spinner } from "react-bootstrap";
import { Link } from "react-router-dom";
import { fetchMySaved, unsavePattern } from "../api/client";
import PatternCard from "../components/PatternCard";
import type { Pattern } from "../types/models";

export default function MySavedPage() {
  const [patterns, setPatterns] = useState<Pattern[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchMySaved()
      .then(setPatterns)
      .finally(() => setLoading(false));
  }, []);

  async function handleUnsave(pattern: Pattern) {
    await unsavePattern(pattern.id);
    setPatterns((prev) => prev.filter((p) => p.id !== pattern.id));
  }

  if (loading) return <Spinner animation="border" variant="primary" />;

  return (
    <div>
      <h1 className="mb-4">My Saved Patterns</h1>
      {patterns.length === 0 && (
        <p className="text-muted">
          You haven't saved any patterns yet. Browse the <Link to="/community">Community</Link>{" "}
          page to find some.
        </p>
      )}
      <Row xs={1} sm={2} lg={3} className="g-3">
        {patterns.map((pattern) => (
          <Col key={pattern.id}>
            <PatternCard pattern={pattern} onToggleSave={handleUnsave} isSaved />
          </Col>
        ))}
      </Row>
    </div>
  );
}
