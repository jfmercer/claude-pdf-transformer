"""Balanced page-range math and pypdf-based split writing."""

import math
from pathlib import Path

from pypdf import PdfReader, PdfWriter

type PageRange = tuple[int, int]
"""Half-open, zero-based ``(start, end)`` page range."""


def balanced_ranges(total_pages: int, num_parts: int) -> list[PageRange]:
    """Split ``total_pages`` into ``num_parts`` contiguous ranges of near-equal size.

    Earlier parts receive the remainder, so sizes differ by at most one page
    and page order is preserved (e.g. 250 pages into 3 parts -> 84/83/83).
    """
    if num_parts < 1:
        raise ValueError("num_parts must be at least 1")
    if total_pages < num_parts:
        raise ValueError(f"cannot split {total_pages} pages into {num_parts} parts")
    base, extra = divmod(total_pages, num_parts)
    ranges: list[PageRange] = []
    start = 0
    for i in range(num_parts):
        size = base + (1 if i < extra else 0)
        ranges.append((start, start + size))
        start += size
    return ranges


def ranges_for_page_limit(total_pages: int, max_pages: int) -> list[PageRange]:
    """Return the fewest balanced ranges such that every part has < ``max_pages`` pages."""
    if max_pages < 2:
        raise ValueError("max_pages must be at least 2")
    num_parts = math.ceil(total_pages / (max_pages - 1))
    return balanced_ranges(total_pages, num_parts)


def write_page_range(src: Path, dest: Path, start: int, end: int) -> None:
    """Write pages ``[start, end)`` of ``src`` to ``dest``."""
    reader = PdfReader(src)
    writer = PdfWriter()
    writer.append(reader, pages=(start, end))
    with dest.open("wb") as fh:
        writer.write(fh)
