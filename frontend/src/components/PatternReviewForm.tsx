/**
 * Editable form for a scraped draft (title/author/materials/abbreviations/
 * instructions) before publishing. The scraper is only best-effort (see
 * backend/app/scraper.py), so every field here is editable rather than
 * read-only -- this is the human review step that makes the heuristic
 * extraction trustworthy enough to publish.
 */
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

  function addPart() {
    const name = `Part ${Object.keys(draft.instructions).length + 1}`;
    updateField("instructions", { ...draft.instructions, [name]: [""] });
  }

  return (
    <div className="pattern-review-form">
      <label>
        Title
        <input value={draft.title} onChange={(e) => updateField("title", e.target.value)} />
      </label>

      <label>
        Original author
        <input
          value={draft.author ?? ""}
          placeholder="Unknown"
          onChange={(e) => updateField("author", e.target.value || null)}
        />
      </label>

      <label>
        Materials
        <textarea
          value={draft.materials}
          onChange={(e) => updateField("materials", e.target.value)}
        />
      </label>

      <label>
        Abbreviations
        <textarea
          value={draft.abbreviations}
          onChange={(e) => updateField("abbreviations", e.target.value)}
        />
      </label>

      <h3>Instructions</h3>
      {Object.entries(draft.instructions).map(([part, steps]) => (
        <div key={part} className="review-form-part">
          <input
            className="part-name-input"
            value={part}
            onChange={(e) => updatePartName(part, e.target.value)}
          />
          {steps.map((step, index) => (
            <input
              key={index}
              value={step}
              onChange={(e) => updateStep(part, index, e.target.value)}
            />
          ))}
          <button type="button" onClick={() => addStep(part)}>
            + Add step
          </button>
        </div>
      ))}
      <button type="button" onClick={addPart}>
        + Add part
      </button>
    </div>
  );
}
