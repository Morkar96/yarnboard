/**
 * Ownership controls shown on a pattern's detail page, only to whoever
 * can manage it (see PatternDetailPage's pattern.can_manage) -- the
 * uploader or an admin, never an edit-level share (see PatternShare.
 * can_edit). Shows the current Public/Private badge, publish/unpublish
 * (reversible either way), delete, and -- while private -- the list of
 * specific users it's been individually shared with (each with a
 * view/edit toggle), plus a form to add a new one by username. Shares
 * become moot once a pattern is public (everyone can already see it), so
 * that section only renders while it's still private.
 */
import { useEffect, useState, type FormEvent } from "react";
import { Alert, Badge, Button, Card, Form } from "react-bootstrap";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import {
  deletePattern,
  fetchPatternShares,
  publishPattern,
  sharePattern,
  unpublishPattern,
  unsharePattern,
  updateSharePermission,
} from "../api/client";
import { useApiErrorMessage } from "../i18n/useApiErrorMessage";
import type { Pattern, PatternShare } from "../types/models";
import PublishConsentNotice from "./PublishConsentNotice";

interface Props {
  pattern: Pattern;
  onPatternChange: (pattern: Pattern) => void;
}

export default function PatternVisibilityPanel({ pattern, onPatternChange }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
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
  const [unpublishing, setUnpublishing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [shareUsername, setShareUsername] = useState("");
  const [shareCanEdit, setShareCanEdit] = useState(false);
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

  async function handleUnpublish() {
    if (!window.confirm(t("visibility.unpublishConfirm"))) return;
    setPublishError(null);
    setUnpublishing(true);
    try {
      const result = await unpublishPattern(pattern.id);
      onPatternChange(result.pattern);
    } catch (err) {
      setPublishError(getErrorMessage(err, t("visibility.unpublishFailed")));
    } finally {
      setUnpublishing(false);
    }
  }

  async function handleDelete() {
    if (!window.confirm(t("visibility.deleteConfirm"))) return;
    setDeleteError(null);
    setDeleting(true);
    try {
      await deletePattern(pattern.id);
      navigate("/mine");
    } catch (err) {
      setDeleteError(getErrorMessage(err, t("visibility.deleteFailed")));
      setDeleting(false);
    }
  }

  async function handleShare(e: FormEvent) {
    e.preventDefault();
    const username = shareUsername.trim();
    if (!username) return;
    setShareError(null);
    setSharing(true);
    try {
      setShares(await sharePattern(pattern.id, username, shareCanEdit));
      setShareUsername("");
      setShareCanEdit(false);
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

  async function handleTogglePermission(userId: number, canEdit: boolean) {
    setShares(await updateSharePermission(pattern.id, userId, canEdit));
  }

  return (
    <Card className="shadow-sm mb-3">
      <Card.Body>
        <div className="d-flex justify-content-between align-items-center flex-wrap gap-2">
          <Badge bg={pattern.is_public ? "success" : "secondary"}>
            {pattern.is_public ? t("visibility.public") : t("visibility.private")}
          </Badge>
          <div className="d-flex gap-2">
            {!pattern.is_public && !confirming && (
              <Button variant="primary" size="sm" onClick={() => setConfirming(true)}>
                {t("visibility.publishButton")}
              </Button>
            )}
            {pattern.is_public && (
              <Button
                variant="outline-secondary"
                size="sm"
                disabled={unpublishing}
                onClick={handleUnpublish}
              >
                {unpublishing ? t("visibility.unpublishing") : t("visibility.unpublishButton")}
              </Button>
            )}
            <Button variant="outline-danger" size="sm" disabled={deleting} onClick={handleDelete}>
              {deleting ? t("visibility.deleting") : t("visibility.deleteButton")}
            </Button>
          </div>
        </div>

        {publishError && (
          <Alert variant="danger" className="mt-2 mb-0 py-2">
            {publishError}
          </Alert>
        )}
        {deleteError && (
          <Alert variant="danger" className="mt-2 mb-0 py-2">
            {deleteError}
          </Alert>
        )}

        {confirming && (
          <div className="mt-3">
            <PublishConsentNotice acknowledged={acknowledged} onAcknowledgeChange={setAcknowledged} />
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
                  <li key={share.id} className="d-flex justify-content-between align-items-center py-1 gap-2">
                    <span>{share.username}</span>
                    <div className="d-flex align-items-center gap-2">
                      <Form.Check
                        type="switch"
                        id={`share-can-edit-${share.user_id}`}
                        label={t("visibility.canEdit")}
                        checked={share.can_edit}
                        onChange={(e) => handleTogglePermission(share.user_id, e.target.checked)}
                      />
                      <Button
                        variant="link"
                        size="sm"
                        className="text-danger p-0"
                        onClick={() => handleUnshare(share.user_id)}
                      >
                        {t("visibility.removeShare")}
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            <Form onSubmit={handleShare} className="d-flex flex-column gap-2" style={{ maxWidth: "20rem" }}>
              <div className="d-flex gap-2">
                <Form.Control
                  size="sm"
                  placeholder={t("visibility.shareUsernamePlaceholder")}
                  value={shareUsername}
                  onChange={(e) => setShareUsername(e.target.value)}
                />
                <Button type="submit" variant="outline-primary" size="sm" disabled={sharing}>
                  {sharing ? t("visibility.sharing") : t("visibility.shareButton")}
                </Button>
              </div>
              <Form.Check
                type="checkbox"
                id="share-new-can-edit"
                label={t("visibility.shareAsEditor")}
                checked={shareCanEdit}
                onChange={(e) => setShareCanEdit(e.target.checked)}
              />
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
