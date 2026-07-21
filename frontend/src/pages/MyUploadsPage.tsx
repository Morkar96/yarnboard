/** Patterns this account personally submitted -- distinct from patterns
 * merely bookmarked from the community (see MySavedPage). */
import { useEffect, useState } from "react";
import { Col, Row, Spinner } from "react-bootstrap";
import { Link } from "react-router-dom";
import { fetchMyUploads } from "../api/client";
import PatternCard from "../components/PatternCard";
import type { Pattern } from "../types/models";

export default function MyUploadsPage() {
  const [patterns, setPatterns] = useState<Pattern[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchMyUploads()
      .then(setPatterns)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Spinner animation="border" variant="primary" />;

  return (
    <div>
      <h1 className="mb-4">My Uploads</h1>
      {patterns.length === 0 && (
        <p className="text-muted">
          You haven't submitted any patterns yet. <Link to="/submit">Submit one</Link>.
        </p>
      )}
      <Row xs={1} sm={2} lg={3} className="g-3">
        {patterns.map((pattern) => (
          <Col key={pattern.id}>
            <PatternCard pattern={pattern} />
          </Col>
        ))}
      </Row>
    </div>
  );
}
