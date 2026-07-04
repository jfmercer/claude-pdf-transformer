import logging
from importlib.metadata import version
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pdf_transformer import cli, compressor
from pdf_transformer.cli import app
from tests.conftest import make_blank_pdf, make_corrupt_pdf

runner = CliRunner()


def test_version_flag_prints_version_and_exits_zero() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert version("claude-pdf-transformer") in result.output


def test_happy_path_exit_zero(input_dir: Path, output_dir: Path) -> None:
    make_blank_pdf(input_dir / "ok.pdf", pages=3)
    result = runner.invoke(app, [str(input_dir), "--output-dir", str(output_dir)])
    assert result.exit_code == 0
    assert (output_dir / "ok.pdf").exists()


def test_custom_max_pages_triggers_split(input_dir: Path, output_dir: Path) -> None:
    make_blank_pdf(input_dir / "doc.pdf", pages=12)
    result = runner.invoke(
        app,
        [str(input_dir), "--output-dir", str(output_dir), "--max-pages", "5"],
    )
    assert result.exit_code == 0
    names = sorted(p.name for p in output_dir.iterdir())
    assert names == ["doc_part1.pdf", "doc_part2.pdf", "doc_part3.pdf"]


def test_dry_run_writes_nothing(input_dir: Path, output_dir: Path) -> None:
    make_blank_pdf(input_dir / "ok.pdf", pages=3)
    result = runner.invoke(app, [str(input_dir), "--output-dir", str(output_dir), "--dry-run"])
    assert result.exit_code == 0
    assert not output_dir.exists()


def test_missing_input_dir_fails(tmp_path: Path) -> None:
    result = runner.invoke(app, [str(tmp_path / "nope")])
    assert result.exit_code != 0


def test_output_dir_equal_to_input_dir_rejected(input_dir: Path) -> None:
    result = runner.invoke(app, [str(input_dir), "--output-dir", str(input_dir)])
    assert result.exit_code != 0


def test_max_size_must_be_positive(input_dir: Path, output_dir: Path) -> None:
    result = runner.invoke(
        app,
        [str(input_dir), "--output-dir", str(output_dir), "--max-size-mb", "0"],
    )
    assert result.exit_code != 0


def test_missing_ghostscript_exits_2(
    input_dir: Path, output_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(compressor, "find_ghostscript", lambda: None)
    make_blank_pdf(input_dir / "ok.pdf", pages=3)
    result = runner.invoke(app, [str(input_dir), "--output-dir", str(output_dir)])
    assert result.exit_code == 2


def test_failed_pdf_exits_1(input_dir: Path, output_dir: Path) -> None:
    make_corrupt_pdf(input_dir / "broken.pdf")
    result = runner.invoke(app, [str(input_dir), "--output-dir", str(output_dir)])
    assert result.exit_code == 1


def test_dry_run_with_missing_ghostscript_warns_but_continues(
    input_dir: Path,
    output_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(compressor, "find_ghostscript", lambda: None)
    make_blank_pdf(input_dir / "ok.pdf", pages=3)
    with caplog.at_level(logging.WARNING):
        result = runner.invoke(app, [str(input_dir), "--output-dir", str(output_dir), "--dry-run"])
    assert result.exit_code == 0
    assert "ghostscript" in caplog.text.lower()


def test_unexpected_pipeline_error_exits_1(
    input_dir: Path, output_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(cli, "process_directory", boom)
    make_blank_pdf(input_dir / "ok.pdf", pages=3)
    result = runner.invoke(app, [str(input_dir), "--output-dir", str(output_dir)])
    assert result.exit_code == 1
