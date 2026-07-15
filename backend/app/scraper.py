"""
Best-effort heuristic extraction of pattern content from arbitrary
knitting/crochet webpages.

There is no standard markup for pattern pages across the web (blogs,
Ravelry, PDF-behind-a-page sites, etc. all structure "materials",
"abbreviations" and "instructions" differently), so this module does NOT
try to be a fully general, guaranteed-correct parser. Instead it makes a
reasonable first pass using heading keywords and common list markup, and
the result is always shown to the user as an *editable draft* before
anything is saved (see the preview/submit split in patterns/routes.py).
Treat every field this module returns as a suggestion, not ground truth.
"""

import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (compatible; YarnboardBot/1.0; "
    "+https://github.com/yarnboard) pattern-preview"
)
REQUEST_TIMEOUT_SECONDS = 10

HEADING_TAGS = ["h1", "h2", "h3", "h4", "strong", "b"]
# Section searches (materials/abbreviations/instructions) deliberately
# exclude h1: that's reserved for the page/pattern title elsewhere
# (_extract_title), and titles routinely contain words like "pattern"
# (e.g. "Cozy Beanie Pattern"), which would otherwise false-match
# INSTRUCTIONS_KEYWORDS and anchor extraction on the title instead of the
# real instructions heading.
SECTION_HEADING_TAGS = ["h2", "h3", "h4", "strong", "b"]

MATERIALS_KEYWORDS = ["materials", "you will need", "you'll need", "ingredients", "supplies"]
ABBREVIATIONS_KEYWORDS = ["abbreviation", "abbrev", "glossary", "terms"]
INSTRUCTIONS_KEYWORDS = ["instructions", "pattern", "directions", "how to make"]

# Matches sub-headings that mark the start of a new named part within the
# instructions, e.g. "Part 1", "Section 2", "Row 1-10", "Round 3", "Step 4".
PART_BOUNDARY_RE = re.compile(r"^(part|section|row|round|step)\s*\d+", re.IGNORECASE)
# Matches a numbered line used as a fallback step splitter when a page has
# no <li> markup at all, e.g. "1. Cast on 40 stitches".
NUMBERED_LINE_RE = re.compile(r"^\d+[.)]\s+")


class ScraperError(Exception):
    """Raised when a pattern page can't be fetched or meaningfully parsed."""


def scrape_pattern_from_url(url: str) -> dict:
    """
    Fetch `url` and heuristically extract a pattern draft.

    Returns a dict: title, author, materials, abbreviations, instructions
    ({part_name: [step_text, ...]}), source_site_name, source_domain.
    Never writes to the database -- the caller (the /preview route) is
    responsible for showing this to the user for review before any Pattern
    row is created. Raises ScraperError on network failure or a non-200
    response; parsing failures degrade gracefully to empty fields rather
    than raising, since a partially-empty draft is still useful to a user
    who's willing to fill in the rest by hand.
    """
    soup = BeautifulSoup(_fetch_html(url), "html.parser")

    site_name, domain = _get_site_name(soup, url)

    return {
        "title": _extract_title(soup),
        "author": _extract_author(soup),
        "materials": _extract_materials(soup),
        "abbreviations": _extract_abbreviations(soup),
        "instructions": _extract_instructions(soup),
        "source_site_name": site_name,
        "source_domain": domain,
    }


def _fetch_html(url: str) -> str:
    """Download the page HTML, raising ScraperError on any failure."""
    try:
        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT},
        )
    except requests.RequestException as exc:
        raise ScraperError(f"Could not reach {url}: {exc}") from exc

    if response.status_code != 200:
        raise ScraperError(f"{url} returned HTTP {response.status_code}")

    return response.text


def _get_site_name(soup: BeautifulSoup, url: str) -> tuple[str, str]:
    """
    Return (source_site_name, source_domain) for attribution.

    site_name prefers the page's own `og:site_name` meta tag (most sites
    that care about link previews set this); domain is always derivable
    from the URL itself and used both as a fallback display name and as a
    stable identifier independent of a site's metadata choices.
    """
    domain = _bare_domain(url)
    meta = soup.find("meta", property="og:site_name")
    site_name = meta["content"].strip() if meta and meta.get("content") else domain
    return site_name, domain


def _bare_domain(url: str) -> str:
    netloc = urlparse(url).netloc
    return netloc[4:] if netloc.startswith("www.") else netloc


def _extract_title(soup: BeautifulSoup) -> str:
    """Priority: og:title meta -> first <h1> -> <title> tag (trimmed)."""
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        return og_title["content"].strip()

    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)

    if soup.title and soup.title.string:
        # Strip common " | Site Name" / " - Site Name" suffixes.
        return re.split(r"\s*[|–-]\s*", soup.title.string.strip())[0]

    return "Untitled Pattern"


def _extract_author(soup: BeautifulSoup) -> str | None:
    """
    Priority: <meta name="author"> -> a "by <name>" / "designed by <name>"
    phrase near the top of the page. Returns None (left blank in the
    review form) rather than guessing when nothing is found.
    """
    meta = soup.find("meta", attrs={"name": "author"})
    if meta and meta.get("content"):
        return meta["content"].strip()

    text = soup.get_text(" ", strip=True)[:2000]
    match = re.search(
        r"\b(?:designed by|pattern by|written by|by)\s+([A-Z][\w'.-]+(?:\s+[A-Z][\w'.-]+){0,2})",
        text,
    )
    return match.group(1).strip() if match else None


def _find_section_by_heading(soup: BeautifulSoup, keywords: list[str]):
    """
    Return the first heading-like tag (h2-h4, strong, b -- not h1, which is
    the page title, see SECTION_HEADING_TAGS) whose text contains one of
    `keywords` (case-insensitive), or None. The caller walks the tag's
    following siblings to collect the section's content.
    """
    for tag in soup.find_all(SECTION_HEADING_TAGS):
        text = tag.get_text(strip=True).lower()
        if any(keyword in text for keyword in keywords):
            return tag
    return None


def _collect_section_text(heading) -> str:
    """
    Starting just after `heading`, collect text from sibling list/paragraph
    elements until the next heading-like tag, and join as newline-separated
    lines. Used for materials/abbreviations, which are usually a short list
    or a few lines of prose rather than a structured checklist.
    """
    lines: list[str] = []
    for sibling in heading.find_next_siblings():
        if sibling.name in HEADING_TAGS:
            break
        if sibling.name in ("ul", "ol"):
            lines.extend(li.get_text(strip=True) for li in sibling.find_all("li"))
        elif sibling.name == "p":
            text = sibling.get_text(strip=True)
            if text:
                lines.append(text)
    return "\n".join(lines)


def _extract_materials(soup: BeautifulSoup) -> str:
    heading = _find_section_by_heading(soup, MATERIALS_KEYWORDS)
    return _collect_section_text(heading) if heading else ""


def _extract_abbreviations(soup: BeautifulSoup) -> str:
    heading = _find_section_by_heading(soup, ABBREVIATIONS_KEYWORDS)
    return _collect_section_text(heading) if heading else ""


def _extract_instructions(soup: BeautifulSoup) -> dict:
    """
    Locate the instructions section and split it into named parts, each a
    list of step strings.

    Heuristic:
      1. Find the instructions block via its heading.
      2. Walk its following siblings; any heading whose text matches
         PART_BOUNDARY_RE (or is itself an h2/h3/h4) starts a new part.
         Everything before the first such boundary goes in a default
         "Instructions" part.
      3. Steps within a part come from <li> elements of any <ul>/<ol>; if a
         part has no list markup at all, fall back to splitting its
         paragraph text on numbered-line patterns ("1. ...", "2. ...").
      4. Stops at the next non-instructions heading (materials/abbreviations
         sections, or the end of the page).

    Returns {} if no instructions heading is found at all -- the review
    form then shows one empty default part for the user to fill in by hand.
    """
    heading = _find_section_by_heading(soup, INSTRUCTIONS_KEYWORDS)
    if heading is None:
        return {}

    parts: dict[str, list[str]] = {}
    current_part_name = "Instructions"
    current_lines: list[str] = []

    def flush():
        if current_lines:
            parts.setdefault(current_part_name, [])
            parts[current_part_name].extend(_split_into_steps(current_lines))

    for sibling in heading.find_next_siblings():
        text = sibling.get_text(strip=True) if hasattr(sibling, "get_text") else ""

        is_new_part = sibling.name in ("h2", "h3", "h4") or (
            sibling.name in HEADING_TAGS and PART_BOUNDARY_RE.match(text)
        )
        if is_new_part:
            flush()
            current_part_name = text or f"Part {len(parts) + 1}"
            current_lines = []
            continue

        if sibling.name in HEADING_TAGS and sibling.name not in ("h2", "h3", "h4"):
            # A bold/strong line that isn't a recognized part boundary and
            # isn't part of the materials/abbreviations sections we already
            # handled elsewhere -- if it looks like a *different* labeled
            # section (materials/abbreviations appearing after instructions
            # on some pages), stop collecting.
            lowered = text.lower()
            if any(k in lowered for k in MATERIALS_KEYWORDS + ABBREVIATIONS_KEYWORDS):
                break

        if sibling.name in ("ul", "ol"):
            current_lines.extend(li.get_text(strip=True) for li in sibling.find_all("li"))
        elif sibling.name == "p":
            if text:
                current_lines.append(text)

    flush()
    return parts


def _split_into_steps(lines: list[str]) -> list[str]:
    """
    Given raw collected lines for a part, return a clean list of step
    strings. If the lines already look like discrete <li> entries (no
    embedded numbering), they're used as-is. Otherwise, lines are treated
    as prose and re-split on numbered-line boundaries ("1. ", "2) ", ...).
    """
    steps: list[str] = []
    for line in lines:
        # A single line may itself contain multiple "1. ... 2. ..." steps
        # when it came from one big <p> rather than a <ul>.
        pieces = NUMBERED_LINE_RE.split(line)
        pieces = [p.strip() for p in pieces if p.strip()]
        steps.extend(pieces if pieces else [line])
    return steps
