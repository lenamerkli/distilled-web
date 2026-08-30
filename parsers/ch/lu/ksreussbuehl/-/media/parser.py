import sys
sys.path.extend(['/home/lena/Documents/python/distilled-web'])
import certifi
from classes import *
from writer import save
import requests
from config import *
from miner_u_pro import pdf_to_markdown


_TMP_DIR = TMP_LOCATION / 'ch.lu.ksreussbuehl.-.media'
PROMPT = 'Extrahiere den Text.'


def parse(url: str):
    url2 = url.rsplit('?')[0]
    if url2.endswith('.pdf'):
        filename = url2.split('/')[-1]
        _TMP_DIR.mkdir(exist_ok=True, parents=True)
        with requests.get(url, stream=True, verify=certifi.where()) as response:
            response.raise_for_status()
            with open(_TMP_DIR / filename, 'wb') as out_file:
                for chunk in response.iter_content(chunk_size=8192):
                    out_file.write(chunk)
        text = pdf_to_markdown(_TMP_DIR / filename)
        save(TextEntry(text, url, ai_enhanced=True))
        with open(_TMP_DIR / filename, 'rb') as file:
            content = file.read()
        save(ChatEntry(Conversation([UserMessage([TextContent(PROMPT), MediaContent('other_media', content=content)]), AssistantMessage(TextContent(text))]), url, ai_enhanced=True))
        (_TMP_DIR / filename).unlink(missing_ok=True)
