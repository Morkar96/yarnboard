/**
 * A Card with a clickable header that collapses/expands its body. Shared
 * by the Materials/Abbreviations sections on PatternDetailPage -- each
 * pattern section can be minimized independently, same idea as each part
 * inside PatternChecklist's instructions (though that one also has its
 * own "collapse all" master toggle, which isn't needed here since there
 * are only ever two of these on a page).
 */
import { useState, type ReactNode } from "react";
import { Card, Collapse } from "react-bootstrap";

interface Props {
  title: string;
  children: ReactNode;
  /** Starts expanded by default; pass false to start collapsed. */
  defaultExpanded?: boolean;
}

export default function CollapsibleCard({ title, children, defaultExpanded = true }: Props) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  return (
    <Card className="shadow-sm mb-3">
      <Card.Header
        className="bg-white fw-semibold d-flex justify-content-between align-items-center"
        role="button"
        onClick={() => setExpanded((prev) => !prev)}
        aria-expanded={expanded}
      >
        {title}
        <span className="text-muted">{expanded ? "▾" : "▸"}</span>
      </Card.Header>
      <Collapse in={expanded}>
        <div>
          <Card.Body>{children}</Card.Body>
        </div>
      </Collapse>
    </Card>
  );
}
