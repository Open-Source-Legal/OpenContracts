"""Enricher that turns a PDF's embedded /Outlines bookmarks into OC_SECTION
annotations — a navigable in-document table of contents.

Most published PDFs (budget documents, statutes, reports) ship an embedded
outline (``/Outlines`` — the bookmark tree). ``pypdf`` exposes it via
``reader.outline``: a deterministic, hierarchical table of contents. This
enricher walks that tree and emits one ``OC_SECTION`` token annotation per
bookmark, anchored to the real PAWLs tokens of the heading on the bookmark's
destination page, with the outline nesting preserved via ``parent_id``.

The PAWLs token data is already present in the parser's ``OpenContractDocExport``
(``pawls_file_content``) by the time enrichers run, so no re-tokenisation is
needed. A bookmark whose title cannot be located among the tokens of its
destination page (image-only heading, or a bookmark label that differs from the
printed heading) is dropped, and its children are re-parented to the nearest
matched ancestor so the surviving tree stays connected.

A document with no usable outline is returned unchanged.
"""

import logging
from dataclasses import dataclass, field
from typing import ClassVar, Optional
from uuid import uuid4

from opencontractserver.constants.annotations import (
    OC_SECTION_LABEL,
    PDF_OUTLINE_FUZZY_MATCH_THRESHOLD,
    PDF_OUTLINE_MAX_DEPTH,
    PDF_OUTLINE_MAX_ENTRIES,
    PDF_OUTLINE_WALK_ITEM_MULTIPLIER,
)
from opencontractserver.pipeline.base.enricher import BaseEnricher
from opencontractserver.pipeline.base.file_types import FileTypeEnum
from opencontractserver.pipeline.base.settings_schema import (
    PipelineSetting,
    SettingType,
)
from opencontractserver.types.dicts import (
    OpenContractDocExport,
    OpenContractsAnnotationPythonType,
    OpenContractsSinglePageAnnotationType,
    TokenIdPythonType,
)
from opencontractserver.utils.pdf_token_matching import (
    match_title_to_tokens,
    page_text_tokens,
    union_bounds,
)

logger = logging.getLogger(__name__)


@dataclass
class _OutlineNode:
    """One node walked from a PDF's /Outlines tree (pre-anchoring)."""

    temp_id: str
    title: str
    page_index: int  # 0-based destination page
    parent_temp_id: Optional[str]
    depth: int


def _walk_outline(
    reader,
    outline,
    id_prefix: str,
    max_entries: int,
    max_depth: int,
) -> list[_OutlineNode]:
    """Flatten a ``pypdf`` ``reader.outline`` tree into a list of nodes.

    ``reader.outline`` is a nested list: each ``Destination`` may be followed
    by a list holding its children. Nodes with an empty title or an
    unresolvable destination page are skipped, and their children are
    re-parented to the skipped node's parent.

    Defends against malformed/cyclic outline data with a visited-object set, a
    depth cap (``max_depth``) and a processed-item cap
    (``max_entries * PDF_OUTLINE_WALK_ITEM_MULTIPLIER``).
    """
    nodes: list[_OutlineNode] = []
    visited: set[int] = set()
    seq = 0
    processed = 0
    item_cap = max_entries * PDF_OUTLINE_WALK_ITEM_MULTIPLIER

    def walk(items, parent_temp_id: Optional[str], depth: int) -> None:
        nonlocal seq, processed
        if depth >= max_depth:
            logger.warning(
                "PdfOutlineEnricher: pruning /Outlines branch deeper than "
                "max_depth=%d",
                max_depth,
            )
            return
        i = 0
        while i < len(items):
            if len(nodes) >= max_entries:
                logger.warning(
                    "PdfOutlineEnricher: /Outlines truncated at " "max_entries=%d",
                    max_entries,
                )
                return
            processed += 1
            if processed > item_cap:
                logger.warning(
                    "PdfOutlineEnricher: /Outlines walk hit the item cap "
                    "(%d); aborting walk (malformed outline?)",
                    item_cap,
                )
                return

            item = items[i]
            # A bare nested list with no preceding Destination — skip it.
            if isinstance(item, list):
                i += 1
                continue
            if id(item) in visited:
                logger.warning(
                    "PdfOutlineEnricher: skipping cyclic/duplicate " "/Outlines entry"
                )
                i += 1
                continue
            visited.add(id(item))

            children = None
            if i + 1 < len(items) and isinstance(items[i + 1], list):
                children = items[i + 1]

            title = ""
            try:
                title = str(getattr(item, "title", "") or "").strip()
            except Exception:  # malformed Destination object
                title = ""

            page_index: Optional[int] = None
            try:
                page_index = reader.get_destination_page_number(item)
            except Exception as exc:  # unresolvable destination
                logger.debug(
                    "PdfOutlineEnricher: could not resolve destination "
                    "page for %r: %s",
                    title,
                    exc,
                )

            if title and page_index is not None and page_index >= 0:
                seq += 1
                node = _OutlineNode(
                    temp_id=f"{id_prefix}{seq}",
                    title=title,
                    page_index=int(page_index),
                    parent_temp_id=parent_temp_id,
                    depth=depth,
                )
                nodes.append(node)
                child_parent: Optional[str] = node.temp_id
            else:
                # Unusable node: drop it but re-parent its children upward.
                child_parent = parent_temp_id

            if children is not None:
                walk(children, child_parent, depth + 1)
                i += 2
            else:
                i += 1

    try:
        walk(outline, None, 0)
    except RecursionError:
        logger.warning(
            "PdfOutlineEnricher: /Outlines walk hit Python recursion limit; "
            "returning the %d nodes collected so far",
            len(nodes),
        )
    return nodes


class PdfOutlineEnricher(BaseEnricher):
    """Emit OC_SECTION annotations from a PDF's embedded bookmark outline."""

    title: str = "PDF Outline Enricher"
    description: str = (
        "Reads a PDF's embedded /Outlines bookmarks and appends hierarchical "
        "OC_SECTION token annotations, forming a navigable in-document table "
        "of contents."
    )
    author: str = "OpenContracts"
    dependencies: ClassVar[list[str]] = ["pypdf>=6.11.0,<7"]
    supported_file_types: ClassVar[list[FileTypeEnum]] = [FileTypeEnum.PDF]

    @dataclass
    class Settings:
        """Configuration schema for PdfOutlineEnricher."""

        fuzzy_match_threshold: float = field(
            default=PDF_OUTLINE_FUZZY_MATCH_THRESHOLD,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description=(
                        "Minimum similarity (0.0-1.0) for fuzzy-matching a "
                        "bookmark title to text on its destination page. "
                        "Bookmarks below this are dropped."
                    ),
                )
            },
        )
        max_entries: int = field(
            default=PDF_OUTLINE_MAX_ENTRIES,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description=(
                        "Maximum number of OC_SECTION annotations emitted "
                        "for a single document."
                    ),
                )
            },
        )
        max_depth: int = field(
            default=PDF_OUTLINE_MAX_DEPTH,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description=(
                        "Maximum /Outlines nesting depth walked; deeper "
                        "branches are pruned."
                    ),
                )
            },
        )

    def __init__(self, **kwargs):
        """Initialize the PdfOutlineEnricher."""
        super().__init__(**kwargs)
        logger.info("PdfOutlineEnricher initialized.")

    def _enrich_document_impl(
        self,
        user_id: int,
        doc_id: int,
        export_data: OpenContractDocExport,
        **all_kwargs,
    ) -> OpenContractDocExport:
        """Append OC_SECTION annotations derived from the PDF's outline.

        Returns ``export_data`` unchanged if the PDF has no usable outline or
        carries no PAWLs token data. Enrichment is strictly additive. An
        unexpected error propagates to ``run_enrichers``, which isolates the
        failure so a misbehaving enricher never fails document ingestion.
        """
        import pypdf
        from django.core.files.storage import default_storage

        from opencontractserver.annotations.models import TOKEN_LABEL
        from opencontractserver.documents.models import Document

        # --- Resolve settings (component settings < direct kwargs) ----------
        defaults = self.settings
        fuzzy_threshold = float(
            all_kwargs.get(
                "fuzzy_match_threshold",
                (
                    defaults.fuzzy_match_threshold
                    if defaults
                    else PDF_OUTLINE_FUZZY_MATCH_THRESHOLD
                ),
            )
        )
        max_entries = int(
            all_kwargs.get(
                "max_entries",
                defaults.max_entries if defaults else PDF_OUTLINE_MAX_ENTRIES,
            )
        )
        max_depth = int(
            all_kwargs.get(
                "max_depth",
                defaults.max_depth if defaults else PDF_OUTLINE_MAX_DEPTH,
            )
        )

        # --- Guard: PAWLs token data must be present to anchor sections -----
        pawls_pages = export_data.get("pawls_file_content")
        if not pawls_pages or not isinstance(pawls_pages, list):
            logger.info(
                "PdfOutlineEnricher: doc %s has no PAWLs token data; " "skipping.",
                doc_id,
            )
            return export_data

        # --- Load the PDF and read its embedded outline ---------------------
        document = Document.objects.get(pk=doc_id)
        pdf_name = document.pdf_file.name if document.pdf_file else None
        if not pdf_name:
            logger.info("PdfOutlineEnricher: doc %s has no pdf_file; skipping.", doc_id)
            return export_data

        # pypdf streams from the open storage handle directly, so a large PDF
        # is never fully buffered in memory. Everything that touches ``reader``
        # therefore stays inside the ``with`` block.
        with default_storage.open(pdf_name, "rb") as fh:
            reader = pypdf.PdfReader(fh)
            outline = reader.outline
            if not outline:
                logger.info(
                    "PdfOutlineEnricher: doc %s PDF has no /Outlines "
                    "bookmarks; skipping.",
                    doc_id,
                )
                return export_data

            # --- ID prefix that cannot collide with parser-emitted ids ------
            existing = export_data.get("labelled_text") or []
            if not isinstance(existing, list):
                existing = []
            existing_ids = {
                str(ann.get("id"))
                for ann in existing
                if isinstance(ann, dict) and ann.get("id") is not None
            }
            id_prefix = "enr_outline_"
            if any(eid.startswith(id_prefix) for eid in existing_ids):
                id_prefix = f"enr_outline_{uuid4().hex[:8]}_"

            # --- Walk the outline tree --------------------------------------
            nodes = _walk_outline(reader, outline, id_prefix, max_entries, max_depth)

        if not nodes:
            logger.info(
                "PdfOutlineEnricher: doc %s outline yielded no usable "
                "bookmarks; skipping.",
                doc_id,
            )
            return export_data

        # --- Anchor each node's title to tokens on its destination page -----
        page_token_cache: dict[int, tuple[list[str], list[int]]] = {}
        matched_spans: dict[str, tuple[int, int]] = {}  # temp_id -> (start, end)

        for node in nodes:
            p = node.page_index
            if p >= len(pawls_pages):
                continue  # destination page beyond the parsed PAWLs layer
            if p not in page_token_cache:
                page_token_cache[p] = page_text_tokens(pawls_pages[p])
            token_texts, _orig = page_token_cache[p]
            if not token_texts:
                continue  # image-only / empty page — cannot anchor
            span = match_title_to_tokens(node.title, token_texts, fuzzy_threshold)
            if span is not None:
                matched_spans[node.temp_id] = span

        if not matched_spans:
            logger.info(
                "PdfOutlineEnricher: doc %s — no bookmark titles could be "
                "anchored to page tokens; skipping.",
                doc_id,
            )
            return export_data

        # --- Drop-and-reparent: re-home matched nodes onto matched ancestors
        node_by_id = {node.temp_id: node for node in nodes}

        def nearest_matched_ancestor(node: _OutlineNode) -> Optional[str]:
            # ``seen`` guards against a cyclic parent_temp_id chain produced by
            # crafted/malformed outline data — without it this loop would spin
            # forever on a document analytics platform that ingests untrusted PDFs.
            pid = node.parent_temp_id
            seen: set[str] = set()
            while pid is not None and pid not in seen:
                seen.add(pid)
                if pid in matched_spans:
                    return pid
                parent = node_by_id.get(pid)
                pid = parent.parent_temp_id if parent is not None else None
            return None

        # --- Build OC_SECTION entries ---------------------------------------
        new_entries: list[OpenContractsAnnotationPythonType] = []
        dropped = 0
        for node in nodes:
            span = matched_spans.get(node.temp_id)
            if span is None:
                dropped += 1
                continue
            p = node.page_index
            token_texts, original_indices = page_token_cache[p]
            start, end = span
            matched_token_indices = original_indices[start : end + 1]
            page_tokens = pawls_pages[p].get("tokens", []) or []
            bounds = union_bounds(page_tokens, matched_token_indices)
            page_raw_text = " ".join(token_texts[start : end + 1])

            tokens_jsons: list[TokenIdPythonType] = [
                {"pageIndex": p, "tokenIndex": idx} for idx in matched_token_indices
            ]
            single_page: OpenContractsSinglePageAnnotationType = {
                "bounds": bounds,
                "tokensJsons": tokens_jsons,
                "rawText": page_raw_text,
            }
            annotation_json: dict[int | str, OpenContractsSinglePageAnnotationType] = {
                str(p): single_page
            }
            new_entries.append(
                {
                    "id": node.temp_id,
                    "annotationLabel": OC_SECTION_LABEL,
                    "rawText": node.title,
                    "page": p,
                    "annotation_json": annotation_json,
                    "parent_id": nearest_matched_ancestor(node),
                    "annotation_type": TOKEN_LABEL,
                    # Not structural: unlike a parser's deterministic
                    # OC_SECTION output, these are fuzzy-matched from bookmark
                    # titles and may be wrong, so a user must be able to edit
                    # or delete them. Structural annotations are read-only.
                    "structural": False,
                }
            )

        logger.info(
            "PdfOutlineEnricher: doc %s — emitting %d OC_SECTION annotations "
            "(%d bookmark(s) dropped: title not found on destination page).",
            doc_id,
            len(new_entries),
            dropped,
        )

        # Atomic append: only mutate export_data once everything succeeded.
        export_data["labelled_text"] = list(existing) + new_entries
        return export_data
