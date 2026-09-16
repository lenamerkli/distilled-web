import sys

sys.path.extend(['/home/lena/Documents/python/distilled-web'])
import json
import re
import typing as t
import requests
from tqdm import tqdm
from classes import *
from writer import save

URL = 'https://huggingface.co/datasets/open-paws/reasoning-and-chat-harmony-format/resolve/main/reasoning-and-conversational-finetuning-harmony-format.jsonl'

# A single harmony message block looks like:
# <|start|>{recipient}[ to={recipient}][<|channel|>{channel}][<|constrain|>{type}]<|message|>{content}[<|return|>][<|call|>]<|end|>
BLOCK = re.compile(
    r'<\|start\|>(?P<header>[^<]*)'
    r'(?:<\|channel\|>(?P<channel>[^<]*))?'
    r'(?:<\|constrain\|>(?P<constrain>[^<]*))?'
    r'<\|message\|>'
)
TRAILING = re.compile(r'(?:<\|return\|>|<\|call\|>)*<\|end\|>\s*$')

# Harmony format metadata that must not end up in the training data: the
# reasoning effort, the channel list and the tool ('functions') channel note.
# Every system message of this dataset contains exactly these lines.
METADATA_LINES = (
    re.compile(r'^Reasoning:\s*\w+\s*$'),
    re.compile(r'^# Valid channels:.*$'),
    re.compile(r'^Calls to these tools.*$'),
)
# Defensive: the current revision of the dataset has no `# Tools` section.
TOOLS_SECTION = re.compile(r'(?ms)^# Tools\s*$.*?(?=^# |\Z)')

Message = t.Union[SystemMessage, UserMessage, AssistantMessage, ToolMessage]


def parse(url: str):
    if url != URL:
        raise ValueError(f'Can only parse this exact URL: `{URL}`')
    saved = 0
    skipped = 0
    with requests.get(url, stream=True) as resp:
        resp.raise_for_status()
        for line in tqdm(resp.iter_lines(), desc='Parsing rows', unit=' row'):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                # Never let a truncated or malformed line abort the whole file.
                skipped += 1
                continue
            messages = _parse_messages(row.get('messages') or '')
            if not messages:
                skipped += 1
                continue
            save(ChatEntry(Conversation(messages), source=url, ai_enhanced=False))
            saved += 1
    print(f'Saved {saved} entries, skipped {skipped} rows.')


def _iter_blocks(text: str) -> t.Iterator[tuple[str, t.Optional[str], t.Optional[str], str]]:
    """Yield (recipient, to, channel, content) for every harmony message block."""
    matches = list(BLOCK.finditer(text))
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        header = match.group('header').split()
        recipient = header[0] if header else ''
        to = next((part[len('to='):] for part in header[1:] if part.startswith('to=')), None)
        yield recipient, to, match.group('channel'), TRAILING.sub('', text[match.end():end])


def _sanitize_system(text: str) -> str:
    """Strip reasoning-effort, channel and tool-call metadata from a system message."""
    text = TOOLS_SECTION.sub('', text)
    lines = [line for line in text.splitlines() if not any(p.match(line.strip()) for p in METADATA_LINES)]
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(lines)).strip()


def _parse_messages(text: str) -> list[Message]:
    """Convert a harmony-formatted conversation into the content of a Conversation.

    Conversations that use tool calls are dropped entirely and only the `final`
    channel of an assistant turn is kept. Assistant turns that end up adjacent to
    each other (because their `analysis` channel was dropped) are merged into a
    single assistant message.
    """
    blocks = list(_iter_blocks(text))
    if '<|call|>' in text or any(to for _, to, _, _ in blocks):
        return []
    messages: list[Message] = []
    for recipient, _, channel, content in blocks:
        if recipient == 'system':
            messages.append(SystemMessage([TextContent(_sanitize_system(content))]))
        elif recipient == 'user':
            messages.append(UserMessage([TextContent(content)]))
        elif recipient == 'assistant' and channel == 'final':
            # An assistant turn whose `analysis` channel was dropped may be directly
            # preceded by another assistant turn; merge the two into one message.
            previous = messages[-1] if messages else None
            if isinstance(previous, AssistantMessage):
                previous.text.text += '\n\n' + content
            else:
                messages.append(AssistantMessage(TextContent(content)))
        # Every other channel (e.g. `analysis`) and every other recipient (tool
        # output) is ignored, conversations using tools having been dropped above.
    if not any(isinstance(message, AssistantMessage) for message in messages):
        return []
    return messages
