import sys
sys.path.extend(['/home/lena/Documents/python/distilled-web'])
import certifi
from classes import *
from writer import save
from curl_cffi import requests
from bs4 import BeautifulSoup, Tag
from urllib.parse import urljoin
import re
from markdownify import MarkdownConverter


def parse(url: str):
    resp = requests.get(url, verify=certifi.where())  # type: ignore
    resp.raise_for_status()
    converter = HtmlToMarkdownConverter(resp.text, url)
    markdown = converter.convert()
    print(markdown)
    save(TextEntry(markdown, url))


class HtmlToMarkdownConverter:
    def __init__(self, raw_html: str, page_url: str = ''):
        self.soup = BeautifulSoup(raw_html, 'html.parser')
        self.page_url = page_url
        # Only individual posts are supported (not the /dreams index or tag pages).
        self.article = self.soup.select_one('article.post')
        if not self.article:
            raise ValueError('No post found (only individual /dreams/<slug>/ pages are supported)')

    def convert(self) -> str:
        parts = []

        self._strip_prefixes()

        title = self.article.select_one('h1.post-title')
        if title:
            parts.append('# ' + title.get_text(strip=True))

        meta = self._convert_meta()
        if meta:
            parts.append(meta)

        tags = self._convert_tags()
        if tags:
            parts.append(tags)

        content = self.article.select_one('.post-content .prose') or self.article.select_one('.post-content')
        if content:
            self._strip_heading_anchors(content)
            parts.append(self._convert_content(content))

        markdown = '\n\n'.join(p for p in parts if p.strip())
        return self._cleanup(markdown)

    # ---------- Metadata ----------
    def _strip_prefixes(self) -> None:
        # Drop the decorative '>'/'by' label spans so the metadata text reads cleanly.
        for prefix in self.article.select('.post-date-prefix, .post-author-prefix'):
            prefix.decompose()

    def _convert_meta(self) -> str:
        bits = []
        date = self.article.select_one('time.post-date')
        if date:
            bits.append(date.get_text(strip=True))
        author = self.article.select_one('.post-author')
        if author:
            name = author.get_text(strip=True)
            if name:
                bits.append('by ' + name)
        updated = self.article.select_one('.post-updated')
        if updated:
            text = updated.get_text(strip=True)
            if text:
                bits.append(text)
        if not bits:
            return ''
        return '*' + ' — '.join(bits) + '*'

    def _convert_tags(self) -> str:
        names = [a.get_text(strip=True) for a in self.article.select('.post-tags a.post-tag-link')]
        names = [n for n in names if n]
        if not names:
            return ''
        return '**Tags:** ' + ', '.join(names)

    # ---------- Content ----------
    def _strip_heading_anchors(self, content: Tag) -> None:
        # Remove the trailing '#' anchor links the site injects into every heading.
        for heading in content.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            for anchor in heading.select('a.heading-anchor'):
                anchor.decompose()

    def _convert_content(self, content: Tag) -> str:
        converter = MarkdownConverter(
            heading_style='ATX',
            bullets='-',
            strip=['script', 'style'],
            code_language_callback=self._code_language,
        )
        markdown = converter.convert_soup(content)
        if self.page_url:
            markdown = self._absolutize_links(markdown)
        return markdown

    @staticmethod
    def _code_language(el: Tag) -> str:
        # Shiki renders code blocks as <pre data-language="...">.
        language = el.get('data-language', '')
        return language if isinstance(language, str) else ''

    def _absolutize_links(self, markdown: str) -> str:
        # Resolve site-relative link/image targets against the page URL.
        base = self.page_url

        def _fix(match: re.Match) -> str:
            target = match.group(2)
            if target.startswith(('#', 'http://', 'https://', 'mailto:', 'data:')):
                return match.group(0)
            return match.group(1) + urljoin(base, target) + match.group(3)

        markdown = re.sub(r'(]\()(\s*[^)\s]+[^)]*)(\s*\))', _fix, markdown)
        markdown = re.sub(r'(<img[^>]+src=")([^"]+)(")', _fix, markdown)
        return markdown

    # ---------- Cleanup ----------
    def _cleanup(self, markdown: str) -> str:
        # Collapse 3+ newlines to 2 and drop stray anchor-only lines.
        markdown = re.sub(r'\n{3,}', '\n\n', markdown)
        markdown = re.sub(r'^#\s*$', '', markdown, flags=re.MULTILINE)
        return markdown.strip() + '\n'
