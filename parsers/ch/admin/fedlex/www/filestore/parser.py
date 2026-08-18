import sys
sys.path.extend(['/home/lena/Documents/python/distilled-web', '/home/lena/Documents/python/distilled-web/parsers/ch/admin/fedlex/www/filestore'])
import _101
import _112
import _210
import _220
import _235_1
import _311
import _312


def parse(url: str):
    if url == 'https://www.fedlex.admin.ch/filestore/fedlex.data.admin.ch/eli/cc/1999/404/20240303/de/html/fedlex-data-admin-ch-eli-cc-1999-404-20240303-de-html-10.html':
        _101.parse(url)
    elif url == 'https://www.fedlex.admin.ch/filestore/fedlex.data.admin.ch/eli/cc/1/600_559_600/18750702/de/html/fedlex-data-admin-ch-eli-cc-1-600_559_600-18750702-de-html-6.html':
        _112.parse(url)
    elif url == 'https://www.fedlex.admin.ch/filestore/fedlex.data.admin.ch/eli/cc/24/233_245_233/20260701/de/html/fedlex-data-admin-ch-eli-cc-24-233_245_233-20260701-de-html-2.html':
        _210.parse(url)
    elif url == 'https://www.fedlex.admin.ch/filestore/fedlex.data.admin.ch/eli/cc/27/317_321_377/20260101/de/html/fedlex-data-admin-ch-eli-cc-27-317_321_377-20260101-de-html-12.html':
        _220.parse(url)
    elif url == 'https://www.fedlex.admin.ch/filestore/fedlex.data.admin.ch/eli/cc/2022/491/20250707/de/html/fedlex-data-admin-ch-eli-cc-2022-491-20250707-de-html-1.html':
        _235_1.parse(url)
    elif url == 'https://www.fedlex.admin.ch/filestore/fedlex.data.admin.ch/eli/cc/54/757_781_799/20260612/de/html/fedlex-data-admin-ch-eli-cc-54-757_781_799-20260612-de-html.html':
        _311.parse(url)
    elif url == 'https://www.fedlex.admin.ch/filestore/fedlex.data.admin.ch/eli/cc/2010/267/20250401/de/html/fedlex-data-admin-ch-eli-cc-2010-267-20250401-de-html-4.html':
        _312.parse(url)
    else:
        raise ValueError(f"Unsupported url: {url}")
