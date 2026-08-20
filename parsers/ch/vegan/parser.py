import sys
sys.path.extend(['/home/lena/Documents/python/distilled-web'])
import certifi
from classes import *
from writer import save
from curl_cffi import requests
from bs4 import BeautifulSoup, Tag, NavigableString
import re


def parse(url: str):
    resp = requests.get(url, verify=certifi.where())  # type: ignore
    resp.raise_for_status()
    raw_html = resp.text
    converter = HtmlToMarkdownConverter(raw_html)
    markdown = converter.convert()
    print(markdown)
    save(TextEntry(markdown, url))


class HtmlToMarkdownConverter:
    def __init__(self, raw_html):
        self.soup = BeautifulSoup(raw_html, 'html.parser')
        self.main_content = self.soup.select_one('main#content')
        if not self.main_content:
            raise ValueError('No main content found')

    def convert(self):
        parts = []

        # Remove elements we want to ignore entirely
        for tbc in self.main_content.select('.table_of_contents'):
            tbc.decompose()

        # Breadcrumb
        breadcrumb = self.main_content.select_one('nav.breadcrumb')
        if breadcrumb:
            crumb_md = self._convert_breadcrumb(breadcrumb)
            if crumb_md:
                parts.append(crumb_md)

        # Process each section in order
        for section in self.main_content.find_all('section', recursive=True):
            section_md = self._convert_section(section)
            if section_md:
                parts.append(section_md)

        markdown = '\n\n'.join(p for p in parts if p.strip())
        return self._cleanup(markdown)

    # ---------- Breadcrumb ----------
    def _convert_breadcrumb(self, breadcrumb):
        names = []
        for li in breadcrumb.select('li'):
            name_el = li.select_one('[itemprop="name"]')
            if name_el:
                names.append(name_el.get_text(strip=True))
        if names:
            return '> ' + ' / '.join(names)
        return ''

    # ---------- Sections ----------
    def _convert_section(self, section):
        # Handle the sources list separately (special formatting)
        sources = section.select_one('.list_of_sources')
        cross_links = section.select_one('.section__cross_links')

        parts = []

        # Regular text blocks (headings, paragraphs)
        for text_div in section.select('.section__text, .section__title'):
            parts.append(self._convert_block(text_div))

        # Info boxes
        for info in section.select('.info_box'):
            info_md = self._convert_info_box(info)
            if info_md:
                parts.append(info_md)

        # Cross links (related links as a bullet list)
        if cross_links:
            parts.append(self._convert_cross_links(cross_links))

        # Sources / bibliography
        if sources:
            parts.append(self._convert_sources(sources))

        return '\n\n'.join(p for p in parts if p and p.strip())

    def _convert_block(self, block):
        out = []
        for child in block.children:
            if isinstance(child, Tag):
                if child.name in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
                    level = int(child.name[1])
                    text = self._inline(child)
                    out.append('#' * level + ' ' + text)
                elif child.name == 'p':
                    out.append(self._inline(child))
        return '\n\n'.join(out)

    def _convert_info_box(self, info):
        text = ' '.join(
            self._inline(p) for p in info.find_all('p')
        ).strip()
        if not text:
            return ''
        return '> ℹ️ ' + text

    def _convert_cross_links(self, cross_links):
        items = []
        for tile in cross_links.select('.tile'):
            title_el = tile.select_one('h3')
            link_el = tile.select_one('a[href]')
            if title_el and link_el:
                title = title_el.get_text(strip=True)
                href = link_el['href']
                items.append(f'- [{title}]({href})')
        return '\n'.join(items)

    def _convert_sources(self, sources):
        lines = ['## Quellenverzeichnis', '']
        for item in sources.select('.source_item'):
            num_el = item.select_one('sup.item')
            num = num_el.get_text(strip=True) if num_el else ''

            # Text is in the span that is a direct sibling of the sup
            text = ''
            link_el = item.select_one('a[href]')
            spans = item.select('.list_of_sources__item > span')
            if spans:
                text = spans[0].get_text(strip=True)

            entry = f'{num}. {text}'.strip()
            if link_el:
                href = link_el['href']
                entry += f' <{href}>'
            lines.append(entry)
        return '\n'.join(lines)

    # ---------- Inline conversion ----------
    def _inline(self, element):
        result = []
        for child in element.children:
            if isinstance(child, NavigableString):
                result.append(str(child))
            elif isinstance(child, Tag):
                if child.name == 'a' and 'source' in (child.get('class') or []):
                    # Source reference like [1]
                    sup = child.get_text(strip=True)
                    result.append(sup)
                elif child.name == 'a':
                    text = self._inline(child)
                    href = child.get('href', '')
                    result.append(f'[{text}]({href})')
                elif child.name in ('strong', 'b'):
                    result.append(f'**{self._inline(child)}**')
                elif child.name in ('em', 'i'):
                    result.append(f'*{self._inline(child)}*')
                elif child.name == 'br':
                    result.append(' ')
                elif child.name == 'sup':
                    result.append(child.get_text(strip=True))
                elif child.name in ('svg', 'meta', 'use'):
                    continue
                else:
                    result.append(self._inline(child))
        text = ''.join(result)
        # Normalize non-breaking spaces and whitespace
        text = text.replace('\xa0', ' ')
        text = re.sub(r'[ \t]+', ' ', text)
        return text.strip()

    # ---------- Cleanup ----------
    def _cleanup(self, markdown):
        # Collapse 3+ newlines to 2
        markdown = re.sub(r'\n{3,}', '\n\n', markdown)
        return markdown.strip() + '\n'
