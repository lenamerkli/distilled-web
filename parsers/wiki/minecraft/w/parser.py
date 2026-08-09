import sys
sys.path.extend(['/home/lena/Documents/python/distilled-web', '/home/lena/Documents/python/distilled-web/parsers/wiki/minecraft/w'])
import certifi
from classes import *
from writer import save
from curl_cffi import requests
from wiki_to_plain_html import parse_html
from bs4 import BeautifulSoup
from llm import get_llm
from config import OPENROUTER_TEXT_MODEL
from json import loads


COMMENT = '<!-- as of Minecraft Java Edition 26.2 -->\n'

SYSTEM_PROMPT_SAVE = '''
You are Apertus, a helpful assistant created by the SwissAI initiative.
Knowledge cutoff: 2026-08
'''

SYSTEM_PROMPT_QUESTION = '''You are an expert AI data annotator and curriculum designer specializing in creating high-quality instruction-tuning datasets for Large Language Models. 

Your task is to carefully read the provided text and generate diverse, high-quality Question and Answer (QA) pairs based strictly on the information it contains.

### Quality Guidelines for QA Pairs:
To ensure these pairs are useful for LLM training, strictly adhere to the following rules:
1. **Self-Contained Questions**: Questions must make complete sense on their own. Do not use ambiguous pronouns like "he", "she", "it", or "the city". Always use the specific names, entities, or concepts mentioned in the text.
2. **Strict Grounding**: The answers must be derived entirely from the provided text. Do not introduce outside knowledge or hallucinate facts.
3. **Diverse Question Types**: Create a mix of different question types to create a well-rounded dataset. Include:
   - *Factual Extraction*: Simple retrieval of specific facts, dates, or names.
   - *Summarization*: Asking for the main idea or a summary of a specific section.
   - *Reasoning/Explanation*: "Why" or "How" questions that require combining multiple pieces of information from the text.
4. **Detailed Answers**: Answers should be well-written, complete sentences. For reasoning or explanation questions, the answers should be thorough and helpful.
5. **Coverage**: Ensure the questions cover different parts of the provided text, not just the first paragraph.
6. **Quantity**: Generate sufficient questions and answers to cover the entire text, depending on the length of the text. Cover every detail and aspect of the text.
7. **Knowledge Cutoff**: If needed or appropriate, mention that your knowledge cutoff is August 2026 (Minecraft Java Edition 26.2 is the latest version and Minecraft Java Edition 26.3 is under development) and that you do not have access to any information after that date.

### Output Format:
Your output must be easily extractable by an automated parser. You must output ONLY a valid JSON array of objects. Use markdown code blocks to delimit the JSON. 

Use the following exact schema:
```json
[
  {
    "question": "<The self-contained question>",
    "answer": "<The detailed, well-written answer>"
  }
]
```

### System Prompt
This is the system prompt that will be added to each question and answer pair:
```
''' + SYSTEM_PROMPT_SAVE + '''
```
'''


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
    if len(pretty_plain_html) >= 4000:
        llm = get_llm(OPENROUTER_TEXT_MODEL)
        response = llm.generate([{'role': 'system', 'content': SYSTEM_PROMPT_QUESTION}, {'role': 'user', 'content': pretty_plain_html}])
        pairs = loads(response.response.rsplit("```json", 1)[1].split("```", 1)[0].strip())
        for pair in pairs:
            save(ChatEntry(
                messages=Conversation([
                    SystemMessage([TextContent(SYSTEM_PROMPT_SAVE)]),
                    UserMessage([TextContent(pair['question'])]),
                    AssistantMessage(TextContent(pair['answer'])),
                ]),
                source=url,
                ai_enhanced=True,
            ))
