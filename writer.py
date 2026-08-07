from classes import *
from config import *
from pathlib import Path
import typing as t
import pyarrow as pa
import pyarrow.parquet as pq
import json


def _load_existing_sources() -> set[str]:
    if USED_SOURCES_LOCATION.exists():
        with open(USED_SOURCES_LOCATION, 'r') as f:
            return {line.strip() for line in f if line.strip()}
    return set()


_seen_sources: set[str] = _load_existing_sources()


def _register_source(source: str) -> None:
    if source in _seen_sources:
        return
    USED_SOURCES_LOCATION.parent.mkdir(parents=True, exist_ok=True)
    with open(USED_SOURCES_LOCATION, 'a') as f:
        f.write(source + '\n')
    _seen_sources.add(source)


FILE_SIZE_LIMIT = 4_000_000_000

CHAT_SCHEMA = pa.schema([
    ('messages',     pa.string()),
    ('source',       pa.string()),
    ('collected_at', pa.string()),
    ('ai_enhanced',  pa.bool_()),
])

TEXT_SCHEMA = pa.schema([
    ('text',         pa.string()),
    ('source',       pa.string()),
    ('collected_at', pa.string()),
    ('ai_enhanced',  pa.bool_()),
])

_active_writers: dict[Path, tuple[pq.ParquetWriter, Path]] = {}


def _next_shard_path(location: Path) -> Path:
    location.mkdir(parents=True, exist_ok=True)
    existing = sorted(location.glob('*.parquet'))
    if not existing:
        return location / '00001.parquet'
    last_index = int(existing[-1].stem)
    return location / f'{last_index + 1:05d}.parquet'


def _get_writer(location: Path, schema: pa.Schema) -> pq.ParquetWriter:
    if location in _active_writers:
        writer, file_path = _active_writers[location]
        if file_path.stat().st_size < FILE_SIZE_LIMIT:
            return writer
        writer.close()
        del _active_writers[location]
    file_path = _next_shard_path(location)
    writer = pq.ParquetWriter(str(file_path), schema, compression='snappy')
    _active_writers[location] = (writer, file_path)
    return writer


def _to_table(data: t.Union[ChatEntry, TextEntry]) -> tuple[pa.Table, pa.Schema]:
    d = data.__dict__()
    if isinstance(data, ChatEntry):
        return (
            pa.table(
                {
                    'messages':     [json.dumps(d['messages'])],
                    'source':       [d['source']],
                    'collected_at': [d['collected_at']],
                    'ai_enhanced':  [d['ai_enhanced']],
                },
                schema=CHAT_SCHEMA,
            ),
            CHAT_SCHEMA,
        )
    return (
        pa.table(
            {
                'text':         [d['text']],
                'source':       [d['source']],
                'collected_at': [d['collected_at']],
                'ai_enhanced':  [d['ai_enhanced']],
            },
            schema=TEXT_SCHEMA,
        ),
        TEXT_SCHEMA,
    )


def save(data: t.Union[ChatEntry, TextEntry]) -> None:
    if isinstance(data, ChatEntry):
        location = CHAT_ENTRY_LOCATION
    elif isinstance(data, TextEntry):
        location = TEXT_ENTRY_LOCATION
    else:
        raise ValueError('data must be either ChatEntry or TextEntry')
    _register_source(data.source)
    location.mkdir(parents=True, exist_ok=True)
    table, schema = _to_table(data)
    writer = _get_writer(location, schema)
    writer.write_table(table)


def close_all() -> None:
    for writer, _ in _active_writers.values():
        writer.close()
    _active_writers.clear()
