"""Typer CLI entry point for the ``pdf-transformer`` command."""

import logging
import sys
from pathlib import Path
from typing import Annotated

import typer

from pdf_transformer import compressor
from pdf_transformer.pipeline import process_directory

app = typer.Typer(add_completion=False)

logger = logging.getLogger(__name__)


@app.command()
def main(
    input_dir: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=False,
            dir_okay=True,
            readable=True,
            help="Directory containing the PDFs to transform.",
        ),
    ],
    output_dir: Annotated[
        Path,
        typer.Option(help="Directory where compliant PDFs are written (created if missing)."),
    ] = Path("./output"),
    max_size_mb: Annotated[
        float,
        typer.Option(help="Maximum output file size in MB; files at or over this are reduced."),
    ] = 30.0,
    max_pages: Annotated[
        int,
        typer.Option(min=2, help="Page limit; files with this many pages or more are split."),
    ] = 100,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Report what would happen without writing any files."),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable detailed (debug) logging."),
    ] = False,
) -> None:
    """Make every PDF in INPUT_DIR comply with Anthropic's multimodal PDF limits.

    PDFs at or over the page limit are split into balanced parts; files at or
    over the size limit are compressed with Ghostscript and, if that is not
    enough, split into smaller page ranges. Compliant PDFs are copied
    unchanged. Originals are never modified.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )
    if max_size_mb <= 0:
        raise typer.BadParameter("--max-size-mb must be positive")
    if input_dir.resolve() == output_dir.resolve():
        raise typer.BadParameter("--output-dir must be different from the input directory")

    if compressor.find_ghostscript() is None:
        if dry_run:
            logger.warning("%s", compressor.GS_INSTALL_HINT)
        else:
            logger.error("%s", compressor.GS_INSTALL_HINT)
            raise typer.Exit(code=2)

    try:
        summary = process_directory(
            input_dir,
            output_dir,
            max_size_mb=max_size_mb,
            max_pages=max_pages,
            dry_run=dry_run,
        )
    except Exception as exc:
        logger.error("Unexpected error: %s", exc)
        raise typer.Exit(code=1) from exc
    if summary.failed:
        raise typer.Exit(code=1)
