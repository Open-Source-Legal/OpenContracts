"""Celery tasks for chunked PDF parsing fan-out.

``parse_document_chunk`` parses a single page-range chunk (one per chord group
member) and writes its OpenContractDocExport to storage, returning the key.
``reassemble_and_save_chunks`` is the chord callback that streams those results
back, reassembles, and persists. Parsers are re-instantiated from their registry
name inside each task; DB-backed kwargs/secrets are loaded by the parser itself,
so no secrets travel over the broker.
"""
import logging
from typing import Any, cast

from celery import shared_task

from opencontractserver.pipeline.base.chunked_parser import BaseChunkedParser
from opencontractserver.pipeline.base.exceptions import DocumentParsingError
from opencontractserver.pipeline.chunk_artifacts import (
    read_chunk_pdf,
    write_chunk_result,
)
from opencontractserver.pipeline.utils import get_component_by_name

logger = logging.getLogger(__name__)


def _load_chunked_parser(parser_name: str) -> BaseChunkedParser:
    parser = cast(BaseChunkedParser, get_component_by_name(parser_name)())
    if not getattr(parser, "supports_chunking", False):
        raise ValueError(f"Parser '{parser_name}' does not support chunking")
    return parser


@shared_task(
    bind=True,
    retry_backoff=10,
    retry_backoff_max=120,
    retry_jitter=True,
    retry_kwargs={"max_retries": 2},
)
def parse_document_chunk(
    self,
    user_id: int,
    doc_id: int,
    parser_name: str,
    chunk_index: int,
    total_chunks: int,
    page_offset: int,
    input_key: str,
) -> str:
    """Parse one chunk; write its result to storage; return the result key.

    Retry design: this task makes a single parse attempt and delegates all
    retry/back-off to Celery (non-blocking, unlike the in-process
    ``_parse_chunk_with_retry`` used by the synchronous path). Only *transient*
    ``DocumentParsingError`` triggers a retry (up to ``max_retries``); permanent
    errors and ``None`` results propagate immediately so the chord fails fast and
    the ingest chain's ``link_error`` marks the document FAILED.
    """
    parser = _load_chunked_parser(parser_name)
    chunk_pdf_bytes = read_chunk_pdf(input_key)
    try:
        result = parser._parse_single_chunk_impl(
            user_id=user_id,
            doc_id=doc_id,
            chunk_pdf_bytes=chunk_pdf_bytes,
            chunk_index=chunk_index,
            total_chunks=total_chunks,
            page_offset=page_offset,
        )
    except DocumentParsingError as exc:
        if exc.is_transient:
            # Non-blocking Celery retry with back-off; the chord fails when
            # retries are exhausted.
            raise self.retry(exc=exc)
        raise  # permanent → propagate immediately (no retry)
    if result is None:
        # Structural failure; treat as permanent so we don't retry a doomed chunk.
        raise DocumentParsingError(
            f"Chunk {chunk_index} returned None for document {doc_id}",
            is_transient=False,
        )
    return write_chunk_result(doc_id, chunk_index, cast(dict, result))


@shared_task(bind=True)
def reassemble_and_save_chunks(
    self,
    out_keys: list[str],
    doc_id: int,
    user_id: int,
    parser_name: str,
    corpus_id: Any,
    page_offsets: list[int],
) -> dict[str, Any]:
    """Chord callback: stream chunk results, reassemble, persist."""
    parser = _load_chunked_parser(parser_name)
    parser.reassemble_and_finalize(
        out_keys=out_keys,
        page_offsets=page_offsets,
        doc_id=doc_id,
        user_id=user_id,
        corpus_id=corpus_id,
        save=True,
    )
    logger.info(
        f"[reassemble_and_save_chunks] Document {doc_id} reassembled + saved"
    )
    return {"status": "success", "doc_id": doc_id}
