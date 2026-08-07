from urllib.parse import urlparse
from pathlib import Path
from collections import defaultdict
from importlib import import_module
from config import USED_SOURCES_LOCATION
from writer import close_all
from time import sleep


def order_urls(urls: list[str]) -> list[str]:
    """Sort URLs alphabetically, then round-robin interleave by domain so
    same-domain URLs are spaced as far apart as possible."""
    urls = sorted(urls)

    # Group URLs by domain while preserving alphabetical order within each group
    groups: dict[str, list[str]] = defaultdict(list)
    for url in urls:
        domain = urlparse(url).netloc
        groups[domain].append(url)

    # Round-robin interleave
    domain_keys = list(groups.keys())
    result: list[str] = []
    indices = {k: 0 for k in domain_keys}
    total = len(urls)

    while len(result) < total:
        for domain in domain_keys:
            if indices[domain] < len(groups[domain]):
                result.append(groups[domain][indices[domain]])
                indices[domain] += 1

    return result


def _load_existing_sources() -> set[str]:
    """Load the set of already-parsed source identifiers."""
    if USED_SOURCES_LOCATION.exists():
        with open(USED_SOURCES_LOCATION, 'r') as f:
            return {line.strip() for line in f if line.strip()}
    return set()


def _url_to_candidate_module_paths(url: str) -> list[str]:
    """Build candidate parser module paths from most specific to least specific.

    Reverses dot-separated domain parts and progressively shortens the path.
    Example: https://huggingface.co/datasets/lenamerkli/LLMinstruct
    → parsers.co.huggingface.datasets.lenamerkli.LLMinstruct.parser
    → parsers.co.huggingface.datasets.lenamerkli.parser
    → parsers.co.huggingface.datasets.parser
    → parsers.co.huggingface.parser
    """
    parsed = urlparse(url)
    # Reverse domain: huggingface.co → co.huggingface
    domain_parts = parsed.netloc.split('.')
    reversed_domain = '.'.join(reversed(domain_parts))

    # Non-empty path segments
    path_parts = [seg for seg in parsed.path.split('/') if seg]

    candidates: list[str] = []
    for i in range(len(path_parts), -1, -1):
        parts = [reversed_domain] + path_parts[:i]
        module_path = 'parsers.' + '.'.join(parts) + '.parser'
        candidates.append(module_path)

    return candidates


def _find_parser_module(url: str) -> str | None:
    """Find the first existing parser module for a URL, or None."""
    candidates = _url_to_candidate_module_paths(url)
    project_root = Path(__file__).resolve().parent
    for module_name in candidates:
        # Convert module path to file path
        rel_path = module_name.replace('.', '/') + '.py'
        if (project_root / rel_path).exists():
            return module_name
    return None


def main():
    with open('urls.txt', 'r') as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    # Remove duplicates while preserving order
    seen: set[str] = set()
    unique_urls: list[str] = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)

    # Filter out already-parsed URLs
    existing_sources = _load_existing_sources()
    new_urls = [url for url in unique_urls if url not in existing_sources]

    if not new_urls:
        print("No new URLs to process.")
        return

    ordered_urls = order_urls(new_urls)

    total = len(ordered_urls)
    processed = 0
    skipped = 0
    failed = 0

    try:
        for i, url in enumerate(ordered_urls, 1):
            print(f"[{i}/{total}] {url}")

            module_name = _find_parser_module(url)
            if module_name is None:
                print(f"  ⚠ No parser found for {url}, skipping.")
                skipped += 1
                continue
            sleep(0.2)
            try:
                parser = import_module(module_name)
                parser.parse(url)
                processed += 1
                print(f"  ✓ Done (parser: {module_name})")
            except Exception as e:
                print(f"  ✗ Failed: {e}")
                failed += 1
                continue
    finally:
        close_all()

    print()
    print(f"Summary: {processed} processed, {skipped} skipped, {failed} failed")


if __name__ == '__main__':
    main()
