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
import { Link } from "react-router-dom";
import {
  ApiError,
  deleteStitchFiddleLink,
  fetchStitchFiddleLinks,
  importStitchFiddleLink,
  saveStitchFiddleLink,
} from "../api/client";
import type { StitchFiddleLink } from "../types/models";

export default function StitchFiddlePage() {
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
      setSaveError(err instanceof ApiError ? err.message : "Could not save that link.");
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
        [link.id]: err instanceof ApiError ? err.message : "Could not import this chart.",
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
      <h1 className="mb-3">Stitch Fiddle Charts</h1>
      <p className="text-muted">
        Paste a link to one of your public Stitch Fiddle charts. Import turns it into a pattern
        with a reconstructed chart image and a color list -- written instructions aren't
        generated (that's a Stitch Fiddle premium feature), so add those yourself afterward via
        the pattern's Edit page if you want them.
      </p>

      <Form onSubmit={handleSave} className="mb-4" style={{ maxWidth: "32rem" }}>
        <Form.Group className="mb-2" controlId="stitchfiddle-url">
          <Form.Label>Stitch Fiddle chart link</Form.Label>
          <Form.Control
            type="url"
            value={shareUrl}
            onChange={(e) => setShareUrl(e.target.value)}
            placeholder="https://www.stitchfiddle.com/c/..."
            required
          />
        </Form.Group>
        {saveError && <Alert variant="danger">{saveError}</Alert>}
        <Button type="submit" variant="primary" disabled={saving}>
          {saving ? "Saving..." : "Save link"}
        </Button>
      </Form>

      {links.length === 0 ? (
        <p className="text-muted">No Stitch Fiddle links saved yet.</p>
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
                      View pattern
                    </Link>
                  ) : (
                    <Button
                      variant="outline-primary"
                      size="sm"
                      disabled={busyLinkId === link.id}
                      onClick={() => handleImport(link)}
                    >
                      {busyLinkId === link.id ? "Importing..." : "Import"}
                    </Button>
                  )}
                  <Button
                    variant="outline-danger"
                    size="sm"
                    disabled={busyLinkId === link.id}
                    onClick={() => handleRemove(link)}
                  >
                    Remove
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
