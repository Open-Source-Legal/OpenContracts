"""
LiteParse Parser for OpenContracts.

This parser uses `LiteParse <https://github.com/run-llama/liteparse>`_ (from
LlamaIndex) to parse PDF documents fully locally (PDFium-based spatial text
extraction, with optional Tesseract OCR for scanned pages).

LiteParse exposes *line-level* spatial text items — each carrying the line's
text plus an absolute bounding box (``x``, ``y``, ``width``, ``height`` in PDF
points, top-left origin) and font metadata (``font_name``, ``font_size``,
``confidence``). It does **not** classify items into element types (title,
paragraph, table, …) or expose a parent-child hierarchy. To match the core
outputs of the other PDF engines (Docling, LlamaParse) we therefore:

* **Tokens** — extract word-level PAWLs tokens with pdfplumber (the same path
  used by :class:`LlamaParseParser`) so the frontend gets word-level
  highlighting, then map each LiteParse line's bbox to the word tokens it
  encloses via a shapely spatial index.
* **Feature labels** — derive labels (Title / Section Header / Text Block) from
  font size: the modal font size is treated as body text; sizes meaningfully
  larger than body are ranked into heading levels.
* **Parent-child** — build a heading stack over the document in reading order so
  each line gets a ``parent_id`` pointing at its nearest enclosing heading.
  These feed ``import_annotations`` (self-FK edges) and
  ``build_subtree_groups_for_document`` (materialised subtree relationships),
  exactly like a hierarchy-aware parser would.
* **Images** — extract embedded images with pdfplumber (shared
  ``extract_images_from_pdf`` utility), add them to the unified PAWLs token
  array, and emit an ``Image`` annotation per embedded image.

Settings are loaded from the PipelineSettings database. Use the management
command ``migrate_pipeline_settings`` to seed initial values from environment.
"""

import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Literal, Optional, Union

import numpy as np
from django.core.files.storage import default_storage
from shapely.strtree import STRtree

from opencontractserver.annotations.models import TOKEN_LABEL
from opencontractserver.constants.document_processing import (
    DEFAULT_PDF_PAGE_HEIGHT,
    DEFAULT_PDF_PAGE_WIDTH,
    DOCUMENT_IMAGE_STORAGE_PREFIX,
)
from opencontractserver.documents.models import Document
from opencontractserver.pipeline.base.file_types import FileTypeEnum
from opencontractserver.pipeline.base.parser import BaseParser
from opencontractserver.pipeline.base.settings_schema import (
    PipelineSetting,
    SettingType,
)
from opencontractserver.types.dicts import (
    BoundingBoxPythonType,
    OpenContractDocExport,
    OpenContractsAnnotationPythonType,
    OpenContractsSinglePageAnnotationType,
    PawlsPagePythonType,
    PawlsTokenPythonType,
    TokenIdPythonType,
)
from opencontractserver.utils.pdf_token_extraction import (
    extract_images_from_pdf,
    extract_pawls_tokens_from_pdf,
    find_tokens_in_bbox,
)

logger = logging.getLogger(__name__)

# Structural annotation labels produced by this parser. LiteParse does not emit
# element types, so the richest signal we have is font size -> heading level.
LABEL_TITLE = "Title"
LABEL_SECTION_HEADER = "Section Header"
LABEL_TEXT_BLOCK = "Text Block"
LABEL_IMAGE = "Image"

# Fallback page dimensions when LiteParse reports an invalid/zero page size.
# Sourced from the shared constants module (US Letter at 72 DPI) so the literal
# lives in exactly one place (CLAUDE.md "no magic numbers").
DEFAULT_WIDTH = DEFAULT_PDF_PAGE_WIDTH
DEFAULT_HEIGHT = DEFAULT_PDF_PAGE_HEIGHT

# Font sizes below this (PDF points) are treated as non-content — vector
# watermarks, hairline artifacts — and excluded from heading-size detection.
# Without this floor a sub-point watermark that happens to carry a lot of
# characters could be picked as "body", dragging the heading threshold to ~0
# and turning every legible line into a heading.
MIN_CONTENT_FONT_SIZE = 1.0


def _attr(obj: Any, name: str, default: Any = None) -> Any:
    """Read ``name`` from a LiteParse dataclass *or* a plain dict.

    LiteParse returns dataclass instances (``ParseResult`` / ``ParsedPage`` /
    ``TextItem``), but accepting dicts too keeps the converter robust against
    version drift in the binding and makes unit testing with lightweight stand-in
    objects trivial.
    """
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


class LiteParseParser(BaseParser):
    """A parser that uses LiteParse for fully-local PDF parsing.

    LiteParse provides spatial (line-level) text with bounding boxes and font
    metadata. This parser augments that with word-level PAWLs tokens
    (pdfplumber), font-size-derived feature labels, and a parent-child
    hierarchy, so its output matches the other PDF engines' core surface.
    """

    title = "LiteParse Parser"
    description = (
        "Parses PDF documents locally with LiteParse (PDFium) — spatial text "
        "with bounding boxes, word-level tokens, font-size feature labels, and "
        "a derived parent-child hierarchy."
    )
    author = "OpenContracts Team"
    dependencies = ["liteparse"]
    supported_file_types = [FileTypeEnum.PDF]

    @dataclass
    class Settings:
        """Configuration schema for LiteParseParser."""

        output_format: str = field(
            default="markdown",
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description=(
                        "LiteParse output format for the full-text layer "
                        "(json, markdown, or text). Per-line bounding boxes are "
                        "always returned regardless of this setting."
                    ),
                    env_var="LITEPARSE_OUTPUT_FORMAT",
                )
            },
        )
        ocr_enabled: bool = field(
            default=False,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Enable Tesseract OCR for scanned/garbled pages",
                    env_var="LITEPARSE_OCR_ENABLED",
                )
            },
        )
        ocr_language: str = field(
            default="eng",
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Tesseract language code for OCR (e.g. eng, deu)",
                    env_var="LITEPARSE_OCR_LANGUAGE",
                )
            },
        )
        ocr_server_url: str = field(
            default="",
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Optional HTTP OCR server endpoint",
                    env_var="LITEPARSE_OCR_SERVER_URL",
                )
            },
        )
        dpi: int = field(
            default=150,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Rendering resolution used by LiteParse",
                    env_var="LITEPARSE_DPI",
                )
            },
        )
        num_workers: int = field(
            default=4,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Number of parallel workers for processing",
                    env_var="LITEPARSE_NUM_WORKERS",
                )
            },
        )
        target_pages: str = field(
            default="",
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Restrict parsing to specific pages (e.g. '1-5,10')",
                    env_var="LITEPARSE_TARGET_PAGES",
                )
            },
        )
        max_pages: int = field(
            default=0,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Maximum number of pages to parse (0 = all)",
                    env_var="LITEPARSE_MAX_PAGES",
                )
            },
        )
        password: str = field(
            default="",
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.SECRET,
                    description="Password for encrypted PDFs",
                    env_var="LITEPARSE_PASSWORD",
                )
            },
        )
        image_mode: str = field(
            default="off",
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description=(
                        "LiteParse image handling (off/placeholder/embed). "
                        "OpenContracts extracts positioned images via pdfplumber "
                        "instead, so 'off' is the recommended default."
                    ),
                    env_var="LITEPARSE_IMAGE_MODE",
                )
            },
        )
        detect_headings: bool = field(
            default=True,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description=(
                        "Derive feature labels (Title/Section Header) and a "
                        "parent-child hierarchy from font sizes"
                    ),
                    env_var="LITEPARSE_DETECT_HEADINGS",
                )
            },
        )
        heading_size_ratio: float = field(
            default=1.2,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description=(
                        "Font-size ratio above the modal body size at which a "
                        "line is treated as a heading"
                    ),
                    env_var="LITEPARSE_HEADING_SIZE_RATIO",
                )
            },
        )
        extract_images: bool = field(
            default=True,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Extract images from PDF for multimodal processing",
                    env_var="LITEPARSE_EXTRACT_IMAGES",
                )
            },
        )
        image_format: str = field(
            default="jpeg",
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Format for extracted images (jpeg, png)",
                    env_var="LITEPARSE_IMAGE_FORMAT",
                )
            },
        )
        image_quality: int = field(
            default=85,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="JPEG quality for extracted images (1-100)",
                    env_var="LITEPARSE_IMAGE_QUALITY",
                )
            },
        )
        min_image_width: int = field(
            default=50,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Minimum width for extracted images (pixels)",
                    env_var="LITEPARSE_MIN_IMAGE_WIDTH",
                )
            },
        )
        min_image_height: int = field(
            default=50,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Minimum height for extracted images (pixels)",
                    env_var="LITEPARSE_MIN_IMAGE_HEIGHT",
                )
            },
        )

    def __init__(self):
        """Initialize the LiteParse parser with settings from PipelineSettings."""
        super().__init__()  # Loads settings via PipelineComponentBase

        # Use dataclass defaults if settings not yet loaded from database.
        s = self.settings if self.settings is not None else self.Settings()

        self.output_format = s.output_format
        self.ocr_enabled = s.ocr_enabled
        self.ocr_language = s.ocr_language
        self.ocr_server_url = s.ocr_server_url
        self.dpi = s.dpi
        self.num_workers = s.num_workers
        self.target_pages = s.target_pages
        self.max_pages = s.max_pages
        self.password = s.password
        self.image_mode = s.image_mode
        self.detect_headings = s.detect_headings
        self.heading_size_ratio = s.heading_size_ratio
        self.extract_images = s.extract_images
        self.image_format = s.image_format
        self.image_quality = s.image_quality
        self.min_image_width = s.min_image_width
        self.min_image_height = s.min_image_height

        logger.info(
            f"LiteParseParser initialized with output_format={self.output_format}, "
            f"ocr_enabled={self.ocr_enabled}, detect_headings={self.detect_headings}, "
            f"extract_images={self.extract_images}"
        )

    def _parse_document_impl(
        self, user_id: int, doc_id: int, **all_kwargs
    ) -> Optional[OpenContractDocExport]:
        """Parse a document using LiteParse.

        Args:
            user_id: ID of the user requesting the parse.
            doc_id: ID of the document to parse.
            **all_kwargs: Optional overrides for the configured settings
                (output_format, ocr_enabled, detect_headings, extract_images, …).

        Returns:
            ``OpenContractDocExport`` with parsed data, or ``None`` on failure.
        """
        # NB: BaseParser.parse_document already logs the (redacted) merged kwargs
        # before dispatching here, so we don't repeat that log at the impl level.

        # Resolve effective options (call-time kwargs override instance settings).
        output_format = all_kwargs.get("output_format", self.output_format)
        ocr_enabled = all_kwargs.get("ocr_enabled", self.ocr_enabled)
        ocr_language = all_kwargs.get("ocr_language", self.ocr_language)
        ocr_server_url = all_kwargs.get("ocr_server_url", self.ocr_server_url)
        dpi = all_kwargs.get("dpi", self.dpi)
        num_workers = all_kwargs.get("num_workers", self.num_workers)
        target_pages = all_kwargs.get("target_pages", self.target_pages)
        max_pages = all_kwargs.get("max_pages", self.max_pages)
        password = all_kwargs.get("password", self.password)
        image_mode = all_kwargs.get("image_mode", self.image_mode)
        extract_images_flag = all_kwargs.get("extract_images", self.extract_images)
        detect_headings = all_kwargs.get("detect_headings", self.detect_headings)
        heading_size_ratio = all_kwargs.get(
            "heading_size_ratio", self.heading_size_ratio
        )

        # Get the document.
        try:
            document = Document.objects.get(pk=doc_id)
        except Document.DoesNotExist:
            logger.error(f"Document {doc_id} not found")
            return None

        if document.pdf_file and document.pdf_file.name:
            doc_path = document.pdf_file.name
        else:
            logger.error(f"No PDF file found for document {doc_id}")
            return None

        try:
            # Import lazily so the registry can discover this parser even when
            # liteparse isn't installed (and so import failures degrade to a
            # clean error rather than crashing startup).
            from liteparse import LiteParse

            # Read the PDF bytes from storage. LiteParse.parse() accepts bytes
            # directly, so unlike LlamaParse we don't need a temp file.
            with default_storage.open(doc_path, "rb") as doc_file:
                doc_bytes = doc_file.read()

            construct_kwargs: dict[str, Any] = {
                "output_format": output_format,
                "ocr_enabled": ocr_enabled,
                "ocr_language": ocr_language,
                "dpi": dpi,
                "num_workers": num_workers,
                "image_mode": image_mode,
            }
            if ocr_server_url:
                construct_kwargs["ocr_server_url"] = ocr_server_url
            if target_pages:
                construct_kwargs["target_pages"] = target_pages
            if max_pages and max_pages > 0:
                construct_kwargs["max_pages"] = max_pages
            if password:
                construct_kwargs["password"] = password

            logger.info("Parsing document with LiteParse...")
            parser = LiteParse(**construct_kwargs)
            result = parser.parse(doc_bytes)

            if result is None or not _attr(result, "pages"):
                logger.error("LiteParse returned no pages")
                return None

        except ImportError:
            logger.error(
                "liteparse library not installed. Install with: pip install liteparse"
            )
            return None
        except Exception as e:
            import traceback

            logger.error(f"LiteParse parsing failed: {e}\n{traceback.format_exc()}")
            return None

        # Conversion is deliberately OUTSIDE the parse try/except so that a
        # failure in the pdfplumber token pass, the shapely spatial query, or
        # annotation assembly is reported as a conversion error rather than being
        # mislabelled "LiteParse parsing failed" — the two have very different
        # triage paths. Still returns None on failure to preserve the contract.
        try:
            return self._convert_result_to_opencontracts(
                document,
                result,
                doc_bytes,
                extract_images=extract_images_flag,
                detect_headings=detect_headings,
                heading_size_ratio=heading_size_ratio,
            )
        except Exception as e:
            import traceback

            logger.error(
                f"LiteParse output conversion failed for document {doc_id}: {e}\n"
                f"{traceback.format_exc()}"
            )
            return None

    def _convert_result_to_opencontracts(
        self,
        document: Document,
        result: Any,
        pdf_bytes: bytes,
        extract_images: bool = True,
        detect_headings: Optional[bool] = None,
        heading_size_ratio: Optional[float] = None,
    ) -> OpenContractDocExport:
        """Convert a LiteParse ``ParseResult`` to OpenContracts format.

        Args:
            document: The Document model instance.
            result: LiteParse ``ParseResult`` (or compatible object/dict).
            pdf_bytes: Raw PDF bytes for token and image extraction.
            extract_images: Whether to extract embedded images.
            detect_headings: Override for heading detection; falls back to the
                instance setting when ``None``.
            heading_size_ratio: Override for the heading font-size ratio; falls
                back to the instance setting when ``None``.

        Returns:
            ``OpenContractDocExport`` with parsed data.
        """
        pages = list(_attr(result, "pages", []) or [])

        # Collect page dimensions keyed by 0-based page index. LiteParse page
        # numbers are 1-based; fall back to enumeration position defensively.
        page_dimensions: dict[int, tuple[float, float]] = {}
        page_index_by_pos: list[int] = []
        for pos, page in enumerate(pages):
            page_num = _attr(page, "page_num", pos + 1)
            try:
                page_idx = int(page_num) - 1
            except (TypeError, ValueError):
                page_idx = pos
            if page_idx < 0:
                page_idx = pos
            page_index_by_pos.append(page_idx)

            width = _attr(page, "width") or DEFAULT_WIDTH
            height = _attr(page, "height") or DEFAULT_HEIGHT
            try:
                width = float(width)
                height = float(height)
            except (TypeError, ValueError):
                width, height = DEFAULT_WIDTH, DEFAULT_HEIGHT
            if width <= 0:
                width = DEFAULT_WIDTH
            if height <= 0:
                height = DEFAULT_HEIGHT
            page_dimensions[page_idx] = (width, height)

        full_text = _attr(result, "text", "") or ""

        # Extract word-level PAWLs tokens from the PDF (pdfplumber) so the
        # frontend gets word-level highlighting and we can map LiteParse line
        # bboxes to the words they enclose.
        pawls_pages: list[PawlsPagePythonType] = []
        spatial_indices: dict[int, STRtree] = {}
        tokens_by_page: dict[int, list[PawlsTokenPythonType]] = {}
        token_indices_by_page: dict[int, np.ndarray] = {}
        try:
            logger.info("Extracting word tokens from PDF for annotation mapping...")
            (
                pawls_pages,
                spatial_indices,
                tokens_by_page,
                token_indices_by_page,
                _,
                _,
            ) = extract_pawls_tokens_from_pdf(pdf_bytes, page_dimensions)
        except Exception as e:
            logger.warning(
                f"Failed to extract tokens from PDF: {e}. "
                "Annotations will have empty tokensJsons."
            )
            pawls_pages = []
            spatial_indices = {}
            tokens_by_page = {}
            token_indices_by_page = {}

        # Ensure a PAWLs page exists for every LiteParse page index, with the
        # list position equal to the absolute page index. The successful
        # extraction path returns pages in 0..N-1 order (one entry per page), an
        # invariant downstream consumers — including ``_append_image_tokens``,
        # which indexes ``pawls_pages`` by absolute page number — rely on. Build
        # the fallback the same way (filling any gaps, e.g. when ``target_pages``
        # restricts parsing to a non-zero-starting range) so a compacted list
        # never misaligns image/token writes with their page.
        if not pawls_pages:
            max_idx = max(page_dimensions) if page_dimensions else -1
            for page_idx in range(max_idx + 1):
                width, height = page_dimensions.get(
                    page_idx, (DEFAULT_WIDTH, DEFAULT_HEIGHT)
                )
                pawls_pages.append(
                    {
                        "page": {
                            "width": width,
                            "height": height,
                            "index": page_idx,
                        },
                        "tokens": [],
                    }
                )

        # Extract embedded images and append them to the unified token array.
        # NOTE: like the pdfplumber word-token pass above, image extraction runs
        # over the WHOLE PDF (pdfplumber doesn't honour target_pages). So when
        # target_pages restricts parsing to a subset, the full document's token
        # layer (text AND image tokens) is present, but only the parsed pages get
        # annotations — image tokens on un-parsed pages are simply unreferenced.
        # This is consistent with the text-token behaviour and harmless: token
        # indices are per-page, so unreferenced tokens never shift any other
        # page's indices.
        images_by_page: dict[int, list[PawlsTokenPythonType]] = {}
        image_token_offsets: dict[int, int] = {}
        image_storage_path = f"{DOCUMENT_IMAGE_STORAGE_PREFIX}/{document.pk}/images"
        if pdf_bytes and extract_images:
            images_by_page, image_token_offsets = self._append_image_tokens(
                pawls_pages, pdf_bytes, image_storage_path
            )

        # Classify font sizes for heading detection (document-wide). Build a
        # size -> level map once so per-item classification is an O(1) lookup.
        heading_sizes, body_size = self._classify_heading_sizes(
            pages,
            detect_headings=detect_headings,
            heading_size_ratio=heading_size_ratio,
        )
        level_by_size = {size: idx for idx, size in enumerate(heading_sizes)}

        annotations: list[OpenContractsAnnotationPythonType] = []
        annotation_id_counter = 0
        # Heading stack of (level, annotation_id), kept across pages so a Title
        # on page 1 can parent body text on page 2.
        heading_stack: list[tuple[int, str]] = []

        for pos, page in enumerate(pages):
            page_idx = page_index_by_pos[pos]
            page_width, page_height = page_dimensions.get(
                page_idx, (DEFAULT_WIDTH, DEFAULT_HEIGHT)
            )

            # Text-line annotations, in LiteParse reading order.
            for item in _attr(page, "text_items", []) or []:
                item_text = (_attr(item, "text", "") or "").strip()
                if not item_text:
                    continue

                bounds = self._bounds_from_item(item, page_width, page_height)
                level, label = self._classify_item(item, level_by_size)

                # Resolve parent from the heading stack. Headings pop shallower-
                # or-equal levels first so equal-level headings become siblings.
                if level is not None:
                    while heading_stack and heading_stack[-1][0] >= level:
                        heading_stack.pop()
                parent_id = heading_stack[-1][1] if heading_stack else None

                token_refs = find_tokens_in_bbox(
                    bounds,
                    page_idx,
                    spatial_indices.get(page_idx),
                    token_indices_by_page.get(page_idx),
                    tokens_by_page.get(page_idx),
                )

                annotation = self._create_annotation(
                    annotation_id=str(annotation_id_counter),
                    label=label,
                    raw_text=item_text,
                    page_idx=page_idx,
                    bounds=bounds,
                    token_refs=token_refs,
                    has_text_tokens=bool(token_refs),
                    parent_id=parent_id,
                )
                annotations.append(annotation)

                if level is not None:
                    heading_stack.append((level, str(annotation_id_counter)))
                annotation_id_counter += 1

            # Image annotations referencing the embedded image tokens we added.
            page_images = images_by_page.get(page_idx, [])
            token_offset = image_token_offsets.get(page_idx, 0)
            for img_idx, img_data in enumerate(page_images):
                # Route through _bounds_from_item so image bounds get the same
                # page clamping (and >=1pt guarantee) as text lines — a pdfplumber
                # image whose stream bbox bleeds past the page edge would
                # otherwise store out-of-page coordinates the frontend can't
                # render. img_data carries x/y/width/height, which is exactly
                # what _bounds_from_item reads.
                image_bounds = self._bounds_from_item(img_data, page_width, page_height)
                annotation = self._create_annotation(
                    annotation_id=str(annotation_id_counter),
                    label=LABEL_IMAGE,
                    raw_text="[Image]",
                    page_idx=page_idx,
                    bounds=image_bounds,
                    token_refs=[
                        {"pageIndex": page_idx, "tokenIndex": token_offset + img_idx}
                    ],
                    has_image_tokens=True,
                    parent_id=None,
                )
                annotations.append(annotation)
                annotation_id_counter += 1

        export: OpenContractDocExport = {
            "title": document.title or "",
            "content": full_text,
            "description": document.description or "",
            "pawls_file_content": pawls_pages,
            # Use the PAWLs page count (full document) rather than the count of
            # LiteParse-parsed pages: save_parsed_data persists
            # ``document.page_count = len(pawls_file_content)``, and with
            # ``target_pages`` set the two differ. Keeping them equal makes the
            # export self-consistent with what is stored.
            "page_count": len(pawls_pages),
            "doc_labels": [],
            "labelled_text": annotations,
            "relationships": [],
        }

        total_tokens = sum(len(p.get("tokens", [])) for p in pawls_pages)
        total_image_tokens = sum(
            sum(bool(t.get("is_image")) for t in p.get("tokens", []))
            for p in pawls_pages
        )
        headings = sum(
            1
            for a in annotations
            if a["annotationLabel"] in (LABEL_TITLE, LABEL_SECTION_HEADER)
        )
        with_parents = sum(1 for a in annotations if a.get("parent_id") is not None)
        logger.info(
            f"Converted LiteParse output: {len(pages)} pages, "
            f"{len(annotations)} annotations ({headings} headings, "
            f"{with_parents} with a parent), "
            f"{total_tokens - total_image_tokens} text tokens, "
            f"{total_image_tokens} image tokens "
            f"(body font size ~{body_size})"
        )

        return export

    def _append_image_tokens(
        self,
        pawls_pages: list[PawlsPagePythonType],
        pdf_bytes: bytes,
        image_storage_path: str,
    ) -> tuple[dict[int, list[PawlsTokenPythonType]], dict[int, int]]:
        """Extract embedded images and append them to the PAWLs token arrays.

        Returns a tuple of (images_by_page, image_token_offsets) where
        ``image_token_offsets[page_idx]`` is the token index at which this
        page's image tokens begin (used to compute per-image token refs).
        """
        images_by_page: dict[int, list[PawlsTokenPythonType]] = {}
        image_token_offsets: dict[int, int] = {}
        # Clamp to a format the storage layer actually encodes. ``cast`` is a
        # type-checker hint only; an operator-supplied value like "webp" would
        # otherwise be saved as PNG bytes but tagged/extensioned "webp",
        # yielding broken data: URLs downstream.
        image_format: Literal["jpeg", "png"] = (
            "png" if str(self.image_format).lower() == "png" else "jpeg"
        )
        try:
            logger.info("Extracting images from PDF for LLM consumption...")
            # NOTE: self.dpi is LiteParse's own page-render DPI; it is
            # intentionally NOT forwarded here. extract_images_from_pdf only
            # rasterizes as a fallback for embedded streams it cannot decode and
            # uses the pipeline-wide IMAGE_EXTRACTION_DPI default — matching the
            # Docling and LlamaParse parsers, which likewise don't couple their
            # parser DPI to embedded-image extraction.
            raw_images_by_page = extract_images_from_pdf(
                pdf_bytes,
                min_width=self.min_image_width,
                min_height=self.min_image_height,
                image_format=image_format,
                jpeg_quality=self.image_quality,
                storage_path=image_storage_path,
            )
            total = sum(len(v) for v in raw_images_by_page.values())
            logger.info(
                f"Extracted {total} images from {len(raw_images_by_page)} pages"
            )

            for page_idx, page_images in raw_images_by_page.items():
                # page_idx is an absolute 0-based PDF page; pawls_pages is indexed
                # the same way (success path = one entry per page; fallback fills
                # gaps). A page beyond the list is skipped: normally a page past
                # the target_pages range, or — rarely — a page pdfplumber omitted
                # after a per-page error, in which case its images are dropped.
                if page_idx >= len(pawls_pages) or not page_images:
                    continue
                token_offset = len(pawls_pages[page_idx].get("tokens", []))
                # Track ONLY the images actually appended (in append order). The
                # caller enumerates this list to build Image annotations as
                # token_offset + position, so it must mirror the appended tokens
                # exactly — storing the raw list would shift every annotation
                # after a skipped image onto the wrong token slot.
                appended: list[PawlsTokenPythonType] = []
                for img_data in page_images:
                    # Skip malformed image dicts defensively: appending mutates
                    # the shared pawls_pages in place, so a mid-loop KeyError on a
                    # missing required key would strand partial image tokens that
                    # the except block cannot roll back. extract_images_from_pdf
                    # always supplies these keys; the guard just keeps the loop
                    # exception-free so the only failure boundary is extraction.
                    if not all(k in img_data for k in ("x", "y", "width", "height")):
                        continue
                    # Required fields first; optional metadata is added only when
                    # present so we don't violate the NotRequired-but-non-None
                    # contract of PawlsTokenPythonType (mirrors the other parsers).
                    unified_token: PawlsTokenPythonType = {
                        "x": img_data["x"],
                        "y": img_data["y"],
                        "width": img_data["width"],
                        "height": img_data["height"],
                        "text": "",
                        "is_image": True,
                        "format": img_data.get("format", "jpeg"),
                    }
                    if img_data.get("image_path") is not None:
                        unified_token["image_path"] = img_data["image_path"]
                    if img_data.get("content_hash") is not None:
                        unified_token["content_hash"] = img_data["content_hash"]
                    if img_data.get("original_width") is not None:
                        unified_token["original_width"] = img_data["original_width"]
                    if img_data.get("original_height") is not None:
                        unified_token["original_height"] = img_data["original_height"]
                    if img_data.get("image_type") is not None:
                        unified_token["image_type"] = img_data["image_type"]
                    pawls_pages[page_idx]["tokens"].append(unified_token)
                    appended.append(img_data)
                if appended:
                    image_token_offsets[page_idx] = token_offset
                    images_by_page[page_idx] = appended
        except Exception as e:
            logger.warning(f"Failed to extract images from PDF: {e}")
            images_by_page = {}
            image_token_offsets = {}
        return images_by_page, image_token_offsets

    def _classify_heading_sizes(
        self,
        pages: list[Any],
        detect_headings: Optional[bool] = None,
        heading_size_ratio: Optional[float] = None,
    ) -> tuple[list[float], Optional[float]]:
        """Determine which font sizes count as headings.

        Body text is taken to be the font size carrying the most *characters*
        (not the most lines). Any rounded size strictly larger than
        ``body_size * heading_size_ratio`` is a heading size. The returned list
        is sorted descending so its index gives the heading level
        (0 = largest = Title).

        Weighting by character mass — rather than line frequency — is what makes
        this robust on documents where heading-style lines are *more numerous*
        than body lines (slide decks, tables of contents, legal exhibits with
        many repeated section labels) or where small footnote/caption text is as
        frequent as body: body prose still dominates the character count, while
        headings/footnotes are short. A frequency-only count would mis-pick the
        heading or footnote size as body in those cases.

        ``detect_headings`` / ``heading_size_ratio`` default to the instance
        settings when ``None`` so call-time overrides from ``parse_document``
        are honoured.

        Returns ``([], None)`` when heading detection is disabled or no usable
        font sizes are present.
        """
        if detect_headings is None:
            detect_headings = self.detect_headings
        if heading_size_ratio is None:
            heading_size_ratio = self.heading_size_ratio
        if not detect_headings:
            return [], None

        # Accumulate character mass per rounded font size. Memory stays
        # proportional to the number of distinct sizes (a handful), not the
        # total number of text items. A floor of 1 char/line keeps blank-ish
        # lines counting so the weighting degrades to frequency when every line
        # has the same length.
        weights: Counter[float] = Counter()
        for page in pages:
            for item in _attr(page, "text_items", []) or []:
                fs = _attr(item, "font_size")
                if fs is None:
                    continue
                try:
                    fs_f = float(fs)
                except (TypeError, ValueError):
                    continue
                if fs_f < MIN_CONTENT_FONT_SIZE:
                    continue
                text = _attr(item, "text", "") or ""
                weights[round(fs_f, 1)] += max(len(text.strip()), 1)

        if not weights:
            return [], None

        # Body size = the size carrying the most characters. On a tie prefer the
        # SMALLEST tied size (body is smaller than headings; a heading rarely
        # out-masses body, but a short doc can tie).
        max_weight = max(weights.values())
        body_size = min(size for size, w in weights.items() if w == max_weight)

        threshold = body_size * heading_size_ratio
        heading_sizes = sorted((s for s in weights if s > threshold), reverse=True)
        return heading_sizes, body_size

    def _classify_item(
        self, item: Any, level_by_size: dict[float, int]
    ) -> tuple[Optional[int], str]:
        """Classify a text item into (heading_level, label).

        ``level_by_size`` maps a rounded font size to its heading level
        (0 = largest). ``heading_level`` is ``None`` for body text; otherwise it
        is the item's level. Body text maps to ``Text Block``; level 0 maps to
        ``Title`` and all other heading levels to ``Section Header``. The dict
        lookup keeps this O(1) per item (it runs once per text line).
        """
        if not level_by_size:
            return None, LABEL_TEXT_BLOCK

        fs = _attr(item, "font_size")
        if fs is None:
            return None, LABEL_TEXT_BLOCK
        try:
            rounded = round(float(fs), 1)
        except (TypeError, ValueError):
            return None, LABEL_TEXT_BLOCK

        level = level_by_size.get(rounded)
        if level is not None:
            label = LABEL_TITLE if level == 0 else LABEL_SECTION_HEADER
            return level, label
        return None, LABEL_TEXT_BLOCK

    @staticmethod
    def _bounds_from_item(
        item: Any, page_width: float, page_height: float
    ) -> BoundingBoxPythonType:
        """Build a clamped bounding box from a LiteParse text item.

        LiteParse coordinates are absolute PDF points with a top-left origin —
        the same convention pdfplumber uses for the word tokens — so no
        fractional/absolute conversion is needed, only clamping to the page.
        """
        try:
            x = float(_attr(item, "x", 0) or 0)
            y = float(_attr(item, "y", 0) or 0)
            w = float(_attr(item, "width", 0) or 0)
            h = float(_attr(item, "height", 0) or 0)
        except (TypeError, ValueError):
            x = y = w = h = 0.0

        left, top, right, bottom = x, y, x + w, y + h
        if left > right:
            left, right = right, left
        if top > bottom:
            top, bottom = bottom, top

        left = max(0.0, min(left, page_width))
        right = max(0.0, min(right, page_width))
        top = max(0.0, min(top, page_height))
        bottom = max(0.0, min(bottom, page_height))

        # Guarantee a >=1pt box even when the item sits exactly on the page edge.
        # Expanding only to the right/bottom would be a no-op there (already at
        # page_width/page_height), so fall back to expanding the other way.
        if right - left < 1:
            right = min(left + 1, page_width)
            if right - left < 1:
                left = max(0.0, right - 1)
        if bottom - top < 1:
            bottom = min(top + 1, page_height)
            if bottom - top < 1:
                top = max(0.0, bottom - 1)

        return {"left": left, "top": top, "right": right, "bottom": bottom}

    def _create_annotation(
        self,
        annotation_id: str,
        label: str,
        raw_text: str,
        page_idx: int,
        bounds: BoundingBoxPythonType,
        token_refs: Optional[list[TokenIdPythonType]] = None,
        has_text_tokens: bool = False,
        has_image_tokens: bool = False,
        parent_id: Optional[str] = None,
    ) -> OpenContractsAnnotationPythonType:
        """Create a structural OpenContracts annotation.

        ``parent_id`` references another annotation's ``id`` in the same export;
        ``import_annotations`` resolves it to the new DB pk in a second pass and
        ``build_subtree_groups_for_document`` materialises the subtree
        relationships from the resulting tree.
        """
        page_annotation: OpenContractsSinglePageAnnotationType = {
            "bounds": bounds,
            "tokensJsons": token_refs if token_refs else [],
            "rawText": raw_text,
        }

        content_modalities: list[str] = []
        if has_text_tokens:
            content_modalities.append("TEXT")
        if has_image_tokens:
            content_modalities.append("IMAGE")

        annotation_json: dict[
            Union[int, str], OpenContractsSinglePageAnnotationType
        ] = {str(page_idx): page_annotation}

        annotation: OpenContractsAnnotationPythonType = {
            "id": annotation_id,
            "annotationLabel": label,
            "rawText": raw_text,
            "page": page_idx,
            "annotation_json": annotation_json,
            "parent_id": parent_id,
            "annotation_type": TOKEN_LABEL,
            "structural": True,
        }
        if content_modalities:
            annotation["content_modalities"] = content_modalities

        return annotation
