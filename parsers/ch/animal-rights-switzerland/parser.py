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
    # Elements that are pure noise (sharing, forms, scripts, spacers)
    NOISE_SELECTORS = [
        '.heateor_sss_sharing_container',
        '.nf-form-cont',
        '.quform',
        '.vc_empty_space',
        'script',
        'style',
        'noscript',
    ]

    def __init__(self, raw_html):
        self.soup = BeautifulSoup(raw_html, 'html.parser')
        self.main_content = self.soup.select_one('.entry-content .wpb-content-wrapper')
        if not self.main_content:
            raise ValueError('No main content found')
        self._title_text = ''

    def convert(self):
        # Remove elements we want to ignore entirely
        for selector in self.NOISE_SELECTORS:
            for el in self.main_content.select(selector):
                el.decompose()

        parts = []

        # Page title (h1, usually at the top of the content)
        title_el = self.main_content.find('h1')
        if title_el:
            self._title_text = self._inline(title_el)
            parts.append('# ' + self._title_text)

        # Convert content elements (text columns and hoverbox fact tiles) in document order
        for el in self.main_content.select('.wpb_text_column, .vc-hoverbox'):
            # Skip hoverboxes nested inside a text column (handled by the outer block)
            if el.find_parent(class_='wpb_text_column'):
                continue
            if 'vc-hoverbox' in (el.get('class') or []):
                hover_md = self._convert_hoverbox(el)
                if not hover_md:
                    continue
                # Merge consecutive hoverboxes into a single bullet list
                if parts and parts[-1].startswith('- '):
                    parts[-1] += '\n' + hover_md
                else:
                    parts.append(hover_md)
            else:
                parts.append(self._convert_block(el))

        markdown = '\n\n'.join(p for p in parts if p and p.strip())
        return self._cleanup(markdown)

    # ---------- Blocks ----------
    def _convert_block(self, block):
        out = []
        for child in block.children:
            if isinstance(child, Tag):
                if child.name in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
                    text = self._inline(child)
                    # Skip a repeated page title, demote any other h1
                    if child.name == 'h1' and text == self._title_text:
                        continue
                    level = max(int(child.name[1]), 2)
                    out.append('#' * level + ' ' + text)
                elif child.name == 'p':
                    out.append(self._inline(child))
                elif child.name in ('ul', 'ol'):
                    out.append(self._convert_list(child))
                elif child.name == 'blockquote':
                    out.append(self._convert_blockquote(child))
                elif child.name == 'div':
                    nested_md = self._convert_block(child)
                    if nested_md:
                        out.append(nested_md)
        return '\n\n'.join(p for p in out if p and p.strip())

    def _convert_hoverbox(self, hoverbox):
        # The explanatory text lives on the back of the flip tile
        back = hoverbox.select_one('.vc-hoverbox-back-inner')
        if not back:
            return ''
        items = []
        for p in back.find_all('p'):
            items.append('- ' + self._inline(p))
        for li in back.select('li'):
            items.append('- ' + self._inline(li))
        return '\n'.join(i for i in items if i.strip())

    def _convert_list(self, list_el, indent=0):
        items = []
        ordered = list_el.name == 'ol'
        for i, li in enumerate(list_el.find_all('li', recursive=False), start=1):
            nested = li.find(['ul', 'ol'], recursive=False)
            if nested:
                nested.extract()
            text = self._inline(li)
            marker = f'{i}.' if ordered else '-'
            prefix = '  ' * indent + marker + ' '
            items.append(prefix + text.replace('\n', ' '))
            if nested:
                items.append(self._convert_list(nested, indent + 1))
        return '\n'.join(items)

    def _convert_blockquote(self, quote):
        text = ' '.join(
            self._inline(p) for p in quote.find_all('p')
        ).strip()
        if not text:
            text = self._inline(quote)
        return '> ' + text if text else ''

    # ---------- Inline conversion ----------
    def _inline(self, element):
        result = []
        last_was_link = False

        def append_text(text, from_link=False):
            nonlocal last_was_link
            if not text:
                last_was_link = from_link
                return
            # A newline before text still separates words
            if text[0].isspace():
                text = ' ' + text.lstrip()
            # Ensure a space between a link and directly adjacent text
            if last_was_link and not text.startswith(' ') and result and not result[-1].endswith(' '):
                result.append(' ')
            result.append(text)
            last_was_link = from_link

        for child in element.children:
            if isinstance(child, NavigableString):
                append_text(str(child))
            elif isinstance(child, Tag):
                if child.name == 'a':
                    text = self._inline(child)
                    href = child.get('href', '')
                    if href:
                        link = f'[{text}]({href})'
                        if result and not result[-1].endswith((' ', '(', '[', '-', '/')):
                            result.append(' ')
                        append_text(link, from_link=True)
                    else:
                        append_text(text)
                elif child.name in ('strong', 'b'):
                    append_text(f'**{self._inline(child)}**')
                elif child.name in ('em', 'i'):
                    append_text(f'*{self._inline(child)}*')
                elif child.name == 'br':
                    append_text(' ')
                elif child.name == 'sup':
                    append_text(child.get_text(strip=True))
                elif child.name in ('svg', 'meta', 'use', 'img', 'figure'):
                    continue
                else:
                    append_text(self._inline(child))
        text = ''.join(result)
        # Normalize non-breaking spaces and whitespace
        text = text.replace('\xa0', ' ')
        text = re.sub(r'[ \t]+', ' ', text)
        # No space between a word and following punctuation
        text = re.sub(r' +([,.;:!?»])', r'\1', text)
        return text.strip()

    # ---------- Cleanup ----------
    def _cleanup(self, markdown):
        # Collapse 3+ newlines to 2
        markdown = re.sub(r'\n{3,}', '\n\n', markdown)
        return markdown.strip() + '\n'
