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
from urllib.parse import unquote, urlparse

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (compatible; YarnboardBot/1.0; "
    "+https://github.com/yarnboard) pattern-preview"
)
REQUEST_TIMEOUT_SECONDS = 10

# Tags that always count as a section/part label if their own text is short
# enough (h1 excluded -- that's the page title, handled by _extract_title,
# and titles routinely contain words like "pattern" which would otherwise
# false-match a materials/abbreviations keyword).
ALWAYS_LABEL_TAGS = ("h2", "h3", "h4", "h5", "h6", "strong", "b")
# Tags that only count as a label when they're styled bold -- very common
# on older/simpler pattern blogs (e.g. classic Blogger templates), which
# often have *no* real heading markup at all: the whole post is one flat
# run of text and <br> tags, with section names marked only by
# `<span style="font-weight: bold;">Materials:</span>`-style inline styling.
MAYBE_BOLD_LABEL_TAGS = ("span", "font", "div", "p")
# Tags whose content should end on its own line when the page is
# linearized into plain text (see _linearize). <br> is handled separately
# since it has no content of its own to append a newline after.
BLOCK_LEVEL_TAGS = ("p", "li", "div", "tr", "h1", "h2", "h3", "h4", "h5", "h6")
# A label longer than this is almost certainly a real sentence that happens
# to be bold, not a section name -- skip it so a bolded phrase mid-paragraph
# doesn't get misread as a new part.
MAX_LABEL_LENGTH = 80

MATERIALS_KEYWORDS = ["materials", "you will need", "you'll need", "ingredients", "supplies"]
ABBREVIATIONS_KEYWORDS = ["abbreviation", "abbrev", "glossary", "terms"]
INSTRUCTIONS_KEYWORDS = ["instructions", "pattern", "directions", "how to make"]

# Matches a numbered line used as a fallback step splitter when a page has
# no line-break markup at all, e.g. "1. Cast on 40 stitches. 2. Join...".
NUMBERED_LINE_RE = re.compile(r"^\d+[.)]\s+")
BOLD_STYLE_RE = re.compile(r"font-weight\s*:\s*(bold|[6-9]00)", re.IGNORECASE)


class ScraperError(Exception):
    """Raised when a pattern page can't be fetched or meaningfully parsed."""


def scrape_pattern_from_url(url: str) -> dict:
    """
    Fetch `url` and heuristically extract a pattern draft.

    Never writes to the database -- the caller (the /preview route) is
    responsible for showing this to the user for review before any Pattern
    row is created. Raises ScraperError on network failure or a non-200
    response (including sites that block automated fetching -- see
    _looks_like_bot_challenge). See parse_pattern_html for what's returned
    and how parsing failures degrade.
    """
    return parse_pattern_html(_fetch_html(url), url)


def parse_pattern_html(html: str, source_url: str) -> dict:
    """
    Heuristically extract a pattern draft from already-fetched HTML,
    without doing any network request of its own.

    Used by scrape_pattern_from_url for the normal case, and directly by
    the file-upload fallback (POST /api/patterns/preview-upload) when a
    site's bot-detection blocks Yarnboard's automatic fetch -- in that
    case the user downloads the page themselves and uploads the HTML, but
    `source_url` (for dedup and attribution) is still the URL they typed.

    Returns a dict: title, author, materials, abbreviations, instructions
    ({part_name: [step_text, ...]}), source_site_name, source_domain.
    Parsing failures degrade gracefully to empty fields rather than
    raising, since a partially-empty draft is still useful to a user who's
    willing to fill in the rest by hand.
    """
    soup = BeautifulSoup(html, "html.parser")

    site_name, domain = _get_site_name(soup, source_url)
    materials, abbreviations, instructions = _extract_sections(soup)

    return {
        "title": _extract_title(soup),
        "author": _extract_author(soup),
        "materials": materials,
        "abbreviations": abbreviations,
        "instructions": instructions,
        "source_site_name": site_name,
        "source_domain": domain,
    }


def _fetch_html(url: str) -> str:
    """
    Download the page HTML, raising ScraperError on any failure.

    Also accepts file:// URLs, which are read straight off disk instead of
    over HTTP -- handy for testing the extraction heuristics against a
    saved HTML snapshot (see the CLI entry point at the bottom of this
    file, which turns a plain local path into one of these automatically).
    """
    if url.startswith("file://"):
        # unquote is required here: Path.resolve().as_uri() (used by the
        # CLI below) percent-encodes characters like spaces (" " -> "%20")
        # per the URI spec, but urlparse() does not decode that back --
        # without this, a path containing a space would 404 against a
        # literal "%20" instead of opening the real file.
        path = unquote(urlparse(url).path)
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except OSError as exc:
            raise ScraperError(f"Could not read {path}: {exc}") from exc

    try:
        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT},
        )
    except requests.RequestException as exc:
        raise ScraperError(f"Could not reach {url}: {exc}") from exc

    if response.status_code != 200:
        if _looks_like_bot_challenge(response):
            raise ScraperError(
                f"{url} is protected by a bot-detection service (e.g. Cloudflare) that "
                "blocks automated fetching -- this can't be scraped. Copy the title, "
                "materials, abbreviations, and instructions from the page yourself and "
                "fill them in on the review form instead."
            )
        raise ScraperError(f"{url} returned HTTP {response.status_code}")

    return response.text


def _looks_like_bot_challenge(response: "requests.Response") -> bool:
    """
    True if a non-200 response looks like an anti-bot interstitial (e.g.
    Cloudflare's "Just a moment..." JS challenge) rather than a normal
    error page. These can't be solved by a plain HTTP client -- they
    require actually running a browser -- so there's no point retrying or
    tweaking headers; the caller should surface a clear, specific message
    instead of a generic "HTTP 403".
    """
    if response.headers.get("cf-mitigated"):
        return True
    body_start = response.text[:2000].lower()
    return "just a moment" in body_start or "checking your browser" in body_start


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


def _is_bold(tag) -> bool:
    """True if `tag` is visually bold -- either semantically (<strong>/<b>)
    or via an inline `font-weight` style, which is how many older/simpler
    pattern blogs (classic Blogger templates especially) mark section names
    instead of using real heading markup."""
    if tag.name in ("strong", "b"):
        return True
    return bool(BOLD_STYLE_RE.search(tag.get("style") or ""))


def _is_label_tag(tag) -> bool:
    """A tag counts as a possible section/part label if it's a heading tag,
    or if it's bold and short -- see MAX_LABEL_LENGTH for why "short"
    matters (a long bolded sentence is prose, not a label)."""
    if tag.name in ALWAYS_LABEL_TAGS:
        return True
    if tag.name in MAYBE_BOLD_LABEL_TAGS and _is_bold(tag):
        text = tag.get_text(strip=True)
        return bool(text) and len(text) <= MAX_LABEL_LENGTH
    return False


def _find_content_container(soup: BeautifulSoup):
    """
    Best-effort scoping to the actual pattern content, so sidebar/footer
    noise (nav links, "About Me" widgets, follower lists, etc. -- all
    common on blog templates) doesn't get scanned alongside the real post
    and misread as pattern sections. Falls back to <body> if nothing more
    specific matches -- never the whole document, since <head> contains
    the <title> tag, which by SEO convention often reads like
    "X Pattern | Site Name" and would otherwise self-match the
    instructions keyword the same way the page's <h1> can (see the
    title-exclusion note on _extract_sections).
    """
    article = soup.find("article")
    if article:
        return article

    tag = soup.find(attrs={"itemprop": "articleBody"})
    if tag:
        return tag

    class_re = re.compile(r"(post-body|entry-content|post-content|article-body|article-content)", re.I)
    tag = soup.find(attrs={"class": class_re})
    if tag:
        return tag

    return soup.body or soup


def _linearize(container) -> list[str]:
    """
    Flatten `container` into a list of non-empty text lines, one per
    visual line break. <br> tags become newlines directly; other
    block-level tags (see BLOCK_LEVEL_TAGS) get a trailing newline
    appended after their own content so each one still ends its own line,
    without breaking apart *inline* tags (<span>, <strong>, <a>, ...) that
    should stay concatenated on the same line as their surrounding text.
    This works whether a page uses proper <p>/<h2>/<ul><li> structure or
    (very common on older pattern blogs) just flows text and <br> tags
    with the occasional bold <span> as a pseudo-heading.
    """
    for br in container.find_all("br"):
        br.replace_with("\n")
    for tag in container.find_all(BLOCK_LEVEL_TAGS):
        tag.append("\n")

    raw = container.get_text()
    return [line.strip() for line in raw.split("\n") if line.strip()]


def _extract_sections(soup: BeautifulSoup) -> tuple[str, str, dict]:
    """
    Single pass that splits a page's content into materials, abbreviations,
    and named instruction parts.

    Heuristic, checked in priority order for every line of the linearized
    content:
      1. Keyword match first, regardless of styling: if a short line's text
         contains a materials/abbreviations/instructions keyword, it starts
         that section -- even if the line is plain unstyled text. Most
         pattern pages are consistent about the *words* "Materials",
         "Abbreviations", "Instructions"/"Directions"/"Pattern" even when
         they're inconsistent (or entirely absent) about bolding them, so
         keyword text is the stronger, more portable signal and is checked
         before anything else.
      2. Bold/heading label as a fallback, used only to find *part*
         boundaries within the instructions once we're past whichever of
         the above got us there -- arbitrary part names like "Body:" or
         "Cuff's Ribbing:" have no shared keyword vocabulary, so styling is
         the only signal available for those.
    Lines before the first recognized section are discarded. A part is only
    kept if at least one step line was collected for it, so a heading that
    turns out to be immediately followed by another heading (e.g. a bare
    "Instructions:" line used only to introduce the first real part)
    doesn't leave behind an empty part.

    The page's own title (an <h1>, typically the site/post header) is
    excluded from line-matching entirely -- pattern titles routinely
    contain the word "pattern" (e.g. "Cozy Beanie Pattern"), which would
    otherwise self-match the instructions keywords and anchor extraction on
    the title instead of the real content.
    """
    container = _find_content_container(soup)

    label_texts = {tag.get_text(strip=True) for tag in container.find_all(_is_label_tag)}
    title_lines = {tag.get_text(strip=True) for tag in container.find_all("h1")}

    lines = _linearize(container)

    materials_lines: list[str] = []
    abbreviations_lines: list[str] = []
    parts: dict[str, list[str]] = {}

    state: str | tuple[str, str] | None = None
    current_lines: list[str] = []

    def flush():
        if not current_lines:
            return
        if state == "materials":
            materials_lines.extend(current_lines)
        elif state == "abbreviations":
            abbreviations_lines.extend(current_lines)
        elif isinstance(state, tuple) and state[0] == "part":
            parts.setdefault(state[1], [])
            parts[state[1]].extend(_split_into_steps(current_lines))

    for line in lines:
        if line in title_lines:
            continue

        lowered = line.lower()
        short_enough = len(line) <= MAX_LABEL_LENGTH

        if short_enough and any(k in lowered for k in MATERIALS_KEYWORDS):
            flush()
            current_lines = []
            state = "materials"
            continue

        if short_enough and any(k in lowered for k in ABBREVIATIONS_KEYWORDS):
            flush()
            current_lines = []
            state = "abbreviations"
            continue

        if short_enough and any(k in lowered for k in INSTRUCTIONS_KEYWORDS):
            flush()
            current_lines = []
            state = ("part", line.rstrip(":").strip() or f"Part {len(parts) + 1}")
            continue

        if line in label_texts:
            flush()
            current_lines = []
            state = ("part", line.rstrip(":").strip() or f"Part {len(parts) + 1}")
            continue

        if state is not None:
            current_lines.append(line)

    flush()
    return "\n".join(materials_lines), "\n".join(abbreviations_lines), parts


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


if __name__ == "__main__":
    # Quick manual testing against a real URL or a local HTML file, without
    # going through Flask or the database at all -- handy while iterating
    # on the heuristics. Usage (from backend/, with the venv active):
    #   python3 app/scraper.py <url>
    #   python3 app/scraper.py ./some-saved-pattern-page.html
    import json
    import sys
    from pathlib import Path

    if len(sys.argv) != 2:
        print("Usage: python3 app/scraper.py <url-or-local-html-file>", file=sys.stderr)
        sys.exit(1)

    target = sys.argv[1]
    if not target.startswith(("http://", "https://", "file://")):
        # Not already a URL -- treat it as a local path and turn it into a
        # file:// URL so _fetch_html can handle both cases uniformly.
        local_path = Path(target)
        if not local_path.is_file():
            print(f"Not a URL and not an existing file: {target}", file=sys.stderr)
            sys.exit(1)
        target = local_path.resolve().as_uri()

    try:
        result = scrape_pattern_from_url(target)
    except ScraperError as exc:
        print(f"ScraperError: {exc}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, indent=2))
