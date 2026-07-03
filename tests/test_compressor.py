import shutil
from pathlib import Path

import pytest
from pypdf import PdfReader

from pdf_transformer.compressor import (
    GS_INSTALL_HINT,
    GhostscriptNotFoundError,
    compress_pdf,
    find_ghostscript,
)
from tests.conftest import make_image_pdf

gs_required = pytest.mark.skipif(shutil.which("gs") is None, reason="Ghostscript not installed")


def test_not_found_error_includes_install_hint() -> None:
    err = GhostscriptNotFoundError()
    assert "brew install ghostscript" in str(err)
    assert "apt-get install ghostscript" in str(err)
    assert str(err) == GS_INSTALL_HINT


def test_failed_process_returns_false(tmp_path: Path) -> None:
    src = make_image_pdf(tmp_path / "in.pdf", px=50)
    dest = tmp_path / "out.pdf"
    assert compress_pdf(src, dest, "/ebook", "/usr/bin/false") is False


def test_missing_output_returns_false(tmp_path: Path) -> None:
    src = make_image_pdf(tmp_path / "in.pdf", px=50)
    dest = tmp_path / "out.pdf"
    assert compress_pdf(src, dest, "/ebook", "/usr/bin/true") is False


@gs_required
def test_real_ghostscript_shrinks_image_pdf(tmp_path: Path) -> None:
    gs = find_ghostscript()
    assert gs is not None
    src = make_image_pdf(tmp_path / "big.pdf", pages=2, px=1200)
    dest = tmp_path / "small.pdf"
    assert compress_pdf(src, dest, "/screen", gs) is True
    assert dest.stat().st_size < src.stat().st_size
    assert len(PdfReader(dest).pages) == 2


@gs_required
def test_real_ghostscript_rejects_corrupt_input(tmp_path: Path) -> None:
    gs = find_ghostscript()
    assert gs is not None
    # No %PDF header at all — Ghostscript repairs mildly damaged PDFs, so the
    # input must be entirely unparseable to exercise the failure path.
    src = tmp_path / "broken.pdf"
    src.write_bytes(b"this is not a pdf in any way")
    dest = tmp_path / "out.pdf"
    assert compress_pdf(src, dest, "/ebook", gs) is False
