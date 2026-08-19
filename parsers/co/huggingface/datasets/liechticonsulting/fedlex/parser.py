import sys
sys.path.extend(['/home/lena/Documents/python/distilled-web', '/home/lena/Documents/python/distilled-web/parsers/co/huggingface/datasets/liechticonsulting/fedlex'])
import requests
import csv
import io
from tqdm import tqdm
import xml.dom.minidom
import xml.etree.ElementTree as ET
from writer import save
from classes import *
from fedlex_to_markdown import FedlexConverter
from traceback import print_exc


csv.field_size_limit(10 * 1024 * 1024)

DE_WARNING = 'Ich bin eine Künstliche Intelligenz und kein Rechtsanwalt. Ich kann eine professionelle juristische Beratung nicht ersetzen. Nachfolgend ist mein bester Versuch, Ihre Frage zu beantworten. Die Richtigkeit der Antwort kann nicht garantiert werden.'
FR_WARNING = 'Je suis une intelligence artificielle et non un avocat. Je ne peux pas me substituer à un conseil juridique professionnel. Vous trouverez ci-dessous ma meilleure tentative de réponse à votre question. Je ne peux garantir l\'exactitude de cette réponse.'
IT_WARNING = 'Sono un\'intelligenza artificiale e non un avvocato. Non posso sostituirmi a una consulenza legale professionale. Di seguito troverete il mio miglior tentativo di rispondere alla sua domanda. Non è possibile garantire la correttezza della risposta.'
DE_PROMPT = '(Schweiz) Wie lautet Artikel %ID% von `%TITLE%`?'
FR_PROMPT = '(Suisse) Quel est le contenu de l\'article %ID% de %TITLE%?'
IT_PROMPT = '(Svizzera) Qual è il testo dell\'articolo %ID% di %TITLE%?'


def pretty_print_xml_minidom(xml_string):
    dom = xml.dom.minidom.parseString(xml_string)
    pretty_xml = dom.toprettyxml(indent="  ")
    return "\n".join(line for line in pretty_xml.split("\n") if line.strip())


def parse(url: str):
    if url != 'https://huggingface.co/datasets/liechticonsulting/fedlex/resolve/main/fedlex_dataset.csv':
        raise ValueError(f"Unsupported URL: {url}")
    resp = requests.get(url)
    resp.raise_for_status()
    text = io.StringIO(resp.content.decode("utf-8", errors="replace"))
    rows: list[list[str]] = list(csv.reader(text))
    print(rows[:3])
    for row in tqdm(rows, desc="Processing rows"):
        title = row[1]
        language = row[3].lower().strip()
        raw_xml = row[5]
        if language not in ['de', 'fr', 'it']:
            continue
        if ('<no-script>' in raw_xml and '<!DOCTYPE html>' in raw_xml) or len(raw_xml) < 16:
            continue
        try:
            match language:
                case 'de':
                    warning = DE_WARNING
                    prompt = DE_PROMPT
                case 'fr':
                    warning = FR_WARNING
                    prompt = FR_PROMPT
                case 'it':
                    warning = IT_WARNING
                    prompt = IT_PROMPT
            pretty_xml = pretty_print_xml_minidom(raw_xml)
            save(TextEntry(pretty_xml, url))
            root = ET.fromstring(raw_xml)
            result = FedlexConverter().convert(root, source=title)
            whole_markdown = result["markdown"]
            save(TextEntry(whole_markdown, url))
            markdown_articles = [
                {"id": article_id, "content": record.markdown}
                for article_id, record in result["articles"].items()
            ]
            for article in markdown_articles:
                save(ChatEntry(Conversation([UserMessage([TextContent(prompt.replace('%TITLE%', title).replace('%ID%', article['id']))]), AssistantMessage(TextContent(f"**{warning}**\n\n{article['content']}"))]), url))
        except Exception as e:
            print(f"Error processing row: {row}")
            print_exc()
            print(f"Error: {e}")
