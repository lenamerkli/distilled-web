import sys
sys.path.extend(['/home/lena/Documents/python/distilled-web', '/home/lena/Documents/python/distilled-web/parsers/ch/admin/fedlex/www/filestore'])
from shared import *


DE_PROMPT_ART = '<p>\n  Wie lautet Artikel %ID% des Schweizerischen Datenschutzgesetzes?\n</p>'
FR_PROMPT_ART = '<p>\n  Quel est le contenu de l\'article %ID% de la loi suisse sur la protection des données?\n</p>'
IT_PROMPT_ART = '<p>\n  Qual è il testo dell\'articolo %ID% della legge svizzera sulla protezione dei dati?\n</p>'


def parse(url: str):
    parse_law(url, (
        ('de', DE_PROMPT_ART, DE_WARNING),
        ('fr', FR_PROMPT_ART, FR_WARNING),
        ('it', IT_PROMPT_ART, IT_WARNING),
    ))
