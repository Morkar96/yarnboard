/**
 * Compact list-view representation of a pattern, used on the Community,
 * My Uploads, and My Saved pages. Always shows AttributionTag so uploader
 * + original-source credit is visible everywhere a pattern appears, not
 * just on its detail page.
 */
import { Badge, Button, Card } from "react-bootstrap";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { resolvePhotoUrl } from "../api/client";
import type { Pattern } from "../types/models";
import { translationForUiLanguage } from "../utils/patternTranslation";
import AttributionTag from "./AttributionTag";

interface Props {
  pattern: Pattern;
  /** Optional save/unsave action rendered on the card (Community/Saved views). */
  onToggleSave?: (pattern: Pattern) => void;
  isSaved?: boolean;
}

export default function PatternCard({ pattern, onToggleSave, isSaved }: Props) {
  const { t, i18n } = useTranslation();
  // Falls back to the pattern's own primary-content title for whichever
  // direction has no translation yet -- see translationForUiLanguage.
  const title = translationForUiLanguage(pattern, i18n.language)?.title ?? pattern.title;

  return (
    <Card className="h-100 shadow-sm">
      {pattern.has_photo && (
        <Card.Img
          variant="top"
          src={resolvePhotoUrl(pattern.photo_url)}
          alt={title}
          style={{ height: "160px", objectFit: "cover" }}
          onError={(e) => {
            e.currentTarget.style.display = "none";
          }}
        />
      )}
      <Card.Body className="d-flex flex-column">
        <div className="d-flex justify-content-between align-items-start gap-2">
          <Card.Title
            as={Link}
            to={`/pattern/${pattern.id}`}
            className="link-primary text-decoration-none"
            dir="auto"
          >
            {title}
          </Card.Title>
          {!pattern.is_public && (
            <Badge bg="secondary" className="mt-1">
              {t("patternCard.private")}
            </Badge>
          )}
        </div>
        <AttributionTag pattern={pattern} />
        {onToggleSave && (
          <Button
            variant={isSaved ? "outline-secondary" : "outline-primary"}
            size="sm"
            className="mt-auto align-self-start"
            onClick={() => onToggleSave(pattern)}
          >
            {isSaved ? t("patternCard.removeSaved") : t("patternCard.save")}
          </Button>
        )}
      </Card.Body>
    </Card>
  );
}
