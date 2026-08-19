#!/usr/bin/env python3
"""
fedlex_to_markdown.py
=====================

Convert Swiss Fedlex / Akoma Ntoso (LegalDocML 3.0) XML acts into

  1. a full Markdown rendering of the document, and
  2. a JSON mapping of article id -> Markdown, e.g.

     {
       "Art. 1": "#### Art. 1  Obligation de respecter les droits de l'homme\n\n...",
       "Art. 2": "...."
     }

Only the Python standard library is required.

This module is a library, not a command-line application. Import it and call
the public API:

    from fedlex_to_markdown import FedlexConverter, Options, convert_path, \
        articles_payload

    opt = Options()                       # or Options(sup="caret", tables="gfm")
    result = convert_path("195.11.fr.xml", opt)

    result["meta"]                        # document metadata
    result["markdown"]                    # the full document as Markdown
    result["articles"]                    # dict[article_id -> ArticleRecord]

    # Shape the per-article map the way you need it:
    flat_md = articles_payload(result, flat=True,  rich=False)  # {"Art. 1": "md"}
    rich    = articles_payload(result, flat=False, rich=True)  # {"meta": ...,
                                                                 #  "articles": {key: {...}}}

ArticleRecord fields: article_id, eId, heading, markdown, path.

Handled AKN constructs: preface / preamble / body, hierarchy (title, part,
chapter, section, level, subdivision), article, paragraph, blockList with
nested items, tables (GFM or HTML fallback for colspan/rowspan), inline
markup (b, i, u, sup, sub, br, ref, span, inline, placeholder), authorial
notes converted to Markdown footnotes, annexes / components (doc name="annex",
"scope", ...) and signature / conclusions blocks.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

AKN = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
FEDLEX = "http://fedlex.admin.ch/"
XML = "http://www.w3.org/XML/1998/namespace"

A = f"{{{AKN}}}"

# Whitespace to collapse: deliberately excludes U+00A0 (non breaking space),
# which is meaningful in legal typography.
_WS = re.compile(r"[ \t\r\n\f\v]+")
# Characters that would otherwise be interpreted as Markdown syntax.
_ESCAPE = re.compile(r"([\\*_`\[\]])")

LINEBREAK = "\uE000"  # private-use sentinel for <br/>, resolved per context


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def localname(el: ET.Element) -> str:
    """Tag name without its namespace."""
    if not isinstance(el.tag, str):  # comments / PIs
        return ""
    return el.tag.rsplit("}", 1)[-1]


def norm(text: str | None) -> str:
    return _WS.sub(" ", text) if text else ""


def squeeze(text: str) -> str:
    """Collapse whitespace and trim - used for keys and headings."""
    return _WS.sub(" ", text or "").strip()


def wrap_emphasis(text: str, marker: str) -> str:
    """`**bold**` without swallowing the surrounding spaces (which breaks it)."""
    stripped = text.strip()
    if not stripped:
        return text
    lead = text[: len(text) - len(text.lstrip())]
    trail = text[len(text.rstrip()):]
    return f"{lead}{marker}{stripped}{marker}{trail}"


def wrap_link(text: str, href: str) -> str:
    """`[label](url)` keeping the surrounding spaces outside the link."""
    stripped = text.strip()
    if not stripped:
        return text
    lead = text[: len(text) - len(text.lstrip())]
    trail = text[len(text.rstrip()):]
    return f"{lead}[{stripped}]({href}){trail}"


def strip_bold(text: str) -> str:
    """Headings are already emphasised - drop redundant ** markers."""
    return text.replace("**", "")


def indent_block(text: str, prefix: str) -> str:
    return "\n".join(prefix + line if line else line for line in text.split("\n"))


# --------------------------------------------------------------------------- #
# options
# --------------------------------------------------------------------------- #
@dataclass
class Options:
    sup: str = "html"          # html | caret | plain -> <sup>1</sup> | ^1^ | 1
    tables: str = "auto"       # auto | html | gfm
    footnotes: bool = True     # authorialNote -> [^n] + definitions
    escape: bool = True        # escape Markdown metacharacters in text
    front_matter: bool = True  # YAML front matter in the .md file
    heading_offset: int = 0    # shift all heading levels


@dataclass
class ArticleRecord:
    article_id: str
    eId: str
    heading: str
    markdown: str
    path: str  # e.g. "Titre 1 > Chapitre 2" or "Annexe"


# --------------------------------------------------------------------------- #
# converter
# --------------------------------------------------------------------------- #
class FedlexConverter:
    """Renders one Akoma Ntoso act to Markdown, collecting articles on the way."""

    HIERARCHY = {
        "book", "tome", "part", "title", "chapter", "subchapter", "section",
        "subsection", "division", "subdivision", "level", "clause", "rule",
        "transitional", "article",
    }
    # Containers whose children are simply rendered in place.
    TRANSPARENT = {
        "act", "bill", "doc", "mainBody", "body", "components", "component",
        "content", "container", "wrapUp", "intro", "preamble", "formula",
        "signature", "conclusions", "coverPage", "attachments", "attachment",
        "quotedStructure", "embeddedStructure", "tblock", "toc",
    }
    SKIP = {"meta", "identification", "references", "notes", "proprietary",
            "analysis", "num", "heading", "subheading", "authorialNote"}

    def __init__(self, options: Options | None = None):
        self.opt = options or Options()
        self.reset()

    # -- state ------------------------------------------------------------- #
    def reset(self) -> None:
        self.footnotes: list[str] = []            # rendered definitions
        self.articles: dict[str, ArticleRecord] = {}
        self._path: list[str] = []                # hierarchy breadcrumb

    # -- public API --------------------------------------------------------- #
    def convert_file(self, path: str | Path) -> dict:
        tree = ET.parse(str(path))
        return self.convert(tree.getroot(), source=Path(path).name)

    def convert(self, root: ET.Element, source: str = "") -> dict:
        self.reset()
        meta = self.extract_meta(root)
        meta["source_file"] = source

        blocks: list[str] = []
        title = meta.get("title") or meta.get("sr_number") or source
        blocks.append(self.h(1) + " " + self.escape_text(title))

        for child in root:
            self.render(child, blocks, depth=1)

        body_md = self.join(blocks)
        doc_md = body_md
        if self.opt.footnotes and self.footnotes:
            doc_md += "\n\n---\n\n" + "\n".join(self.footnotes)
        if self.opt.front_matter:
            doc_md = self.front_matter(meta) + "\n" + doc_md
        return {
            "meta": meta,
            "markdown": doc_md.strip() + "\n",
            "articles": self.articles,
        }

    # -- metadata ----------------------------------------------------------- #
    def extract_meta(self, root: ET.Element) -> dict:
        meta: dict = {}
        ident = root.find(f".//{A}meta/{A}identification")
        if ident is None:
            return meta
        work = ident.find(f"{A}FRBRWork")
        expr = ident.find(f"{A}FRBRExpression")

        def val(parent, tag, attr="value"):
            if parent is None:
                return None
            el = parent.find(f"{A}{tag}")
            return el.get(attr) if el is not None else None

        meta["sr_number"] = val(work, "FRBRnumber")
        meta["country"] = val(work, "FRBRcountry")
        meta["eli"] = val(work, "FRBRuri")
        lang = None
        if expr is not None:
            le = expr.find(f"{A}FRBRlanguage")
            lang = le.get("language") if le is not None else None
            meta["eli_expression"] = val(expr, "FRBRuri")
        meta["language"] = lang

        titles: dict[str, str] = {}
        short: dict[str, str] = {}
        if work is not None:
            for name in work.findall(f"{A}FRBRname"):
                lg = name.get(f"{{{XML}}}lang") or ""
                titles[lg] = re.sub(r"<[^>]+>", "", name.get("value") or "")
                if name.get("shortForm"):
                    short[lg] = name.get("shortForm")
            dates = {}
            for d in work.findall(f"{A}FRBRdate"):
                key = (d.get("name") or "date").split(":")[-1]
                dates[key] = d.get("date")
            meta["dates"] = dates
        meta["titles"] = titles
        meta["title"] = titles.get(lang or "") or next(iter(titles.values()), "")
        meta["short_title"] = short.get(lang or "") or next(iter(short.values()), "")
        return meta

    def front_matter(self, meta: dict) -> str:
        def esc(v):
            return '"' + str(v).replace('\\', '\\\\').replace('"', '\\"') + '"'

        lines = ["---"]
        for key in ("source_file", "sr_number", "language", "title",
                    "short_title", "eli", "eli_expression"):
            if meta.get(key):
                lines.append(f"{key}: {esc(meta[key])}")
        for key, value in (meta.get("dates") or {}).items():
            lines.append(f"date_{re.sub(r'(?<!^)(?=[A-Z])', '_', key).lower()}: {value}")
        lines.append("---")
        return "\n".join(lines) + "\n"

    # -- small utilities ---------------------------------------------------- #
    def h(self, level: int) -> str:
        return "#" * max(1, min(6, level + self.opt.heading_offset))

    @staticmethod
    def join(blocks: Iterable[str]) -> str:
        return "\n\n".join(b for b in (x.strip("\n") for x in blocks) if b.strip())

    def escape_text(self, text: str) -> str:
        return _ESCAPE.sub(r"\\\1", text) if self.opt.escape else text

    @staticmethod
    def resolve_breaks(text: str, mode: str) -> str:
        """Turn the <br/> sentinel into something valid for the context."""
        if mode == "block":
            return text.replace(LINEBREAK, "  \n")
        if mode == "cell":
            return text.replace(LINEBREAK, "<br>")
        return text.replace(LINEBREAK, " ")  # headings, keys, ...

    # -- inline rendering --------------------------------------------------- #
    def inline(self, el: ET.Element, *, notes: bool = True) -> str:
        """Render the inline content of `el` (its text + children + tails)."""
        out: list[str] = [self.escape_text(norm(el.text))]
        for child in el:
            out.append(self.inline_child(child, notes=notes))
            out.append(self.escape_text(norm(child.tail)))
        return "".join(out)

    def inline_child(self, el: ET.Element, *, notes: bool = True) -> str:
        tag = localname(el)

        if tag == "authorialNote":
            return self.footnote(el) if (notes and self.opt.footnotes) else ""
        if tag == "br":
            return LINEBREAK
        if tag in ("b", "strong"):
            return wrap_emphasis(self.inline(el, notes=notes), "**")
        if tag in ("i", "em"):
            return wrap_emphasis(self.inline(el, notes=notes), "*")
        if tag in ("sup", "sub"):
            inner = self.inline(el, notes=notes)
            if self.opt.sup == "plain":
                return inner
            if self.opt.sup == "caret":
                return f"^{inner.strip()}^" if tag == "sup" else f"~{inner.strip()}~"
            return f"<{tag}>{inner.strip()}</{tag}>"
        if tag in ("ref", "a", "eref"):
            href = el.get("href") or el.get("xlink:href") or ""
            text = self.inline(el, notes=notes)
            return wrap_link(text, href) if href else text
        if tag == "img":
            src = el.get("src") or ""
            return f"![{el.get('alt', '')}]({src})"
        if tag in ("del",):
            return wrap_emphasis(self.inline(el, notes=notes), "~~")
        # inline, span, placeholder, docNumber, docTitle, date, organization,
        # person, term, def, remark, ... -> transparent
        return self.inline(el, notes=notes)

    def text_of(self, el: ET.Element | None) -> str:
        """Plain, whitespace-squeezed text (footnotes stripped) - used for keys."""
        return squeeze(self._raw_text(el))

    def _raw_text(self, el: ET.Element | None) -> str:
        if el is None:
            return ""
        parts: list[str] = [el.text or ""]
        for child in el:
            if localname(child) != "authorialNote":
                parts.append(self._raw_text(child))
            parts.append(child.tail or "")
        return "".join(parts)

    def footnote(self, el: ET.Element) -> str:
        index = len(self.footnotes) + 1
        self.footnotes.append("")  # reserve the slot (nested notes stay ordered)
        chunks: list[str] = []
        if el.text and el.text.strip():
            chunks.append(self.escape_text(norm(el.text)).strip())
        for child in el:
            if localname(child) in ("p", "block", "content"):
                chunks.append(self.inline(child).strip())
            else:
                chunks.append(self.inline_child(child).strip())
            if child.tail and child.tail.strip():
                chunks.append(self.escape_text(norm(child.tail)).strip())
        body = self.resolve_breaks(" ".join(c for c in chunks if c), "inline")
        self.footnotes[index - 1] = f"[^{index}]: {squeeze(body)}"
        return f"[^{index}]"

    def para(self, el: ET.Element) -> str:
        return self.resolve_breaks(self.inline(el), "block").strip()

    def heading_text(self, el: ET.Element | None, *, bold: bool = False) -> str:
        """Inline text suitable for a heading line: no line breaks, no bold."""
        if el is None:
            return ""
        text = self.resolve_breaks(self.inline(el), "inline").strip()
        text = re.sub(r"[ \t]+(\[\^\d+\])", r"\1", text)
        return text if bold else squeeze(strip_bold(text))

    # -- block rendering ---------------------------------------------------- #
    def render(self, el: ET.Element, out: list[str], depth: int) -> None:
        tag = localname(el)

        if tag in self.SKIP or not tag:
            return
        if tag == "article":
            out.extend(self.render_article(el, depth))
            return
        if tag in self.HIERARCHY:
            out.extend(self.render_hierarchy(el, depth))
            return
        if tag == "preface":
            out.extend(self.render_preface(el, depth))
            return
        if tag in ("paragraph", "subparagraph", "point", "indent", "alinea"):
            out.extend(self.render_paragraph(el))
            return
        if tag in ("blockList", "list", "ul", "ol"):
            out.extend(self.render_list(el))
            return
        if tag == "table":
            out.append(self.render_table(el))
            return
        if tag == "p":
            text = self.para(el)
            if text:
                out.append(text)
            return
        if tag == "block":
            text = self.heading_text(el)
            if not text:
                return
            if (el.get("name") or "").lower() in ("heading", "title", "docheading"):
                out.append(f"{self.h(depth + 1)} {text}")
            else:
                out.append(self.resolve_breaks(self.inline(el), "block").strip())
            return
        if tag in ("foreign", "hcontainer", "componentRef"):
            return
        if tag in self.TRANSPARENT:
            # An annex/scope document gets a heading of its own.
            if tag == "doc":
                name = (el.get("name") or "").strip()
                header = el.find(f".//{A}container[@name='headerOfAnnex']")
                label = self.heading_text(header) if header is not None else ""
                if label:
                    out.append(f"{self.h(depth + 1)} {label}")
                elif name:
                    out.append(f"{self.h(depth + 1)} {name.capitalize()}")
                depth += 1
                self._path.append(squeeze(re.sub(r"\[\^\d+\]", "", label)) or name)
                for child in el:
                    if el.find(f".//{A}container[@name='headerOfAnnex']") is child:
                        continue
                    self.render(child, out, depth)
                self._path.pop()
                return
            if el.get("name") == "headerOfAnnex":
                text = self.heading_text(el)
                if text:
                    out.append(f"{self.h(depth + 1)} {text}")
                return
            for child in el:
                self.render(child, out, depth)
            return

        # Unknown element: render its children, then fall back to inline text.
        if len(el):
            for child in el:
                self.render(child, out, depth)
        else:
            text = self.para(el)
            if text:
                out.append(text)

    def render_preface(self, el: ET.Element, depth: int) -> list[str]:
        blocks: list[str] = []
        for child in el:
            text = self.heading_text(child)
            if not text:
                continue
            if child.find(f".//{A}docTitle") is not None or localname(child) == "docTitle":
                blocks.append(f"{self.h(depth + 1)} {text}")
            else:
                blocks.append(f"*{text}*" if child.find(f".//{A}docNumber") is None
                              else f"**{text}**")
        return blocks

    def render_hierarchy(self, el: ET.Element, depth: int) -> list[str]:
        num = self.heading_text(el.find(f"{A}num"))
        head = self.heading_text(el.find(f"{A}heading"))
        sub = self.heading_text(el.find(f"{A}subheading"))

        label = " ".join(x for x in (num, head) if x).strip()
        blocks: list[str] = []
        if label:
            blocks.append(f"{self.h(depth + 1)} {label}")
        if sub:
            blocks.append(f"*{sub}*")

        crumb = squeeze(re.sub(r"\[\^\d+\]", "", label))
        self._path.append(crumb)
        try:
            for child in el:
                if localname(child) in ("num", "heading", "subheading"):
                    continue
                self.render(child, blocks, depth + 1)
        finally:
            self._path.pop()
        return blocks

    def render_article(self, el: ET.Element, depth: int) -> list[str]:
        num_el = el.find(f"{A}num")
        head_el = el.find(f"{A}heading")
        sub_el = el.find(f"{A}subheading")

        article_id = self.article_id(num_el, el)
        first_note = len(self.footnotes)  # notes are numbered document-wide
        num_md = self.heading_text(num_el) or article_id
        head_md = self.heading_text(head_el)
        sub_md = self.heading_text(sub_el)

        blocks: list[str] = []
        title_line = f"{self.h(depth + 1)} {num_md}"
        if head_md:
            title_line += f"  {head_md}"
        blocks.append(title_line)
        if sub_md:
            blocks.append(f"*{sub_md}*")

        for child in el:
            if localname(child) in ("num", "heading", "subheading"):
                continue
            self.render(child, blocks, depth + 1)

        markdown = self.join(blocks)
        if self.opt.footnotes and len(self.footnotes) > first_note:
            defs = [d for d in self.footnotes[first_note:] if d]
            if defs:
                markdown += "\n\n" + "\n".join(defs)

        key = article_id
        if key in self.articles:  # duplicates (e.g. annex articles) stay addressable
            key = f"{article_id} [{el.get('eId') or len(self.articles)}]"
        self.articles[key] = ArticleRecord(
            article_id=article_id,
            eId=el.get("eId") or "",
            heading=squeeze(re.sub(r"\[\^\d+\]", "", head_md)),
            markdown=markdown.strip() + "\n",
            path=" > ".join(p for p in self._path if p),
        )
        return blocks

    def article_id(self, num_el: ET.Element | None, article: ET.Element) -> str:
        """'Art. 1' - footnote text stripped, whitespace squeezed."""
        raw = self.text_of(num_el)
        raw = raw.strip().rstrip(".,;:")
        if raw:
            return squeeze(raw)
        eid = article.get("eId") or ""
        m = re.match(r"art_(\w+)", eid)
        return f"Art. {m.group(1).replace('_', '')}" if m else eid or "Art. ?"

    def render_paragraph(self, el: ET.Element) -> list[str]:
        num_el = el.find(f"{A}num")
        blocks: list[str] = []
        for child in el:
            if localname(child) in ("num", "heading", "subheading"):
                continue
            self.render(child, blocks, depth=6)

        if num_el is not None:
            num = self.heading_text(num_el).strip()
            if num:
                marker = (num if self.opt.sup == "plain"
                          else f"^{num}^" if self.opt.sup == "caret"
                          else f"<sup>{num}</sup>")
                if blocks and not blocks[0].lstrip().startswith(("#", "-", "|", "<table")):
                    blocks[0] = f"{marker} {blocks[0].lstrip()}"
                else:
                    blocks.insert(0, marker)
        return blocks

    def render_list(self, el: ET.Element, level: int = 0) -> list[str]:
        """Render a blockList / list as Markdown bullets (labels kept verbatim)."""
        intro, items, wrap = self.list_parts(el, level)
        ind = "  " * level
        blocks: list[str] = []
        if intro:
            blocks.append(indent_block(intro, ind) if level else intro)
        if items:
            blocks.append(items)
        if wrap:
            blocks.append(indent_block(wrap, ind) if level else wrap)
        return blocks

    def list_parts(self, el: ET.Element, level: int) -> tuple[str, str, str]:
        """(introduction, bullet block, wrap-up) - bullets already indented."""
        ind = "  " * level
        intro_el = el.find(f"{A}listIntroduction")
        intro = self.para(intro_el) if intro_el is not None else ""
        wrap_el = el.find(f"{A}listWrapUp")
        wrap = self.para(wrap_el) if wrap_el is not None else ""

        items: list[str] = []
        for child in el:
            tag = localname(child)
            if tag in ("listIntroduction", "listWrapUp", "num", "heading"):
                continue
            if tag in ("item", "point", "indent", "li"):
                items.append(self.render_item(child, level))
            else:
                sub: list[str] = []
                self.render(child, sub, depth=6)
                items.extend(indent_block(b, ind) if level else b for b in sub if b.strip())
        return intro.strip(), "\n".join(items), wrap.strip()

    def render_item(self, el: ET.Element, level: int) -> str:
        """One bullet: '- a. text', with nested content indented underneath."""
        label = self.heading_text(el.find(f"{A}num"))
        ind = "  " * level

        parts: list[tuple[str, bool]] = []  # (text, already_indented)
        for child in el:
            tag = localname(child)
            if tag in ("num", "heading"):
                continue
            if tag in ("blockList", "list", "ul", "ol"):
                intro, items, wrap = self.list_parts(child, level + 1)
                if intro:
                    parts.append((intro, False))
                if items:
                    parts.append((items, True))
                if wrap:
                    parts.append((wrap, False))
            else:
                sub: list[str] = []
                self.render(child, sub, depth=6)
                parts.extend((b, False) for b in sub if b.strip())

        first_text = ""
        rest = list(parts)
        if parts and not parts[0][1]:
            first_text = parts[0][0].strip()
            rest = parts[1:]

        lines = [(f"{ind}- " + " ".join(x for x in (label, first_text) if x)).rstrip()]
        for text, done in rest:
            lines.append("")
            lines.append(text if done else indent_block(text.strip(), ind + "  "))
        return "\n".join(lines)

    # -- tables ------------------------------------------------------------- #
    def render_table(self, el: ET.Element) -> str:
        rows: list[list[dict]] = []
        for tr in el.iter(f"{A}tr"):
            row: list[dict] = []
            for cell in tr:
                tag = localname(cell)
                if tag not in ("td", "th"):
                    continue
                row.append({
                    "header": tag == "th",
                    "colspan": int(cell.get("colspan") or 1),
                    "rowspan": int(cell.get("rowspan") or 1),
                    "text": self.cell_text(cell),
                })
            rows.append(row)

        rows = [r for r in rows if r]
        while rows and not any(c["text"].strip() for c in rows[0]):
            rows.pop(0)
        while rows and not any(c["text"].strip() for c in rows[-1]):
            rows.pop()
        if not rows:
            return ""

        spanned = any(c["colspan"] > 1 or c["rowspan"] > 1 for r in rows for c in r)
        if self.opt.tables == "html" or (self.opt.tables == "auto" and spanned):
            return self.render_table_html(rows)
        return self.render_table_gfm(rows)

    def cell_text(self, cell: ET.Element) -> str:
        parts: list[str] = []
        if cell.text and cell.text.strip():
            parts.append(self.escape_text(norm(cell.text)).strip())
        for child in cell:
            tag = localname(child)
            if tag in ("p", "block"):
                parts.append(self.inline(child).strip())
            elif tag in ("blockList", "list"):
                parts.append(" ".join(self.render_list(child)).replace("\n", " "))
            else:
                parts.append(self.inline_child(child).strip())
            if child.tail and child.tail.strip():
                parts.append(self.escape_text(norm(child.tail)).strip())
        text = self.resolve_breaks(" ".join(p for p in parts if p), "cell")
        return squeeze(text).replace("|", "\\|")

    def render_table_gfm(self, rows: list[list[dict]]) -> str:
        width = max(sum(c["colspan"] for c in r) for r in rows)

        def line(cells: list[str]) -> str:
            cells = cells + [""] * (width - len(cells))
            return "| " + " | ".join(cells[:width]) + " |"

        if all(c["header"] for c in rows[0]):
            header, body = [c["text"] for c in rows[0]], rows[1:]
        else:
            header, body = [""] * width, rows
        out = [line(header), "|" + "|".join([" --- "] * width) + "|"]
        out.extend(line([c["text"] for c in r]) for r in body)
        return "\n".join(out)

    def render_table_html(self, rows: list[list[dict]]) -> str:
        out = ["<table>"]
        for r in rows:
            out.append("  <tr>")
            for c in r:
                tag = "th" if c["header"] else "td"
                attrs = ""
                if c["colspan"] > 1:
                    attrs += f' colspan="{c["colspan"]}"'
                if c["rowspan"] > 1:
                    attrs += f' rowspan="{c["rowspan"]}"'
                text = c["text"].replace("\\|", "|")
                out.append(f"    <{tag}{attrs}>{text}</{tag}>")
            out.append("  </tr>")
        out.append("</table>")
        return "\n".join(out)


# --------------------------------------------------------------------------- #
# public helpers
# --------------------------------------------------------------------------- #
def convert_path(path: str | Path, opt: Options | None = None) -> dict:
    """Convert a single Fedlex XML file and return ``{meta, markdown, articles}``."""
    return FedlexConverter(opt).convert_file(path)


def articles_payload(result: dict, flat: bool = False, rich: bool = False) -> dict:
    """Reshape a converter result's article map.

    ``flat`` drops the ``{"meta": ...}`` wrapper.
    ``rich`` makes each value an object (markdown + eId + heading + path)
    instead of a plain Markdown string.
    """
    articles = result["articles"]
    if rich:
        flat_map = {
            key: {
                "article_id": rec.article_id,
                "eId": rec.eId,
                "heading": rec.heading,
                "path": rec.path,
                "markdown": rec.markdown,
            }
            for key, rec in articles.items()
        }
    else:
        flat_map = {key: rec.markdown for key, rec in articles.items()}
    if flat:
        return flat_map
    return {"meta": result["meta"], "articles": flat_map}


__all__ = [
    "Options",
    "ArticleRecord",
    "FedlexConverter",
    "convert_path",
    "articles_payload",
]
