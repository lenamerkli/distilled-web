"""MinerU2.5-Pro PDF-to-Markdown extraction using the `transformers` backend.

This module wraps `mineru-vl-utils` so a whole PDF can be turned into Markdown.
The model, processor and client are loaded lazily once and reused across calls.
"""

from functools import lru_cache
from pathlib import Path

from pdf2image import convert_from_path

MODEL_NAME = "opendatalab/MinerU2.5-Pro-2605-1.2B"
PDF_DPI = 144


@lru_cache(maxsize=1)
def _client():
    """Load the MinerU2.5-Pro model/processor/client once (singleton)."""
    from transformers import AutoProcessor, Qwen2VLForConditionalGeneration
    from mineru_vl_utils import MinerUClient

    model = Qwen2VLForConditionalGeneration.from_pretrained(
        MODEL_NAME, dtype="auto", device_map="auto"
    )
    processor = AutoProcessor.from_pretrained(MODEL_NAME, use_fast=True)
    return MinerUClient(
        backend="transformers",
        model=model,
        processor=processor,
        image_analysis=False,  # set True to enable image/chart analysis
    )


def pdf_to_markdown(
    pdf_path: str,
    max_pages: int | None = None,
    dpi: int = PDF_DPI,
) -> str:
    """Convert a PDF into Markdown via MinerU2.5-Pro.

    Args:
        pdf_path: Path to the PDF file.
        max_pages: Optional cap on the number of pages to process (None = all).
        dpi: Render resolution for page images fed to the model.

    Returns:
        The concatenated Markdown of all processed pages.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    from mineru_vl_utils.post_process import json2md

    images = convert_from_path(
        str(path),
        dpi=dpi,
        first_page=1,
        last_page=max_pages,
    )

    client = _client()
    pages: list[str] = []
    for index, image in enumerate(images, start=1):
        print(f"MinerU: extracting page {index}/{len(images)}")
        content_list = client.two_step_extract(image)
        pages.append(json2md(content_list))

    return "\n\n".join(pages)
