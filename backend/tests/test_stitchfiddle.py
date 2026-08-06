"""
Tests for the pure, network-free parts of app/stitchfiddle.py: parsing a
share URL, decoding the grid, mapping the palette to its stored JSON
shape, and building the materials text. fetch_chart itself (the
Playwright/network part) is exercised indirectly via
test_stitch_fiddle_routes.py, which monkeypatches it -- there's no real
network access in this suite, same convention as test_scraper.py's
static HTML/PDF fixtures.
"""

import json
from pathlib import Path

import pytest

from app.stitchfiddle import (
    StitchFiddleError,
    decode_grid,
    materials_text_from_palette,
    palette_to_json,
    parse_share_url,
)

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "stitchfiddle-chart-response.json").read_text()
)
CHART = FIXTURE["state"]["chart"]
SIZE = CHART["grid"]["settings"]["size"]


def test_parse_share_url_accepts_real_share_link():
    assert parse_share_url("https://www.stitchfiddle.com/c/so1rbr-bw0bk4") == "so1rbr-bw0bk4"


def test_parse_share_url_accepts_locale_prefix_and_trailing_slash():
    assert parse_share_url("https://stitchfiddle.com/en/c/so1rbr-bw0bk4/") == "so1rbr-bw0bk4"


@pytest.mark.parametrize(
    "url",
    [
        "",
        "not a url",
        "https://example.com/c/so1rbr-bw0bk4",
        "https://stitchfiddle.com/en/browse",
    ],
)
def test_parse_share_url_rejects_non_chart_urls(url):
    with pytest.raises(StitchFiddleError):
        parse_share_url(url)


def test_decode_grid_matches_column_times_row_count():
    grid = decode_grid(CHART["grid"]["rows"], SIZE["columnCount"], SIZE["rowCount"])

    assert len(grid) == SIZE["columnCount"] * SIZE["rowCount"]
    # Every byte must be a valid index into this chart's 7-color palette.
    assert set(grid) <= set(range(len(CHART["palette"]["styles"])))


def test_decode_grid_rejects_mismatched_size():
    with pytest.raises(StitchFiddleError):
        decode_grid(CHART["grid"]["rows"], SIZE["columnCount"] + 1, SIZE["rowCount"])


def test_palette_to_json_matches_grid_byte_indices():
    grid = decode_grid(CHART["grid"]["rows"], SIZE["columnCount"], SIZE["rowCount"])

    palette = palette_to_json(CHART["palette"]["styles"])

    assert len(palette) == len(CHART["palette"]["styles"])
    # Every decoded grid byte must resolve to a real palette entry.
    assert all(0 <= value < len(palette) for value in grid)
    assert all(entry["hex"].startswith("#") for entry in palette)


def test_palette_to_json_uses_description_or_abbreviation_or_fallback():
    palette = [
        {"colorBackground": "#849c62", "description": "Forest Green", "abbreviation": ""},
        {"colorBackground": "#578151", "description": "", "abbreviation": "FG2"},
        {"colorBackground": "#d0b9a9", "description": "", "abbreviation": ""},
    ]

    result = palette_to_json(palette)

    assert result == [
        {"hex": "#849C62", "label": "Forest Green"},
        {"hex": "#578151", "label": "FG2"},
        {"hex": "#D0B9A9", "label": "Color 3"},
    ]


def test_materials_text_uses_description_when_present():
    palette = [
        {"colorBackground": "#849c62", "description": "Forest Green", "abbreviation": ""},
        {"colorBackground": "#578151", "description": "", "abbreviation": "FG2"},
        {"colorBackground": "#d0b9a9", "description": "", "abbreviation": ""},
    ]

    text = materials_text_from_palette(palette)

    assert "Forest Green (#849C62)" in text
    assert "FG2 (#578151)" in text
    assert "Color 3 (#D0B9A9)" in text
