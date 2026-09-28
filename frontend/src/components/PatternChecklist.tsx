/**
 * Renders a pattern's instructions as a per-part checklist. Checking a box
 * optimistically flips local state, then persists it:
 *   - logged-in users: via the progress API, reverting the local flip if
 *     that call fails, so the UI never lies about what's actually saved.
 *   - anonymous viewers: to this browser's localStorage only (see
 *     ../utils/guestProgress) -- there's no account to store it against
 *     server-side, so it's a local-only convenience that doesn't sync
 *     across devices and is lost if this browser's storage is cleared.
 *
 * Each part can be collapsed independently (handy once you've finished a
 * section and want it out of the way), and a single "Collapse/Expand all"
 * toggle above the list controls every part at once.
 *
 * `instructionsHe`/`instructionsEn` (both optional) are pure *display*
 * overlays, shown instead of the pattern's own primary-content text when
 * the UI language matches that direction -- whichever of the two matches
 * the current UI language wins, falling back to the primary text if that
 * direction has no translation yet (see PatternDetailPage's identical
 * fallback for title/materials/abbreviations). But `part`/`index` passed
 * to toggleProgress (or cached for a guest), and every state key here,
 * always stay the pattern's own primary-content identifiers regardless
 * of what's on screen. See Pattern.instructions_he/instructions_en's
 * docstrings in backend/app/models.py for why: checklist progress is
 * keyed by the primary part name, so an overlaid-language checklist
 * would have nowhere compatible to store progress against if it used its
 * own translated keys instead of looking them up against the same
 * primary structure.
 */
import { useState } from "react";
import { Alert, Button, Card, Collapse, Form } from "react-bootstrap";
import { useTranslation } from "react-i18next";
import { toggleProgress } from "../api/client";
import { useAuth } from "../context/AuthContext";
import type { EnglishInstructionEntry, HebrewInstructionEntry, InstructionsMap } from "../types/models";
import { getGuestProgress, setGuestStep } from "../utils/guestProgress";

interface Props {
  patternId: number;
  instructions: InstructionsMap;
  instructionsHe?: Record<string, HebrewInstructionEntry> | null;
  instructionsEn?: Record<string, EnglishInstructionEntry> | null;
}

/** Overlay any cached guest progress onto server-provided instructions
 * (which come back all-unchecked for a viewer with no account). No-op for
 * a logged-in user, whose completed flags already reflect their own
 * UserPatternProgress row. */
function withGuestProgress(patternId: number, instructions: InstructionsMap, isGuest: boolean): InstructionsMap {
  if (!isGuest) return instructions;
  const cached = getGuestProgress(patternId);
  const result: InstructionsMap = {};
  for (const [part, steps] of Object.entries(instructions)) {
    const flags = cached[part];
    result[part] = flags ? steps.map((s, i) => ({ ...s, completed: !!flags[i] })) : steps;
  }
  return result;
}

export default function PatternChecklist({ patternId, instructions, instructionsHe, instructionsEn }: Props) {
  const { user } = useAuth();
  const { t, i18n } = useTranslation();
  const showHebrew = i18n.language === "he" && !!instructionsHe;
  const showEnglish = i18n.language === "en" && !!instructionsEn;
  const [localInstructions, setLocalInstructions] = useState(() =>
    withGuestProgress(patternId, instructions, !user),
  );
  const [collapsedParts, setCollapsedParts] = useState<Set<string>>(new Set());

  async function handleToggle(part: string, index: number, nextCompleted: boolean) {
    setLocalInstructions((prev) => ({
      ...prev,
      [part]: prev[part].map((s, i) => (i === index ? { ...s, completed: nextCompleted } : s)),
    }));

    if (!user) {
      // Guest: cache-only, no server round trip -- nothing to revert on
      // failure since there's no network call that can fail.
      setGuestStep(patternId, part, index, nextCompleted);
      return;
    }

    try {
      await toggleProgress(patternId, part, index, nextCompleted);
    } catch {
      // Revert on failure.
      setLocalInstructions((prev) => ({
        ...prev,
        [part]: prev[part].map((s, i) => (i === index ? { ...s, completed: !nextCompleted } : s)),
      }));
    }
  }

  function togglePart(part: string) {
    setCollapsedParts((prev) => {
      const next = new Set(prev);
      if (next.has(part)) next.delete(part);
      else next.add(part);
      return next;
    });
  }

  const parts = Object.entries(localInstructions);
  if (parts.length === 0) {
    return <p className="text-muted">{t("checklist.noInstructions")}</p>;
  }

  const allCollapsed = parts.every(([part]) => collapsedParts.has(part));

  return (
    <div className="d-flex flex-column gap-3">
      {!user && <Alert variant="light">{t("checklist.guestNotice")}</Alert>}

      <Button
        variant="outline-secondary"
        size="sm"
        className="align-self-start"
        onClick={() =>
          setCollapsedParts(allCollapsed ? new Set() : new Set(parts.map(([part]) => part)))
        }
      >
        {allCollapsed ? t("checklist.expandAll") : t("checklist.collapseAll")}
      </Button>

      {parts.map(([part, steps]) => {
        const isCollapsed = collapsedParts.has(part);
        const heading = showHebrew
          ? (instructionsHe?.[part]?.heading_he ?? part)
          : showEnglish
            ? (instructionsEn?.[part]?.heading_en ?? part)
            : part;
        return (
          <Card key={part} className="shadow-sm">
            <Card.Header
              className="bg-white fw-semibold d-flex justify-content-between align-items-center"
              dir="auto"
              role="button"
              onClick={() => togglePart(part)}
              aria-expanded={!isCollapsed}
            >
              {heading}
              <span className="text-muted">{isCollapsed ? "▸" : "▾"}</span>
            </Card.Header>
            <Collapse in={!isCollapsed}>
              <div>
                <Card.Body className="d-flex flex-column gap-2">
                  {steps.map((step, index) => {
                    const label = showHebrew
                      ? (instructionsHe?.[part]?.steps_he?.[index] ?? step.step)
                      : showEnglish
                        ? (instructionsEn?.[part]?.steps_en?.[index] ?? step.step)
                        : step.step;
                    return (
                      <Form.Check
                        key={index}
                        type="checkbox"
                        id={`${part}-${index}`}
                        label={label}
                        dir="auto"
                        checked={step.completed}
                        onChange={(e) => handleToggle(part, index, e.target.checked)}
                      />
                    );
                  })}
                </Card.Body>
              </div>
            </Collapse>
          </Card>
        );
      })}
    </div>
  );
}
