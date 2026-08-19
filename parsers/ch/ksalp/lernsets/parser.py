import sys
sys.path.extend(['/home/lena/Documents/python/distilled-web'])
import certifi
from classes import *
from writer import save
import requests
from json import dumps


PROMPT = 'You are an expert translator. Translate any user input to French.'
TRANSLATIONS = [
    'https://ksalp.ch/lernsets/vorschau/1uFTfyv8',
    'https://ksalp.ch/lernsets/vorschau/2STpVr0o',
    'https://ksalp.ch/lernsets/vorschau/47hwwbLJ',
    'https://ksalp.ch/lernsets/vorschau/5bR-nef1',
    'https://ksalp.ch/lernsets/vorschau/KHFtygoa',
    'https://ksalp.ch/lernsets/vorschau/LbYjlxzS',
    'https://ksalp.ch/lernsets/vorschau/M8wzHqmL',
    'https://ksalp.ch/lernsets/vorschau/P7Set2ON',
    'https://ksalp.ch/lernsets/vorschau/PCgVd065',
    'https://ksalp.ch/lernsets/vorschau/PmyOBvOw',
    'https://ksalp.ch/lernsets/vorschau/Rte_ftf4',
    'https://ksalp.ch/lernsets/vorschau/UXbdU7Py',
    'https://ksalp.ch/lernsets/vorschau/UYgsxCAq',
    'https://ksalp.ch/lernsets/vorschau/WxwWm2mJ',
    'https://ksalp.ch/lernsets/vorschau/YBXDkaXT',
    'https://ksalp.ch/lernsets/vorschau/_1l3nHAl',
    'https://ksalp.ch/lernsets/vorschau/c311XW4j',
    'https://ksalp.ch/lernsets/vorschau/fXT4bqBH',
    'https://ksalp.ch/lernsets/vorschau/gELwNyHh',
    'https://ksalp.ch/lernsets/vorschau/i90gss4n',
    'https://ksalp.ch/lernsets/vorschau/iKRjjC62',
    'https://ksalp.ch/lernsets/vorschau/kSb_QzFN',
    'https://ksalp.ch/lernsets/vorschau/kbfQnc1D',
    'https://ksalp.ch/lernsets/vorschau/nMIgMTFR',
    'https://ksalp.ch/lernsets/vorschau/sD12AjSc',
    'https://ksalp.ch/lernsets/vorschau/t68z4uim',
    'https://ksalp.ch/lernsets/vorschau/telfg_bl',
    'https://ksalp.ch/lernsets/vorschau/ujydA-5X',
    'https://ksalp.ch/lernsets/vorschau/v5PGt7JU',
    'https://ksalp.ch/lernsets/vorschau/vKAKsAy5',
    'https://ksalp.ch/lernsets/vorschau/y0Ziopnp',
    'https://ksalp.ch/lernsets/vorschau/zBQ3GJlj',
]


def parse(url: str):
    download_url = url.replace('lernsets/vorschau', 'dateien/lernsets') + '/file.json'
    response = requests.get(download_url, verify=certifi.where())
    response.raise_for_status()
    data = response.json()
    save(TextEntry(dumps(data, ensure_ascii=False, indent=2), url))
    save(TextEntry(dumps(data, ensure_ascii=True, indent=2), url))
    if isinstance(data, list) and url in TRANSLATIONS:
        for item in data:
            if 'question' in item and 'answer' in item and len(item['question']) > 2 and len(item['answer']) > 2:
                save(ChatEntry(Conversation([SystemMessage([TextContent(PROMPT)]), UserMessage([TextContent(item['question'])]), AssistantMessage(TextContent(item['answer']))]), url))
