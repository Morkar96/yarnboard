/** Save Stitch Fiddle (stitchfiddle.com) chart share links here, then
 * import each one on demand into a real Yarnboard pattern -- a
 * reconstructed image of the chart plus a plain color list, no written
 * instructions (Stitch Fiddle's own written-instructions feature is
 * premium; write your own via the pattern's Edit page if you want them).
 *
 * Saving a link is cheap (just validates the URL) -- importing is slow
 * (a real headless browser loads the chart server-side), so each row
 * tracks its own import loading/error state rather than one page-wide
 * flag. */
import { useEffect, useState, type FormEvent } from "react";
import { Alert, Button, Form, ListGroup, Spinner } from "react-bootstrap";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import {
  deleteStitchFiddleLink,
  fetchStitchFiddleLinks,
  importStitchFiddleLink,
  saveStitchFiddleLink,
} from "../api/client";
import { useApiErrorMessage } from "../i18n/useApiErrorMessage";
import type { StitchFiddleLink } from "../types/models";

export default function StitchFiddlePage() {
  const { t } = useTranslation();
  const getErrorMessage = useApiErrorMessage();
  const [links, setLinks] = useState<StitchFiddleLink[]>([]);
  const [loading, setLoading] = useState(true);

  const [shareUrl, setShareUrl] = useState("");
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const [busyLinkId, setBusyLinkId] = useState<number | null>(null);
  const [rowErrors, setRowErrors] = useState<Record<number, string>>({});

  useEffect(() => {
    fetchStitchFiddleLinks()
      .then(setLinks)
      .finally(() => setLoading(false));
  }, []);

  async function handleSave(e: FormEvent) {
    e.preventDefault();
    setSaveError(null);
    setSaving(true);
    try {
      const link = await saveStitchFiddleLink(shareUrl);
      setLinks((prev) => (prev.some((l) => l.id === link.id) ? prev : [link, ...prev]));
      setShareUrl("");
    } catch (err) {
      setSaveError(getErrorMessage(err, t("stitchFiddle.saveFailed")));
    } finally {
      setSaving(false);
    }
  }

  async function handleImport(link: StitchFiddleLink) {
    setRowErrors((prev) => ({ ...prev, [link.id]: "" }));
    setBusyLinkId(link.id);
    try {
      const result = await importStitchFiddleLink(link.id);
      setLinks((prev) =>
        prev.map((l) => (l.id === link.id ? { ...l, imported_pattern_id: result.pattern.id } : l)),
      );
    } catch (err) {
      setRowErrors((prev) => ({
        ...prev,
        [link.id]: getErrorMessage(err, t("stitchFiddle.importFailed")),
      }));
    } finally {
      setBusyLinkId(null);
    }
  }

  async function handleRemove(link: StitchFiddleLink) {
    setBusyLinkId(link.id);
    try {
      await deleteStitchFiddleLink(link.id);
      setLinks((prev) => prev.filter((l) => l.id !== link.id));
    } finally {
      setBusyLinkId(null);
    }
  }

  if (loading) return <Spinner animation="border" variant="primary" />;

  return (
    <div>
      <h1 className="mb-3">{t("stitchFiddle.title")}</h1>
      <p className="text-muted">{t("stitchFiddle.intro")}</p>

      <Form onSubmit={handleSave} className="mb-4" style={{ maxWidth: "32rem" }}>
        <Form.Group className="mb-2" controlId="stitchfiddle-url">
          <Form.Label>{t("stitchFiddle.urlLabel")}</Form.Label>
          <Form.Control
            type="url"
            value={shareUrl}
            onChange={(e) => setShareUrl(e.target.value)}
            placeholder={t("stitchFiddle.urlPlaceholder")}
            required
          />
        </Form.Group>
        {saveError && <Alert variant="danger">{saveError}</Alert>}
        <Button type="submit" variant="primary" disabled={saving}>
          {saving ? t("stitchFiddle.saving") : t("stitchFiddle.saveButton")}
        </Button>
      </Form>

      {links.length === 0 ? (
        <p className="text-muted">{t("stitchFiddle.empty")}</p>
      ) : (
        <ListGroup>
          {links.map((link) => (
            <ListGroup.Item key={link.id} className="d-flex flex-column gap-1">
              <div className="d-flex justify-content-between align-items-center gap-2">
                <a href={link.share_url} target="_blank" rel="noreferrer" className="text-truncate">
                  {link.share_url}
                </a>
                <div className="d-flex gap-2 flex-shrink-0">
                  {link.imported_pattern_id ? (
                    <Link
                      to={`/pattern/${link.imported_pattern_id}`}
                      className="btn btn-outline-primary btn-sm"
                    >
                      {t("stitchFiddle.viewPattern")}
                    </Link>
                  ) : (
                    <Button
                      variant="outline-primary"
                      size="sm"
                      disabled={busyLinkId === link.id}
                      onClick={() => handleImport(link)}
                    >
                      {busyLinkId === link.id ? t("stitchFiddle.importing") : t("stitchFiddle.import")}
                    </Button>
                  )}
                  <Button
                    variant="outline-danger"
                    size="sm"
                    disabled={busyLinkId === link.id}
                    onClick={() => handleRemove(link)}
                  >
                    {t("stitchFiddle.remove")}
                  </Button>
                </div>
              </div>
              {rowErrors[link.id] && (
                <Alert variant="danger" className="mb-0 py-1 px-2">
                  {rowErrors[link.id]}
                </Alert>
              )}
            </ListGroup.Item>
          ))}
        </ListGroup>
      )}
    </div>
  );
}
