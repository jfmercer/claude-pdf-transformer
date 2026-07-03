import pytest
from pypdf import PdfWriter

from pdf_transformer.inspector import (
    CorruptPdfError,
    EncryptedPdfError,
    inspect_pdf,
)
from tests.conftest import make_blank_pdf, make_corrupt_pdf, make_encrypted_pdf


def test_reports_page_count_and_size(tmp_path):
    path = make_blank_pdf(tmp_path / "doc.pdf", pages=7)
    info = inspect_pdf(path)
    assert info.pages == 7
    assert info.size_bytes == path.stat().st_size
    assert info.path == path


def test_encrypted_pdf_raises(tmp_path):
    path = make_encrypted_pdf(tmp_path / "locked.pdf")
    with pytest.raises(EncryptedPdfError, match="encrypted"):
        inspect_pdf(path)


def test_corrupt_pdf_raises(tmp_path):
    path = make_corrupt_pdf(tmp_path / "broken.pdf")
    with pytest.raises(CorruptPdfError):
        inspect_pdf(path)


def test_empty_file_raises(tmp_path):
    path = tmp_path / "empty.pdf"
    path.write_bytes(b"")
    with pytest.raises(CorruptPdfError):
        inspect_pdf(path)


def test_zero_page_pdf_raises(tmp_path):
    path = tmp_path / "nopages.pdf"
    with path.open("wb") as fh:
        PdfWriter().write(fh)
    with pytest.raises(CorruptPdfError, match="no pages"):
        inspect_pdf(path)
