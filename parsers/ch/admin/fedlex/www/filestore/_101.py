import sys
sys.path.append('/home/lena/Documents/python/distilled-web')
from curl_cffi import requests
from bs4 import BeautifulSoup, Doctype
import certifi
from writer import save
from classes import TextEntry, ChatEntry, Conversation, UserMessage, AssistantMessage, TextContent


DE_PROMPT_ART = '<p>\n  Wie lautet Artikel %ID% der Schweizerischen Bundesverfassung?\n</p>'
FR_PROMPT_ART = '<p>\n  Quel est le contenu de l\'article %ID% de la Constitution fédérale suisse?\n</p>'
IT_PROMPT_ART = '<p>\n  Qual è il testo dell\'articolo %ID% della Costituzione federale svizzera?\n</p>'

DE_WARNING = '''<p>
  <b>
    <i>
      Ich bin eine Künstliche Intelligenz und kein Rechtsanwalt. Ich kann eine professionelle juristische Beratung nicht ersetzen. Nachfolgend ist mein bester Versuch, Ihre Frage zu beantworten. Die Richtigkeit der Antwort kann nicht garantiert werden.
    </i>
  </b>
</p>
'''
FR_WARNING = '''<p>
  <b>
    <i>
      Je suis une intelligence artificielle et non un avocat. Je ne peux pas me substituer à un conseil juridique professionnel. Vous trouverez ci-dessous ma meilleure tentative de réponse à votre question. Je ne peux garantir l'exactitude de cette réponse.
    </i>
  </b>
</p>
'''
IT_WARNING = '''<p>
  <b>
    <i>
      Sono un'intelligenza artificiale e non un avvocato. Non posso sostituirmi a una consulenza legale professionale. Di seguito troverete il mio miglior tentativo di rispondere alla sua domanda. Non è possibile garantire la correttezza della risposta.
    </i>
  </b>
</p>
'''

_VOID_TAGS = {'br', 'hr', 'img'}
_UNWRAP_TAGS = ['div', 'section', 'article', 'main']
_KEEP_ATTRS = {'colspan', 'rowspan'}


def parse(url: str):
    languages = (
        ('de', DE_PROMPT_ART, DE_WARNING),
        ('fr', FR_PROMPT_ART, FR_WARNING),
        ('it', IT_PROMPT_ART, IT_WARNING),
    )

    # Fetch all languages first so saves keep the original ordering:
    # first all raw HTML, then all plain HTML, then the per-article chats.
    soups: dict[str, tuple[str, BeautifulSoup]] = {}
    for lang, _, _ in languages:
        lang_url = url.replace('de', lang)
        soups[lang] = (lang_url, BeautifulSoup(requests.get(lang_url, impersonate='chrome', verify=certifi.where()).text, 'html.parser'))  # noqa

    for lang, _, _ in languages:
        lang_url, soup = soups[lang]
        save(TextEntry(soup.prettify(), source=lang_url))

    for lang, _, _ in languages:
        lang_url, soup = soups[lang]
        save(TextEntry(to_plain_html(soup), source=lang_url))

    for lang, prompt, warning in languages:
        lang_url, soup = soups[lang]
        for article in soup.find_all('article'):
            art_id = _article_id(article)
            art_html = _article_to_plain_html(article)
            save(ChatEntry(
                messages=Conversation([
                    UserMessage([TextContent(prompt.replace('%ID%', art_id))]),
                    AssistantMessage(TextContent(warning + art_html)),
                ]),
                source=lang_url,
            ))


def to_plain_html(soup: BeautifulSoup) -> str:
    """
    - Removes `<div id="dispositions">` and its contents
    - Remove all div tags, classes, ids, roles, names, section tags, article tags
    - Remove the html head and doctype declarations
    - Replace links with their text content
    - Remove the body tag
    - Call .prettify() on the soup
    """
    # Work on a copy so the original soup is left intact for article extraction.
    soup = BeautifulSoup(str(soup), 'html.parser')
    for div in soup.find_all('div', id='dispositions'):
        div.decompose()
    _strip(soup, remove_footnotes=False)
    return soup.prettify()


def _article_id(article) -> str:
    """Extract the article number (e.g. '5a') from its `<a name="a5a">` anchor."""
    anchor = article.find('a', attrs={'name': True})
    return anchor['name'][1:]  # strip the leading 'a'


def _article_to_plain_html(article) -> str:
    soup = BeautifulSoup(str(article), 'html.parser')
    _strip(soup, remove_footnotes=True)
    return soup.prettify()


def _strip(soup: BeautifulSoup, remove_footnotes: bool) -> None:
    if remove_footnotes:
        # Footnote reference markers, e.g. `<sup><a href="#fn-...">2</a></sup>`.
        for sup in soup.find_all('sup'):
            if sup.find('a', href=lambda h: h and h.startswith('#fn')):
                sup.decompose()
        # Footnote definitions.
        for div in soup.find_all('div', class_='footnotes'):
            div.decompose()

    # Replace links with their text content.
    for a in soup.find_all('a'):
        a.unwrap()

    # Remove structural wrapper tags (keep their contents).
    for tag in soup.find_all(_UNWRAP_TAGS):
        tag.unwrap()
    for body in soup.find_all('body'):
        body.unwrap()

    # Remove the html head and doctype declarations.
    for head in soup.find_all('head'):
        head.decompose()
    for doctype in soup.find_all(string=lambda s: isinstance(s, Doctype)):
        doctype.extract()

    # Strip decorative attributes (classes, ids, roles, names, aria-*, href, …).
    for tag in soup.find_all(True):
        for attr in list(tag.attrs):
            if attr not in _KEEP_ATTRS:
                del tag.attrs[attr]

    # Prune tags left empty by the cleanup above (e.g. decorative icon spans).
    for tag in soup.find_all(lambda t: t.name not in _VOID_TAGS and not t.get_text(strip=True) and not t.find_all(True)):
        tag.decompose()
