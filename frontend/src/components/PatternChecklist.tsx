/**
 * Renders a pattern's instructions as a per-part checklist. Checking a box
 * optimistically flips local state, then calls the progress API; if that
 * call fails, the local flip is reverted so the UI never lies about what's
 * actually saved.
 *
 * Anonymous viewers (not logged in) see the same checklist but with
 * disabled checkboxes -- their progress has nowhere to be stored server
 * side, since progress is always tied to a specific user's account.
 */
import { useState } from "react";
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

  const parts = Object.entries(localInstructions);
  if (parts.length === 0) {
    return <p>No instructions were extracted for this pattern.</p>;
  }

  return (
    <div className="pattern-checklist">
      {!user && (
        <p className="checklist-login-hint">Log in to track your progress on this pattern.</p>
      )}
      {parts.map(([part, steps]) => (
        <section key={part}>
          <h3>{part}</h3>
          <ul>
            {steps.map((step, index) => (
              <li key={index}>
                <label>
                  <input
                    type="checkbox"
                    checked={step.completed}
                    disabled={!user}
                    onChange={(e) => handleToggle(part, index, e.target.checked)}
                  />
                  {step.step}
                </label>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
