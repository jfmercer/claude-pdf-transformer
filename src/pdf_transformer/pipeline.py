"""Per-file decision flow: split by pages, compress by size, finalize, summarize."""

import logging
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader

from pdf_transformer import compressor, splitter
from pdf_transformer.inspector import PdfInfo, PdfInspectionError, inspect_pdf

logger = logging.getLogger(__name__)

_MB = 1024 * 1024


class PieceTooLargeError(Exception):
    """A single page exceeds the size limit and cannot be reduced further."""


@dataclass
class FileResult:
    source: Path
    outputs: list[Path] = field(default_factory=list)
    was_split: bool = False
    was_compressed: bool = False
    error: str | None = None


@dataclass
class Summary:
    results: list[FileResult] = field(default_factory=list)
    skipped_non_pdf: list[Path] = field(default_factory=list)

    @property
    def failed(self) -> list[FileResult]:
        return [r for r in self.results if r.error]

    @property
    def split(self) -> list[FileResult]:
        return [r for r in self.results if r.was_split and not r.error]

    @property
    def compressed(self) -> list[FileResult]:
        return [r for r in self.results if r.was_compressed and not r.error]

    @property
    def copied_unchanged(self) -> list[FileResult]:
        return [r for r in self.results if not r.error and not r.was_split and not r.was_compressed]


def process_directory(
    input_dir: Path,
    output_dir: Path,
    *,
    max_size_mb: float,
    max_pages: int,
    dry_run: bool = False,
) -> Summary:
    """Process every file in ``input_dir``, writing compliant PDFs to ``output_dir``.

    Originals are never modified. Non-PDF, encrypted, and corrupt files are
    logged and skipped; one bad file never aborts the run.
    """
    max_bytes = int(max_size_mb * _MB)
    gs_path = compressor.find_ghostscript()
    summary = Summary()
    files = sorted(p for p in input_dir.iterdir() if p.is_file())
    if not files:
        logger.warning("No files found in %s", input_dir)
    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    for path in files:
        if path.suffix.lower() != ".pdf":
            logger.info("Skipping non-PDF file: %s", path.name)
            summary.skipped_non_pdf.append(path)
            continue
        try:
            info = inspect_pdf(path)
        except PdfInspectionError as exc:
            logger.error("Skipping %s: %s", path.name, exc)
            summary.results.append(FileResult(source=path, error=str(exc)))
            continue
        summary.results.append(
            _process_pdf(
                info,
                output_dir,
                max_bytes=max_bytes,
                max_pages=max_pages,
                dry_run=dry_run,
                gs_path=gs_path,
            )
        )

    _log_summary(summary, dry_run=dry_run)
    return summary


def _process_pdf(
    info: PdfInfo,
    output_dir: Path,
    *,
    max_bytes: int,
    max_pages: int,
    dry_run: bool,
    gs_path: str | None,
) -> FileResult:
    result = FileResult(source=info.path)
    needs_split = info.pages >= max_pages
    needs_size_work = info.size_bytes >= max_bytes

    if not needs_split and not needs_size_work:
        dest = output_dir / info.path.name
        if dry_run:
            logger.info("[dry-run] %s: already compliant, would copy unchanged", info.path.name)
        else:
            shutil.copy2(info.path, dest)
            logger.info("%s: already compliant, copied unchanged", info.path.name)
        result.outputs = [dest]
        return result

    if dry_run:
        _report_dry_run(
            info,
            result,
            needs_split=needs_split,
            needs_size_work=needs_size_work,
            max_pages=max_pages,
        )
        return result

    with tempfile.TemporaryDirectory(prefix="pdf-transformer-") as tmp:
        workdir = Path(tmp)
        if needs_split:
            pieces = _split_by_pages(info, workdir, max_pages=max_pages, result=result)
        else:
            pieces = [info.path]

        final_pieces: list[Path] = []
        try:
            for piece in pieces:
                final_pieces.extend(
                    _fit_to_size(
                        piece,
                        workdir=workdir,
                        max_bytes=max_bytes,
                        gs_path=gs_path,
                        result=result,
                    )
                )
        except PieceTooLargeError as exc:
            result.error = str(exc)
            logger.error("%s: %s — no output written for this file", info.path.name, exc)
            return result

        if len(final_pieces) > len(pieces):
            result.was_split = True
        _write_outputs(final_pieces, info, output_dir, result)
    return result


def _report_dry_run(
    info: PdfInfo,
    result: FileResult,
    *,
    needs_split: bool,
    needs_size_work: bool,
    max_pages: int,
) -> None:
    actions = []
    if needs_split:
        parts = len(splitter.ranges_for_page_limit(info.pages, max_pages))
        actions.append(f"would split {info.pages} pages into {parts} parts")
    if needs_size_work:
        actions.append(
            f"would compress ({info.size_bytes / _MB:.1f} MB); may split further "
            "if compression alone is not enough"
        )
    logger.info("[dry-run] %s: %s", info.path.name, "; ".join(actions))
    result.was_split = needs_split
    result.was_compressed = needs_size_work


def _split_by_pages(
    info: PdfInfo, workdir: Path, *, max_pages: int, result: FileResult
) -> list[Path]:
    ranges = splitter.ranges_for_page_limit(info.pages, max_pages)
    pieces = []
    for i, (start, end) in enumerate(ranges):
        piece = workdir / f"pagesplit_{i:04d}.pdf"
        splitter.write_page_range(info.path, piece, start, end)
        pieces.append(piece)
    result.was_split = True
    logger.info("%s: split %d pages into %d parts", info.path.name, info.pages, len(pieces))
    return pieces


def _write_outputs(
    final_pieces: list[Path], info: PdfInfo, output_dir: Path, result: FileResult
) -> None:
    if len(final_pieces) == 1:
        dests = [output_dir / info.path.name]
    else:
        dests = [
            output_dir / f"{info.path.stem}_part{i}.pdf" for i in range(1, len(final_pieces) + 1)
        ]
    for src, dest in zip(final_pieces, dests, strict=True):
        if src == info.path:
            shutil.copy2(src, dest)
        else:
            shutil.move(src, dest)
    result.outputs = dests
    logger.info("%s -> %s", info.path.name, ", ".join(d.name for d in dests))


def _fit_to_size(
    piece: Path,
    *,
    workdir: Path,
    max_bytes: int,
    gs_path: str | None,
    result: FileResult,
) -> list[Path]:
    """Return compliant piece(s) for ``piece``: compress first, split as a last resort."""
    if piece.stat().st_size < max_bytes:
        return [piece]
    if gs_path is None:
        raise compressor.GhostscriptNotFoundError()

    best = piece
    for preset in compressor.PRESETS:
        candidate = workdir / f"{piece.stem}_{preset.strip('/')}.pdf"
        if not compressor.compress_pdf(piece, candidate, preset, gs_path):
            continue
        logger.debug("%s: %s -> %.2f MB", piece.name, preset, candidate.stat().st_size / _MB)
        if candidate.stat().st_size < best.stat().st_size:
            best = candidate
        if best.stat().st_size < max_bytes:
            result.was_compressed = True
            logger.info(
                "%s: compressed %.1f MB -> %.1f MB (%s)",
                piece.name,
                piece.stat().st_size / _MB,
                best.stat().st_size / _MB,
                preset,
            )
            return [best]

    if best != piece:
        result.was_compressed = True
    logger.info(
        "%s: still %.1f MB after compression, splitting by size",
        piece.name,
        best.stat().st_size / _MB,
    )
    return _split_until_fits(best, workdir=workdir, max_bytes=max_bytes)


def _split_until_fits(piece: Path, *, workdir: Path, max_bytes: int) -> list[Path]:
    """Recursively halve ``piece`` until every part is under ``max_bytes``."""
    if piece.stat().st_size < max_bytes:
        return [piece]
    pages = len(PdfReader(piece).pages)
    if pages <= 1:
        raise PieceTooLargeError(
            f"a single page is {piece.stat().st_size / _MB:.1f} MB, over the "
            f"{max_bytes / _MB:.1f} MB limit even after compression"
        )
    out: list[Path] = []
    for i, (start, end) in enumerate(splitter.balanced_ranges(pages, 2)):
        half = workdir / f"{piece.stem}_h{i}.pdf"
        splitter.write_page_range(piece, half, start, end)
        out.extend(_split_until_fits(half, workdir=workdir, max_bytes=max_bytes))
    return out


def _log_summary(summary: Summary, *, dry_run: bool) -> None:
    prefix = "[dry-run] " if dry_run else ""
    logger.info(
        "%sSummary: %d PDFs processed — %d copied unchanged, %d split, %d compressed, "
        "%d failed; %d non-PDF files skipped",
        prefix,
        len(summary.results),
        len(summary.copied_unchanged),
        len(summary.split),
        len(summary.compressed),
        len(summary.failed),
        len(summary.skipped_non_pdf),
    )
    for failure in summary.failed:
        logger.info("  failed: %s (%s)", failure.source.name, failure.error)
