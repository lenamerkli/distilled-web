import sys
sys.path.extend(['/home/lena/Documents/python/distilled-web', '/home/lena/Documents/python/distilled-web/parsers/ch/admin/fedlex/www/filestore'])
from shared import *


DE_PROMPT_ART = '<p>\n  Wie lautet Artikel %ID% der `Übereinkunft zwischen dem Schweizerischen Bundesrate und dem Einwohnergemeinderate der Stadt Bern betreffend die Leistungen der Stadt Bern an den Bundessitz`?\n</p>'
FR_PROMPT_ART = '<p>\n  Quel est le contenu de l\'article %ID% de la `Convention entre le Conseil fédéral suisse et le Conseil municipal de la ville de Berne, concernant les prestations de la ville de Berne pour le siège fédéral`?\n</p>'
IT_PROMPT_ART = '<p>\n  Qual è il testo dell\'articolo %ID% della `Convenzione tra il Consiglio federale svizzero e il Consiglio municipale della città di Berna sulle prestazioni di questa città per la sede federale`?\n</p>'


def parse(url: str):
    parse_law(url, (
        ('de', DE_PROMPT_ART, DE_WARNING),
        ('fr', FR_PROMPT_ART, FR_WARNING),
        ('it', IT_PROMPT_ART, IT_WARNING),
    ))
