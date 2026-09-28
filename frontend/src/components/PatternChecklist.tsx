/**
 * Renders a pattern's instructions as a per-part checklist. Checking a box
 * optimistically flips local state, then calls the progress API; if that
 * call fails, the local flip is reverted so the UI never lies about what's
 * actually saved.
 *
 * Each part can be collapsed independently (handy once you've finished a
 * section and want it out of the way), and a single "Collapse/Expand all"
 * toggle above the list controls every part at once.
 *
 * Anonymous viewers (not logged in) see the same checklist but with
 * disabled checkboxes -- their progress has nowhere to be stored server
 * side, since progress is always tied to a specific user's account.
 */
import { useState } from "react";
import { Alert, Button, Card, Collapse, Form } from "react-bootstrap";
import { toggleProgress } from "../api/client";
import { useAuth } from "../context/AuthContext";
import type { InstructionsMap } from "../types/models";

interface Props {
  patternId: number;
  instructions: InstructionsMap;
}

export default function PatternChecklist({ patternId, instructions }: Props) {
  const { user } = useAuth();
  const [localInstructions, setLocalInstructions] = useState(instructions);
  const [collapsedParts, setCollapsedParts] = useState<Set<string>>(new Set());

  async function handleToggle(part: string, index: number, nextCompleted: boolean) {
    setLocalInstructions((prev) => ({
      ...prev,
      [part]: prev[part].map((s, i) => (i === index ? { ...s, completed: nextCompleted } : s)),
    }));

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
      {!user && <Alert variant="light">Log in to track your progress on this pattern.</Alert>}

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
                      disabled={!user}
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
