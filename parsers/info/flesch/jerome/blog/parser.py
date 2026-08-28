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
        self.article = self.soup.select_one('article.post-single') or self.soup.select_one('main.main')
        if not self.article:
            raise ValueError('No main content found')

    def convert(self) -> str:
        # Remove the table of contents entirely (details.toc / nav#TableOfContents)
        for tbc in self.article.select('details.toc, nav#TableOfContents'):
            tbc.decompose()

        parts = []

        title = self.article.select_one('.post-title')
        if title:
            parts.append('# ' + title.get_text(strip=True))

        date = self.article.select_one('.post-meta time, .post-meta span[title]')
        if date:
            date_text = date.get('title') or date.get_text(strip=True)
            parts.append('*' + date_text.strip() + '*')

        content = self.article.select_one('.post-content, .md-content')
        if content:
            self._strip_heading_anchors(content)
            parts.append(self._convert_content(content))
        else:
            parts.append('')

        markdown = '\n\n'.join(p for p in parts if p.strip())
        return self._cleanup(markdown)

    def _strip_heading_anchors(self, content: Tag) -> None:
        # Remove the trailing '#' anchor links Hugo adds inside headings.
        for heading in content.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            for anchor in heading.select('a.anchor'):
                anchor.decompose()

    def _convert_content(self, content: Tag) -> str:
        converter = MarkdownConverter(
            heading_style='ATX',
            bullets='-',
            strip=['script', 'style'],
        )
        markdown = converter.convert_soup(content)
        if self.page_url:
            markdown = self._absolutize_links(markdown)
        return markdown

    def _absolutize_links(self, markdown: str) -> str:
        # Resolve site-relative link/image targets against the page URL.
        base = self.page_url

        def _fix(match: re.Match) -> str:
            target = match.group(2)
            if target.startswith(('#', 'http://', 'https://', 'mailto:', 'data:')):
                return match.group(0)
            return match.group(1) + urljoin(base, target) + match.group(3)

        markdown = re.sub(r'(\]\()(\s*[^)\s]+[^)]*)(\s*\))', _fix, markdown)
        markdown = re.sub(r'(<img[^>]+src=")([^"]+)(")', _fix, markdown)
        return markdown

    def _cleanup(self, markdown: str) -> str:
        # Collapse 3+ newlines to 2 and drop stray anchor-only lines.
        markdown = re.sub(r'\n{3,}', '\n\n', markdown)
        markdown = re.sub(r'^#\s*$', '', markdown, flags=re.MULTILINE)
        return markdown.strip() + '\n'
