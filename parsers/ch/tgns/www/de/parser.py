import sys
sys.path.extend(['/home/lena/Documents/python/distilled-web'])
import certifi
from classes import *
from writer import save
from curl_cffi import requests
from bs4 import BeautifulSoup
from bs4.element import Tag, NavigableString
import html


def parse(url: str):
    resp = requests.get(url, verify=certifi.where())  # type: ignore
    resp.raise_for_status()
    markdown = html_to_markdown(resp.text)
    save(TextEntry(markdown, url))


def html_to_markdown(source: str) -> str:
    soup = BeautifulSoup(source, "html.parser")
    article = soup.find("article") or soup

    # Publication date
    time = article.select_one(
        "header.entry-header time.entry-date.published"
    )

    # Title
    title = article.select_one("h1.entry-title")

    # Main content only
    content = article.select_one(".entry-content")

    parts = []

    if time:
        parts.append(f"*{time.get_text(' ', strip=True)}*")

    if title:
        parts.append(f"# {title.get_text(' ', strip=True)}")

    if content:
        for child in content.children:
            if not isinstance(child, Tag):
                continue

            # Only retain textual paragraphs from the article.
            if child.name == "p":
                text = _inline_to_markdown(child).strip()
                if text:
                    parts.append(text)

            # Add more content types here if needed, e.g. lists/headings.
            elif child.name in {"h2", "h3", "h4", "h5", "h6"}:
                level = int(child.name[1])
                text = _inline_to_markdown(child).strip()
                if text:
                    parts.append(f"{'#' * level} {text}")

            elif child.name in {"ul", "ol"}:
                lines = []
                for i, li in enumerate(child.find_all("li", recursive=False), 1):
                    text = _inline_to_markdown(li).strip()
                    prefix = f"{i}. " if child.name == "ol" else "- "
                    lines.append(prefix + text)
                if lines:
                    parts.append("\n".join(lines))

    return "\n\n".join(parts).strip()


def _inline_to_markdown(node: Tag) -> str:
    """Convert inline HTML while deliberately dropping link destinations."""
    result = []

    for child in node.children:
        if isinstance(child, NavigableString):
            result.append(str(child))
            continue

        if not isinstance(child, Tag):
            continue

        text = _inline_to_markdown(child)

        if child.name in {"strong", "b"}:
            if text.strip():
                result.append(f"**{text}**")

        elif child.name in {"em", "i"}:
            if text.strip():
                result.append(f"*{text}*")

        elif child.name == "br":
            result.append("\n")

        elif child.name == "a":
            # Expected output keeps anchor text but removes the URL.
            result.append(text)

        elif child.name in {"img", "svg", "object"}:
            pass

        else:
            result.append(text)

    return html.unescape("".join(result))
