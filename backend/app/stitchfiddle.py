"""
Fetching and decoding Stitch Fiddle (stitchfiddle.com) chart data.

Stitch Fiddle has no public API (confirmed against their own
Integrations/API help page) -- a chart's share page
(stitchfiddle.com/c/<chartId>) is a client-rendered SPA whose real data
arrives via a POST to /en/ajax/chart/get/<chartId>, with request-body
values (a numeric chart id, a JS build hash) computed by Stitch Fiddle's
own client-side code. There's no way to hand-craft that request directly,
so fetch_chart below actually loads the page in a real browser
(Playwright, the same tool scraper.py uses for JS-heavy/Cloudflare-
protected sites) and captures the response Stitch Fiddle's own JS
triggers.

Once captured, the chart's grid is a deterministic, exact pixel array (see
decode_grid) -- unlike scraper.py's heuristic HTML parsing, there's no
guessing involved here, which is why the import flow that calls into this
module (stitch_fiddle/routes.py) skips the "always show an editable draft
first" step scraper.py insists on: there's nothing here that can be
subtly wrong the way keyword-matched HTML sections can be.

The grid is stored and served as structured data (Pattern.chart_grid_data
+ chart_palette, see models.py), rendered as an actual colored <table> on
the frontend (PatternChartGrid.tsx) -- not flattened into an image, so a
crafter can read individual cells the way they would in Stitch Fiddle's
own chart view.

Deliberately not attempted: reconstructing Stitch Fiddle's row-by-row
written instructions (that's a premium feature on their end, driven by a
large client-side template/direction/run-length-grouping engine -- out of
scope; see this module's callers for the product decision).
"""

import base64
import re

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

USER_AGENT = (
    "Mozilla/5.0 (compatible; YarnboardBot/1.0; "
    "+https://github.com/yarnboard) stitch-fiddle-import"
)
FETCH_TIMEOUT_MS = 30_000

# stitchfiddle.com/c/<chartId> or stitchfiddle.com/en/c/<chartId> (locale
# prefix), with or without www., trailing slash, or query string.
SHARE_URL_RE = re.compile(
    r"^https?://(?:www\.)?stitchfiddle\.com/(?:[a-z]{2}/)?c/([A-Za-z0-9_-]+)/?"
)


class StitchFiddleError(Exception):
    """Raised when a Stitch Fiddle chart link can't be parsed or fetched."""


def parse_share_url(url: str) -> str:
    """
    Validate that `url` is a Stitch Fiddle chart share link and return its
    chart_id. Raises StitchFiddleError on anything else -- used both when
    a link is first saved (reject typos immediately) and again at import
    time (the saved share_url is always re-validated, not trusted blindly).
    """
    match = SHARE_URL_RE.match((url or "").strip())
    if not match:
        raise StitchFiddleError(
            "That doesn't look like a Stitch Fiddle chart link. "
            "It should look like https://www.stitchfiddle.com/c/<id>."
        )
    return match.group(1)


def fetch_chart(share_url: str) -> dict:
    """
    Load `share_url` in a real browser and capture the chart data Stitch
    Fiddle's own JS fetches for it. Returns
    {title, chart_id, column_count, row_count, palette, grid_rows_field}.

    Raises StitchFiddleError if the chart isn't public (Stitch Fiddle
    returns {"status": "fail", "reason": "accessDeniedAnonymous"} for a
    chart that isn't shared publicly), on any other non-"ok" status, or on
    a network/timeout failure.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(user_agent=USER_AGENT)
        try:
            with page.expect_response(
                lambda r: "/ajax/chart/get/" in r.url, timeout=FETCH_TIMEOUT_MS
            ) as response_info:
                page.goto(share_url, timeout=FETCH_TIMEOUT_MS, wait_until="domcontentloaded")
            body = response_info.value.json()
        except PlaywrightTimeoutError as exc:
            raise StitchFiddleError(
                "Timed out waiting for Stitch Fiddle to load this chart."
            ) from exc
        except Exception as exc:
            raise StitchFiddleError(f"Could not load {share_url}: {exc}") from exc
        finally:
            browser.close()

    if body.get("status") != "ok":
        if body.get("reason") == "accessDeniedAnonymous":
            raise StitchFiddleError(
                "This chart isn't public. In Stitch Fiddle, open the "
                "chart's Share settings and set access to Public, then try again."
            )
        raise StitchFiddleError("Stitch Fiddle couldn't load this chart.")

    chart = body["state"]["chart"]
    size = chart["grid"]["settings"]["size"]

    return {
        "title": chart["settings"]["title"],
        "chart_id": chart["settings"]["chartId"],
        "column_count": size["columnCount"],
        "row_count": size["rowCount"],
        "palette": chart["palette"]["styles"],
        "grid_rows_field": chart["grid"]["rows"],
    }


def decode_grid(rows_field: str, column_count: int, row_count: int) -> bytes:
    """
    Decode grid.rows into one byte per cell, row-major, each byte a
    0-indexed lookup into the chart's palette. The field is a "1:" prefix
    (a format marker, not a row number -- the whole grid is one blob, not
    per-row segments) followed by a single base64 blob.
    """
    _, _, encoded = rows_field.partition(":")
    padded = encoded + "=" * (-len(encoded) % 4)
    decoded = base64.b64decode(padded)

    expected = column_count * row_count
    if len(decoded) != expected:
        raise StitchFiddleError(
            f"Unexpected chart grid size (got {len(decoded)} cells, expected {expected})."
        )
    return decoded


def _palette_label(style: dict, index: int) -> str:
    """A human-readable name for palette entry `index` (0-based): the
    chart owner's own description/abbreviation from Stitch Fiddle if they
    filled one in, else a generic "Color N" fallback. Shared by
    palette_to_json and materials_text_from_palette so both agree on
    naming."""
    return style.get("description") or style.get("abbreviation") or f"Color {index + 1}"


def palette_to_json(palette: list[dict]) -> list[dict]:
    """
    Map Stitch Fiddle's raw palette entries to the compact shape stored in
    Pattern.chart_palette: [{"hex": "#849C62", "label": "Color 1"}, ...],
    in the same index order the decoded grid bytes reference (see
    decode_grid) -- the frontend looks up cells[i] into this list
    directly.
    """
    return [
        {"hex": style.get("colorBackground", "").upper(), "label": _palette_label(style, i)}
        for i, style in enumerate(palette)
    ]


def materials_text_from_palette(palette: list[dict]) -> str:
    """
    A plain-text color list for Pattern.materials, e.g. "Color 1
    (#849C62)" or "Forest Green (#849C62)" when the chart's owner filled
    in a color's description/abbreviation in Stitch Fiddle. Rendered
    as-is in a <pre> tag on the frontend (PatternDetailPage.tsx), so
    plain lines are all that's expected -- no markdown. A quick-glance
    text summary alongside the full colored table (PatternChartGrid.tsx).
    """
    lines = [
        f"{_palette_label(style, i)} ({style.get('colorBackground', '').upper()})"
        for i, style in enumerate(palette)
    ]
    return "\n".join(lines)
