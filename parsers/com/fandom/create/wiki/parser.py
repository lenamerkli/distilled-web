import sys
sys.path.extend(['/home/lena/Documents/python/distilled-web', '/home/lena/Documents/python/distilled-web/parsers/wiki/minecraft/w'])
import certifi
from classes import *
from writer import save
from curl_cffi import requests
from wiki_to_plain_html import parse_html
from bs4 import BeautifulSoup


COMMENT = '<!-- as of Create Mod version 6.0.10 -->\n'

HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Upgrade-Insecure-Requests': '1',
}

IMPERSONATIONS = ['chrome120', 'chrome110', 'safari17_0']


def _fetch(session: requests.Session, url: str) -> requests.Response:
    """Fetch a URL with retry and impersonation fallback on 403."""
    for idx, impersonate in enumerate(IMPERSONATIONS):
        resp = session.get(
            url,
            headers=HEADERS,
            impersonate=impersonate,
            verify=certifi.where(),
        )
        if resp.status_code != 403:
            return resp
        # On 403, try the next impersonation fingerprint
        if idx < len(IMPERSONATIONS) - 1:
            continue
    # All impersonations failed — still return the last response so
    # raise_for_status() in the caller surfaces the actual error.
    return resp


def parse(url: str):
    session = requests.Session()

    # Seed cookies by visiting the wiki homepage first.
    seed_url = 'https://create.fandom.com/wiki/Create_Mod_Wiki'
    session.get(seed_url, headers=HEADERS, impersonate=IMPERSONATIONS[0], verify=certifi.where())

    # 1) Raw wikitext export
    export_url = url + '?action=raw'
    response_xml = _fetch(session, export_url)
    response_xml.raise_for_status()
    xml = response_xml.text
    save(TextEntry(COMMENT + xml, source=url))

    # 2) Rendered HTML page
    response_html = _fetch(session, url)
    response_html.raise_for_status()
    plain_html = parse_html(response_html.text)
    soup = BeautifulSoup(plain_html, 'html.parser')
    pretty_plain_html = soup.prettify()
    save(TextEntry(COMMENT + pretty_plain_html, source=url))