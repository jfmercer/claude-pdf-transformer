import logging
import shutil
from collections.abc import Iterable
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

from pdf_transformer import compressor, pipeline
from pdf_transformer.inspector import inspect_pdf
from tests.conftest import (
    gs_required,
    make_blank_pdf,
    make_corrupt_pdf,
    make_encrypted_pdf,
    make_image_pdf,
    make_noisy_pdf,
    page_indices,
)

MB = 1024 * 1024


@pytest.fixture
def compression_effective(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend Ghostscript shrinks any file to a tiny 1-page PDF."""

    def fake(src: Path, dest: Path, preset: str, gs_path: str) -> bool:
        make_blank_pdf(dest, pages=1)
        return True

    monkeypatch.setattr(compressor, "compress_pdf", fake)
    monkeypatch.setattr(compressor, "find_ghostscript", lambda: "gs")


@pytest.fixture
def compression_ineffective(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend Ghostscript runs fine but achieves no size reduction."""

    def fake(src: Path, dest: Path, preset: str, gs_path: str) -> bool:
        shutil.copyfile(src, dest)
        return True

    monkeypatch.setattr(compressor, "compress_pdf", fake)
    monkeypatch.setattr(compressor, "find_ghostscript", lambda: "gs")


@pytest.fixture
def compression_effective_screen_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend /ebook is insufficient but /screen shrinks the file enough."""

    def fake(src: Path, dest: Path, preset: str, gs_path: str) -> bool:
        if preset == "/ebook":
            shutil.copyfile(src, dest)
        else:
            make_blank_pdf(dest, pages=1)
        return True

    monkeypatch.setattr(compressor, "compress_pdf", fake)
    monkeypatch.setattr(compressor, "find_ghostscript", lambda: "gs")


@pytest.fixture
def compression_first_preset_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend /ebook fails outright (as Ghostscript itself might) but /screen succeeds."""

    def fake(src: Path, dest: Path, preset: str, gs_path: str) -> bool:
        if preset == "/ebook":
            return False
        make_blank_pdf(dest, pages=1)
        return True

    monkeypatch.setattr(compressor, "compress_pdf", fake)
    monkeypatch.setattr(compressor, "find_ghostscript", lambda: "gs")


@pytest.fixture
def compression_partially_effective(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend Ghostscript shrinks the file (by dropping pages) but not below the limit."""

    def fake(src: Path, dest: Path, preset: str, gs_path: str) -> bool:
        reader = PdfReader(src)
        writer = PdfWriter()
        for page in reader.pages[: len(reader.pages) // 2]:
            writer.add_page(page)
        with dest.open("wb") as fh:
            writer.write(fh)
        return True

    monkeypatch.setattr(compressor, "compress_pdf", fake)
    monkeypatch.setattr(compressor, "find_ghostscript", lambda: "gs")


def all_output_page_indices(outputs: Iterable[Path]) -> list[int]:
    indices: list[int] = []
    for path in sorted(outputs, key=lambda p: p.name):
        indices.extend(page_indices(path))
    return indices


def test_compliant_pdf_copied_byte_identical(input_dir: Path, output_dir: Path) -> None:
    src = make_blank_pdf(input_dir / "ok.pdf", pages=3)
    summary = pipeline.process_directory(input_dir, output_dir, max_size_mb=30, max_pages=100)
    dest = output_dir / "ok.pdf"
    assert dest.read_bytes() == src.read_bytes()
    assert len(summary.copied_unchanged) == 1
    assert not summary.failed


def test_page_split_balanced_order_preserved(input_dir: Path, output_dir: Path) -> None:
    make_blank_pdf(input_dir / "big.pdf", pages=25)
    summary = pipeline.process_directory(input_dir, output_dir, max_size_mb=30, max_pages=10)
    outputs = sorted(output_dir.iterdir())
    assert [p.name for p in outputs] == ["big_part1.pdf", "big_part2.pdf", "big_part3.pdf"]
    sizes = [len(PdfReader(p).pages) for p in outputs]
    assert sizes == [9, 8, 8]
    assert all_output_page_indices(outputs) == list(range(25))
    assert len(summary.split) == 1
    assert not summary.failed


def test_oversized_pdf_compressed_keeps_name(
    input_dir: Path, output_dir: Path, compression_effective: None
) -> None:
    make_noisy_pdf(input_dir / "heavy.pdf", pages=3)
    summary = pipeline.process_directory(input_dir, output_dir, max_size_mb=0.05, max_pages=100)
    assert [p.name for p in output_dir.iterdir()] == ["heavy.pdf"]
    result = summary.results[0]
    assert result.was_compressed
    assert not result.was_split
    assert not summary.failed


def test_size_split_fallback_when_compression_insufficient(
    input_dir: Path, output_dir: Path, compression_ineffective: None
) -> None:
    make_noisy_pdf(input_dir / "stubborn.pdf", pages=8)
    max_size_mb = 0.1
    summary = pipeline.process_directory(
        input_dir, output_dir, max_size_mb=max_size_mb, max_pages=100
    )
    outputs = sorted(output_dir.iterdir())
    assert len(outputs) >= 2
    assert [p.name for p in outputs] == [
        f"stubborn_part{i}.pdf" for i in range(1, len(outputs) + 1)
    ]
    assert all(p.stat().st_size < max_size_mb * MB for p in outputs)
    assert all_output_page_indices(outputs) == list(range(8))
    result = summary.results[0]
    assert result.was_split
    assert not summary.failed


def test_single_page_over_limit_fails_without_output(
    input_dir: Path, output_dir: Path, compression_ineffective: None
) -> None:
    make_noisy_pdf(input_dir / "onepage.pdf", pages=1)
    summary = pipeline.process_directory(input_dir, output_dir, max_size_mb=0.01, max_pages=100)
    assert len(summary.failed) == 1
    error = summary.failed[0].error
    assert error is not None
    assert "single page" in error
    assert list(output_dir.iterdir()) == []


def test_mixed_directory_bad_files_skipped(input_dir: Path, output_dir: Path) -> None:
    ok = make_blank_pdf(input_dir / "ok.pdf", pages=3)
    make_blank_pdf(input_dir / "long.pdf", pages=12)
    make_encrypted_pdf(input_dir / "locked.pdf")
    make_corrupt_pdf(input_dir / "broken.pdf")
    (input_dir / "notes.txt").write_text("not a pdf")

    summary = pipeline.process_directory(input_dir, output_dir, max_size_mb=30, max_pages=5)

    assert len(summary.results) == 4
    assert len(summary.copied_unchanged) == 1
    assert len(summary.split) == 1
    assert len(summary.failed) == 2
    assert {r.source.name for r in summary.failed} == {"locked.pdf", "broken.pdf"}
    assert [p.name for p in summary.skipped_non_pdf] == ["notes.txt"]

    names = sorted(p.name for p in output_dir.iterdir())
    assert names == ["long_part1.pdf", "long_part2.pdf", "long_part3.pdf", "ok.pdf"]
    assert (output_dir / "ok.pdf").read_bytes() == ok.read_bytes()


def test_uppercase_pdf_extension_is_processed(input_dir: Path, output_dir: Path) -> None:
    make_blank_pdf(input_dir / "SHOUTY.PDF", pages=3)
    summary = pipeline.process_directory(input_dir, output_dir, max_size_mb=30, max_pages=100)
    assert summary.skipped_non_pdf == []
    assert len(summary.copied_unchanged) == 1
    assert (output_dir / "SHOUTY.PDF").exists()


def test_subdirectories_in_input_dir_are_ignored(input_dir: Path, output_dir: Path) -> None:
    make_blank_pdf(input_dir / "ok.pdf", pages=3)
    nested = input_dir / "nested.pdf"  # a directory, despite the name
    nested.mkdir()
    make_blank_pdf(nested / "inner.pdf", pages=3)
    summary = pipeline.process_directory(input_dir, output_dir, max_size_mb=30, max_pages=100)
    assert len(summary.results) == 1
    assert summary.skipped_non_pdf == []
    assert [p.name for p in output_dir.iterdir()] == ["ok.pdf"]


def test_write_outputs_never_moves_the_original(input_dir: Path, output_dir: Path) -> None:
    """Even if a piece is the untouched original (TOCTOU race), it must be copied, not moved."""
    src = make_blank_pdf(input_dir / "ok.pdf", pages=3)
    output_dir.mkdir()
    info = inspect_pdf(src)
    result = pipeline.FileResult(source=src)
    pipeline._write_outputs([src], info, output_dir, result)
    assert src.exists()
    assert (output_dir / "ok.pdf").read_bytes() == src.read_bytes()


def test_dry_run_writes_nothing(input_dir: Path, output_dir: Path) -> None:
    make_blank_pdf(input_dir / "ok.pdf", pages=3)
    make_blank_pdf(input_dir / "long.pdf", pages=200)
    summary = pipeline.process_directory(
        input_dir, output_dir, max_size_mb=30, max_pages=100, dry_run=True
    )
    assert not output_dir.exists()
    assert len(summary.results) == 2
    assert len(summary.split) == 1
    assert not summary.failed


def test_missing_ghostscript_recorded_as_failure(
    input_dir: Path, output_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(compressor, "find_ghostscript", lambda: None)
    make_noisy_pdf(input_dir / "heavy.pdf", pages=3)
    summary = pipeline.process_directory(input_dir, output_dir, max_size_mb=0.05, max_pages=100)
    assert len(summary.failed) == 1
    error = summary.failed[0].error
    assert error is not None
    assert "Ghostscript" in error


def test_empty_input_directory_logs_warning(
    input_dir: Path, output_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        summary = pipeline.process_directory(input_dir, output_dir, max_size_mb=30, max_pages=100)
    assert summary.results == []
    assert "No files found" in caplog.text


def test_dry_run_reports_size_driven_compression(
    input_dir: Path, output_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    make_noisy_pdf(input_dir / "heavy.pdf", pages=3)
    with caplog.at_level(logging.INFO):
        summary = pipeline.process_directory(
            input_dir, output_dir, max_size_mb=0.05, max_pages=100, dry_run=True
        )
    assert not output_dir.exists()
    result = summary.results[0]
    assert result.was_compressed
    assert "would compress" in caplog.text


def test_preset_fallback_to_screen_when_ebook_insufficient(
    input_dir: Path, output_dir: Path, compression_effective_screen_only: None
) -> None:
    make_noisy_pdf(input_dir / "heavy.pdf", pages=3)
    summary = pipeline.process_directory(input_dir, output_dir, max_size_mb=0.05, max_pages=100)
    assert [p.name for p in output_dir.iterdir()] == ["heavy.pdf"]
    result = summary.results[0]
    assert result.was_compressed
    assert not result.was_split
    assert not summary.failed


def test_preset_continues_after_ghostscript_failure(
    input_dir: Path, output_dir: Path, compression_first_preset_fails: None
) -> None:
    make_noisy_pdf(input_dir / "heavy.pdf", pages=3)
    summary = pipeline.process_directory(input_dir, output_dir, max_size_mb=0.05, max_pages=100)
    assert [p.name for p in output_dir.iterdir()] == ["heavy.pdf"]
    result = summary.results[0]
    assert result.was_compressed
    assert not summary.failed


def test_was_compressed_flag_set_when_compression_insufficient_then_split(
    input_dir: Path, output_dir: Path, compression_partially_effective: None
) -> None:
    make_noisy_pdf(input_dir / "stubborn.pdf", pages=8)
    summary = pipeline.process_directory(input_dir, output_dir, max_size_mb=0.05, max_pages=100)
    result = summary.results[0]
    assert result.was_compressed
    assert result.was_split
    assert not summary.failed
    assert len(list(output_dir.iterdir())) >= 2


@gs_required
def test_real_ghostscript_end_to_end_compression(input_dir: Path, output_dir: Path) -> None:
    src = make_image_pdf(input_dir / "photos.pdf", pages=2, px=1200)
    assert src.stat().st_size > 2 * MB
    summary = pipeline.process_directory(input_dir, output_dir, max_size_mb=2, max_pages=100)
    assert not summary.failed
    result = summary.results[0]
    assert result.was_compressed
    outputs = list(output_dir.iterdir())
    assert all(p.stat().st_size < 2 * MB for p in outputs)
    total_pages = sum(len(PdfReader(p).pages) for p in outputs)
    assert total_pages == 2
