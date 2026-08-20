"""Full MinerU PDF-to-Markdown extraction wrapper.

This module invokes the MinerU CLI to convert documents (PDFs, images, etc.) into Markdown.
It automatically resolves the MinerU binary from local virtual environments (such as `.venv-mineru`)
or the system PATH.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile

# Predefined paths to look for the mineru binary
_PROJECT_ROOT = Path(__file__).resolve().parent
_CANDIDATE_BINARIES = [
    _PROJECT_ROOT / ".venv-mineru" / "bin" / "mineru",
    _PROJECT_ROOT / ".venv" / "bin" / "mineru",
]


def _find_mineru_executable() -> str:
    """Locate the mineru CLI executable."""
    # Check custom environment variable override first if set
    custom_bin = os.environ.get("MINERU_BIN")
    if custom_bin and Path(custom_bin).is_file():
        return custom_bin

    for candidate in _CANDIDATE_BINARIES:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)

    which_bin = shutil.which("mineru")
    if which_bin:
        return which_bin

    raise FileNotFoundError(
        "Could not find the 'mineru' executable. "
        "Please ensure it is installed in .venv-mineru or available in PATH."
    )


def pdf_to_markdown(
    pdf_path: str | Path,
    output_dir: str | Path | None = None,
    max_pages: int | None = None,
    start_page: int | None = None,
    backend: str = "vlm-engine",
    effort: str = "high",
    image_analysis: bool | None = None,
    method: str | None = None,
    lang: str | None = None,
    formula: bool = True,
    table: bool = True,
) -> str:
    """Convert a PDF to Markdown using the full MinerU pipeline.

    Args:
        pdf_path: Path to the input PDF file.
        output_dir: Directory where MinerU output files (Markdown, images, JSONs) are stored.
                    If None, a temporary directory is used and cleaned up after reading.
        max_pages: Optional cap on the number of pages to process. (e.g. max_pages=5 processes pages 0..4).
        start_page: Optional 0-based starting page index.
        backend: MinerU backend ('hybrid-engine', 'vlm-engine', 'pipeline', etc.).
        effort: Hybrid parsing effort ('medium' or 'high').
        image_analysis: Enable image/chart analysis.
        method: Method for parsing PDF ('auto', 'txt', 'ocr').
        lang: Language hint for OCR ('ch', 'korean', etc.).
        formula: Enable formula parsing.
        table: Enable table parsing.

    Returns:
        The generated Markdown string.
    """
    path = Path(pdf_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"PDF not found: {path}")

    if max_pages is not None and max_pages < 1:
        raise ValueError("max_pages must be at least 1")
    if start_page is not None and start_page < 0:
        raise ValueError("start_page must be non-negative")

    mineru_bin = _find_mineru_executable()

    is_temp_output = output_dir is None
    temp_dir_obj: tempfile.TemporaryDirectory | None = None

    if is_temp_output:
        temp_dir_obj = tempfile.TemporaryDirectory()
        target_output = Path(temp_dir_obj.name)
    else:
        target_output = Path(output_dir).expanduser().resolve()
        target_output.mkdir(parents=True, exist_ok=True)

    try:
        command = [
            mineru_bin,
            "-p",
            str(path),
            "-o",
            str(target_output),
            "-b",
            backend,
        ]

        if backend.startswith("hybrid"):
            command.extend(["--effort", effort])

        if start_page is not None:
            command.extend(["-s", str(start_page)])

        # MinerU's page indexes are zero-based and --end is inclusive.
        if max_pages is not None:
            start_offset = start_page or 0
            end_page = start_offset + max_pages - 1
            command.extend(["-e", str(end_page)])

        if image_analysis is not None:
            command.extend(["--image-analysis", str(image_analysis).lower()])

        if method is not None:
            command.extend(["-m", method])

        if lang is not None:
            command.extend(["-l", lang])

        if not formula:
            command.extend(["-f", "false"])

        if not table:
            command.extend(["-t", "false"])

        env = {**os.environ, "VLLM_USE_FLASHINFER_SAMPLER": "0"}
        subprocess.run(command, check=True, env=env)

        # Locate the generated markdown file
        markdown_files = list(target_output.rglob(f"{path.stem}.md"))
        if not markdown_files:
            # Fallback in case the output filename stem differs slightly or subfolder structure varies
            markdown_files = list(target_output.rglob("*.md"))

        if not markdown_files:
            raise RuntimeError(
                f"MinerU completed but no Markdown file was found under {target_output}"
            )

        if len(markdown_files) > 1:
            markdown_files.sort(
                key=lambda candidate: candidate.stat().st_mtime_ns,
                reverse=True,
            )

        markdown_path = markdown_files[0]
        return markdown_path.read_text(encoding="utf-8")

    finally:
        if temp_dir_obj is not None:
            temp_dir_obj.cleanup()
