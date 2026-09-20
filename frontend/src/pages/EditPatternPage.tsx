/** Edit an already-published pattern. Reuses PatternReviewForm (the same
 * component used pre-publish in the submit flow) -- no PublishConsentNotice
 * here, since this isn't a first-time publish.
 *
 * The client-side gate on who can edit (admin or the original uploader)
 * is UX only -- the backend is the real authority (PATCH /api/patterns/<id>
 * 403s otherwise), so a direct navigation to this URL for a pattern you
 * can't edit still safely fails, just with a plain error message instead
 * of hiding the page entirely.
 *
 * The translation sections below (Hebrew, and its exact mirror English --
 * see Pattern.instructions_en's docstring in backend/app/models.py for
 * why a Hebrew-*primary* pattern needs an English overlay the same way
 * an English-primary one needs a Hebrew overlay) are deliberately NOT
 * built on PatternReviewForm -- that component lets the pattern's own
 * primary-content instructions be restructured freely (add/remove/
 * reorder parts and steps), but a translation is required to mirror that
 * structure exactly (same part-name keys, same per-part step counts), so
 * each translation editor only ever edits *text* against a structure
 * fixed by the primary-content side, never the structure itself. */
import { useEffect, useState, type FormEvent } from "react";
import { Alert, Button, Card, Form, Spinner } from "react-bootstrap";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import {
  deletePatternPhoto,
  fetchPattern,
  resolvePhotoUrl,
  updatePattern,
  uploadPatternPhoto,
} from "../api/client";
import PatternReviewForm from "../components/PatternReviewForm";
import { useApiErrorMessage } from "../i18n/useApiErrorMessage";
import type {
  EnglishInstructionEntry,
  HebrewInstructionEntry,
  Pattern,
  PatternDraft,
  PatternEditPayload,
} from "../types/models";
import { useUnsavedChangesWarning } from "../utils/useUnsavedChangesWarning";

/** Pattern.instructions is {part: [{step, completed}]} (viewer-specific
 * progress merged in); PatternReviewForm expects the plain-string draft
 * shape {part: [step]} it already uses pre-publish -- strip `completed`. */
function patternToDraft(pattern: Pattern): PatternDraft {
  const instructions: Record<string, string[]> = {};
  for (const [part, steps] of Object.entries(pattern.instructions)) {
    instructions[part] = steps.map((s) => s.step);
  }
  return {
    title: pattern.title,
    author: pattern.author,
    materials: pattern.materials ?? "",
    abbreviations: pattern.abbreviations ?? "",
    instructions,
    source_site_name: pattern.source_site_name ?? "",
    source_domain: pattern.source_domain ?? "",
    photo_url: pattern.photo_url,
  };
}

interface HeDraft {
  title_he: string;
  materials_he: string;
  abbreviations_he: string;
  instructions_he: Record<string, HebrewInstructionEntry>;
}

function patternToHeDraft(pattern: Pattern): HeDraft | null {
  const he = pattern.translations.he;
  if (!he) return null;
  return {
    title_he: he.title,
    materials_he: he.materials ?? "",
    abbreviations_he: he.abbreviations ?? "",
    instructions_he: he.instructions,
  };
}

interface EnDraft {
  title_en: string;
  materials_en: string;
  abbreviations_en: string;
  instructions_en: Record<string, EnglishInstructionEntry>;
}

function patternToEnDraft(pattern: Pattern): EnDraft | null {
  const en = pattern.translations.en;
  if (!en) return null;
  return {
    title_en: en.title,
    materials_en: en.materials ?? "",
    abbreviations_en: en.abbreviations ?? "",
    instructions_en: en.instructions,
  };
}

export default function EditPatternPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const getErrorMessage = useApiErrorMessage();

  const [pattern, setPattern] = useState<Pattern | null>(null);
  const [draft, setDraft] = useState<PatternDraft | null>(null);
  const [heDraft, setHeDraft] = useState<HeDraft | null>(null);
  const [enDraft, setEnDraft] = useState<EnDraft | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [photoFile, setPhotoFile] = useState<File | null>(null);
  const [photoError, setPhotoError] = useState<string | null>(null);
  const [photoBusy, setPhotoBusy] = useState(false);
  // Snapshot of {draft, heDraft} as first loaded, to diff the live state
  // against for the unsaved-changes warning below -- not photo uploads/
  // removals, which save immediately on their own rather than going
  // through handleSave, so they're never "unsaved" in that sense.
  const [initialSnapshot, setInitialSnapshot] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    fetchPattern(Number(id))
      .then((p) => {
        setPattern(p);
        const draft = patternToDraft(p);
        const heDraft = patternToHeDraft(p);
        const enDraft = patternToEnDraft(p);
        setDraft(draft);
        setHeDraft(heDraft);
        setEnDraft(enDraft);
        setInitialSnapshot(JSON.stringify({ draft, heDraft, enDraft }));
      })
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false));
  }, [id]);

  useUnsavedChangesWarning(
    initialSnapshot !== null && JSON.stringify({ draft, heDraft, enDraft }) !== initialSnapshot,
  );

  if (loading) return <Spinner animation="border" variant="primary" />;
  if (notFound || !pattern || !draft) return <p className="text-muted">{t("editPattern.notFound")}</p>;

  if (!pattern.can_edit) {
    return <Alert variant="danger">{t("editPattern.permissionDenied")}</Alert>;
  }

  function updateHeHeading(part: string, heading_he: string) {
    setHeDraft((d) =>
      d ? { ...d, instructions_he: { ...d.instructions_he, [part]: { ...d.instructions_he[part], heading_he } } } : d,
    );
  }

  function updateHeStep(part: string, index: number, text: string) {
    setHeDraft((d) => {
      if (!d) return d;
      const steps_he = [...(d.instructions_he[part]?.steps_he ?? [])];
      steps_he[index] = text;
      return { ...d, instructions_he: { ...d.instructions_he, [part]: { ...d.instructions_he[part], steps_he } } };
    });
  }

  function updateEnHeading(part: string, heading_en: string) {
    setEnDraft((d) =>
      d ? { ...d, instructions_en: { ...d.instructions_en, [part]: { ...d.instructions_en[part], heading_en } } } : d,
    );
  }

  function updateEnStep(part: string, index: number, text: string) {
    setEnDraft((d) => {
      if (!d) return d;
      const steps_en = [...(d.instructions_en[part]?.steps_en ?? [])];
      steps_en[index] = text;
      return { ...d, instructions_en: { ...d.instructions_en, [part]: { ...d.instructions_en[part], steps_en } } };
    });
  }

  /** Uploading/removing a photo happens against the already-persisted
   * Pattern id (unlike the pre-publish review form, which has none yet --
   * see PatternReviewForm's preview-and-clear-only affordance for that
   * case). Both branches sync `pattern` AND `draft.photo_url` from the
   * response so PatternReviewForm's own preview doesn't show stale state. */
  async function handlePhotoUpload(e: FormEvent) {
    e.preventDefault();
    if (!photoFile || !pattern) return;
    setPhotoError(null);
    setPhotoBusy(true);
    try {
      const result = await uploadPatternPhoto(pattern.id, photoFile);
      setPattern(result.pattern);
      setDraft((d) => (d ? { ...d, photo_url: result.pattern.photo_url } : d));
      setPhotoFile(null);
    } catch (err) {
      setPhotoError(getErrorMessage(err, t("editPattern.photoUploadFailed")));
    } finally {
      setPhotoBusy(false);
    }
  }

  async function handlePhotoRemove() {
    if (!pattern) return;
    setPhotoError(null);
    setPhotoBusy(true);
    try {
      const result = await deletePatternPhoto(pattern.id);
      setPattern(result.pattern);
      setDraft((d) => (d ? { ...d, photo_url: result.pattern.photo_url } : d));
    } catch (err) {
      setPhotoError(getErrorMessage(err, t("editPattern.photoRemoveFailed")));
    } finally {
      setPhotoBusy(false);
    }
  }

  async function handleSave() {
    if (!draft || !pattern) return;
    setError(null);
    setSaving(true);
    try {
      // heDraft/enDraft fields are only attached when that translation
      // already exists to edit -- see patternToHeDraft/patternToEnDraft.
      // If the primary-content instructions above were also restructured
      // in this same save (parts/steps added, removed, or reordered),
      // the backend rejects the whole request rather than accepting a
      // translation that no longer structurally matches (see
      // _validate_translated_instructions in
      // backend/app/patterns/routes.py) -- a real but rare edge case,
      // surfaced via the normal error Alert below rather than specially
      // handled here.
      const payload: PatternEditPayload = {
        ...draft,
        ...(heDraft
          ? {
              title_he: heDraft.title_he,
              materials_he: heDraft.materials_he,
              abbreviations_he: heDraft.abbreviations_he,
              instructions_he: heDraft.instructions_he,
            }
          : {}),
        ...(enDraft
          ? {
              title_en: enDraft.title_en,
              materials_en: enDraft.materials_en,
              abbreviations_en: enDraft.abbreviations_en,
              instructions_en: enDraft.instructions_en,
            }
          : {}),
      };
      await updatePattern(pattern.id, payload);
      navigate(`/pattern/${pattern.id}`);
    } catch (err) {
      setError(getErrorMessage(err, t("editPattern.saveFailed")));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <h1 className="mb-3">{t("editPattern.title")}</h1>

      <Form onSubmit={handlePhotoUpload} className="mb-4" style={{ maxWidth: "32rem" }}>
        <Form.Group controlId="edit-photo">
          <Form.Label>{t("editPattern.photoLabel")}</Form.Label>
          {pattern.has_photo && (
            <div className="mb-2">
              <img
                src={resolvePhotoUrl(pattern.photo_url)}
                alt={pattern.title}
                style={{ maxWidth: "240px", maxHeight: "240px", objectFit: "cover" }}
                onError={(e) => {
                  e.currentTarget.style.display = "none";
                }}
              />
            </div>
          )}
          <Form.Control
            type="file"
            accept="image/*"
            onChange={(e) => setPhotoFile((e.target as HTMLInputElement).files?.[0] ?? null)}
          />
        </Form.Group>
        {photoError && (
          <Alert variant="danger" className="mt-2">
            {photoError}
          </Alert>
        )}
        <div className="d-flex gap-2 mt-2">
          <Button type="submit" variant="outline-primary" size="sm" disabled={photoBusy || !photoFile}>
            {photoBusy
              ? t("editPattern.uploading")
              : pattern.has_photo
                ? t("editPattern.replacePhoto")
                : t("editPattern.uploadPhoto")}
          </Button>
          {pattern.has_photo && (
            <Button
              type="button"
              variant="outline-danger"
              size="sm"
              disabled={photoBusy}
              onClick={handlePhotoRemove}
            >
              {t("editPattern.removePhoto")}
            </Button>
          )}
        </div>
      </Form>

      <PatternReviewForm draft={draft} onChange={setDraft} />

      <div className="mt-4 pt-4 border-top">
        <h2 className="h4 mb-3">{t("editPattern.translationHeadingHe")}</h2>
        {heDraft ? (
          <div className="d-flex flex-column gap-3">
            <Form.Group controlId="edit-translation-title">
              <Form.Label>{t("editPattern.translationTitleLabel")}</Form.Label>
              <Form.Control
                dir="rtl"
                value={heDraft.title_he}
                onChange={(e) => setHeDraft((d) => (d ? { ...d, title_he: e.target.value } : d))}
              />
            </Form.Group>
            <Form.Group controlId="edit-translation-materials">
              <Form.Label>{t("editPattern.translationMaterialsLabel")}</Form.Label>
              <Form.Control
                as="textarea"
                rows={3}
                dir="rtl"
                value={heDraft.materials_he}
                onChange={(e) => setHeDraft((d) => (d ? { ...d, materials_he: e.target.value } : d))}
              />
            </Form.Group>
            <Form.Group controlId="edit-translation-abbreviations">
              <Form.Label>{t("editPattern.translationAbbreviationsLabel")}</Form.Label>
              <Form.Control
                as="textarea"
                rows={3}
                dir="rtl"
                value={heDraft.abbreviations_he}
                onChange={(e) => setHeDraft((d) => (d ? { ...d, abbreviations_he: e.target.value } : d))}
              />
            </Form.Group>

            <h3 className="h6">{t("editPattern.translationInstructionsHeading")}</h3>
            {Object.entries(pattern.instructions).map(([part, steps]) => (
              <Card key={part} className="shadow-sm">
                <Card.Body className="d-flex flex-column gap-2">
                  <div className="d-flex justify-content-between align-items-center gap-2">
                    <span className="text-muted small flex-shrink-0" dir="auto">{part}</span>
                    <Form.Control
                      className="fw-semibold"
                      dir="rtl"
                      value={heDraft.instructions_he[part]?.heading_he ?? ""}
                      onChange={(e) => updateHeHeading(part, e.target.value)}
                    />
                  </div>
                  {steps.map((step, index) => (
                    <div key={index} className="d-flex gap-2 align-items-start">
                      <span className="text-muted small" dir="auto" style={{ flex: 1 }}>
                        {step.step}
                      </span>
                      <Form.Control
                        dir="rtl"
                        style={{ flex: 1 }}
                        value={heDraft.instructions_he[part]?.steps_he?.[index] ?? ""}
                        onChange={(e) => updateHeStep(part, index, e.target.value)}
                      />
                    </div>
                  ))}
                </Card.Body>
              </Card>
            ))}
            <Form.Text className="text-muted">{t("editPattern.translationReviewedNotice")}</Form.Text>
          </div>
        ) : (
          <p className="text-muted">{t("editPattern.translationNotYetAvailable")}</p>
        )}
      </div>

      <div className="mt-4 pt-4 border-top">
        <h2 className="h4 mb-3">{t("editPattern.translationHeadingEn")}</h2>
        {enDraft ? (
          <div className="d-flex flex-column gap-3">
            <Form.Group controlId="edit-translation-title-en">
              <Form.Label>{t("editPattern.translationTitleLabel")}</Form.Label>
              <Form.Control
                dir="auto"
                value={enDraft.title_en}
                onChange={(e) => setEnDraft((d) => (d ? { ...d, title_en: e.target.value } : d))}
              />
            </Form.Group>
            <Form.Group controlId="edit-translation-materials-en">
              <Form.Label>{t("editPattern.translationMaterialsLabel")}</Form.Label>
              <Form.Control
                as="textarea"
                rows={3}
                dir="auto"
                value={enDraft.materials_en}
                onChange={(e) => setEnDraft((d) => (d ? { ...d, materials_en: e.target.value } : d))}
              />
            </Form.Group>
            <Form.Group controlId="edit-translation-abbreviations-en">
              <Form.Label>{t("editPattern.translationAbbreviationsLabel")}</Form.Label>
              <Form.Control
                as="textarea"
                rows={3}
                dir="auto"
                value={enDraft.abbreviations_en}
                onChange={(e) => setEnDraft((d) => (d ? { ...d, abbreviations_en: e.target.value } : d))}
              />
            </Form.Group>

            <h3 className="h6">{t("editPattern.translationInstructionsHeading")}</h3>
            {Object.entries(pattern.instructions).map(([part, steps]) => (
              <Card key={part} className="shadow-sm">
                <Card.Body className="d-flex flex-column gap-2">
                  <div className="d-flex justify-content-between align-items-center gap-2">
                    <span className="text-muted small flex-shrink-0" dir="auto">{part}</span>
                    <Form.Control
                      className="fw-semibold"
                      dir="auto"
                      value={enDraft.instructions_en[part]?.heading_en ?? ""}
                      onChange={(e) => updateEnHeading(part, e.target.value)}
                    />
                  </div>
                  {steps.map((step, index) => (
                    <div key={index} className="d-flex gap-2 align-items-start">
                      <span className="text-muted small" dir="auto" style={{ flex: 1 }}>
                        {step.step}
                      </span>
                      <Form.Control
                        dir="auto"
                        style={{ flex: 1 }}
                        value={enDraft.instructions_en[part]?.steps_en?.[index] ?? ""}
                        onChange={(e) => updateEnStep(part, index, e.target.value)}
                      />
                    </div>
                  ))}
                </Card.Body>
              </Card>
            ))}
            <Form.Text className="text-muted">{t("editPattern.translationReviewedNotice")}</Form.Text>
          </div>
        ) : (
          <p className="text-muted">{t("editPattern.translationNotYetAvailable")}</p>
        )}
      </div>

      {error && (
        <Alert variant="danger" className="mt-3">
          {error}
        </Alert>
      )}
      <Button variant="primary" className="mt-3" disabled={saving} onClick={handleSave}>
        {saving ? t("editPattern.saving") : t("editPattern.saveButton")}
      </Button>
    </div>
  );
}
