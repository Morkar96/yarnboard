"""
Regression tests for the extraction heuristics in app/scraper.py.

mock-pattern.pdf is a Playwright print-to-PDF of mock-pattern.html, so the
two tests below double as the refactor's regression check: _classify_lines
is shared by both parse_pattern_html and parse_pattern_pdf, and both
fixtures are expected to land on the same materials/abbreviations/
instructions given they describe the same pattern.
"""

from pathlib import Path

import pytest

from app.scraper import (
    ScraperError,
    _extract_image_url,
    _guard_request_url,
    _is_public_hostname,
    _is_request_allowed,
    parse_pattern_html,
    parse_pattern_pdf,
    scrape_pattern_from_url,
)
from bs4 import BeautifulSoup

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_pattern_html_extracts_structured_pattern():
    html = (FIXTURES / "mock-pattern.html").read_text()
    draft = parse_pattern_html(html, "https://woolyblog.example.com/mock-pattern")

    assert draft["title"] == "Cozy Beanie Pattern"
    assert draft["author"] == "Jane Designer"
    assert draft["source_site_name"] == "Wooly Blog"
    assert draft["source_domain"] == "woolyblog.example.com"
    assert "1 skein worsted weight yarn" in draft["materials"]
    assert "4.5mm circular needles" in draft["materials"]
    assert "k: knit" in draft["abbreviations"]
    assert "p: purl" in draft["abbreviations"]
    assert list(draft["instructions"].keys()) == ["Part 1: Brim", "Part 2: Body"]
    assert draft["instructions"]["Part 1: Brim"] == [
        "Cast on 88 stitches.",
        "Join in the round, place marker.",
    ]
    assert draft["instructions"]["Part 2: Body"] == [
        "Knit every round until piece measures 6 inches from cast on.",
    ]
    # The fixture has no og:image/twitter:image meta tag at all.
    assert draft["photo_url"] is None


def test_parse_pattern_pdf_extracts_same_structure_as_html():
    pdf_bytes = (FIXTURES / "mock-pattern.pdf").read_bytes()
    draft = parse_pattern_pdf(pdf_bytes, "https://example-etsy-shop.test/pattern")

    assert draft["title"] == "Cozy Beanie Pattern"
    assert "1 skein worsted weight yarn" in draft["materials"]
    assert "k: knit" in draft["abbreviations"]
    assert list(draft["instructions"].keys()) == ["Part 1: Brim", "Part 2: Body"]
    assert draft["instructions"]["Part 1: Brim"] == [
        "Cast on 88 stitches.",
        "Join in the round, place marker.",
    ]
    # A PDF has no per-file "site" concept -- both fields are just the
    # domain of the URL the user typed alongside the upload.
    assert draft["source_domain"] == "example-etsy-shop.test"
    assert draft["source_site_name"] == "example-etsy-shop.test"
    # PDFs have no og:image equivalent -- always None, never omitted.
    assert draft["photo_url"] is None


def test_parse_pattern_html_degrades_gracefully_on_content_free_page():
    html = "<html><head><title>Example Domain</title></head><body><h1>Example Domain</h1></body></html>"
    draft = parse_pattern_html(html, "https://example.com/")

    assert draft["title"] == "Example Domain"
    assert draft["materials"] == ""
    assert draft["abbreviations"] == ""
    assert draft["instructions"] == {}
    assert draft["photo_url"] is None


def test_parse_pattern_html_recognizes_hebrew_section_keywords():
    """MATERIALS_KEYWORDS/ABBREVIATIONS_KEYWORDS/INSTRUCTIONS_KEYWORDS all
    carry Hebrew equivalents alongside the English ones -- a Hebrew-
    language pattern page should extract exactly as well as an English
    one, not come back empty just because the section headers aren't in
    English (see _classify_lines' docstring)."""
    html = """
    <html><head><title>דוגמית כובע חמים</title></head>
    <body>
      <h1>דוגמית כובע חמים</h1>
      <p>מאת דנה כהן</p>
      <h2>חומרים</h2>
      <ul>
        <li>פקעת אחת של חוט עבה</li>
        <li>מסרגות 4.5 מ"מ</li>
      </ul>
      <h2>קיצורים</h2>
      <p>ע: עמוד<br>שר: שרשרת</p>
      <h2>הוראות</h2>
      <strong>חלק 1: שוליים</strong>
      <ul>
        <li>להעלות 88 עיניים.</li>
        <li>לסגור לעיגול.</li>
      </ul>
      <strong>חלק 2: גוף</strong>
      <ul>
        <li>לסרוג עד שהעבודה מגיעה ל-15 ס"מ.</li>
      </ul>
    </body></html>
    """
    draft = parse_pattern_html(html, "https://example.co.il/hat-pattern")

    assert draft["author"] == "דנה כהן"
    assert "פקעת אחת של חוט עבה" in draft["materials"]
    assert "ע: עמוד" in draft["abbreviations"]
    assert list(draft["instructions"].keys()) == ["חלק 1: שוליים", "חלק 2: גוף"]
    assert draft["instructions"]["חלק 1: שוליים"] == [
        "להעלות 88 עיניים.",
        "לסגור לעיגול.",
    ]


def test_extract_image_url_prefers_og_image_over_twitter_image():
    html = """
    <html><head>
      <meta property="og:image" content="https://cdn.example.com/photo.jpg">
      <meta name="twitter:image" content="https://cdn.example.com/other.jpg">
    </head></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    assert _extract_image_url(soup, "https://example.com/pattern") == "https://cdn.example.com/photo.jpg"


def test_extract_image_url_falls_back_to_twitter_image():
    html = """
    <html><head>
      <meta name="twitter:image" content="https://cdn.example.com/other.jpg">
    </head></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    assert _extract_image_url(soup, "https://example.com/pattern") == "https://cdn.example.com/other.jpg"


def test_extract_image_url_resolves_relative_url_against_source():
    html = """
    <html><head>
      <meta property="og:image" content="/images/photo.jpg">
    </head></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    assert (
        _extract_image_url(soup, "https://example.com/blog/pattern")
        == "https://example.com/images/photo.jpg"
    )


def test_extract_image_url_returns_none_when_no_tag_present():
    soup = BeautifulSoup("<html><head></head></html>", "html.parser")
    assert _extract_image_url(soup, "https://example.com/pattern") is None


# --- SSRF / local-file-read protection -------------------------------
#
# scrape_pattern_from_url is reachable from POST /api/patterns/preview
# with a raw, user-supplied URL (see test_security.py for the route-level
# tests). These cover the underlying guards directly: file:// must be
# opt-in only (never reachable from the route), and http(s) URLs pointing
# at loopback/private/link-local addresses must be rejected before
# Playwright ever fetches them.


def test_is_public_hostname_rejects_loopback_and_private_addresses():
    assert _is_public_hostname("127.0.0.1") is False
    assert _is_public_hostname("localhost") is False
    assert _is_public_hostname("10.0.0.5") is False
    assert _is_public_hostname("192.168.1.1") is False
    # The AWS/GCP/Azure cloud metadata endpoint -- a classic SSRF target.
    assert _is_public_hostname("169.254.169.254") is False


def test_is_public_hostname_accepts_a_real_public_ip_literal():
    # A literal IP needs no DNS resolution, so this doesn't touch the
    # network and can't flake -- 8.8.8.8 (Google's public DNS) is about
    # as stable a "definitely public" address as exists.
    assert _is_public_hostname("8.8.8.8") is True


def test_guard_request_url_rejects_non_http_schemes():
    with pytest.raises(ScraperError):
        _guard_request_url("file:///etc/passwd")
    with pytest.raises(ScraperError):
        _guard_request_url("ftp://example.com/x")


def test_guard_request_url_rejects_private_addresses():
    with pytest.raises(ScraperError):
        _guard_request_url("http://127.0.0.1/admin")
    with pytest.raises(ScraperError):
        _guard_request_url("http://169.254.169.254/latest/meta-data/")


def test_is_request_allowed_blocks_file_scheme_but_allows_data_uris():
    # file: is blocked unconditionally here (this is the per-request guard
    # a page.route handler applies while rendering, independent of the
    # allow_file flag, which only covers _fetch_html reading a local path
    # directly -- never the browser navigating to one).
    assert _is_request_allowed("file:///etc/passwd") is False
    # Non-network schemes used for inline sub-resources are harmless and
    # must stay allowed, or ordinary pages would fail to render.
    assert _is_request_allowed("data:image/png;base64,AAAA") is True


def test_scrape_pattern_from_url_rejects_file_url_by_default():
    fixture = (FIXTURES / "mock-pattern.html").resolve().as_uri()
    with pytest.raises(ScraperError):
        scrape_pattern_from_url(fixture)


def test_scrape_pattern_from_url_allows_file_url_when_explicitly_opted_in():
    fixture = (FIXTURES / "mock-pattern.html").resolve().as_uri()
    # Only the local CLI entry point at the bottom of scraper.py passes
    # allow_file=True -- confirms that opt-in still works for that use.
    result = scrape_pattern_from_url(fixture, allow_file=True)
    assert result["title"]
