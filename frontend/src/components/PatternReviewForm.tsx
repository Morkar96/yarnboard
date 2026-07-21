/**
 * Editable form for a scraped draft (title/author/materials/abbreviations/
 * instructions) before publishing. The scraper is only best-effort (see
 * backend/app/scraper.py), so every field here is editable rather than
 * read-only -- this is the human review step that makes the heuristic
 * extraction trustworthy enough to publish.
 */
import { Button, Card, Form, InputGroup } from "react-bootstrap";
import type { PatternDraft } from "../types/models";

interface Props {
  draft: PatternDraft;
  onChange: (draft: PatternDraft) => void;
}

export default function PatternReviewForm({ draft, onChange }: Props) {
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
        <Form.Label>Title</Form.Label>
        <Form.Control value={draft.title} onChange={(e) => updateField("title", e.target.value)} />
      </Form.Group>

      <Form.Group controlId="review-author">
        <Form.Label>Original author</Form.Label>
        <Form.Control
          value={draft.author ?? ""}
          placeholder="Unknown"
          onChange={(e) => updateField("author", e.target.value || null)}
        />
      </Form.Group>

      <Form.Group controlId="review-materials">
        <Form.Label>Materials</Form.Label>
        <Form.Control
          as="textarea"
          rows={3}
          value={draft.materials}
          onChange={(e) => updateField("materials", e.target.value)}
        />
      </Form.Group>

      <Form.Group controlId="review-abbreviations">
        <Form.Label>Abbreviations</Form.Label>
        <Form.Control
          as="textarea"
          rows={3}
          value={draft.abbreviations}
          onChange={(e) => updateField("abbreviations", e.target.value)}
        />
      </Form.Group>

      <h5 className="mt-2">Instructions</h5>
      {Object.entries(draft.instructions).map(([part, steps], partIndex, allParts) => (
        <Card key={part} className="shadow-sm">
          <Card.Body className="d-flex flex-column gap-2">
            <InputGroup>
              <Button
                variant="outline-secondary"
                onClick={() => movePart(part, -1)}
                disabled={partIndex === 0}
                title="Move part up"
                aria-label={`Move part "${part}" up`}
              >
                &uarr;
              </Button>
              <Button
                variant="outline-secondary"
                onClick={() => movePart(part, 1)}
                disabled={partIndex === allParts.length - 1}
                title="Move part down"
                aria-label={`Move part "${part}" down`}
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
                title="Delete this part"
                aria-label={`Delete part "${part}"`}
              >
                Delete part
              </Button>
            </InputGroup>
            {steps.map((step, index) => (
              <InputGroup key={index}>
                <Form.Control value={step} onChange={(e) => updateStep(part, index, e.target.value)} />
                <Button
                  variant="outline-secondary"
                  onClick={() => deleteStep(part, index)}
                  title="Delete this step"
                  aria-label={`Delete step ${index + 1} of "${part}"`}
                >
                  &times;
                </Button>
              </InputGroup>
            ))}
            <Button variant="outline-primary" size="sm" className="align-self-start" onClick={() => addStep(part)}>
              + Add step
            </Button>
          </Card.Body>
        </Card>
      ))}
      <Button variant="outline-primary" className="align-self-start" onClick={addPart}>
        + Add part
      </Button>
    </div>
  );
}
