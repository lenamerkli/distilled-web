"""
wiki_to_plain_html.py — Convert Minecraft-Wiki / Fandom Wiki HTML pages into plain, LLM-friendly HTML.

Removes:
  * images/audio/video/iframes and their captions/descriptions
    (but preserves item names shown via icons: either adjacent text or the
    icon's short title tooltip is injected as plain text)
  * the sections: Contents, Sounds, Videos, Gallery, See also, External links, Navigation
  * hyperlinks (keeps the rendered text)
  * all CSS and JavaScript (tags, inline styles, event handlers)
  * unnecessary divs/spans, class names, ids and other decorative attributes
  * the infobox "history-json" blob

Exports:
    parse_html(raw_html: str, default_title: str) -> str
"""

import re

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

# ---------------------------------------------------------------- constants

HEAD_TAGS = ["h1", "h2", "h3", "h4", "h5", "h6"]

# Elements removed together with everything inside them.
DROP_WITH_CONTENT = {
    "style", "script", "link", "meta", "noscript", "template",
    "audio", "video", "iframe", "object", "embed", "source", "track",
    "figure",                       # thumbnails / embeds incl. <figcaption> descriptions
    "input", "button", "select", "textarea", "label",
    "map", "area", "picture", "param", "wbr",
    "colgroup", "col",
}

# Elements kept (everything else gets unwrapped, i.e. replaced by its children).
KEEP_TAGS = {
    "html", "head", "body", "title",
    "p", "br", "hr",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "dl", "dt", "dd",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption",
    "blockquote", "q", "pre", "code",
    "b", "strong", "i", "em", "u", "s", "small", "sub", "sup",
}

# Attributes allowed to survive (everything else is stripped).
KEEP_ATTRS = {"colspan", "rowspan"}

# Sections to remove, keyed by normalized heading text.
REMOVE_SECTIONS = {
    "contents", "sounds", "videos", "gallery",
    "see also", "external links", "navigation",
}


# ---------------------------------------------------------------- helpers

def collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def norm(text: str) -> str:
    """For comparisons only: collapses whitespace, lowercases, drops underscores."""
    return collapse_ws(text).lower().replace("_", " ")


def heading_level(el) -> "int | None":
    """Level (1-6) if `el` is a heading or a heading-wrapper div, else None."""
    if not isinstance(el, Tag):
        return None
    if el.name in HEAD_TAGS:
        return int(el.name[1])
    if el.name == "div":
        h = el.find(HEAD_TAGS)
        if h is not None and norm(el.get_text(" ")) == norm(h.get_text(" ")):
            return int(h.name[1])
    return None


def looks_like_item_name(text: str) -> bool:
    """True if a tooltip/title reads like an item name rather than a description."""
    t = re.sub(r"\s+", " ", text or "").strip()
    if not t or len(t) > 40:
        return False
    if t.endswith((".", "!", "?", ",")):
        return False
    low = t.lower()
    if ":" in t:                                    # "File:Foo.png", sentences with ':'
        return False
    if re.search(r"\.(png|jpe?g|gif|webp|svg|ogg|mp3|wav)\b", low):
        return False
    return True


# ---------------------------------------------------------------- passes

def pass_drop_dead_tags(soup):
    # HTML comments (MediaWiki debug reports: "NewPP limit report", parser cache info)
    for c in soup.find_all(string=lambda t: isinstance(t, Comment)):
        c.extract()
    for tag_name in DROP_WITH_CONTENT:
        for el in soup.find_all(tag_name):
            el.decompose()
    for el in soup.select("#toc"):
        el.decompose()
    # hidden machine-readable blobs: infobox "history-json", loot-table "chest-json", ...
    for el in soup.find_all(class_="noexcerpt"):
        el.decompose()
    for el in soup.select(".mw-editsection"):
        el.decompose()
    # navigation boxes at page bottom
    for table in soup.find_all("table", class_="navbox"):
        table.decompose()
    # image/video galleries
    for ul in soup.find_all("ul", class_="gallery"):
        ul.decompose()
    # "See also" hatnotes and similar search-auxiliary links
    for div in soup.find_all("div", class_="hatnote"):
        div.decompose()
    # elements hidden from readers via CSS (calculator controls, toggles, ...)
    for el in soup.find_all(attrs={"hidden": True}):
        el.decompose()
    for el in soup.find_all(style=lambda v: v and re.search(r"display\s*:\s*none|visibility\s*:\s*hidden", v)):
        el.decompose()
    # Fandom-specific: remove ad containers and placeholders
    for el in soup.find_all(class_=re.compile(r"fandom-ad|ad-container|ad-placeholder", re.I)):
        el.decompose()
    # Fandom-specific: remove the right rail / sidebar
    for el in soup.select("#WikiaRail, .page__right-rail, .right-rail-wrapper"):
        el.decompose()
    # Fandom-specific: remove global navigation headers
    for el in soup.select("#global-top-navigation, #community-navigation, .global-explore-navigation"):
        el.decompose()
    # Fandom-specific: remove community header
    for el in soup.select(".fandom-community-header, .community-header-wrapper"):
        el.decompose()
    # Fandom-specific: remove page header actions (edit, history, etc.)
    for el in soup.select(".page-header__actions"):
        el.decompose()
    # Fandom-specific: remove footer
    for el in soup.select(".global-footer, .page-footer"):
        el.decompose()
    # Fandom-specific: remove age gate
    for el in soup.select("#age-gate"):
        el.decompose()
    # Fandom-specific: remove search containers
    for el in soup.select(".search-container"):
        el.decompose()
    # Fandom-specific: remove wiki tools
    for el in soup.select(".wiki-tools"):
        el.decompose()
    # Fandom-specific: remove notifications placeholder
    for el in soup.select(".notifications-placeholder"):
        el.decompose()
    # Minecraft Wiki: remove navigation breadcrumbs ("From Minecraft Wiki Jump to navigation Jump to search")
    for el in soup.select(".mw-indicator"):
        el.decompose()
    # Remove any leftover navigation/help links
    for el in soup.select(".mw-empty-elt"):
        el.decompose()


def pass_remove_sections(root):
    """Remove REMOVE_SECTIONS headings plus all content up to the next same-or-higher heading."""
    while True:
        target = None
        for h in root.find_all(HEAD_TAGS):
            if norm(h.get_text(" ")) in REMOVE_SECTIONS:
                target = h
                break
        if target is None:
            return
        # climb to the heading-wrapper div if there is one
        node = target
        while (node.parent is not None and node.parent.name == "div"
               and heading_level(node.parent) is not None):
            node = node.parent
        level = int(target.name[1])
        doomed, sib = [node], node.next_sibling
        while sib is not None:
            sl = heading_level(sib)
            if sl is not None and sl <= level:
                break
            doomed.append(sib)
            sib = sib.next_sibling
        for el in doomed:
            if isinstance(el, Tag):
                el.decompose()
            else:
                el.extract()


def _is_media_node(el) -> bool:
    """True for images and the tight icon/sprite wrappers around them."""
    if not isinstance(el, Tag):
        return False
    if el.name in ("img", "audio", "video"):
        return True
    if el.name == "span":
        classes = el.get("class") or []
        return ("mw:File" in (el.get("typeof") or "")
                or any(c in classes for c in
                       ("sprite-file", "pixel-image", "invslot", "invslot-item-image")))
    if el.name == "a":
        return "mw-file-description" in (el.get("class") or [])
    return False


def _enclosing_block(el):
    anc = el.parent
    while anc is not None and anc.name not in ("td", "th", "li", "p", "dt", "dd",
                                               "caption", "blockquote", "body"):
        anc = anc.parent
    return anc if anc is not None else el


def _visible_text_around(container) -> str:
    """Text of the enclosing block, excluding text inside media nodes."""
    block = _enclosing_block(container)
    parts = []
    for text in block.descendants if isinstance(block, Tag) else []:
        if not isinstance(text, NavigableString):
            continue
        anc, inside = text.parent, False
        while anc is not None and anc is not block:
            if _is_media_node(anc):
                inside = True
                break
            anc = anc.parent
        if not inside:
            parts.append(str(text))
    return "".join(parts).strip()


def pass_media(soup):
    """Handle <img> remnants: inject item names, drop media + descriptions."""
    # loop: replacements can expose or detach nested images
    while True:
        img = None
        for candidate in soup.find_all("img"):
            if candidate.parent is not None:
                img = candidate
                break
        if img is None:
            break
        # locate the outermost tight media wrapper (never crossing cell boundaries)
        container = img
        anc = img
        while anc is not None and anc.name not in ("td", "th", "li", "p", "body",
                                                     "table", "caption", None):
            if anc.name == "span" and _is_media_node(anc):
                container = anc
            anc = anc.parent
        if container.parent is None:
            continue
        # Only inject the icon's name when no visible name sits next to it already.
        if _visible_text_around(container):
            container.decompose()
            continue
        # candidate name: title attributes (container itself, then children, then img)
        name = None
        if looks_like_item_name(container.get("title") or ""):
            name = container.get("title")
        else:
            for el in [container, *container.descendants]:
                if isinstance(el, Tag) and el.name in ("a", "span"):
                    t = el.get("title")
                    if looks_like_item_name(t or ""):
                        name = t
                        break
        if name is None and looks_like_item_name(img.get("alt") or ""):
            name = img.get("alt")
        if name:
            container.replace_with(NavigableString(" " + collapse_ws(name) + " "))
        else:
            container.decompose()
    # any leftover media wrappers that never contained an <img> (e.g. audio spans)
    for el in soup.find_all(attrs={"typeof": re.compile(r"mw:(File|Audio|Video)")}):
        if not el.get_text(strip=True):
            el.decompose()


def pass_unwrap_links(soup):
    for a in soup.find_all("a"):
        a.unwrap()


def _is_valid_title(text: str) -> bool:
    """Check if a title looks valid (not corrupted/garbled text).

    Some wiki pages have corrupted infobox titles (e.g., Tibetan script, zero-width chars).
    We detect these by checking for high proportions of non-ASCII characters or
    characters that are unlikely in normal English titles.
    """
    if not text:
        return False

    # Allow common ASCII and some extended Latin
    ascii_count = sum(1 for c in text if ord(c) < 128)
    total_count = len(text)

    if total_count == 0:
        return False

    # If more than 50% of characters are non-ASCII (and non-common extended Latin), it's likely corrupted
    # Extended Latin range: 128-255 (includes accented chars like é, ñ, ü, etc.)
    non_ascii_non_latin = sum(1 for c in text if ord(c) > 255)

    if total_count > 0 and non_ascii_non_latin / total_count > 0.3:
        return False

    # Check for characters commonly seen in corrupted text (Tibetan, etc.)
    # Tibetan Unicode range: U+0F00-U+0FFF
    has_tibetan = any(0x0F00 <= ord(c) <= 0x0FFF for c in text)
    if has_tibetan:
        return False

    # Check minimum length - extremely short or long titles are suspicious
    if len(text) < 2 or len(text) > 100:
        return False

    return True


def pass_promote_infobox_title(soup):
    """Promote infobox title to h1. Handles both Minecraft Wiki and Fandom formats."""
    title_promoted = False

    # Prefer #firstHeading / .mw-first-heading when available (more reliable than infobox)
    first_heading = soup.select_one("#firstHeading, .mw-first-heading, h1#firstHeading")
    if first_heading and _is_valid_title(first_heading.get_text(strip=True)):
        h1 = soup.new_tag("h1")
        h1.string = collapse_ws(first_heading.get_text(" "))
        first_heading.replace_with(h1)
        title_promoted = True

    if not title_promoted:
        # Minecraft Wiki format (only use if title looks valid)
        for el in soup.select(".infobox-title, .mcwiki-header"):
            title_text = el.get_text(strip=True)
            if title_text and _is_valid_title(title_text):
                h1 = soup.new_tag("h1")
                h1.string = collapse_ws(title_text)
                el.replace_with(h1)
                title_promoted = True
                break

    if not title_promoted:
        # Fandom portable-infobox format
        for el in soup.select(".portable-infobox .pi-title"):
            title_text = el.get_text(strip=True)
            if title_text and _is_valid_title(title_text):
                h1 = soup.new_tag("h1")
                h1.string = collapse_ws(title_text)
                el.replace_with(h1)
                title_promoted = True
                break

    if not title_promoted:
        # Fandom page header title (fallback when no infobox)
        for el in soup.select(".page-header__title .mw-page-title-main"):
            title_text = el.get_text(strip=True)
            if title_text and _is_valid_title(title_text):
                h1 = soup.new_tag("h1")
                h1.string = collapse_ws(title_text)
                el.replace_with(h1)
                title_promoted = True
                break

    # Remove any invalid/corrupted infobox titles to clean up the output
    # (This runs regardless of whether a valid title was found)
    for el in soup.select(".infobox-title, .mcwiki-header, .portable-infobox .pi-title"):
        title_text = el.get_text(strip=True)
        if title_text and not _is_valid_title(title_text):
            el.decompose()


def pass_unwrap_noise(soup, protect=()):
    """Unwrap layout containers; repeat until stable."""
    changed = True
    while changed:
        changed = False
        for el in list(soup.find_all(True)):
            if el.name in KEEP_TAGS or el.name in DROP_WITH_CONTENT:
                continue
            if any(el is p for p in protect):
                continue
            el.unwrap()
            changed = True


def pass_strip_attributes(soup):
    for el in soup.find_all(True):
        for attr in list(el.attrs):
            if attr not in KEEP_ATTRS:
                del el.attrs[attr]
            elif el.attrs[attr] in ("1", 1):
                del el.attrs[attr]


def pass_prune_empty(soup):
    """Drop elements that carry no text (but keep empty table cells — they mean 'none')."""
    removable = ("p", "li", "ul", "ol", "dl", "dt", "dd", "table", "tr", "span", "div",
                 "b", "strong", "i", "em", "u", "s", "small", "sub", "sup", "q", "blockquote",
                 "caption")
    changed = True
    while changed:
        changed = False
        for el in list(soup.find_all(removable)):
            if not el.get_text(strip=True) and el.find(["br", "hr", "table"]) is None:
                el.decompose()
                changed = True
        # tables whose rows are all empty
        for tbl in list(soup.find_all("table")):
            if not tbl.get_text(strip=True):
                tbl.decompose()
                changed = True
        # <br> with nothing before it (remnants of empty styled spans)
        for br in list(soup.find_all("br")):
            before = "".join(
                str(s) for s in br.previous_siblings if isinstance(s, NavigableString)
            ) + "".join(
                s.get_text() for s in br.previous_siblings if isinstance(s, Tag)
            )
            if not before.strip() and br.parent is not None and br.parent.name != "pre":
                br.decompose()
                changed = True


def pass_normalize_whitespace(soup):
    """Collapse whitespace and re-insert spaces lost at inline-element boundaries."""
    def in_pre(node):
        return node.parent is not None and node.parent.name == "pre"

    # 1) collapse whitespace inside each text node
    for text in list(soup.find_all(string=True)):
        if type(text) is not NavigableString or in_pre(text):
            continue
        collapsed = re.sub(r"\s+", " ", str(text))
        if collapsed != str(text):
            text.replace_with(NavigableString(collapsed))

    # 2) merge adjacent text nodes left over from unwrapped inline tags. Where the
    #    source relied on tag boundaries for word separation ("26.20<div>Experiment</div>"),
    #    insert a space so words don't run together; then collapse whitespace runs.
    merged = True
    while merged:
        merged = False
        for text in list(soup.find_all(string=True)):
            if type(text) is not NavigableString:
                continue
            nxt = text.next_sibling
            if type(nxt) is not NavigableString:
                continue
            a, b = str(text), str(nxt)
            joiner = ""
            if not in_pre(text) and a and b and a[-1].isalnum() and b[0].isalnum():
                joiner = " "
            combo = a + joiner + b
            if not in_pre(text):
                combo = re.sub(r" {2,}", " ", combo)
            text.replace_with(NavigableString(combo))
            nxt.extract()
            merged = True

    # 3) final sweep: collapse leftover double spaces outside <pre>
    for text in list(soup.find_all(string=True)):
        if type(text) is not NavigableString or in_pre(text):
            continue
        if "  " in str(text):
            text.replace_with(NavigableString(re.sub(r" {2,}", " ", str(text))))


# ---------------------------------------------------------------- main

def _extract_title_from_outside_root(soup, root) -> str:
    """Extract any h1 title that was created outside the mw-parser-output root.

    Fandom wikis have the page header title outside mw-parser-output, so we need
    to find it and prepend it to the output.

    However, if an h1 was already created INSIDE the root (from an infobox),
    we should not also extract the page header title to avoid duplication.
    """
    # First, check if there's already an h1 inside the root (from infobox)
    has_h1_inside = False
    if root.name != "[document]" and root.parent is not None:
        for h1 in root.find_all("h1"):
            if h1.get_text(strip=True):
                has_h1_inside = True
                break

    # If we already have an h1 inside root, don't extract another one
    if has_h1_inside:
        return ""

    # Look for h1 elements that are not inside root
    title_html = ""
    for h1 in soup.find_all("h1"):
        # Check if this h1 is inside root
        if root.name != "[document]" and root.parent is not None:
            # Check if h1 is a descendant of root
            is_inside = False
            parent = h1.parent
            while parent:
                if parent is root:
                    is_inside = True
                    break
                parent = parent.parent
            if is_inside:
                continue

        # This h1 is outside root, extract its content
        if h1.get_text(strip=True):
            title_html = f"<h1>{h1.get_text(strip=True)}</h1>"
            h1.decompose()  # Remove from soup to avoid duplication
            break  # Only take the first one

    return title_html


def _find_content_root(soup) -> Tag:
    """Find the best content root element.

    Tries multiple selectors to find the main content container:
    1. mw-parser-output (standard MediaWiki)
    2. mw-content-text (some Wikipedia/Minecraft Wiki pages)
    3. mw-body-content (some pages)
    4. div#content (fallback)
    5. body (last resort)
    """
    # Standard MediaWiki content
    root = soup.find("div", class_="mw-parser-output")
    if root and len(root.get_text(strip=True)) > 50:  # Has substantial content
        return root

    # Alternative content containers (for pages with unusual structure)
    for selector in ["div#mw-content-text", "div.mw-body-content", "div#content"]:
        root = soup.select_one(selector)
        if root and len(root.get_text(strip=True)) > 50:
            return root

    # Last resort: the whole body
    body = soup.find("body")
    if body:
        return body

    return soup


def parse_html(raw_html: str) -> str:
    soup = BeautifulSoup(raw_html, "html.parser")
    root = _find_content_root(soup)

    pass_drop_dead_tags(soup)
    pass_remove_sections(root)
    pass_media(soup)
    pass_unwrap_links(soup)
    pass_promote_infobox_title(soup)
    pass_unwrap_noise(soup, protect=(root,) if root.name != "[document]" else ())
    pass_strip_attributes(soup)
    pass_prune_empty(soup)
    pass_normalize_whitespace(soup)

    # Extract any title that was created outside the root (Fandom page headers)
    title_html = _extract_title_from_outside_root(soup, root)

    if root.name == "[document]" or root.parent is None:
        html = "".join(str(c) for c in soup.contents)
    else:
        html = "".join(str(c) for c in root.contents)

    # Prepend the title if it was outside root
    if title_html:
        html = title_html + "\n" + html
    else:
        # Check if h1 is already at the beginning of the content
        # If not, move it to the beginning (handles infobox titles positioned after intro text)
        html_stripped = html.strip()
        if not html_stripped.startswith("<h1>"):
            # Find the h1 in the html and move it to the front
            h1_match = re.search(r"<h1>[^<]*</h1>", html_stripped)
            if h1_match:
                h1_tag = h1_match.group(0)
                # Remove the h1 from its current position
                html_stripped = html_stripped[:h1_match.start()] + html_stripped[h1_match.end():]
                # Prepend it
                html = h1_tag + "\n" + html_stripped
                html = html.strip()

    # light pretty-printing: one block element per line
    block = ("p", "table", "tr", "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6",
             "blockquote", "pre", "dl", "dt", "dd", "hr", "tbody", "thead", "tfoot")
    html = re.sub(r"(</?(?:%s)\b[^>]*>)" % "|".join(block), r"\n\1", html)
    html = re.sub(r"[ \t]+\n", "\n", html)
    html = re.sub(r"\n{3,}", "\n\n", html)
    html = "\n".join(line.strip() for line in html.splitlines() if line.strip())

    return html
