import sys
sys.path.extend(['/home/lena/Documents/python/distilled-web'])
import certifi
from classes import *
from writer import save
from curl_cffi import requests
from bs4 import BeautifulSoup


def parse(url: str):
    resp = requests.get(url, verify=certifi.where())  # type: ignore
    resp.raise_for_status()
    raw_html = resp.text
    soup = BeautifulSoup(raw_html, 'html.parser')
    selector = soup.select_one('div.text')
    if not selector:
        raise ValueError('No text found')
    text = selector.decode_contents()
    save(TextEntry(text, url))
