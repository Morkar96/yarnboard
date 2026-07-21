/**
 * Compact list-view representation of a pattern, used on the Community,
 * My Uploads, and My Saved pages. Always shows AttributionTag so uploader
 * + original-source credit is visible everywhere a pattern appears, not
 * just on its detail page.
 */
import { Button, Card } from "react-bootstrap";
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
    <Card className="h-100 shadow-sm">
      <Card.Body className="d-flex flex-column">
        <Card.Title as={Link} to={`/pattern/${pattern.id}`} className="link-primary text-decoration-none">
          {pattern.title}
        </Card.Title>
        <AttributionTag pattern={pattern} />
        {onToggleSave && (
          <Button
            variant={isSaved ? "outline-secondary" : "outline-primary"}
            size="sm"
            className="mt-auto align-self-start"
            onClick={() => onToggleSave(pattern)}
          >
            {isSaved ? "Remove from Saved" : "Save"}
          </Button>
        )}
      </Card.Body>
    </Card>
  );
}
