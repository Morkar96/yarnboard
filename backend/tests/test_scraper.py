"""
Regression tests for the extraction heuristics in app/scraper.py.

mock-pattern.pdf is a Playwright print-to-PDF of mock-pattern.html, so the
two tests below double as the refactor's regression check: _classify_lines
is shared by both parse_pattern_html and parse_pattern_pdf, and both
fixtures are expected to land on the same materials/abbreviations/
instructions given they describe the same pattern.
"""

from pathlib import Path

from app.scraper import parse_pattern_html, parse_pattern_pdf

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


def test_parse_pattern_html_degrades_gracefully_on_content_free_page():
    html = "<html><head><title>Example Domain</title></head><body><h1>Example Domain</h1></body></html>"
    draft = parse_pattern_html(html, "https://example.com/")

    assert draft["title"] == "Example Domain"
    assert draft["materials"] == ""
    assert draft["abbreviations"] == ""
    assert draft["instructions"] == {}
