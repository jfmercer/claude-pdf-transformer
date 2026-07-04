# CLAUDE.md

CLI tool (`pdf-transformer`) that makes a directory of PDFs comply with Anthropic's
multimodal PDF limits: each output file must be **under 100 pages** and **under 30 MB**
(both configurable). Originals are never modified; compliant copies land in a separate
output directory.

## Commands

```sh
uv sync                    # install deps (Python 3.14 locally; 3.13 is the supported floor)
uv run pytest              # tests; Ghostscript-dependent tests auto-skip if gs missing
uv run pytest --cov=pdf_transformer   # tests with branch coverage (gates at 95% via pyproject fail_under)
uv run ruff check          # lint (includes bandit `S`, mccabe `C90`, pylint `PLR09`)
uv run ruff format         # format
uv run mypy                # strict type checking (src + tests)
uvx pre-commit install     # optional: run ruff/mypy/gitleaks as git pre-commit hooks
uv run pdf-transformer --help
```

Ghostscript (`gs`) is a required system dependency for compression
(`brew install ghostscript` / `apt-get install ghostscript`).

## Architecture

`src/pdf_transformer/` — each module has one responsibility; `pipeline.py` orchestrates:

- **`cli.py`** — Typer app (single command). Validates args, checks `gs` is on PATH
  (exit 2 if missing), configures logging (`--verbose` → DEBUG), maps failures to exit 1.
  `--version` reads the package version via `importlib.metadata` (single-sourced from
  pyproject.toml; there is no `__version__` attribute).
- **`inspector.py`** — `inspect_pdf()` returns `PdfInfo` (path, pages, size) or raises
  `EncryptedPdfError` / `CorruptPdfError` (both subclass `PdfInspectionError`).
- **`splitter.py`** — pure range math (`balanced_ranges`, `ranges_for_page_limit`) plus
  `write_page_range()` (pypdf). Ranges are zero-based half-open `(start, end)` tuples.
- **`compressor.py`** — Ghostscript discovery and one-shot `compress_pdf(src, dest,
  preset, gs_path)` subprocess wrapper. `PRESETS = ("/ebook", "/screen")`, tried in order.
- **`pipeline.py`** — per-file decision flow and `Summary`/`FileResult` reporting.

## Decision flow (pipeline)

Per PDF: (1) skip non-PDF/encrypted/corrupt files with a logged warning, never abort the
run; (2) if `pages >= max_pages`, split into the fewest **balanced** parts each under the
limit (250 pages → 84/83/83); (3) any piece `>= max_size_mb` is compressed with `/ebook`,
then `/screen` (both run against the original piece; a result is kept only if smaller);
(4) if still too big, recursively halve by page range; a single page over the limit fails
that file and writes nothing for it. Intermediates live in a `TemporaryDirectory`.

Naming is a **flat renumber**: multiple final pieces become `stem_part1.pdf …
stem_partN.pdf` in page order no matter why splits happened; a single output keeps the
original filename. Already-compliant files are copied byte-for-byte (`shutil.copy2`),
never re-encoded.

## Conventions

- Thresholds are parameters everywhere (`max_size_mb`, `max_pages`) — tests exploit this
  with tiny values instead of large fixtures.
- Test fixtures are **generated, never committed**: see `tests/conftest.py`
  (`make_blank_pdf`, `make_noisy_pdf`, `make_image_pdf`, …). Fixture page `i` has width
  `BASE_WIDTH + i` so `page_indices()` can verify page order after splits.
- Ghostscript behavior in pipeline tests is mocked via the `compression_effective` /
  `compression_ineffective` fixtures; real-`gs` tests carry the `gs_required` skipif
  marker (CI installs Ghostscript so they run there).
- Note: Ghostscript *repairs* mildly damaged PDFs — corrupt-input tests must use files
  with no `%PDF` header at all.
- Ruff: line length 100, rules `E,W,F,I,UP,B,SIM,PTH,S,C90,PLR09` (max-complexity 10,
  max-args 6; `cli.py` is exempt from `PLR0913`). Logging via stdlib `logging`
  (module-level `logger`), lazy `%s` formatting.
- Mypy runs in strict mode over `src` and `tests` with `python_version = "3.13"` (the
  supported floor); annotate everything, including test functions and fixtures. Ruff's
  `target-version` stays `py313` for the same reason.
- Pytest runs with `filterwarnings = ["error"]` — new deprecation warnings fail the
  suite; add targeted ignores rather than reverting to blanket warnings.
- CI (`.github/workflows/ci.yml`) runs parallel jobs: `lint` (ruff/mypy), `test`
  (ubuntu + macos × Python 3.13/3.14 matrix; coverage HTML uploaded as an artifact,
  XML to Codecov from the linux/3.13 cell; `uv sync --locked` fails on a stale lockfile), and
  `audit` (pip-audit for dependency CVEs, zizmor for workflow audits), plus actionlint
  and gitleaks (secrets); `codeql.yml` runs CodeQL SAST. Superseded runs are cancelled
  via a `concurrency` group; push triggers only on `master` (PRs cover branches).
  Actions are pinned to version tags (`.github/zizmor.yml` relaxes zizmor's hash-pin
  policy to ref-pin) — Dependabot keeps them and uv.lock updated.
