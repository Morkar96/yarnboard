/** Full pattern view: materials, abbreviations, attribution, and the
 * interactive per-user checklist (PatternChecklist). Fully public --
 * anonymous viewers can use the checklist too, just cached to their own
 * browser instead of synced to an account (see PatternChecklist).
 *
 * Displayed language follows the global UI language (the nav bar's
 * toggle, see NavBar.tsx) rather than a separate per-pattern control:
 * title/materials/abbreviations/instructions show whichever translation
 * (he/en) matches the current UI language, falling back to the pattern's
 * own primary content if that direction has no translation yet -- same
 * fallback PatternCard already uses in list views. This works
 * regardless of which language the primary content actually is in (a
 * pattern scraped from a Hebrew source page is just as valid as an
 * English one -- see backend/app/scraper.py's Hebrew keyword support):
 * an English-primary pattern viewed in Hebrew prefers its `he`
 * translation, a Hebrew-primary pattern viewed in English prefers its
 * `en` translation, and either one viewed in its own primary language
 * just shows that primary content untranslated (its own-language
 * translation column is never populated, so the fallback is what
 * always renders). */
import { useEffect, useState } from "react";
import { Alert, Button, Spinner } from "react-bootstrap";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";
import { fetchPattern, resolvePhotoUrl, translatePattern, translatePatternToEnglish } from "../api/client";
import AttributionTag from "../components/AttributionTag";
import CollapsibleCard from "../components/CollapsibleCard";
import PatternChartGrid from "../components/PatternChartGrid";
import PatternChecklist from "../components/PatternChecklist";
import PatternVisibilityPanel from "../components/PatternVisibilityPanel";
import { useAuth } from "../context/AuthContext";
import { useApiErrorMessage } from "../i18n/useApiErrorMessage";
import type { Pattern } from "../types/models";
import { translationForUiLanguage } from "../utils/patternTranslation";

/** Hebrew Unicode block -- used as a lightweight, purely-client-side
 * heuristic to guess whether a pattern's own primary content is Hebrew
 * or English (there's no stored "primary language" field on Pattern; a
 * scraped/uploaded pattern's language is whatever its source happened to
 * be in). Only decides which translate button(s) to offer -- getting
 * this wrong for an edge case (mixed-language title, etc.) just offers
 * the "wrong" button, it doesn't block anything the backend wouldn't
 * otherwise allow. */
function looksHebrew(text: string): boolean {
  return /[\u0590-\u05FF]/.test(text);
}

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
  const [translatingToEnglish, setTranslatingToEnglish] = useState(false);
  const [translateToEnglishError, setTranslateToEnglishError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    fetchPattern(Number(id))
      .then(setPattern)
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <Spinner animation="border" variant="primary" />;
  if (notFound || !pattern) return <p className="text-muted">{t("patternDetail.notFound")}</p>;

  // Whichever translation matches the current UI language, falling back
  // to the pattern's own primary content -- see the module docstring above.
  const activeTranslation = translationForUiLanguage(pattern, i18n.language);
  const title = activeTranslation?.title ?? pattern.title;
  const materials = activeTranslation?.materials ?? pattern.materials;
  const abbreviations = activeTranslation?.abbreviations ?? pattern.abbreviations;
  const he = pattern.translations.he;
  const en = pattern.translations.en;
  // Only offer translating *away* from whatever the pattern's own
  // primary content already looks like it's in -- translating Hebrew to
  // Hebrew (or English to English) isn't a real action.
  const primaryIsHebrew = looksHebrew(pattern.title);

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

  async function handleTranslateToEnglish() {
    if (!pattern) return;
    setTranslateToEnglishError(null);
    setTranslatingToEnglish(true);
    try {
      const result = await translatePatternToEnglish(pattern.id);
      setPattern(result.pattern);
    } catch (err) {
      setTranslateToEnglishError(getErrorMessage(err, t("patternDetail.translateToEnglishFailed")));
    } finally {
      setTranslatingToEnglish(false);
    }
  }

  return (
    <div>
      <div className="d-flex justify-content-between align-items-start">
        <h1 className="mb-2">{title}</h1>
        {pattern.can_edit && (
          <Link to={`/pattern/${pattern.id}/edit`} className="btn btn-outline-primary btn-sm">
            {t("patternDetail.edit")}
          </Link>
        )}
      </div>
      <AttributionTag pattern={pattern} />

      {pattern.can_manage && <PatternVisibilityPanel pattern={pattern} onPatternChange={setPattern} />}

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

      {user && !primaryIsHebrew && !he && (
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
      {user && primaryIsHebrew && !en && (
        <div className="mb-3">
          <Button variant="outline-secondary" size="sm" disabled={translatingToEnglish} onClick={handleTranslateToEnglish}>
            {translatingToEnglish ? t("patternDetail.translating") : t("patternDetail.translateToEnglishButton")}
          </Button>
          {translateToEnglishError && (
            <Alert variant="danger" className="mt-2 mb-0">
              {translateToEnglishError}
            </Alert>
          )}
        </div>
      )}
      {activeTranslation && !activeTranslation.reviewed && (
        <Alert variant="warning" className="py-2">
          {t("patternDetail.unreviewedNotice")}
        </Alert>
      )}

      {materials && (
        <CollapsibleCard title={t("patternDetail.materials")}>
          <pre className="mb-0" dir="auto" style={{ whiteSpace: "pre-wrap" }}>
            {materials}
          </pre>
        </CollapsibleCard>
      )}

      {abbreviations && (
        <CollapsibleCard title={t("patternDetail.abbreviations")}>
          <pre className="mb-0" dir="auto" style={{ whiteSpace: "pre-wrap" }}>
            {abbreviations}
          </pre>
        </CollapsibleCard>
      )}

      <h2 className="h4 mt-4 mb-3">{t("patternDetail.instructions")}</h2>
      <PatternChecklist
        patternId={pattern.id}
        instructions={pattern.instructions}
        instructionsHe={pattern.translations.he?.instructions}
        instructionsEn={pattern.translations.en?.instructions}
      />
    </div>
  );
}
