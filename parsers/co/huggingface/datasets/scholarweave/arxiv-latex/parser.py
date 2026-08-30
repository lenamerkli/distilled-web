import sys
sys.path.append('/home/lena/Documents/python/distilled-web')
from shutil import rmtree
from subprocess import run
from classes import *
from config import *
from writer import save
import pyarrow.parquet as pq


def parse(url: str):
    if url != 'https://huggingface.co/datasets/scholarweave/arxiv-latex':
        raise ValueError('Can only parse this exact URL: `https://huggingface.co/datasets/scholarweave/arxiv-latex`')
    temp_dir = TMP_LOCATION / 'co.huggingface.datasets.scholarweave.arxiv-latex'
    if temp_dir.exists():
        rmtree(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)
    command = ['git', 'clone', '--single-branch', '--branch', 'main', '--depth', '1', url, str(temp_dir)]
    run(command, check=True, cwd=temp_dir)
    data_files = (temp_dir / 'data').glob('*.parquet')
    for data_file in data_files:
        pf = pq.ParquetFile(data_file)
        for batch in pf.iter_batches(columns=['latex'], batch_size=512):
            records = batch.to_pydict()
            for record in records['latex']:
                if isinstance(record, str) and len(record) > 256:
                    save(TextEntry(record, url))
