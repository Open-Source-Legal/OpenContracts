"""FastAPI microservice over the extraction library.

No accounts, no permissions — a single-tenant local service backed by one
SQLite file. POST documents and fieldsets in, start an extract, poll its
status, read the result grid (with citations) back out.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, UploadFile
from pydantic import BaseModel, Field

from . import __version__
from .constants import DEFAULT_CONCURRENCY, DEFAULT_DB_PATH
from .documents import load_bytes
from .engine import ExtractionEngine
from .runner import run_extract
from .schema import FieldSet
from .store import Store

logger = logging.getLogger(__name__)

#: Builds the engine for a run; swap in tests to avoid real LLM calls.
EngineFactory = Callable[[dict], ExtractionEngine]


def _default_engine_factory(extract: dict) -> ExtractionEngine:
    return ExtractionEngine(model=extract.get("model"))


class DocumentIn(BaseModel):
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)
    meta: dict[str, Any] = Field(default_factory=dict)


class DocumentsIn(BaseModel):
    documents: list[DocumentIn] = Field(min_length=1)


class ExtractIn(BaseModel):
    name: str = "extract"
    fieldset_id: int
    document_ids: list[int] = Field(min_length=1)
    #: Optional pydantic-ai model id override, e.g. "anthropic:claude-sonnet-5".
    model: str | None = None
    #: Start processing immediately (in the background).
    run: bool = True
    concurrency: int = DEFAULT_CONCURRENCY


def create_app(
    db_path: str = DEFAULT_DB_PATH,
    *,
    engine_factory: EngineFactory = _default_engine_factory,
) -> FastAPI:
    """Build the service. ``engine_factory`` is the test seam: it receives
    the extract record and returns the engine used for that run."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.store = Store(db_path)
        app.state.run_tasks = {}
        yield
        app.state.store.close()

    app = FastAPI(title="oc-extract", version=__version__, lifespan=lifespan)

    def store() -> Store:
        return app.state.store

    def _get_or_404(getter: Callable, *args, **kwargs):
        try:
            return getter(*args, **kwargs)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    # -- documents -------------------------------------------------------

    @app.post("/documents", status_code=201)
    def add_documents(payload: DocumentsIn) -> dict:
        ids = [
            store().add_document(doc.title, doc.text, meta=doc.meta)
            for doc in payload.documents
        ]
        return {"document_ids": ids}

    @app.post("/documents/upload", status_code=201)
    async def upload_documents(files: list[UploadFile]) -> dict:
        ids = []
        for upload in files:
            data = await upload.read()
            try:
                loaded = load_bytes(
                    data, upload.filename or "upload", upload.content_type
                )
            except (ValueError, RuntimeError) as exc:
                raise HTTPException(status_code=415, detail=str(exc)) from exc
            ids.append(
                store().add_document(
                    loaded.title,
                    loaded.text,
                    page_offsets=loaded.page_offsets,
                    meta=loaded.meta,
                )
            )
        return {"document_ids": ids}

    @app.get("/documents")
    def list_documents() -> dict:
        return {"documents": store().list_documents()}

    @app.get("/documents/{document_id}")
    def get_document(document_id: int, include_text: bool = False) -> dict:
        return _get_or_404(store().get_document, document_id, include_text=include_text)

    # -- fieldsets ---------------------------------------------------------

    @app.post("/fieldsets", status_code=201)
    def create_fieldset(fieldset: FieldSet) -> dict:
        fieldset_id = store().create_fieldset(fieldset)
        return store().get_fieldset(fieldset_id)

    @app.get("/fieldsets")
    def list_fieldsets() -> dict:
        return {"fieldsets": store().list_fieldsets()}

    @app.get("/fieldsets/{fieldset_id}")
    def get_fieldset(fieldset_id: int) -> dict:
        return _get_or_404(store().get_fieldset, fieldset_id)

    # -- extracts -------------------------------------------------------------

    def _schedule_run(extract_id: int, concurrency: int) -> None:
        extract = store().get_extract(extract_id)
        engine = engine_factory(extract)

        async def runner() -> None:
            try:
                await run_extract(
                    store(), extract_id, engine=engine, concurrency=concurrency
                )
            except Exception:  # noqa: BLE001 - background task barrier
                logger.exception("extract run %s crashed", extract_id)
            finally:
                app.state.run_tasks.pop(extract_id, None)

        app.state.run_tasks[extract_id] = asyncio.get_running_loop().create_task(
            runner()
        )

    @app.post("/extracts", status_code=202)
    async def create_extract(payload: ExtractIn) -> dict:
        try:
            extract_id = store().create_extract(
                payload.name,
                payload.fieldset_id,
                payload.document_ids,
                model=payload.model,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if payload.run:
            _schedule_run(extract_id, payload.concurrency)
        return store().get_extract(extract_id)

    @app.post("/extracts/{extract_id}/run", status_code=202)
    async def start_extract(
        extract_id: int, concurrency: int = DEFAULT_CONCURRENCY
    ) -> dict:
        _get_or_404(store().get_extract, extract_id)
        if extract_id in app.state.run_tasks:
            raise HTTPException(status_code=409, detail="extract is already running")
        _schedule_run(extract_id, concurrency)
        return store().get_extract(extract_id)

    @app.get("/extracts")
    def list_extracts() -> dict:
        return {"extracts": store().list_extracts()}

    @app.get("/extracts/{extract_id}")
    def get_extract(extract_id: int) -> dict:
        extract = _get_or_404(store().get_extract, extract_id)
        extract["running"] = extract_id in app.state.run_tasks
        return extract

    @app.get("/extracts/{extract_id}/cells")
    def get_cells(extract_id: int, include_llm_log: bool = False) -> dict:
        _get_or_404(store().get_extract, extract_id)
        return {"cells": store().get_cells(extract_id, include_llm_log=include_llm_log)}

    @app.get("/extracts/{extract_id}/table")
    def get_table(extract_id: int) -> dict:
        _get_or_404(store().get_extract, extract_id)
        return {"rows": store().extract_table(extract_id)}

    @app.get("/cells/{cell_id}")
    def get_cell(cell_id: int, include_llm_log: bool = False) -> dict:
        return _get_or_404(store().get_cell, cell_id, include_llm_log=include_llm_log)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    return app
