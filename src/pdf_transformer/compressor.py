"""Ghostscript discovery and PDF compression via subprocess."""

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

PRESETS = ("/ebook", "/screen")
"""Ghostscript quality presets tried in order, most conservative first."""

GS_INSTALL_HINT = (
    "Ghostscript ('gs') was not found on PATH. Install it first:\n"
    "  macOS:          brew install ghostscript\n"
    "  Debian/Ubuntu:  sudo apt-get install ghostscript"
)


class GhostscriptNotFoundError(RuntimeError):
    def __init__(self) -> None:
        super().__init__(GS_INSTALL_HINT)


def find_ghostscript() -> str | None:
    """Return the path to the ``gs`` executable, or None if not on PATH."""
    return shutil.which("gs")


def compress_pdf(src: Path, dest: Path, preset: str, gs_path: str) -> bool:
    """Compress ``src`` to ``dest`` using a Ghostscript ``-dPDFSETTINGS`` preset.

    Returns True when Ghostscript exited cleanly and produced a non-empty file.
    The caller decides whether the result is small enough to be worth keeping.
    """
    cmd = [
        gs_path,
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.4",
        f"-dPDFSETTINGS={preset}",
        "-dNOPAUSE",
        "-dBATCH",
        "-dQUIET",
        f"-sOutputFile={dest}",
        str(src),
    ]
    logger.debug("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        logger.warning("Ghostscript failed on %s (%s): %s", src.name, preset, result.stderr.strip())
        return False
    if not dest.exists() or dest.stat().st_size == 0:
        logger.warning("Ghostscript produced no output for %s (%s)", src.name, preset)
        return False
    return True
