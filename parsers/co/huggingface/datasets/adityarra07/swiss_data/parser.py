import sys
sys.path.append('/home/lena/Documents/python/distilled-web')
from shutil import rmtree
from subprocess import run
from classes import *
from config import *
from writer import save
import pyarrow.parquet as pq


PROMPT = 'Transcribe the audio. Lowercase only.'


def parse(url: str):
    if url != 'https://huggingface.co/datasets/adityarra07/swiss_data':
        raise ValueError('Can only parse this exact URL: `https://huggingface.co/datasets/adityarra07/swiss_data`')
    temp_dir = TMP_LOCATION / 'co.huggingface.datasets.adityarra07.swiss_data'
    if not temp_dir.exists():
        temp_dir.mkdir(parents=True, exist_ok=True)
        command = ['git', 'clone', '--single-branch', '--branch', 'main', '--depth', '1', url, str(temp_dir)]
        run(command, check=True, cwd=temp_dir)
    data_path = temp_dir / 'data' / 'test-00000-of-00001-77e5d9454d802751.parquet'
    pf = pq.ParquetFile(str(data_path))
    for batch in pf.iter_batches(batch_size=500):
        records = batch.to_pydict()
        for i in range(len(records['audio'])):
            audio = records['audio'][i]
            if not audio or not audio.get('bytes'):
                continue
            transcription = records['transcription'][i]
            if not transcription:
                continue
            audio_content = MediaContent('audio', content=audio['bytes'])
            entry = ChatEntry(
                Conversation([
                    UserMessage([TextContent(PROMPT), audio_content]),
                    AssistantMessage(TextContent(transcription.lower())),
                ]),
                source=url,
            )
            save(entry)
    rmtree(temp_dir)
