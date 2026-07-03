# claude-pdf-transformer

Transform a directory of PDFs into copies that comply with [Anthropic's requirements for multimodal PDF processing](https://support.claude.com/en/articles/8241126):

- **File size under 30 MB**
- **Page count under 100 pages** (so Claude processes visual/image content, not just extracted text)

For each PDF, the tool:

1. **Splits** files at or over the page limit into balanced parts (e.g. 250 pages → 3 parts of 84/83/83), preserving page order.
2. **Compresses** any resulting file at or over the size limit with Ghostscript, trying the `/ebook` preset (150 dpi images) first, then `/screen` (72 dpi).
3. **Splits further** by page range if compression alone is not enough.
4. **Copies compliant PDFs unchanged** — they are never re-encoded.

Originals are never modified. Encrypted, corrupt, and non-PDF files are logged and skipped without aborting the run, and a summary is printed at the end.

## Requirements

- Python 3.13+ and [uv](https://docs.astral.sh/uv/)
- **Ghostscript** (`gs`) on your `PATH` — used for compression:
  - macOS: `brew install ghostscript`
  - Debian/Ubuntu: `sudo apt-get install ghostscript`

  The tool fails with a clear error at startup if `gs` is missing.

## Installation

```sh
# As a tool (puts `pdf-transformer` on your PATH)
uv tool install git+https://github.com/jfmercer/claude-pdf-transformer

# Or for development, from a clone of this repo
uv sync
uv run pdf-transformer --help
```

## Usage

```sh
# Process ./my-pdfs, writing compliant copies to ./output
pdf-transformer ./my-pdfs

# Custom output directory and limits
pdf-transformer ./my-pdfs --output-dir ./ready --max-size-mb 20 --max-pages 50

# See what would happen without writing anything
pdf-transformer ./my-pdfs --dry-run

# Detailed logging
pdf-transformer ./my-pdfs --verbose
```

Split outputs use a flat, page-ordered naming convention: `report.pdf` becomes `report_part1.pdf`, `report_part2.pdf`, … regardless of whether the split was triggered by page count, file size, or both. A PDF that ends up as a single output file keeps its original name.

## CLI reference

| Flag | Default | Description |
| --- | --- | --- |
| `INPUT_DIR` (required) | — | Directory containing the PDFs to transform |
| `--output-dir` | `./output` | Where compliant PDFs are written (created if missing) |
| `--max-size-mb` | `30` | Size limit in MB; files at or over it are compressed/split |
| `--max-pages` | `100` | Page limit; files at or over it are split |
| `--dry-run` | off | Report planned actions without writing files |
| `--verbose`, `-v` | off | Debug-level logging |

Exit codes: `0` success (including cleanly skipped non-PDFs), `1` one or more PDFs failed to process, `2` Ghostscript not found.

## Development

```sh
uv sync                  # install deps (incl. dev group)
uv run pytest            # tests (Ghostscript tests auto-skip if gs is absent)
uv run ruff check        # lint
uv run ruff format       # format
```

## License

[MIT](LICENSE)
