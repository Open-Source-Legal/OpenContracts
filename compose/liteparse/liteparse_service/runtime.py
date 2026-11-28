"""Service configuration and the OCRia-nano model guard (pure Python).

The model guard exists because LiteParse parses text-layer PDFs fine without
the model and only fails on the first page that needs OCR; the service must
refuse to start instead of failing later on some scanned upload.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

MODEL_NAME = "ocria-nano"

# Memory budget (measured, LiteParse 2.21.3 + ocria-nano 1.0.0, scanned pages at
# the default 300 DPI): one parse peaks at ~0.5 GiB + ~11.5 MiB per page
# (100 pages 1.7 GiB, 300 pages 3.8 GiB, 400 pages 5.1 GiB). The container's
# mem_limit must cover pool_size x that peak at max_pages, or a large scan's
# worker is OOM-killed and can take a concurrent parse down with it. Defaults:
# one worker, 300 pages, mem_limit 6g (~64% at the limit). See
# docs/pipelines/liteparse_parser.md before raising any of the three.
#
# A request beyond pool_size waits for a free worker; that wait is NOT bounded
# by the parse timeout below.
DEFAULT_POOL_SIZE = 1
# Per-parse deadline, kept below OpenContracts' LITEPARSE_PARSER_REQUEST_TIMEOUT_SECONDS
# (1800) so a single stalled parse reports 504 before the client gives up.
DEFAULT_PARSE_TIMEOUT_SECONDS = 1500.0
DEFAULT_OCR_WORKERS = 4
DEFAULT_MAX_PAGES = 300
DEFAULT_MAX_UPLOAD_MB = 200


@dataclass(frozen=True)
class ServiceConfig:
    api_key: str
    pool_size: int
    parse_timeout: float
    ocr_workers: int
    max_pages: int
    max_upload_mb: int
    model_version: str


def _required(environ: Mapping[str, str], name: str) -> str:
    value = environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} must be set to a non-empty value")
    return value


def _number(environ: Mapping[str, str], name: str, default: Any, cast: type) -> Any:
    raw = environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return cast(raw)
    except ValueError as e:
        raise ValueError(f"{name} must be a {cast.__name__}, got {raw!r}") from e


def load_config(environ: Mapping[str, str]) -> ServiceConfig:
    """Read the service settings from the environment."""
    return ServiceConfig(
        api_key=_required(environ, "LITEPARSE_API_KEY"),
        pool_size=_number(environ, "LITEPARSE_POOL_SIZE", DEFAULT_POOL_SIZE, int),
        parse_timeout=_number(
            environ,
            "LITEPARSE_PARSE_TIMEOUT_SECONDS",
            DEFAULT_PARSE_TIMEOUT_SECONDS,
            float,
        ),
        ocr_workers=_number(environ, "LITEPARSE_OCR_WORKERS", DEFAULT_OCR_WORKERS, int),
        max_pages=_number(environ, "LITEPARSE_MAX_PAGES", DEFAULT_MAX_PAGES, int),
        max_upload_mb=_number(
            environ, "LITEPARSE_MAX_UPLOAD_MB", DEFAULT_MAX_UPLOAD_MB, int
        ),
        model_version=_required(environ, "OCRIA_NANO_MODEL_VERSION"),
    )


def require_model(installed: Iterable[Any], *, name: str, version: str) -> Any:
    """Return the installed model package, or raise if it is missing/incomplete."""
    for model in installed:
        if model.name == name and model.version == version and model.complete is True:
            return model
    raise RuntimeError(
        f"{name} {version} is not installed (or is incomplete) in "
        "LITEPARSE_MODEL_DIR; rebuild the image"
    )


def parser_options(config: ServiceConfig) -> dict:
    """Keyword arguments for ``liteparse.LiteParse`` (kept pure so CI tests it)."""
    return {
        # Explicit: LiteParse falls back to Tesseract when the model is absent.
        "ocr_backend": MODEL_NAME,
        "emit_word_boxes": True,
        "extract_blocks": True,
        # A bad page is reported in page_errors instead of failing the document.
        "continue_on_page_error": True,
        "output_format": "json",
        "quiet": True,
        "pool_size": config.pool_size,
        "parse_timeout": config.parse_timeout,
        "num_workers": config.ocr_workers,
        "max_pages": config.max_pages,
    }
