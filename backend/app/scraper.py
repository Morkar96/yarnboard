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

import io
import re
from urllib.parse import unquote, urlparse

import pdfplumber
from bs4 import BeautifulSoup

from playwright.sync_api import (
    Page,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

USER_AGENT = (
    "Mozilla/5.0 (compatible; YarnboardBot/1.0; "
    "+https://github.com/yarnboard) pattern-preview"
)
REQUEST_TIMEOUT_SECONDS = 10

# A PDF text line counts as "bold" (PDF's equivalent of an HTML label tag)
# if at least this fraction of its characters are rendered in a
# bold-named font (e.g. "Helvetica-Bold", "AAAAAA+Times-Bold" -- the
# "AAAAAA+" is a common font-subsetting prefix, harmless to the substring
# check). Not 100%: a bold line can still contain the occasional
# non-bold character (kerning artifacts, embedded symbols) without that
# meaning the line as a whole isn't a label.
PDF_BOLD_LINE_RATIO = 0.6

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
ABBREVIATIONS_KEYWORDS = ["abbreviation", "abbrev", "glossary", "terms", "ab"]
INSTRUCTIONS_KEYWORDS = ["instructions", "pattern", "crochet pattern", "directions", "how to make"]

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
def looks_like_cloudflare_challenge(page: Page) -> bool:
    title = page.title().lower()
    body_text = page.locator("body").inner_text(timeout=5_000).lower()

    challenge_phrases = (
        "just a moment",
        "checking your browser",
        "verify you are human",
        "performing security verification",
        "cloudflare",
    )

    return any(
        phrase in title or phrase in body_text
        for phrase in challenge_phrases
    )
def wait_for_article(page: Page) -> None:
    try:
        page.locator("h1").filter(
            has_text="Rainbow Cuddles Crochet Unicorn Pattern"
        ).wait_for(timeout=20_000)
    except PlaywrightTimeoutError as exc:
        raise RuntimeError(
            "The article did not load. Cloudflare may still be blocking the page."
        ) from exc


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


def parse_pattern_pdf(pdf_bytes: bytes, source_url: str) -> dict:
    """
    Heuristically extract a pattern draft from a PDF file's raw bytes.

    Mirrors parse_pattern_html's contract exactly (same return shape, same
    "never assume this is correct" caveat) -- called from the upload path
    (POST /api/patterns/preview-upload) when the uploaded file is a PDF
    rather than saved HTML, and from the CLI at the bottom of this file.
    `source_url` is still whatever URL the user typed alongside the
    upload (a PDF has no notion of "the page it came from" on its own),
    used the same way for dedup/attribution as the HTML upload path.

    PDFs have no tags, so the two HTML-specific signals _extract_sections
    relies on need PDF equivalents: "is this a heading/bold tag" becomes
    "is this line's text rendered in a bold-named font" (pdfplumber
    exposes a fontname per character), and "the page's <h1>" becomes the
    PDF's own title (metadata, falling back to its first line). Once
    reduced to a set of label-line strings and a title string, the actual
    section-classification algorithm (_classify_lines) is identical to
    the HTML path -- see its docstring.
    """
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            metadata_title = (pdf.metadata or {}).get("Title")
            metadata_author = (pdf.metadata or {}).get("Author")

            lines: list[str] = []
            label_texts: set[str] = set()
            for page in pdf.pages:
                for line in page.extract_text_lines():
                    text = line["text"].strip()
                    if not text:
                        continue
                    lines.append(text)

                    chars = line.get("chars") or []
                    if not chars or len(text) > MAX_LABEL_LENGTH:
                        continue
                    bold_ratio = sum(
                        1 for c in chars if "bold" in (c.get("fontname") or "").lower()
                    ) / len(chars)
                    if bold_ratio >= PDF_BOLD_LINE_RATIO:
                        label_texts.add(text)
    except Exception as exc:
        raise ScraperError(f"Could not read this PDF: {exc}") from exc

    if metadata_title and metadata_title.strip():
        title = _strip_site_name_suffix(metadata_title.strip())
    elif lines:
        title = lines[0]
    else:
        title = "Untitled Pattern"

    author = metadata_author.strip() if metadata_author and metadata_author.strip() else None
    if not author:
        author = _find_author_phrase(" ".join(lines))

    materials, abbreviations, instructions = _classify_lines(lines, label_texts, {title})

    domain = _bare_domain(source_url)

    return {
        "title": title,
        "author": author,
        "materials": materials,
        "abbreviations": abbreviations,
        "instructions": instructions,
        "source_site_name": domain,
        "source_domain": domain,
    }


def _fetch_html(url: str) -> str:
    """
    Download the page HTML, raising ScraperError on any failure.

    Uses a headless browser (Playwright) to handle JavaScript-based sites
    and bot-detection challenges (e.g. Cloudflare).

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

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(user_agent=USER_AGENT)
        try:
            response = page.goto(url, timeout=30_000, wait_until="domcontentloaded")

            if looks_like_cloudflare_challenge(page):
                wait_for_article(page)

            if response is None or not response.ok:
                if looks_like_cloudflare_challenge(page):
                    raise ScraperError(
                        f"{url} is protected by a bot-detection service (e.g. Cloudflare) that "
                        "blocks automated fetching. Yarnboard tried to wait for the challenge to "
                        "complete, but it may have failed or timed out. You can try saving "
                        "the page's HTML yourself and using the file upload option instead."
                    )
                status = response.status if response else "unknown"
                raise ScraperError(f"{url} returned HTTP {status}")

            content = page.content()
        except PlaywrightTimeoutError as exc:
            raise ScraperError(f"Timed out trying to fetch {url}") from exc
        except Exception as exc:
            raise ScraperError(f"Could not fetch {url} with Playwright: {exc}") from exc
        finally:
            browser.close()

    return content


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
        return _strip_site_name_suffix(soup.title.string.strip())

    return "Untitled Pattern"


def _strip_site_name_suffix(title: str) -> str:
    """
    Strips a trailing " | Site Name" / " - Site Name" suffix from a title.
    Shared by the HTML <title> tag fallback and the PDF metadata Title
    field -- PDFs "printed" from a webpage (a common way patterns end up
    as PDFs at all) frequently inherit that page's <title> verbatim,
    suffix and all, into their own embedded Title property.
    """
    return re.split(r"\s*[|–-]\s*", title)[0]


def _extract_author(soup: BeautifulSoup) -> str | None:
    """
    Priority: <meta name="author"> -> a "by <name>" / "designed by <name>"
    phrase near the top of the page. Returns None (left blank in the
    review form) rather than guessing when nothing is found.
    """
    meta = soup.find("meta", attrs={"name": "author"})
    if meta and meta.get("content"):
        return meta["content"].strip()

    return _find_author_phrase(soup.get_text(" ", strip=True))


def _find_author_phrase(text: str) -> str | None:
    """
    Shared by both the HTML and PDF extraction paths: searches the first
    ~2000 characters of plain text for a "by <Name>" / "designed by
    <Name>" phrase. Used as the fallback when there's no more authoritative
    metadata field available (an HTML <meta name="author"> tag, or a PDF's
    embedded Author property).
    """
    match = re.search(
        r"\b(?:designed by|pattern by|written by|by)\s+([A-Z][\w'.-]+(?:\s+[A-Z][\w'.-]+){0,2})",
        text[:2000],
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
    # Some themes wrap every blog *comment* in its own <article> too (seen
    # on WordPress/Divi sites, e.g. <article class="comment-body">) --
    # taking the first <article> on the page unconditionally can land on
    # a random early comment instead of the real post. Skip those.
    for article in soup.find_all("article"):
        classes = " ".join(article.get("class") or [])
        if "comment" in classes or "comment" in (article.get("id") or ""):
            continue
        return article

    tag = soup.find(attrs={"itemprop": "articleBody"})
    if tag:
        return tag

    # Separator varies by theme/builder -- "entry-content" (hyphen) is the
    # common WordPress convention, but page-builder themes like Divi use
    # underscores instead (e.g. "et_pb_post_content"), so both must match.
    class_re = re.compile(r"(post[-_]body|entry[-_]content|post[-_]content|article[-_]body|article[-_]content)", re.I)
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
    HTML front-end for _classify_lines: finds the real content container,
    collects "label" tag texts (headings + bold-styled short tags) and the
    page's own <h1> title text (excluded from matching -- see
    _classify_lines' docstring for why), and linearizes the container into
    plain text lines. The actual section-classification algorithm is
    format-agnostic and lives in _classify_lines, shared with the PDF
    extraction path (parse_pattern_pdf) -- neither "bold tag" nor "<h1>"
    are HTML-specific concepts once reduced to a set of label/title
    strings, so nothing about the classification itself needs to change
    for a different input format.
    """
    container = _find_content_container(soup)

    label_texts = {tag.get_text(strip=True) for tag in container.find_all(_is_label_tag)}
    title_lines = {tag.get_text(strip=True) for tag in container.find_all("h1")}

    lines = _linearize(container)

    return _classify_lines(lines, label_texts, title_lines)


def _classify_lines(
    lines: list[str], label_texts: set[str], excluded_lines: set[str]
) -> tuple[str, str, dict]:
    """
    Single pass that splits a list of already-linearized text lines into
    materials, abbreviations, and named instruction parts. Format-agnostic:
    doesn't know or care whether `lines` came from HTML or a PDF, only that
    `label_texts` identifies which of those lines are section/part labels
    (however "bold" was determined for that format) and `excluded_lines`
    identifies the page/document title (excluded from matching -- see
    below).

    Heuristic, checked in priority order for every line:
      1. Keyword match first, regardless of styling: if a short line's text
         contains a materials/abbreviations/instructions keyword, it starts
         that section -- even if the line isn't in `label_texts` at all.
         Most pattern pages are consistent about the *words* "Materials",
         "Abbreviations", "Instructions"/"Directions"/"Pattern" even when
         they're inconsistent (or entirely absent) about bolding them, so
         keyword text is the stronger, more portable signal and is checked
         before anything else.
      2. `label_texts` membership as a fallback, used only to find *part*
         boundaries within the instructions once we're past whichever of
         the above got us there -- arbitrary part names like "Body:" or
         "Cuff's Ribbing:" have no shared keyword vocabulary, so styling
         (however it's represented for this format) is the only signal
         available for those.
    Lines before the first recognized section are discarded. A part is only
    kept if at least one step line was collected for it, so a heading that
    turns out to be immediately followed by another heading (e.g. a bare
    "Instructions:" line used only to introduce the first real part)
    doesn't leave behind an empty part.

    `excluded_lines` (the document's own title) is skipped entirely --
    pattern titles routinely contain the word "pattern" (e.g. "Cozy Beanie
    Pattern"), which would otherwise self-match the instructions keyword
    and anchor extraction on the title instead of the real content. This
    applies equally to an HTML page's <h1> and a PDF's title (from its
    metadata or first line) -- same risk, same fix.
    """
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
        if line in excluded_lines:
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
    # Quick manual testing against a real URL or a local HTML/PDF file,
    # without going through Flask or the database at all -- handy while
    # iterating on the heuristics. Usage (from backend/, with the venv
    # active):
    #   python3 -m app.scraper <url>
    #   python3 -m app.scraper ./some-saved-pattern-page.html
    #   python3 -m app.scraper ./some-pattern.pdf
    #
    # Must be run as `-m app.scraper`, NOT `python3 app/scraper.py`
    # directly -- direct script execution puts backend/app/ itself (not
    # backend/) on sys.path, and this package's own app/email.py then
    # shadows Python's *stdlib* email package for the whole process.
    # pdfplumber's dependency chain imports the real stdlib `email`
    # internally, so that collision breaks PDF parsing specifically with
    # a confusing ModuleNotFoundError deep inside pdfminer. `-m` avoids it
    # by putting backend/ (the actual package root) on sys.path instead.
    import json
    import sys
    from pathlib import Path

    if len(sys.argv) != 2:
        print("Usage: python3 -m app.scraper <url-or-local-html-or-pdf-file>", file=sys.stderr)
        sys.exit(1)

    target = sys.argv[1]

    # A local PDF path goes through parse_pattern_pdf directly (it needs
    # raw bytes, not something _fetch_html/parse_pattern_html can produce)
    # -- the URL used for attribution is just the local path turned into a
    # file:// URI, same placeholder convention the HTML file case already
    # uses for source_url when there's no real URL to speak of.
    if not target.startswith(("http://", "https://", "file://")) and target.lower().endswith(".pdf"):
        local_path = Path(target)
        if not local_path.is_file():
            print(f"Not an existing file: {target}", file=sys.stderr)
            sys.exit(1)
        try:
            result = parse_pattern_pdf(local_path.read_bytes(), local_path.resolve().as_uri())
        except ScraperError as exc:
            print(f"ScraperError: {exc}", file=sys.stderr)
            sys.exit(1)
        print(json.dumps(result, indent=2))
        sys.exit(0)

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
