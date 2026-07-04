"""Programmatically generated PDF fixtures — no binary files are committed."""

import os
import shutil
from pathlib import Path
from typing import Final

import pytest
from pypdf import PdfWriter

BASE_WIDTH: Final = 500.0
PAGE_HEIGHT: Final = 700.0

gs_required = pytest.mark.skipif(shutil.which("gs") is None, reason="Ghostscript not installed")


def make_blank_pdf(path: Path, pages: int) -> Path:
    """Write a PDF of blank pages. Page ``i`` has width ``BASE_WIDTH + i``
    so tests can verify page order after splitting."""
    writer = PdfWriter()
    for i in range(pages):
        writer.add_blank_page(width=BASE_WIDTH + i, height=PAGE_HEIGHT)
    with path.open("wb") as fh:
        writer.write(fh)
    return path


def page_indices(path: Path) -> list[int]:
    """Recover the original page indices of a (possibly split) blank-pdf fixture."""
    from pypdf import PdfReader

    return [round(float(page.mediabox.width) - BASE_WIDTH) for page in PdfReader(path).pages]


def make_image_pdf(path: Path, pages: int = 1, px: int = 1200) -> Path:
    """Write a PDF with one random-noise image per page.

    Noise stores poorly under Flate, so the file is large; Ghostscript's
    JPEG recompression/downsampling shrinks it substantially.
    """
    from PIL import Image
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=letter)
    for _ in range(pages):
        img = Image.frombytes("RGB", (px, px), os.urandom(px * px * 3))
        c.drawImage(ImageReader(img), 0, 0, width=letter[0], height=letter[1])
        c.showPage()
    c.save()
    return path


def make_noisy_pdf(path: Path, pages: int, px: int = 100) -> Path:
    """Write a PDF whose size is dominated by per-page noise images (~30 KB each),
    so file size scales predictably with page count. Page ``i`` has width
    ``BASE_WIDTH + i`` so :func:`page_indices` can verify order after splits."""
    from PIL import Image
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path))
    for i in range(pages):
        c.setPageSize((BASE_WIDTH + i, PAGE_HEIGHT))
        img = Image.frombytes("RGB", (px, px), os.urandom(px * px * 3))
        c.drawImage(ImageReader(img), 0, 0, width=100, height=100)
        c.showPage()
    c.save()
    return path


def make_encrypted_pdf(path: Path, pages: int = 2) -> Path:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=BASE_WIDTH, height=PAGE_HEIGHT)
    writer.encrypt("secret")
    with path.open("wb") as fh:
        writer.write(fh)
    return path


def make_corrupt_pdf(path: Path) -> Path:
    path.write_bytes(b"%PDF-1.7\nthis is not a real pdf body")
    return path


@pytest.fixture
def input_dir(tmp_path: Path) -> Path:
    d = tmp_path / "input"
    d.mkdir()
    return d


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    return tmp_path / "out"
