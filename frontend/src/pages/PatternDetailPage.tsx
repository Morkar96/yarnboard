/** Full pattern view: materials, abbreviations, attribution, and the
 * interactive per-user checklist (PatternChecklist). Public to view; the
 * checklist itself only accepts input from logged-in users.
 *
 * Displayed language follows the global UI language (the nav bar's
 * toggle, see NavBar.tsx) rather than a separate per-pattern control --
 * title/materials/abbreviations/instructions all fall back to English
 * whenever no Hebrew translation exists yet, same fallback PatternCard
 * already uses in list views. */
import { useEffect, useState } from "react";
import { Alert, Button, Spinner } from "react-bootstrap";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";
import { fetchPattern, resolvePhotoUrl, translatePattern } from "../api/client";
import AttributionTag from "../components/AttributionTag";
import CollapsibleCard from "../components/CollapsibleCard";
import PatternChartGrid from "../components/PatternChartGrid";
import PatternChecklist from "../components/PatternChecklist";
import { useAuth } from "../context/AuthContext";
import { useApiErrorMessage } from "../i18n/useApiErrorMessage";
import type { Pattern } from "../types/models";

export default function PatternDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const { t, i18n } = useTranslation();
  const getErrorMessage = useApiErrorMessage();
  const [pattern, setPattern] = useState<Pattern | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [translating, setTranslating] = useState(false);
  const [translateError, setTranslateError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    fetchPattern(Number(id))
      .then(setPattern)
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <Spinner animation="border" variant="primary" />;
  if (notFound || !pattern) return <p className="text-muted">{t("patternDetail.notFound")}</p>;

  const canEdit = !!user && (user.is_admin || user.id === pattern.uploader_id);
  const he = i18n.language === "he" ? pattern.translations.he : null;
  const title = he?.title ?? pattern.title;
  const materials = he?.materials ?? pattern.materials;
  const abbreviations = he?.abbreviations ?? pattern.abbreviations;

  async function handleTranslate() {
    if (!pattern) return;
    setTranslateError(null);
    setTranslating(true);
    try {
      const result = await translatePattern(pattern.id);
      setPattern(result.pattern);
    } catch (err) {
      setTranslateError(getErrorMessage(err, t("patternDetail.translateFailed")));
    } finally {
      setTranslating(false);
    }
  }

  return (
    <div>
      <div className="d-flex justify-content-between align-items-start">
        <h1 className="mb-2">{title}</h1>
        {canEdit && (
          <Link to={`/pattern/${pattern.id}/edit`} className="btn btn-outline-primary btn-sm">
            {t("patternDetail.edit")}
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
            alt={title}
            className="mb-3"
            style={{ maxWidth: "100%", maxHeight: "400px", objectFit: "cover" }}
            onError={(e) => {
              e.currentTarget.style.display = "none";
            }}
          />
        )
      )}

      {user && !pattern.translations.he && (
        <div className="mb-3">
          <Button variant="outline-secondary" size="sm" disabled={translating} onClick={handleTranslate}>
            {translating ? t("patternDetail.translating") : t("patternDetail.translateButton")}
          </Button>
          {translateError && (
            <Alert variant="danger" className="mt-2 mb-0">
              {translateError}
            </Alert>
          )}
        </div>
      )}
      {he && !he.reviewed && (
        <Alert variant="warning" className="py-2">
          {t("patternDetail.unreviewedNotice")}
        </Alert>
      )}

      {materials && (
        <CollapsibleCard title={t("patternDetail.materials")}>
          <pre className="mb-0" style={{ whiteSpace: "pre-wrap" }}>
            {materials}
          </pre>
        </CollapsibleCard>
      )}

      {abbreviations && (
        <CollapsibleCard title={t("patternDetail.abbreviations")}>
          <pre className="mb-0" style={{ whiteSpace: "pre-wrap" }}>
            {abbreviations}
          </pre>
        </CollapsibleCard>
      )}

      <h2 className="h4 mt-4 mb-3">{t("patternDetail.instructions")}</h2>
      <PatternChecklist
        patternId={pattern.id}
        instructions={pattern.instructions}
        instructionsHe={pattern.translations.he?.instructions}
      />
    </div>
  );
}
