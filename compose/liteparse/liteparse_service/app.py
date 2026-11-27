"""FastAPI app: ``POST /parse`` (PDF → LiteParse projection) and ``GET /health``.

Run with ``uvicorn --factory liteparse_service.app:build_app``. ``build_app``
refuses to start unless the pinned OCRia-nano model is installed, and always
selects the ``ocria-nano`` OCR backend explicitly (LiteParse would otherwise
fall back to Tesseract when the model is absent).
"""

from __future__ import annotations

import hmac
import logging
import os
import time
from contextlib import asynccontextmanager
from importlib.metadata import version as package_version
from typing import Any

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from liteparse import ParseError, ParseTimeoutError

from .projection import SCHEMA_VERSION, is_truncated, project_result
from .runtime import MODEL_NAME, ServiceConfig, load_config, require_model

logger = logging.getLogger("liteparse_service")

PDF_MAGIC = b"%PDF-"
_BYTES_PER_MB = 1024 * 1024


def _authorized(supplied: str | None, expected: str) -> bool:
    return supplied is not None and hmac.compare_digest(
        supplied.encode(), expected.encode()
    )


def create_app(
    *, config: ServiceConfig, parser: Any, liteparse_version: str
) -> FastAPI:
    """Wire routes to an already-built parser (tests pass a fake)."""

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        close = getattr(parser, "close", None)
        if close is not None:
            close()

    app = FastAPI(title="OpenContracts LiteParse service", lifespan=lifespan)
    upload_limit = config.max_upload_mb * _BYTES_PER_MB

    @app.get("/health")
    def health() -> dict:
        return {
            "status": "ok",
            "liteparse_version": liteparse_version,
            "model_version": config.model_version,
            "schema_version": SCHEMA_VERSION,
        }

    # Sync handler: FastAPI runs it in its threadpool, and LiteParse's worker
    # pool hands each concurrent call its own worker process.
    @app.post("/parse")
    def parse(
        file: UploadFile = File(...),
        x_api_key: str | None = Header(default=None),
    ) -> dict:
        if not _authorized(x_api_key, config.api_key):
            raise HTTPException(status_code=401, detail="Invalid or missing API key")

        data = file.file.read(upload_limit + 1)
        if len(data) > upload_limit:
            raise HTTPException(
                status_code=413,
                detail=f"Upload exceeds the {config.max_upload_mb} MB limit",
            )
        if not data.startswith(PDF_MAGIC):
            raise HTTPException(
                status_code=415, detail="Only PDF uploads are supported"
            )

        started = time.monotonic()
        try:
            result = parser.parse(data)
        except ParseTimeoutError as e:
            raise HTTPException(
                status_code=504, detail=f"Parse exceeded {e.timeout}s"
            ) from e
        except ParseError as e:
            raise HTTPException(status_code=422, detail=f"LiteParse failed: {e}") from e

        if is_truncated(result):
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Document has {result.total_pages} pages; this service parses "
                    f"at most {config.max_pages} (LITEPARSE_MAX_PAGES)"
                ),
            )

        logger.info(
            "Parsed %d pages in %.2fs", len(result.pages), time.monotonic() - started
        )
        return project_result(
            result,
            liteparse_version=liteparse_version,
            model_version=config.model_version,
        )

    return app


def build_app() -> FastAPI:
    """Build the production app: real config, model check, warmed worker pool."""
    from liteparse import LiteParse, models

    logging.basicConfig(level=logging.INFO)
    config = load_config(os.environ)
    model = require_model(models.list(), name=MODEL_NAME, version=config.model_version)
    logger.info("Using %s %s from %s", model.name, model.version, model.path)

    parser = LiteParse(
        ocr_backend=MODEL_NAME,
        emit_word_boxes=True,
        extract_blocks=True,
        output_format="json",
        quiet=True,
        pool_size=config.pool_size,
        parse_timeout=config.parse_timeout,
        num_workers=config.ocr_workers,
        max_pages=config.max_pages,
    )
    parser.warm_up()
    return create_app(
        config=config, parser=parser, liteparse_version=package_version("liteparse")
    )
