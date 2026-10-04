/** Patterns someone else explicitly granted this account view access to
 * (see PatternVisibilityPanel's share form) -- distinct from MySavedPage
 * (your own bookmarks, always something you could already see) and
 * MyUploadsPage (your own uploads). No save/unsave action here -- these
 * aren't yours to bookmark, just to view. */
import { useEffect, useState } from "react";
import { Col, Row, Spinner } from "react-bootstrap";
import { useTranslation } from "react-i18next";
import { fetchSharedWithMe } from "../api/client";
import PatternCard from "../components/PatternCard";
import type { Pattern } from "../types/models";

export default function SharedWithMePage() {
  const { t } = useTranslation();
  const [patterns, setPatterns] = useState<Pattern[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchSharedWithMe()
      .then(setPatterns)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Spinner animation="border" variant="primary" />;

  return (
    <div>
      <h1 className="mb-4">{t("sharedWithMe.title")}</h1>
      {patterns.length === 0 && <p className="text-muted">{t("sharedWithMe.empty")}</p>}
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
