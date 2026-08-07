import sys
sys.path.extend(['/home/lena/Documents/python/distilled-web', '/home/lena/Documents/python/distilled-web/parsers/wiki/minecraft/w'])
import certifi
from classes import *
from writer import save
from curl_cffi import requests
from wiki_to_plain_html import parse_html
from bs4 import BeautifulSoup


COMMENT = '<!-- as of Minecraft Java Edition 26.2 -->\n'


def parse(url: str):
    export_url = url + '?action=raw'
    response_xml = requests.get(export_url, impersonate='chrome', verify=certifi.where())  # noqa
    response_xml.raise_for_status()
    xml = response_xml.text
    save(TextEntry(COMMENT + xml, source=url))
    response_html = requests.get(url, impersonate='chrome', verify=certifi.where())  # noqa
    response_html.raise_for_status()
    plain_html = parse_html(response_html.text)
    soup = BeautifulSoup(plain_html, 'html.parser')
    pretty_plain_html = soup.prettify()
    save(TextEntry(COMMENT + pretty_plain_html, source=url))
