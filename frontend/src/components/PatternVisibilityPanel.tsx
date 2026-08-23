/**
 * Visibility controls shown on a pattern's detail page, but only to
 * whoever can edit it (see PatternDetailPage's canEdit) -- a private
 * pattern's uploader or an admin. Shows the current Public/Private badge,
 * a one-way "Publish to Community" action, and (while still private)
 * the list of specific users it's been individually shared with, plus a
 * form to add/remove one by username. Shares become moot once a pattern
 * is public (everyone can already see it), so that section only renders
 * while it's still private.
 */
import { useEffect, useState, type FormEvent } from "react";
import { Alert, Badge, Button, Card, Form } from "react-bootstrap";
import { useTranslation } from "react-i18next";
import { fetchPatternShares, publishPattern, sharePattern, unsharePattern } from "../api/client";
import { useApiErrorMessage } from "../i18n/useApiErrorMessage";
import type { Pattern, PatternShare } from "../types/models";
import PublishConsentNotice from "./PublishConsentNotice";

interface Props {
  pattern: Pattern;
  onPatternChange: (pattern: Pattern) => void;
}

export default function PatternVisibilityPanel({ pattern, onPatternChange }: Props) {
  const { t } = useTranslation();
  const getErrorMessage = useApiErrorMessage();

  const [shares, setShares] = useState<PatternShare[]>([]);
  // Clicking "Publish to Community" doesn't publish immediately -- it
  // reveals PublishConsentNotice first (the same "this becomes public"
  // gate submitting/importing a pattern used to show up front, before it
  // stopped publishing on its own -- see ReviewPatternPage). Publishing
  // only fires once that's explicitly acknowledged.
  const [confirming, setConfirming] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [publishError, setPublishError] = useState<string | null>(null);
  const [shareUsername, setShareUsername] = useState("");
  const [sharing, setSharing] = useState(false);
  const [shareError, setShareError] = useState<string | null>(null);

  useEffect(() => {
    if (pattern.is_public) return;
    fetchPatternShares(pattern.id).then(setShares);
  }, [pattern.id, pattern.is_public]);

  function handleCancelPublish() {
    setConfirming(false);
    setAcknowledged(false);
    setPublishError(null);
  }

  async function handleConfirmPublish() {
    setPublishError(null);
    setPublishing(true);
    try {
      const result = await publishPattern(pattern.id);
      onPatternChange(result.pattern);
      setConfirming(false);
      setAcknowledged(false);
    } catch (err) {
      setPublishError(getErrorMessage(err, t("visibility.publishFailed")));
    } finally {
      setPublishing(false);
    }
  }

  async function handleShare(e: FormEvent) {
    e.preventDefault();
    const username = shareUsername.trim();
    if (!username) return;
    setShareError(null);
    setSharing(true);
    try {
      setShares(await sharePattern(pattern.id, username));
      setShareUsername("");
    } catch (err) {
      setShareError(getErrorMessage(err, t("visibility.shareFailed")));
    } finally {
      setSharing(false);
    }
  }

  async function handleUnshare(userId: number) {
    await unsharePattern(pattern.id, userId);
    setShares((prev) => prev.filter((s) => s.user_id !== userId));
  }

  return (
    <Card className="shadow-sm mb-3">
      <Card.Body>
        <div className="d-flex justify-content-between align-items-center flex-wrap gap-2">
          <Badge bg={pattern.is_public ? "success" : "secondary"}>
            {pattern.is_public ? t("visibility.public") : t("visibility.private")}
          </Badge>
          {!pattern.is_public && !confirming && (
            <Button variant="primary" size="sm" onClick={() => setConfirming(true)}>
              {t("visibility.publishButton")}
            </Button>
          )}
        </div>

        {confirming && (
          <div className="mt-3">
            <PublishConsentNotice acknowledged={acknowledged} onAcknowledgeChange={setAcknowledged} />
            {publishError && (
              <Alert variant="danger" className="mt-2 mb-2 py-2">
                {publishError}
              </Alert>
            )}
            <div className="d-flex gap-2">
              <Button
                variant="primary"
                size="sm"
                disabled={!acknowledged || publishing}
                onClick={handleConfirmPublish}
              >
                {publishing ? t("visibility.publishing") : t("publishConsent.confirmButton")}
              </Button>
              <Button variant="outline-secondary" size="sm" onClick={handleCancelPublish}>
                {t("publishConsent.cancelButton")}
              </Button>
            </div>
          </div>
        )}

        {!pattern.is_public && (
          <div className="mt-3">
            <h6>{t("visibility.sharedWithHeading")}</h6>
            {shares.length === 0 ? (
              <p className="text-muted small mb-2">{t("visibility.noShares")}</p>
            ) : (
              <ul className="list-unstyled mb-2">
                {shares.map((share) => (
                  <li key={share.id} className="d-flex justify-content-between align-items-center py-1">
                    {share.username}
                    <Button
                      variant="link"
                      size="sm"
                      className="text-danger p-0"
                      onClick={() => handleUnshare(share.user_id)}
                    >
                      {t("visibility.removeShare")}
                    </Button>
                  </li>
                ))}
              </ul>
            )}
            <Form onSubmit={handleShare} className="d-flex gap-2" style={{ maxWidth: "20rem" }}>
              <Form.Control
                size="sm"
                placeholder={t("visibility.shareUsernamePlaceholder")}
                value={shareUsername}
                onChange={(e) => setShareUsername(e.target.value)}
              />
              <Button type="submit" variant="outline-primary" size="sm" disabled={sharing}>
                {sharing ? t("visibility.sharing") : t("visibility.shareButton")}
              </Button>
            </Form>
            {shareError && (
              <Alert variant="danger" className="mt-2 mb-0 py-2">
                {shareError}
              </Alert>
            )}
          </div>
        )}
      </Card.Body>
    </Card>
  );
}
