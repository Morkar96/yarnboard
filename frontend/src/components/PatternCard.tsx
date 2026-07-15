/**
 * Compact list-view representation of a pattern, used on the Community,
 * My Uploads, and My Saved pages. Always shows AttributionTag so uploader
 * + original-source credit is visible everywhere a pattern appears, not
 * just on its detail page.
 */
import { Link } from "react-router-dom";
import type { Pattern } from "../types/models";
import AttributionTag from "./AttributionTag";

interface Props {
  pattern: Pattern;
  /** Optional save/unsave action rendered on the card (Community/Saved views). */
  onToggleSave?: (pattern: Pattern) => void;
  isSaved?: boolean;
}

export default function PatternCard({ pattern, onToggleSave, isSaved }: Props) {
  return (
    <div className="pattern-card">
      <Link to={`/pattern/${pattern.id}`} className="pattern-card-title">
        {pattern.title}
      </Link>
      <AttributionTag pattern={pattern} />
      {onToggleSave && (
        <button type="button" onClick={() => onToggleSave(pattern)}>
          {isSaved ? "Remove from Saved" : "Save"}
        </button>
      )}
    </div>
  );
}
