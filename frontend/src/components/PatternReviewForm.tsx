/**
 * Editable form for a scraped draft (title/author/materials/abbreviations/
 * instructions) before publishing. The scraper is only best-effort (see
 * backend/app/scraper.py), so every field here is editable rather than
 * read-only -- this is the human review step that makes the heuristic
 * extraction trustworthy enough to publish.
 */
import { Button, Card, Form, InputGroup } from "react-bootstrap";
import { useTranslation } from "react-i18next";
import { resolvePhotoUrl } from "../api/client";
import type { PatternDraft } from "../types/models";

interface Props {
  draft: PatternDraft;
  onChange: (draft: PatternDraft) => void;
}

export default function PatternReviewForm({ draft, onChange }: Props) {
  const { t } = useTranslation();

  function updateField<K extends keyof PatternDraft>(field: K, value: PatternDraft[K]) {
    onChange({ ...draft, [field]: value });
  }

  function updatePartName(oldName: string, newName: string) {
    if (!newName || newName === oldName) return;
    const entries = Object.entries(draft.instructions).map(([name, steps]) =>
      name === oldName ? [newName, steps] : [name, steps],
    ) as [string, string[]][];
    updateField("instructions", Object.fromEntries(entries));
  }

  function updateStep(part: string, index: number, text: string) {
    const steps = [...draft.instructions[part]];
    steps[index] = text;
    updateField("instructions", { ...draft.instructions, [part]: steps });
  }

  function addStep(part: string) {
    updateField("instructions", {
      ...draft.instructions,
      [part]: [...draft.instructions[part], ""],
    });
  }

  /** Removes one step from a part. The scraper is only best-effort (see
   * backend/app/scraper.py) and sometimes splits things in ways that
   * don't belong -- e.g. a bolded materials-list item getting misread as
   * its own instruction part -- so reviewers need to be able to drop
   * individual steps, not just edit their text. */
  function deleteStep(part: string, index: number) {
    const steps = draft.instructions[part].filter((_, i) => i !== index);
    updateField("instructions", { ...draft.instructions, [part]: steps });
  }

  /** Removes an entire part (e.g. a stray "Pin for Later" divider section
   * the scraper misread as an instruction part). */
  function deletePart(part: string) {
    const { [part]: _removed, ...rest } = draft.instructions;
    updateField("instructions", rest);
  }

  function addPart() {
    const name = `Part ${Object.keys(draft.instructions).length + 1}`;
    updateField("instructions", { ...draft.instructions, [name]: [""] });
  }

  /** Swaps a part with its neighbor in the opposite direction. Object key
   * order (JS preserves string-key insertion order) is what determines the
   * part order everywhere else this draft is rendered -- the checklist,
   * the published pattern -- so reordering means rebuilding the object
   * with keys in the new order, not just relabeling anything. */
  function movePart(part: string, direction: -1 | 1) {
    const entries = Object.entries(draft.instructions);
    const index = entries.findIndex(([name]) => name === part);
    const swapWith = index + direction;
    if (swapWith < 0 || swapWith >= entries.length) return;
    [entries[index], entries[swapWith]] = [entries[swapWith], entries[index]];
    updateField("instructions", Object.fromEntries(entries));
  }

  return (
    <div className="d-flex flex-column gap-3">
      <Form.Group controlId="review-title">
        <Form.Label>{t("reviewForm.titleLabel")}</Form.Label>
        <Form.Control value={draft.title} onChange={(e) => updateField("title", e.target.value)} />
      </Form.Group>

      {draft.photo_url && (
        <Form.Group controlId="review-photo">
          <Form.Label>{t("reviewForm.photoLabel")}</Form.Label>
          <div>
            <img
              src={resolvePhotoUrl(draft.photo_url)}
              alt={draft.title}
              style={{ maxWidth: "240px", maxHeight: "240px", objectFit: "cover" }}
              onError={(e) => {
                e.currentTarget.style.display = "none";
              }}
            />
          </div>
          <Button
            variant="outline-secondary"
            size="sm"
            className="mt-2"
            onClick={() => updateField("photo_url", null)}
          >
            {t("reviewForm.removePhoto")}
          </Button>
          <Form.Text className="d-block text-muted">{t("reviewForm.photoHint")}</Form.Text>
        </Form.Group>
      )}

      <Form.Group controlId="review-author">
        <Form.Label>{t("reviewForm.authorLabel")}</Form.Label>
        <Form.Control
          value={draft.author ?? ""}
          placeholder={t("reviewForm.authorPlaceholder")}
          onChange={(e) => updateField("author", e.target.value || null)}
        />
      </Form.Group>

      <Form.Group controlId="review-materials">
        <Form.Label>{t("reviewForm.materialsLabel")}</Form.Label>
        <Form.Control
          as="textarea"
          rows={3}
          value={draft.materials}
          onChange={(e) => updateField("materials", e.target.value)}
        />
      </Form.Group>

      <Form.Group controlId="review-abbreviations">
        <Form.Label>{t("reviewForm.abbreviationsLabel")}</Form.Label>
        <Form.Control
          as="textarea"
          rows={3}
          value={draft.abbreviations}
          onChange={(e) => updateField("abbreviations", e.target.value)}
        />
      </Form.Group>

      <h5 className="mt-2">{t("reviewForm.instructionsHeading")}</h5>
      {Object.entries(draft.instructions).map(([part, steps], partIndex, allParts) => (
        <Card key={part} className="shadow-sm">
          <Card.Body className="d-flex flex-column gap-2">
            <InputGroup>
              <Button
                variant="outline-secondary"
                onClick={() => movePart(part, -1)}
                disabled={partIndex === 0}
                title={t("reviewForm.movePartUp")}
                aria-label={t("reviewForm.movePartUpAria", { part })}
              >
                &uarr;
              </Button>
              <Button
                variant="outline-secondary"
                onClick={() => movePart(part, 1)}
                disabled={partIndex === allParts.length - 1}
                title={t("reviewForm.movePartDown")}
                aria-label={t("reviewForm.movePartDownAria", { part })}
              >
                &darr;
              </Button>
              <Form.Control
                className="fw-semibold"
                value={part}
                onChange={(e) => updatePartName(part, e.target.value)}
              />
              <Button
                variant="outline-danger"
                onClick={() => deletePart(part)}
                title={t("reviewForm.deletePart")}
                aria-label={t("reviewForm.deletePartAria", { part })}
              >
                {t("reviewForm.deletePart")}
              </Button>
            </InputGroup>
            {steps.map((step, index) => (
              <InputGroup key={index}>
                <Form.Control value={step} onChange={(e) => updateStep(part, index, e.target.value)} />
                <Button
                  variant="outline-secondary"
                  onClick={() => deleteStep(part, index)}
                  title={t("reviewForm.deleteStepAria", { number: index + 1, part })}
                  aria-label={t("reviewForm.deleteStepAria", { number: index + 1, part })}
                >
                  &times;
                </Button>
              </InputGroup>
            ))}
            <Button variant="outline-primary" size="sm" className="align-self-start" onClick={() => addStep(part)}>
              {t("reviewForm.addStep")}
            </Button>
          </Card.Body>
        </Card>
      ))}
      <Button variant="outline-primary" className="align-self-start" onClick={addPart}>
        {t("reviewForm.addPart")}
      </Button>
    </div>
  );
}
