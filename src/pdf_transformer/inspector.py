"""Inspect PDF files: page count, byte size, and validity checks."""

from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader


class PdfInspectionError(Exception):
    """Base error for PDFs that cannot be processed."""


class EncryptedPdfError(PdfInspectionError):
    """The PDF is password-protected and cannot be read."""


class CorruptPdfError(PdfInspectionError):
    """The file cannot be parsed as a valid PDF."""


@dataclass(frozen=True)
class PdfInfo:
    path: Path
    pages: int
    size_bytes: int


def inspect_pdf(path: Path) -> PdfInfo:
    """Return page count and size for ``path``.

    Raises :class:`EncryptedPdfError` for password-protected files and
    :class:`CorruptPdfError` for files pypdf cannot parse.
    """
    size_bytes = path.stat().st_size
    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise EncryptedPdfError(f"{path.name} is encrypted/password-protected")
        pages = len(reader.pages)
    except PdfInspectionError:
        raise
    except Exception as exc:
        raise CorruptPdfError(f"{path.name} could not be parsed as a PDF: {exc}") from exc
    if pages == 0:
        raise CorruptPdfError(f"{path.name} contains no pages")
    return PdfInfo(path=path, pages=pages, size_bytes=size_bytes)
