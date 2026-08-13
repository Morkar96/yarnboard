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
 */
import { useState } from "react";
import { Alert, Button, Card, Collapse, Form } from "react-bootstrap";
import { toggleProgress } from "../api/client";
import { useAuth } from "../context/AuthContext";
import type { InstructionsMap } from "../types/models";
import { getGuestProgress, setGuestStep } from "../utils/guestProgress";

interface Props {
  patternId: number;
  instructions: InstructionsMap;
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

export default function PatternChecklist({ patternId, instructions }: Props) {
  const { user } = useAuth();
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
    return <p className="text-muted">No instructions were extracted for this pattern.</p>;
  }

  const allCollapsed = parts.every(([part]) => collapsedParts.has(part));

  return (
    <div className="d-flex flex-column gap-3">
      {!user && (
        <Alert variant="light">
          You're checking items off as a guest -- progress is saved on this device only. Log in to
          sync it to your account.
        </Alert>
      )}

      <Button
        variant="outline-secondary"
        size="sm"
        className="align-self-start"
        onClick={() =>
          setCollapsedParts(allCollapsed ? new Set() : new Set(parts.map(([part]) => part)))
        }
      >
        {allCollapsed ? "Expand all" : "Collapse all"}
      </Button>

      {parts.map(([part, steps]) => {
        const isCollapsed = collapsedParts.has(part);
        return (
          <Card key={part} className="shadow-sm">
            <Card.Header
              className="bg-white fw-semibold d-flex justify-content-between align-items-center"
              role="button"
              onClick={() => togglePart(part)}
              aria-expanded={!isCollapsed}
            >
              {part}
              <span className="text-muted">{isCollapsed ? "▸" : "▾"}</span>
            </Card.Header>
            <Collapse in={!isCollapsed}>
              <div>
                <Card.Body className="d-flex flex-column gap-2">
                  {steps.map((step, index) => (
                    <Form.Check
                      key={index}
                      type="checkbox"
                      id={`${part}-${index}`}
                      label={step.step}
                      checked={step.completed}
                      onChange={(e) => handleToggle(part, index, e.target.checked)}
                    />
                  ))}
                </Card.Body>
              </div>
            </Collapse>
          </Card>
        );
      })}
    </div>
  );
}
