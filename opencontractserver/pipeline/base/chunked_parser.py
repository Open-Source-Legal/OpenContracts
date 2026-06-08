"""
Base class for parsers that support chunked processing of large documents.

When a document exceeds a configurable page threshold, BaseChunkedParser
automatically splits the PDF into smaller page-range chunks, parses each
chunk independently (optionally in parallel), and reassembles the results
into a single ``OpenContractDocExport``.

Subclasses implement ``_parse_single_chunk_impl()`` instead of
``_parse_document_impl()``.  The public API (``process_document``,
``parse_document``, ``save_parsed_data``) remains unchanged.
"""

import io
import logging
import time
from abc import abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import ClassVar, Optional, cast

from django.core.files.storage import default_storage
from pypdf import PdfReader

from opencontractserver.annotations.compact_json import offset_annotation_json
from opencontractserver.constants import (
    DEFAULT_CHUNK_RETRY_LIMIT,
    DEFAULT_MAX_CONCURRENT_CHUNKS,
    DEFAULT_MAX_PAGES_PER_CHUNK,
    DEFAULT_MIN_PAGES_FOR_CHUNKING,
    MAX_CHUNK_RETRY_BACKOFF_SECONDS,
)
from opencontractserver.documents.models import Document
from opencontractserver.pipeline.base.exceptions import DocumentParsingError
from opencontractserver.pipeline.base.parser import BaseParser
from opencontractserver.types.dicts import (
    OpenContractDocExport,
    OpenContractsAnnotationPythonType,
    OpenContractsRelationshipPythonType,
    PawlsPagePythonType,
)
from opencontractserver.utils.pdf_splitting import (
    calculate_page_chunks,
    get_pdf_page_count,
    split_pdf_by_page_range,
)

logger = logging.getLogger(__name__)


class BaseChunkedParser(BaseParser):
    """
    Extension of :class:`BaseParser` that transparently chunks large PDFs.

    Subclasses must implement :meth:`_parse_single_chunk_impl` which receives
    the raw PDF bytes for a single chunk.  The base class handles:

    * Reading the PDF from storage
    * Deciding whether to chunk (based on page count thresholds)
    * Splitting the PDF via :func:`split_pdf_by_page_range`
    * Dispatching chunks (sequentially or concurrently)
    * Reassembling results with correct page offsets
    * Per-chunk retry with back-off

    For documents below the chunking threshold, the full PDF bytes are passed
    to ``_parse_single_chunk_impl`` as a single chunk (no splitting overhead).
    All results consistently receive chunk-prefixed IDs (``c0_``), including
    single-chunk documents, to ensure downstream consumers see a uniform format.

    **Limitation -- cross-chunk parent-child relationships:**
    Each chunk is parsed independently, so parent-child annotation references
    that span chunk boundaries will be orphaned after reassembly.  For example,
    a paragraph in chunk 1 whose section header is in chunk 0 will have a
    ``parent_id`` that does not match any annotation ID in the final result.
    A debug-level message is emitted during reassembly when orphaned references
    are detected.

    A future improvement could snap chunk boundaries to section headers rather
    than arbitrary page limits, reducing orphaned references in hierarchical
    documents.  See GitHub issue #914 item 4 for discussion.
    """

    # ------------------------------------------------------------------
    # Chunking configuration (overridable by subclasses / settings)
    # ------------------------------------------------------------------

    # Opt into the chunked parse path (overrides BaseParser default). This is a
    # pure capability flag — never reassigned per instance — so it is ClassVar.
    supports_chunking: ClassVar[bool] = True

    # The numeric knobs below are deliberately NOT ClassVar: subclasses set them
    # per instance from injected settings (e.g. DoclingParser.__init__ assigns
    # self.max_pages_per_chunk = settings.max_pages_per_chunk). ClassVar would
    # make mypy reject those instance assignments.
    max_pages_per_chunk: int = DEFAULT_MAX_PAGES_PER_CHUNK
    min_pages_for_chunking: int = DEFAULT_MIN_PAGES_FOR_CHUNKING
    max_concurrent_chunks: int = DEFAULT_MAX_CONCURRENT_CHUNKS
    # Intentionally low: per-chunk retries handle transient blips, while the
    # outer Celery task provides a second tier of retries for broader failures.
    chunk_retry_limit: int = DEFAULT_CHUNK_RETRY_LIMIT

    # ------------------------------------------------------------------
    # Abstract method – subclasses implement this
    # ------------------------------------------------------------------

    @abstractmethod
    def _parse_single_chunk_impl(
        self,
        user_id: int,
        doc_id: int,
        chunk_pdf_bytes: bytes,
        chunk_index: int,
        total_chunks: int,
        page_offset: int,
        **all_kwargs,
    ) -> Optional[OpenContractDocExport]:
        """
        Parse a single chunk of a PDF document.

        Args:
            user_id: ID of the requesting user.
            doc_id: ID of the Document in the database.
            chunk_pdf_bytes: Raw PDF bytes for this chunk only.
            chunk_index: 0-based index of this chunk.
            total_chunks: Total number of chunks for the document.
            page_offset: The global page offset for this chunk (i.e. the
                first page of this chunk in the original document).
            **all_kwargs: Merged pipeline + direct kwargs.

        Returns:
            ``OpenContractDocExport`` with page indices *local to the chunk*
            (0-based).  The base class handles re-indexing to global offsets.
        """
        ...

    # ------------------------------------------------------------------
    # Optional hook for subclasses – post-reassembly processing
    # ------------------------------------------------------------------

    def _post_reassemble_hook(
        self,
        user_id: int,
        doc_id: int,
        reassembled: OpenContractDocExport,
        pdf_bytes: bytes,
        **all_kwargs,
    ) -> OpenContractDocExport:
        """
        Hook called after chunk results are reassembled.

        Subclasses can override this to run document-wide post-processing
        that requires the full PDF bytes and complete result set (e.g. image
        extraction from the original PDF).

        The default implementation returns the result unchanged.
        """
        return reassembled

    # ------------------------------------------------------------------
    # Core implementation – replaces BaseParser._parse_document_impl
    # ------------------------------------------------------------------

    def _parse_document_impl(
        self, user_id: int, doc_id: int, **all_kwargs
    ) -> Optional[OpenContractDocExport]:
        """
        Parse a document, automatically chunking large PDFs.

        The method reads the PDF from storage, counts pages, and decides
        whether to chunk.  If chunking is needed, it splits the PDF, parses
        each chunk via ``_parse_single_chunk_impl``, and reassembles.

        Otherwise it delegates to ``_parse_single_chunk_impl`` with the
        full PDF as a single chunk.
        """
        document = Document.objects.get(pk=doc_id)
        doc_path = document.pdf_file.name
        if doc_path is None:
            raise DocumentParsingError(
                f"Document {doc_id} has no PDF file associated",
                is_transient=False,
            )

        try:
            with default_storage.open(doc_path, "rb") as pdf_file:
                pdf_bytes = pdf_file.read()
        except Exception as e:
            raise DocumentParsingError(
                f"Failed to read PDF from storage for document {doc_id}: {e}",
                is_transient=True,
            )

        # Determine page count and chunk boundaries
        try:
            page_count = get_pdf_page_count(pdf_bytes)
        except ValueError as e:
            raise DocumentParsingError(
                f"Cannot determine page count for document {doc_id}: {e}",
                is_transient=False,
            )

        # Validate config eagerly — a misconfigured parser should fail
        # consistently regardless of document size.
        if self.max_concurrent_chunks <= 0:
            raise DocumentParsingError(
                f"max_concurrent_chunks must be > 0, got {self.max_concurrent_chunks}",
                is_transient=False,
            )

        try:
            chunks = calculate_page_chunks(
                page_count, self.max_pages_per_chunk, self.min_pages_for_chunking
            )
        except ValueError as e:
            raise DocumentParsingError(str(e), is_transient=False)

        if len(chunks) <= 1:
            # No chunking needed – parse the whole document in one shot
            logger.info(
                f"Document {doc_id} has {page_count} pages, "
                "below chunking threshold – parsing as single request"
            )
            result = self._parse_chunk_with_retry(
                user_id=user_id,
                doc_id=doc_id,
                chunk_pdf_bytes=pdf_bytes,
                chunk_index=0,
                total_chunks=1,
                page_offset=0,
                **all_kwargs,
            )
            if result is not None:
                # Route through reassembly for consistent chunk-prefixed IDs,
                # even for single-chunk documents.
                result = _reassemble_chunk_results([result], [0])
                result = self._post_reassemble_hook(
                    user_id, doc_id, result, pdf_bytes, **all_kwargs
                )
            return result

        # Chunked parsing
        logger.info(
            f"Document {doc_id} has {page_count} pages – splitting into "
            f"{len(chunks)} chunks (max {self.max_pages_per_chunk} pages each)"
        )

        # Parse chunks
        if self.max_concurrent_chunks <= 1:
            # Sequential: split lazily to reduce peak memory
            chunk_results = self._dispatch_sequential(
                user_id=user_id,
                doc_id=doc_id,
                chunks=chunks,
                pdf_bytes=pdf_bytes,
                total_chunks=len(chunks),
                **all_kwargs,
            )
        else:
            # Concurrent: pre-split all chunks (needed for upfront submission).
            # NOTE: This loads all chunk PDFs into memory simultaneously, unlike
            # sequential dispatch which splits lazily one at a time.  For very
            # large documents (e.g. 500 pages / 10 chunks) this is a meaningful
            # memory trade-off in exchange for parallel processing throughput.
            # Create a single PdfReader to avoid re-parsing the PDF per chunk.
            shared_reader = PdfReader(io.BytesIO(pdf_bytes))
            chunk_data: list[tuple[int, bytes, int]] = []
            for idx, (start, end) in enumerate(chunks):
                try:
                    chunk_bytes = split_pdf_by_page_range(
                        pdf_bytes, start, end, reader=shared_reader
                    )
                except ValueError as e:
                    raise DocumentParsingError(
                        f"Failed to split PDF for document {doc_id}, "
                        f"chunk {idx} (pages {start}-{end}): {e}",
                        is_transient=False,
                    )
                chunk_data.append((idx, chunk_bytes, start))

            chunk_results = self._dispatch_concurrent(
                user_id=user_id,
                doc_id=doc_id,
                chunk_data=chunk_data,
                total_chunks=len(chunks),
                **all_kwargs,
            )

        # Reassemble
        page_offsets = [start for (start, _end) in chunks]
        reassembled = _reassemble_chunk_results(chunk_results, page_offsets)

        logger.info(
            f"Document {doc_id} reassembled: {reassembled['page_count']} pages, "
            f"{len(reassembled.get('labelled_text', []))} annotations, "
            f"{len(reassembled.get('relationships', []))} relationships"
        )

        # Post-reassembly hook (e.g. image extraction on full PDF)
        reassembled = self._post_reassemble_hook(
            user_id, doc_id, reassembled, pdf_bytes, **all_kwargs
        )

        return reassembled

    # ------------------------------------------------------------------
    # Chunk dispatch (sequential or concurrent)
    # ------------------------------------------------------------------

    def _dispatch_sequential(
        self,
        user_id: int,
        doc_id: int,
        chunks: list[tuple[int, int]],
        pdf_bytes: bytes,
        total_chunks: int,
        **all_kwargs,
    ) -> list[OpenContractDocExport]:
        """
        Parse chunks one at a time, splitting each from the source PDF lazily
        to avoid holding all chunk PDFs in memory simultaneously.
        """
        results: list[OpenContractDocExport] = []
        for chunk_index, (start, end) in enumerate(chunks):
            try:
                chunk_bytes = split_pdf_by_page_range(pdf_bytes, start, end)
            except ValueError as e:
                raise DocumentParsingError(
                    f"Failed to split PDF for document {doc_id}, "
                    f"chunk {chunk_index} (pages {start}-{end}): {e}",
                    is_transient=False,
                )

            result = self._parse_chunk_with_retry(
                user_id=user_id,
                doc_id=doc_id,
                chunk_pdf_bytes=chunk_bytes,
                chunk_index=chunk_index,
                total_chunks=total_chunks,
                page_offset=start,
                **all_kwargs,
            )
            if result is None:
                raise DocumentParsingError(
                    f"Chunk {chunk_index} returned None for document {doc_id}",
                    is_transient=True,
                )
            results.append(result)
        return results

    def _dispatch_concurrent(
        self,
        user_id: int,
        doc_id: int,
        chunk_data: list[tuple[int, bytes, int]],
        total_chunks: int,
        **all_kwargs,
    ) -> list[OpenContractDocExport]:
        """
        Parse chunks concurrently using a thread pool.

        Results are collected and returned in original chunk order.
        """
        results: list[Optional[OpenContractDocExport]] = [None] * len(chunk_data)
        max_workers = min(self.max_concurrent_chunks, len(chunk_data))

        logger.info(
            f"Dispatching {len(chunk_data)} chunks for document {doc_id} "
            f"with {max_workers} concurrent workers"
        )

        executor = ThreadPoolExecutor(max_workers=max_workers)
        try:
            future_to_index = {}
            for chunk_index, chunk_bytes, page_offset in chunk_data:
                future = executor.submit(
                    self._parse_chunk_with_retry,
                    user_id=user_id,
                    doc_id=doc_id,
                    chunk_pdf_bytes=chunk_bytes,
                    chunk_index=chunk_index,
                    total_chunks=total_chunks,
                    page_offset=page_offset,
                    **all_kwargs,
                )
                future_to_index[future] = chunk_index

            for future in as_completed(future_to_index):
                chunk_index = future_to_index[future]
                exc = future.exception()
                if exc is not None:
                    if isinstance(exc, DocumentParsingError):
                        raise exc
                    raise DocumentParsingError(
                        f"Chunk {chunk_index} failed for document {doc_id}: {exc}",
                        is_transient=True,
                    ) from exc

                result = future.result()
                if result is None:
                    raise DocumentParsingError(
                        f"Chunk {chunk_index} returned None for document {doc_id}",
                        is_transient=True,
                    )
                results[chunk_index] = result
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        # All None slots would have raised above; cast for type checkers.
        return cast(list[OpenContractDocExport], results)

    # ------------------------------------------------------------------
    # Per-chunk retry logic
    # ------------------------------------------------------------------

    def _parse_chunk_with_retry(
        self,
        user_id: int,
        doc_id: int,
        chunk_pdf_bytes: bytes,
        chunk_index: int,
        total_chunks: int,
        page_offset: int,
        **all_kwargs,
    ) -> Optional[OpenContractDocExport]:
        """
        Attempt to parse a single chunk with limited retries.

        On transient failure, retries up to ``chunk_retry_limit`` times with
        exponential back-off (5s base).  Permanent errors are re-raised
        immediately.
        """
        last_error: Optional[Exception] = None

        for attempt in range(1 + self.chunk_retry_limit):
            try:
                if attempt > 0:
                    backoff = min(
                        5 * (2 ** (attempt - 1)), MAX_CHUNK_RETRY_BACKOFF_SECONDS
                    )
                    logger.info(
                        f"Retrying chunk {chunk_index} for document {doc_id} "
                        f"(attempt {attempt + 1}, backoff {backoff}s)"
                    )
                    time.sleep(backoff)

                return self._parse_single_chunk_impl(
                    user_id=user_id,
                    doc_id=doc_id,
                    chunk_pdf_bytes=chunk_pdf_bytes,
                    chunk_index=chunk_index,
                    total_chunks=total_chunks,
                    page_offset=page_offset,
                    **all_kwargs,
                )

            except DocumentParsingError as e:
                last_error = e
                if not e.is_transient:
                    raise
                logger.warning(
                    f"Chunk {chunk_index} transient error on attempt {attempt + 1}: {e}"
                )

            except Exception as e:
                last_error = e
                logger.warning(
                    f"Chunk {chunk_index} unexpected error on attempt {attempt + 1}: {e}"
                )

        # All retries exhausted – raise to let Celery handle top-level retry
        raise DocumentParsingError(
            f"Chunk {chunk_index} for document {doc_id} failed after "
            f"{1 + self.chunk_retry_limit} attempts: {last_error}",
            is_transient=True,
        )


# ======================================================================
# Reassembly – pure function, easy to test independently
# ======================================================================


def _reassemble_chunk_results(
    chunk_results: list[OpenContractDocExport],
    page_offsets: list[int],
) -> OpenContractDocExport:
    """
    Merge a list of per-chunk ``OpenContractDocExport`` dicts into one.

    For each chunk the function:

    * Offsets ``pawls_file_content[*].page.index`` by the chunk's page offset
    * Offsets annotation ``page`` fields and ``annotation_json`` page keys
    * Prefixes annotation and relationship IDs to keep them unique across chunks
    * Concatenates text content

    Args:
        chunk_results: Ordered list of chunk results (chunk-local page indices).
        page_offsets: Parallel list of page offsets (global start page per chunk).

    Returns:
        A single ``OpenContractDocExport`` with globally-correct page indices.
    """
    if not chunk_results:
        raise ValueError("Cannot reassemble empty chunk_results list")

    first = chunk_results[0]

    combined_pawls: list[PawlsPagePythonType] = []
    combined_annotations: list[OpenContractsAnnotationPythonType] = []
    combined_relationships: list[OpenContractsRelationshipPythonType] = []
    combined_content_parts: list[str] = []
    combined_doc_labels: list[str] = []
    total_pages = 0

    seen_doc_labels: set[str] = set()

    for chunk_idx, (chunk, offset) in enumerate(zip(chunk_results, page_offsets)):
        prefix = f"c{chunk_idx}_"

        # -- PAWLs pages --
        for page_data in chunk.get("pawls_file_content", []):
            page_info = page_data.get("page", {})
            page_info["index"] = page_info.get("index", 0) + offset
            combined_pawls.append(page_data)

        # -- Text content --
        content = chunk.get("content", "")
        if content:
            combined_content_parts.append(content)

        # -- Page count --
        total_pages += chunk.get("page_count", 0)

        # -- Document labels (deduplicated) --
        for label in chunk.get("doc_labels", []):
            if label not in seen_doc_labels:
                seen_doc_labels.add(label)
                combined_doc_labels.append(label)

        # -- Annotations --
        for annotation in chunk.get("labelled_text", []):
            _offset_annotation(annotation, offset, prefix)
            combined_annotations.append(annotation)

        # -- Relationships --
        for relationship in chunk.get("relationships", []):
            _offset_relationship(relationship, prefix)
            combined_relationships.append(relationship)

    result: OpenContractDocExport = {
        "title": first.get("title", ""),
        "content": "\n".join(combined_content_parts),
        "description": first.get("description"),
        "pawls_file_content": combined_pawls,
        "page_count": total_pages,
        "doc_labels": combined_doc_labels,
        "labelled_text": combined_annotations,
        "relationships": combined_relationships,
    }

    # Detect and warn about orphaned cross-chunk parent references
    all_annotation_ids = {a["id"] for a in combined_annotations if a.get("id")}
    orphaned_count = 0
    for ann in combined_annotations:
        pid = ann.get("parent_id")
        if pid is not None and pid not in all_annotation_ids:
            orphaned_count += 1

    if orphaned_count > 0:
        logger.debug(
            f"Reassembly produced {orphaned_count} orphaned parent_id "
            f"reference(s). Cross-chunk parent-child relationships cannot "
            f"be preserved when chunks are parsed independently."
        )

    return result


def _offset_annotation(
    annotation: OpenContractsAnnotationPythonType,
    page_offset: int,
    id_prefix: str,
) -> None:
    """Mutate *annotation* in place: offset pages and prefix IDs."""
    # Offset the primary page field
    annotation["page"] = annotation.get("page", 0) + page_offset

    # Prefix the annotation ID
    old_id = annotation.get("id")
    if old_id is not None:
        annotation["id"] = f"{id_prefix}{old_id}"

    # Prefix parent_id
    parent_id = annotation.get("parent_id")
    if parent_id is not None:
        annotation["parent_id"] = f"{id_prefix}{parent_id}"

    # Offset annotation_json page keys and token references
    annotation_json = annotation.get("annotation_json")
    if isinstance(annotation_json, dict):
        annotation["annotation_json"] = offset_annotation_json(
            annotation_json, page_offset
        )


def _offset_relationship(
    relationship: OpenContractsRelationshipPythonType,
    id_prefix: str,
) -> None:
    """Mutate *relationship* in place: prefix all IDs."""
    old_id = relationship.get("id")
    if old_id is not None:
        relationship["id"] = f"{id_prefix}{old_id}"

    relationship["source_annotation_ids"] = [
        f"{id_prefix}{sid}" for sid in relationship.get("source_annotation_ids", [])
    ]
    relationship["target_annotation_ids"] = [
        f"{id_prefix}{tid}" for tid in relationship.get("target_annotation_ids", [])
    ]
