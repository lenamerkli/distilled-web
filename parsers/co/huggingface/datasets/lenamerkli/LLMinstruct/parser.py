import sys
sys.path.append('/home/lena/Documents/python/distilled-web')
import json
from shutil import rmtree
from subprocess import run
from pathlib import Path
from classes import *
from config import *
from writer import save
import pyarrow.parquet as pq
from filetype import guess as guess_file_type


LOCAL_COPY = Path('/home/lena/Documents/huggingface/LLMinstruct')


def parse(url: str):
    if url != 'https://huggingface.co/datasets/lenamerkli/LLMinstruct':
        raise ValueError('Can only parse this exact URL: `https://huggingface.co/datasets/lenamerkli/LLMinstruct`')
    temp_dir = TMP_LOCATION / 'co.huggingface.datasets.lenamerkli.LLMinstruct'
    if LOCAL_COPY.exists():
        temp_dir.parent.mkdir(parents=True, exist_ok=True)
        if temp_dir.exists() or temp_dir.is_symlink():
            temp_dir.unlink()
        temp_dir.symlink_to(LOCAL_COPY)
    else:
        temp_dir.mkdir(parents=True, exist_ok=True)
        command = ['git', 'clone', '--single-branch', '--branch', 'main', '--depth', '1', 'https://huggingface.co/datasets/lenamerkli/LLMinstruct', str(temp_dir)]
        run(command, check=True, cwd=temp_dir)

    data_path = temp_dir / 'data.parquet'
    pf = pq.ParquetFile(str(data_path))

    for batch in pf.iter_batches(batch_size=500):
        records = batch.to_pydict()
        for i in range(len(records['messages'])):
            msgs, tools = _parse_messages(records['messages'][i], temp_dir)
            entry = ChatEntry(
                messages=Conversation(msgs, tools),
                source=url,
                ai_enhanced=records['mistakes'][i]
            )
            save(entry)

    if temp_dir.is_symlink():
        temp_dir.unlink()
    else:
        rmtree(temp_dir)


def _parse_tools(attachments: list) -> list[dict]:
    tools = []
    for att in attachments:
        if att.get('type') == 'application/json/tools':
            tools.extend(json.loads(att['value']))
    return tools


def _parse_messages(msgs: list, temp_dir: Path) -> tuple[list, list[dict]]:
    result = []
    tools: list[dict] = []
    for msg in msgs:
        role = msg.get('role', '')
        content_text = msg.get('content', '')
        attachments = msg.get('attachments', [])

        if role == 'system':
            tools.extend(_parse_tools(attachments))
            result.append(SystemMessage([TextContent(content_text)]))
        elif role == 'user':
            media = _parse_media(attachments, temp_dir)
            content: list = [TextContent(content_text)] if content_text else []
            content.extend(media)
            result.append(UserMessage(content))
        elif role == 'assistant':
            text = TextContent(content_text)
            tool_calls = _parse_tool_calls(attachments)
            result.append(AssistantMessage(text, tool_calls if tool_calls else None))
        elif role == 'tool':
            result.append(ToolMessage([TextContent(content_text)]))
    return result, tools


def _parse_tool_calls(attachments: list) -> list[ToolCall]:
    tool_calls = []
    for att in attachments:
        if att['type'] == 'application/json/tool_call':
            data = json.loads(att['value'])
            func = data['function']
            tool_calls.append(ToolCall(func['name'], func['arguments']))
    return tool_calls


def _parse_media(attachments: list, temp_dir: Path) -> list[MediaContent]:
    media = []
    for att in attachments:
        att_type = att.get('type', '')
        att_value = att.get('value', '')
        if att_type == 'application/pdf/sha256sum' or att_value.startswith('sha256sum:'):
            hash_val = att_value.replace('sha256sum:', '')
            file_path = temp_dir / 'attachments' / hash_val
            if file_path.exists():
                with open(file_path, 'rb') as f:
                    content = f.read()
                kind = guess_file_type(content)
                if kind and kind.mime:
                    mime_main = kind.mime.split('/')[0]
                    if mime_main in ('image', 'audio', 'video'):
                        media_type = mime_main
                    else:
                        media_type = 'other_media'
                else:
                    media_type = 'other_media'
                media.append(MediaContent(media_type, content=content))
    return media
