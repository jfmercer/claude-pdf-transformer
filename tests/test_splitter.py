from pathlib import Path

import pytest
from pypdf import PdfReader

from pdf_transformer.splitter import balanced_ranges, ranges_for_page_limit, write_page_range
from tests.conftest import make_blank_pdf, page_indices


class TestBalancedRanges:
    def test_even_division(self) -> None:
        assert balanced_ranges(10, 2) == [(0, 5), (5, 10)]

    def test_remainder_goes_to_earlier_parts(self) -> None:
        assert balanced_ranges(250, 3) == [(0, 84), (84, 167), (167, 250)]

    def test_single_part(self) -> None:
        assert balanced_ranges(5, 1) == [(0, 5)]

    def test_ranges_are_contiguous_and_cover_all_pages(self) -> None:
        ranges = balanced_ranges(101, 7)
        assert ranges[0][0] == 0
        assert ranges[-1][1] == 101
        for (_, prev_end), (next_start, _) in zip(ranges, ranges[1:], strict=False):
            assert prev_end == next_start

    def test_invalid_inputs(self) -> None:
        with pytest.raises(ValueError):
            balanced_ranges(5, 0)
        with pytest.raises(ValueError):
            balanced_ranges(2, 3)


class TestRangesForPageLimit:
    def test_typical_split(self) -> None:
        ranges = ranges_for_page_limit(250, 100)
        sizes = [end - start for start, end in ranges]
        assert sizes == [84, 83, 83]
        assert all(size < 100 for size in sizes)

    def test_exactly_at_limit_splits_in_two(self) -> None:
        ranges = ranges_for_page_limit(100, 100)
        assert [end - start for start, end in ranges] == [50, 50]

    def test_just_under_limit_is_one_part(self) -> None:
        assert ranges_for_page_limit(99, 100) == [(0, 99)]

    def test_max_pages_must_be_at_least_two(self) -> None:
        with pytest.raises(ValueError):
            ranges_for_page_limit(10, 1)


class TestWritePageRange:
    def test_page_counts_and_order_preserved(self, tmp_path: Path) -> None:
        src = make_blank_pdf(tmp_path / "src.pdf", pages=10)
        first = tmp_path / "a.pdf"
        second = tmp_path / "b.pdf"
        write_page_range(src, first, 0, 6)
        write_page_range(src, second, 6, 10)
        assert len(PdfReader(first).pages) == 6
        assert len(PdfReader(second).pages) == 4
        assert page_indices(first) == [0, 1, 2, 3, 4, 5]
        assert page_indices(second) == [6, 7, 8, 9]
