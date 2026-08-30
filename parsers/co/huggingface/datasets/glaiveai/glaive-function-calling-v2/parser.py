import sys
sys.path.append('/home/lena/Documents/python/distilled-web')
import json
from shutil import rmtree
from subprocess import run
from classes import *
from config import *
from writer import save
import re
import typing as t


def parse(url: str):
    if url != 'https://huggingface.co/datasets/glaiveai/glaive-function-calling-v2':
        raise ValueError(f'Can only parse this exact url: `https://huggingface.co/datasets/glaiveai/glaive-function-calling-v2`')
    temp_dir = TMP_LOCATION / 'co.huggingface.datasets.glaiveai.glaive-function-calling-v2'
    if temp_dir.exists():
        rmtree(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)
    run(['git', 'clone', '--single-branch', '--branch', 'main', '--depth', '1', url, str(temp_dir)])
    data_path = temp_dir / 'glaive-function-calling-v2.json'
    if not data_path.exists():
        raise FileNotFoundError(f'Expected file not found: {data_path}')
    with open(data_path, 'r') as f:
        data = json.load(f)
    for row in data:
        system = row['system']
        chat = row['chat']
        conversation = chat_to_conversation(chat, system)
        save(ChatEntry(conversation, url))


def chat_to_conversation(chat: str, system: str) -> Conversation:
    has_tools = 'with access to the following functions' in system
    system = system.replace('SYSTEM: ', '')
    if has_tools:
        system_message = SystemMessage([TextContent(system.split('Use them if required')[0] + 'Use them if required.')])
        pattern = re.compile(r'(?m)^\s*\{\s*"name"\s*:')
        decoder = json.JSONDecoder()
        tools = []
        for match in pattern.finditer(system):
            start = match.start()
            while system[start].isspace():
                start += 1
            tool, _ = decoder.raw_decode(system, start)
            tools.append(tool)
    else:
        system_message = SystemMessage([TextContent(system)])
        tools = []

    def _parse_function_call(blob: str) -> ToolCall:
        blob = blob.strip()
        for candidate in (blob, blob.replace("\\'", "'")):
            try:
                data = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and 'name' in data:
                arguments = data.get('arguments', {})
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
                return ToolCall(data['name'], arguments)
        # Fallback: Glaive wraps `arguments` in (sometimes escaped) single quotes,
        # which is not valid JSON. Extract the name and the arguments object
        # separately instead of parsing the whole blob.
        name_match = re.search(r'"name"\s*:\s*"([^"]+)"', blob)
        name = name_match.group(1) if name_match else ''
        args_start = blob.find('{', blob.find('"arguments"'))
        if args_start != -1:
            arg_text = blob[args_start:].replace("\\'", "'")
            try:
                arguments, _ = json.JSONDecoder().raw_decode(arg_text)
            except json.JSONDecodeError:
                arguments = {}
        else:
            arguments = {}
        if isinstance(arguments, str):
            arguments = json.loads(arguments)
        return ToolCall(name, arguments)
    chat = chat.replace('<|endoftext|>', '')
    # Some rows separate turns with '\n\n' instead of '\n\n\n', so split on
    # role prefixes rather than blank-line runs.
    block_pattern = re.compile(r'(?m)^(USER: |ASSISTANT: |FUNCTION RESPONSE: )')
    matches = list(block_pattern.finditer(chat))
    messages: list[t.Union[SystemMessage, UserMessage, AssistantMessage, ToolMessage]] = [system_message]
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(chat)
        prefix = match.group(1)
        segment = chat[match.end():end]
        if prefix == 'USER: ':
            messages.append(UserMessage([TextContent(segment.strip())]))
        elif prefix == 'FUNCTION RESPONSE: ':
            messages.append(ToolMessage([TextContent(segment.strip())]))
        elif prefix == 'ASSISTANT: ':
            payload = segment
            tool_calls: list[ToolCall] = []
            text_parts: list[str] = []
            for i, part in enumerate(payload.split('<functioncall>')):
                if i == 0:
                    text_parts.append(part)
                    continue
                blob, _, rest = part.partition('<|endoftext|>')
                if blob.strip():
                    tool_calls.append(_parse_function_call(blob))
                text_parts.append(rest)
            text = '\n'.join(p.strip() for p in text_parts if p.strip()).strip()
            messages.append(AssistantMessage(TextContent(text), tool_calls))
    return Conversation(messages, tools)
