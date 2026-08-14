import sys
sys.path.extend(['/home/lena/Documents/python/distilled-web', '/home/lena/Documents/python/distilled-web/parsers/ch/admin/fedlex/www/filestore'])
import _101


def parse(url: str):
    if url == 'https://www.fedlex.admin.ch/filestore/fedlex.data.admin.ch/eli/cc/1999/404/20240303/de/html/fedlex-data-admin-ch-eli-cc-1999-404-20240303-de-html-10.html':
        _101.parse(url)
    else:
        raise ValueError(f"Unsupported url: {url}")
