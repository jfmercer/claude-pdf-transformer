import sys
from pathlib import Path

import pytest
from pypdf import PdfReader

from pdf_transformer import compressor
from pdf_transformer.compressor import (
    GS_INSTALL_HINT,
    GhostscriptNotFoundError,
    compress_pdf,
    find_ghostscript,
)
from tests.conftest import gs_required, make_image_pdf


def _fake_gs(tmp_path: Path, exit_code: int) -> str:
    """Write a throwaway executable that exits with ``exit_code``, standing in for ``gs``."""
    script = tmp_path / "fake_gs"
    script.write_text(f"#!{sys.executable}\nimport sys\nsys.exit({exit_code})\n")
    script.chmod(0o755)
    return str(script)


def _fake_gs_sleep(tmp_path: Path, seconds: float) -> str:
    """Write a throwaway executable that sleeps, standing in for a hung ``gs``."""
    script = tmp_path / "fake_gs_slow"
    script.write_text(f"#!{sys.executable}\nimport time\ntime.sleep({seconds})\n")
    script.chmod(0o755)
    return str(script)


def test_not_found_error_includes_install_hint() -> None:
    err = GhostscriptNotFoundError()
    assert "brew install ghostscript" in str(err)
    assert "apt-get install ghostscript" in str(err)
    assert str(err) == GS_INSTALL_HINT


def test_failed_process_returns_false(tmp_path: Path) -> None:
    src = make_image_pdf(tmp_path / "in.pdf", px=50)
    dest = tmp_path / "out.pdf"
    fake_gs = _fake_gs(tmp_path, exit_code=1)
    assert compress_pdf(src, dest, "/ebook", fake_gs) is False


def test_missing_output_returns_false(tmp_path: Path) -> None:
    src = make_image_pdf(tmp_path / "in.pdf", px=50)
    dest = tmp_path / "out.pdf"
    fake_gs = _fake_gs(tmp_path, exit_code=0)
    assert compress_pdf(src, dest, "/ebook", fake_gs) is False


def test_timeout_returns_false(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(compressor, "_TIMEOUT_SECONDS", 0.1)
    src = make_image_pdf(tmp_path / "in.pdf", px=50)
    dest = tmp_path / "out.pdf"
    fake_gs = _fake_gs_sleep(tmp_path, seconds=5)
    assert compress_pdf(src, dest, "/ebook", fake_gs) is False


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
