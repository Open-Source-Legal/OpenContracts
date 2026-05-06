"""
LlamaParse Parser for OpenContracts.

This parser uses the LlamaParse API (from LlamaIndex) to parse PDF documents
and extract structural annotations with bounding boxes.

Token extraction is performed using pdfplumber to enable word-level highlighting
in the frontend. The token extraction and bbox intersection logic is based on
the Docsling microservice implementation.
"""

import logging
import os
import tempfile
from dataclasses import dataclass, field
from typing import Any, Literal, Optional, Union, cast

import numpy as np
from django.core.files.storage import default_storage
from shapely.strtree import STRtree

from opencontractserver.annotations.models import TOKEN_LABEL
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
    crop_image_from_pdf,
    extract_images_from_pdf,
    extract_pawls_tokens_from_pdf,
    find_image_tokens_in_bounds,
    find_tokens_in_bbox,
)

logger = logging.getLogger(__name__)


class LlamaParseParser(BaseParser):
    """
    A parser that uses the LlamaParse API to parse PDF documents.

    LlamaParse provides advanced document parsing with layout extraction,
    returning bounding boxes for various document elements (titles, text,
    tables, figures, lists).

    Settings are loaded from PipelineSettings database. Use the management
    command `migrate_pipeline_settings` to seed initial values from environment.
    """

    title = "LlamaParse Parser"
    description = (
        "Parses PDF documents using the LlamaParse API with layout extraction."
    )
    author = "OpenContracts Team"
    dependencies = ["llama-parse"]
    supported_file_types = [FileTypeEnum.PDF]

    # Mapping from LlamaParse element types to OpenContracts annotation labels
    ELEMENT_TYPE_MAPPING = {
        "title": "Title",
        "section_header": "Section Header",
        "heading": "Heading",
        "text": "Text Block",
        "paragraph": "Paragraph",
        "table": "Table",
        "figure": "Figure",
        "image": "Image",
        "list": "List",
        "list_item": "List Item",
        "caption": "Caption",
        "footnote": "Footnote",
        "header": "Page Header",
        "footer": "Page Footer",
        "page_number": "Page Number",
        "equation": "Equation",
        "code": "Code Block",
    }

    @dataclass
    class Settings:
        """Configuration schema for LlamaParseParser."""

        api_key: str = field(
            default="",
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.SECRET,
                    required=True,
                    description="LlamaParse API key (from LlamaIndex Cloud)",
                    env_var="LLAMAPARSE_API_KEY",
                )
            },
        )
        result_type: str = field(
            default="json",
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Output format: json, markdown, or text",
                    env_var="LLAMAPARSE_RESULT_TYPE",
                )
            },
        )
        extract_layout: bool = field(
            default=True,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Extract layout information with bounding boxes",
                    env_var="LLAMAPARSE_EXTRACT_LAYOUT",
                )
            },
        )
        num_workers: int = field(
            default=4,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Number of parallel workers for processing",
                    env_var="LLAMAPARSE_NUM_WORKERS",
                )
            },
        )
        language: str = field(
            default="en",
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Document language code (e.g., en, es, fr)",
                    env_var="LLAMAPARSE_LANGUAGE",
                )
            },
        )
        verbose: bool = field(
            default=False,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Enable verbose logging from LlamaParse",
                    env_var="LLAMAPARSE_VERBOSE",
                )
            },
        )
        extract_images: bool = field(
            default=True,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Extract images from PDF for multimodal processing",
                    env_var="LLAMAPARSE_EXTRACT_IMAGES",
                )
            },
        )
        image_format: str = field(
            default="jpeg",
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Format for extracted images (jpeg, png, webp)",
                    env_var="LLAMAPARSE_IMAGE_FORMAT",
                )
            },
        )
        image_quality: int = field(
            default=85,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="JPEG quality for extracted images (1-100)",
                    env_var="LLAMAPARSE_IMAGE_QUALITY",
                )
            },
        )
        image_dpi: int = field(
            default=150,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="DPI for cropped images",
                    env_var="LLAMAPARSE_IMAGE_DPI",
                )
            },
        )
        min_image_width: int = field(
            default=50,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Minimum width for extracted images (pixels)",
                    env_var="LLAMAPARSE_MIN_IMAGE_WIDTH",
                )
            },
        )
        min_image_height: int = field(
            default=50,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Minimum height for extracted images (pixels)",
                    env_var="LLAMAPARSE_MIN_IMAGE_HEIGHT",
                )
            },
        )

    def __init__(self):
        """Initialize the LlamaParse parser with settings from PipelineSettings."""
        super().__init__()  # Loads settings via PipelineComponentBase

        # Access settings via the settings property (populated from PipelineSettings DB)
        # Use dataclass defaults if settings not yet loaded from database
        s = self.settings if self.settings is not None else self.Settings()

        self.api_key = s.api_key
        self.result_type = s.result_type
        self.extract_layout = s.extract_layout
        self.num_workers = s.num_workers
        self.language = s.language
        self.verbose = s.verbose
        self.extract_images = s.extract_images
        self.image_format = s.image_format
        self.image_quality = s.image_quality
        self.image_dpi = s.image_dpi
        self.min_image_width = s.min_image_width
        self.min_image_height = s.min_image_height

        logger.info(
            f"LlamaParseParser initialized with extract_layout={self.extract_layout}, "
            f"extract_images={self.extract_images}, language={self.language}"
        )

    def _parse_document_impl(
        self, user_id: int, doc_id: int, **all_kwargs
    ) -> Optional[OpenContractDocExport]:
        """
        Parse a document using the LlamaParse API.

        Args:
            user_id: ID of the user requesting the parse.
            doc_id: ID of the document to parse.
            **all_kwargs: Additional configuration options that can override defaults:
                - api_key: Override the API key
                - result_type: Output type ("json", "markdown", "text")
                - extract_layout: Whether to extract layout/bounding boxes
                - num_workers: Number of parallel workers
                - language: Document language
                - verbose: Enable verbose logging

        Returns:
            OpenContractDocExport with the parsed document data, or None if parsing failed.
        """
        from opencontractserver.utils.logging import redact_sensitive_kwargs

        logger.info(
            f"LlamaParseParser - Parsing doc {doc_id} for user {user_id} "
            f"with effective kwargs: {redact_sensitive_kwargs(all_kwargs)}"
        )

        # Override settings with kwargs if provided
        api_key = all_kwargs.get("api_key", self.api_key)
        result_type = all_kwargs.get("result_type", self.result_type)
        extract_layout = all_kwargs.get("extract_layout", self.extract_layout)
        num_workers = all_kwargs.get("num_workers", self.num_workers)
        language = all_kwargs.get("language", self.language)
        verbose = all_kwargs.get("verbose", self.verbose)

        if not api_key:
            logger.error(
                "LlamaParse API key not configured. Set LLAMAPARSE_API_KEY or "
                "LLAMA_CLOUD_API_KEY environment variable."
            )
            return None

        # Get the document
        try:
            document = Document.objects.get(pk=doc_id)
        except Document.DoesNotExist:
            logger.error(f"Document {doc_id} not found")
            return None

        # Determine which file to use
        if document.pdf_file and document.pdf_file.name:
            doc_path = document.pdf_file.name
        else:
            logger.error(f"No PDF file found for document {doc_id}")
            return None

        try:
            # Import llama-parse here to avoid import errors if not installed
            from llama_parse import LlamaParse

            # Initialize the parser
            parser = LlamaParse(
                api_key=api_key,
                result_type=result_type,
                num_workers=num_workers,
                verbose=verbose,
                language=language,
            )

            # Read the file from storage and write to a temp file
            # (LlamaParse needs a file path)
            with default_storage.open(doc_path, "rb") as doc_file:
                doc_bytes = doc_file.read()

            # Determine file extension from document type.
            # NOTE: This is NOT a path traversal risk. The suffix is whitelisted
            # to "pdf" or "docx" only; any other value (including path separators)
            # falls through to ".pdf". NamedTemporaryFile appends the suffix to a
            # random filename in $TMPDIR, so it cannot escape the temp directory.
            file_type = document.file_type.lower() if document.file_type else "pdf"
            suffix = f".{file_type}" if file_type in ("pdf", "docx") else ".pdf"

            # Create a temporary file - use a nested try-finally to ensure cleanup
            # on all exit paths (success, error, or early return)
            temp_file_path = None
            try:
                with tempfile.NamedTemporaryFile(
                    suffix=suffix, delete=False
                ) as temp_file:
                    temp_file.write(doc_bytes)
                    temp_file_path = temp_file.name

                # Parse the document
                logger.info("Sending document to LlamaParse API...")

                # Use get_json_result for JSON with layout data
                if result_type == "json" and extract_layout:
                    # For JSON with layout, we need to use the async API or
                    # get_json_result method
                    json_results = parser.get_json_result(temp_file_path)

                    if not json_results:
                        logger.error("LlamaParse returned empty results")
                        return None

                    # Convert to OpenContracts format
                    # Pass doc_bytes for token and image extraction
                    extract_images_flag = all_kwargs.get(
                        "extract_images", self.extract_images
                    )
                    return self._convert_json_to_opencontracts(
                        document,
                        json_results,
                        extract_layout,
                        doc_bytes,
                        extract_images=extract_images_flag,
                    )
                else:
                    # For markdown/text output, use load_data
                    documents = parser.load_data(temp_file_path)

                    if not documents:
                        logger.error("LlamaParse returned empty results")
                        return None

                    # Convert simple text/markdown output
                    return self._convert_text_to_opencontracts(document, documents)

            finally:
                # Clean up temp file - always runs on any exit path
                if temp_file_path and os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)

        except ImportError:
            logger.error(
                "llama-parse library not installed. "
                "Install with: pip install llama-parse"
            )
            return None
        except Exception as e:
            import traceback

            stacktrace = traceback.format_exc()
            logger.error(f"LlamaParse parsing failed: {e}\n{stacktrace}")
            return None

    def _convert_json_to_opencontracts(
        self,
        document: Document,
        json_results: list[dict[str, Any]],
        extract_layout: bool = True,
        pdf_bytes: Optional[bytes] = None,
        extract_images: bool = True,
    ) -> OpenContractDocExport:
        """
        Convert LlamaParse JSON results to OpenContracts format.

        Args:
            document: The Document model instance.
            json_results: List of JSON results from LlamaParse.
            extract_layout: Whether layout data with bounding boxes is included.
            pdf_bytes: Raw PDF bytes for token extraction. If provided, tokens
                      will be extracted and mapped to annotation bounding boxes.
            extract_images: Whether to extract images from the PDF and include
                          them in the PAWLs output for LLM consumption.

        Returns:
            OpenContractDocExport with parsed data.
        """
        # The first result contains the parsed document
        result = json_results[0] if json_results else {}
        pages = result.get("pages", [])

        # Build the full text content and collect page dimensions
        full_text_parts = []
        annotations: list[OpenContractsAnnotationPythonType] = []
        page_dimensions: dict[int, tuple[float, float]] = {}

        # Default page dimensions
        DEFAULT_WIDTH = 612
        DEFAULT_HEIGHT = 792

        # First pass: collect page dimensions from LlamaParse
        for page_idx, page in enumerate(pages):
            page_text = page.get("text", "")
            full_text_parts.append(page_text)

            # Log full page structure on first page for debugging
            if page_idx == 0:
                page_keys = list(page.keys())
                logger.info(f"DEBUG: Page keys: {page_keys}")

            # Get page dimensions
            page_width = page.get("width", page.get("w", page.get("pageWidth")))
            page_height = page.get("height", page.get("h", page.get("pageHeight")))

            # Validate dimensions - must be positive numbers
            if page_width is None or page_width <= 0:
                page_width = DEFAULT_WIDTH
                logger.warning(
                    f"Page {page_idx} has invalid width, using default: {page_width}"
                )
            if page_height is None or page_height <= 0:
                page_height = DEFAULT_HEIGHT
                logger.warning(
                    f"Page {page_idx} has invalid height, using default: {page_height}"
                )

            page_dimensions[page_idx] = (float(page_width), float(page_height))

        # Extract tokens from PDF if bytes are provided
        pawls_pages: list[PawlsPagePythonType] = []
        spatial_indices: dict[int, STRtree] = {}
        tokens_by_page: dict[int, list[PawlsTokenPythonType]] = {}
        token_indices_by_page: dict[int, np.ndarray] = {}
        extracted_page_dims: dict[int, tuple[float, float]] = {}

        if pdf_bytes:
            try:
                logger.info("Extracting tokens from PDF for annotation mapping...")
                (
                    pawls_pages,
                    spatial_indices,
                    tokens_by_page,
                    token_indices_by_page,
                    extracted_page_dims,
                    _,  # content - we already have it from LlamaParse
                ) = extract_pawls_tokens_from_pdf(pdf_bytes, page_dimensions)
                logger.info(
                    f"Extracted tokens from {len(pawls_pages)} pages. "
                    f"Token counts: {[len(p.get('tokens', [])) for p in pawls_pages]}"
                )
            except Exception as e:
                logger.warning(
                    f"Failed to extract tokens from PDF: {e}. "
                    "Annotations will have empty tokensJsons."
                )
                # Fall back to empty PAWLS pages
                pawls_pages = []
                spatial_indices = {}
                tokens_by_page = {}
                token_indices_by_page = {}

        # If token extraction failed or wasn't attempted, create empty PAWLS pages
        if not pawls_pages:
            for page_idx in range(len(pages)):
                width, height = page_dimensions.get(
                    page_idx, (DEFAULT_WIDTH, DEFAULT_HEIGHT)
                )
                pawls_page: PawlsPagePythonType = {
                    "page": {
                        "width": width,
                        "height": height,
                        "index": page_idx,
                    },
                    "tokens": [],
                }
                pawls_pages.append(pawls_page)

        # Extract images from PDF if enabled
        # images_by_page maps page_idx -> list of raw image token dicts from extraction
        images_by_page: dict[int, list[PawlsTokenPythonType]] = {}
        # image_token_offsets tracks where image tokens start in each page's tokens array
        image_token_offsets: dict[int, int] = {}
        # Construct storage path for images based on document ID
        image_storage_path = f"documents/{document.pk}/images"
        if pdf_bytes and extract_images:
            try:
                logger.info("Extracting images from PDF for LLM consumption...")
                raw_images_by_page = extract_images_from_pdf(
                    pdf_bytes,
                    min_width=self.min_image_width,
                    min_height=self.min_image_height,
                    image_format=cast(Literal["jpeg", "png"], self.image_format),
                    jpeg_quality=self.image_quality,
                    storage_path=image_storage_path,
                )
                total_images = sum(len(imgs) for imgs in raw_images_by_page.values())
                logger.info(
                    f"Extracted {total_images} images from {len(raw_images_by_page)} pages"
                )

                # Add images as unified tokens to PAWLS pages
                for page_idx, page_images in raw_images_by_page.items():
                    if page_idx < len(pawls_pages) and page_images:
                        # Track token offset for image token indexing
                        token_offset = len(pawls_pages[page_idx].get("tokens", []))
                        image_token_offsets[page_idx] = token_offset

                        # Convert image dicts to unified token format and add
                        # to tokens. Optional metadata is added only when
                        # present so we don't violate the NotRequired-but-
                        # non-None contract of PawlsTokenPythonType.
                        for img_data in page_images:
                            unified_token: PawlsTokenPythonType = {
                                "x": img_data["x"],
                                "y": img_data["y"],
                                "width": img_data["width"],
                                "height": img_data["height"],
                                "text": "",  # Required, empty for images
                                "is_image": True,
                                "format": img_data.get("format", "jpeg"),
                            }
                            if img_data.get("image_path") is not None:
                                unified_token["image_path"] = img_data["image_path"]
                            if img_data.get("content_hash") is not None:
                                unified_token["content_hash"] = img_data["content_hash"]
                            if img_data.get("original_width") is not None:
                                unified_token["original_width"] = img_data[
                                    "original_width"
                                ]
                            if img_data.get("original_height") is not None:
                                unified_token["original_height"] = img_data[
                                    "original_height"
                                ]
                            if img_data.get("image_type") is not None:
                                unified_token["image_type"] = img_data["image_type"]
                            pawls_pages[page_idx]["tokens"].append(unified_token)

                        # Store raw image data for overlap detection
                        images_by_page[page_idx] = page_images
            except Exception as e:
                logger.warning(f"Failed to extract images from PDF: {e}")
                images_by_page = {}

        # Track annotation IDs
        annotation_id_counter = 0

        # Process LlamaParse-detected images (from page["images"] array)
        # These are separate from embedded images - LlamaParse visually detects images
        # and provides their bounding boxes and OCR text
        for page_idx, page in enumerate(pages):
            llamaparse_images = page.get("images", [])
            if llamaparse_images and pdf_bytes and extract_images:
                page_width, page_height = page_dimensions.get(
                    page_idx, (DEFAULT_WIDTH, DEFAULT_HEIGHT)
                )
                logger.info(
                    f"Processing {len(llamaparse_images)} LlamaParse-detected "
                    f"images on page {page_idx}"
                )

                for img_data in llamaparse_images:
                    # LlamaParse provides absolute coordinates (not fractional)
                    img_x = float(img_data.get("x", 0))
                    img_y = float(img_data.get("y", 0))
                    img_width = float(img_data.get("width", 0))
                    img_height = float(img_data.get("height", 0))

                    # Skip tiny images
                    if (
                        img_width < self.min_image_width
                        or img_height < self.min_image_height
                    ):
                        logger.debug(
                            f"Skipping small LlamaParse image: {img_width}x{img_height}"
                        )
                        continue

                    # Create bounds from LlamaParse bbox
                    bounds: BoundingBoxPythonType = {
                        "left": img_x,
                        "top": img_y,
                        "right": img_x + img_width,
                        "bottom": img_y + img_height,
                    }

                    # Check if we already have an embedded image at this location
                    existing_image_refs = find_image_tokens_in_bounds(
                        bounds,
                        page_idx,
                        images_by_page.get(page_idx, []),
                        image_token_offsets.get(page_idx, 0),
                    )

                    image_token_refs = []  # list[TokenIdPythonType]

                    if existing_image_refs:
                        # Use existing embedded image token
                        image_token_refs = existing_image_refs
                        logger.debug(
                            f"Found existing embedded image at LlamaParse bbox on page {page_idx}"
                        )
                    else:
                        # Crop the region from the PDF
                        current_token_count = len(
                            pawls_pages[page_idx].get("tokens", [])
                            if page_idx < len(pawls_pages)
                            else []
                        )
                        cropped_image = crop_image_from_pdf(
                            pdf_bytes,
                            page_idx,
                            bounds,
                            page_width,
                            page_height,
                            image_format=cast(
                                Literal["jpeg", "png"], self.image_format
                            ),
                            jpeg_quality=self.image_quality,
                            dpi=self.image_dpi,
                            storage_path=image_storage_path,
                            img_idx=current_token_count,
                        )
                        if cropped_image:
                            # Add cropped image as unified token
                            if page_idx < len(pawls_pages):
                                new_token_idx = len(
                                    pawls_pages[page_idx].get("tokens", [])
                                )
                                unified_token = self._build_image_token(cropped_image)
                                pawls_pages[page_idx]["tokens"].append(unified_token)
                                image_token_refs = [
                                    {"pageIndex": page_idx, "tokenIndex": new_token_idx}
                                ]
                                logger.debug(
                                    f"Cropped LlamaParse image on page {page_idx}: "
                                    f"{img_width:.0f}x{img_height:.0f}"
                                )

                    # Create annotation for the image if we have token refs
                    if image_token_refs:
                        # Get OCR text from LlamaParse if available
                        ocr_texts = img_data.get("ocr", [])
                        ocr_text = " ".join(
                            ocr_item.get("text", "")
                            for ocr_item in ocr_texts
                            if isinstance(ocr_item, dict)
                        )
                        raw_text = ocr_text.strip() if ocr_text else "[Image]"

                        annotation = self._create_annotation(
                            annotation_id=str(annotation_id_counter),
                            label="Image",
                            raw_text=raw_text,
                            page_idx=page_idx,
                            bounds=bounds,
                            token_refs=image_token_refs,
                            has_text_tokens=False,
                            has_image_tokens=True,
                        )
                        annotations.append(annotation)
                        annotation_id_counter += 1
                        logger.debug(
                            f"Created annotation for LlamaParse image on page {page_idx}"
                        )

        # Second pass: process items and create annotations with token references
        for page_idx, page in enumerate(pages):
            page_width, page_height = page_dimensions.get(
                page_idx, (DEFAULT_WIDTH, DEFAULT_HEIGHT)
            )

            # Extract layout elements if available
            layout_elements = page.get("layout", []) if extract_layout else []
            items = page.get("items", [])

            # Debug: Log first few items to understand bbox format
            if page_idx == 0 and items:
                logger.info(f"DEBUG: Page dimensions: {page_width}x{page_height}")
                if items:
                    logger.info(f"DEBUG: Full first item structure: {items[0]}")
                for i, debug_item in enumerate(items[:3]):
                    bbox_val = debug_item.get(
                        "bBox",
                        debug_item.get("bbox", debug_item.get("bounding_box", "NONE")),
                    )
                    logger.info(
                        f"DEBUG: Item {i} keys: {debug_item.keys()}, "
                        f"bBox: {bbox_val}, "
                        f"text: {debug_item.get('text', debug_item.get('value', ''))[:50]}"
                    )

            for item in items:
                item_text = item.get("text", "") or item.get("value", "")
                item_type = item.get("type", "text").lower()
                bbox = item.get("bBox", item.get("bbox", item.get("bounding_box", {})))
                is_image_type = item_type in ["figure", "image", "chart", "diagram"]

                # For non-image types, require text content
                if not item_text.strip() and not is_image_type:
                    continue

                # Parse bbox to get bounds
                _, bounds = self._create_pawls_tokens_from_bbox(
                    item_text or f"[{item_type}]",
                    bbox,
                    page_width,
                    page_height,
                    annotation_id_counter,
                )

                # Find tokens that intersect with this annotation's bounding box
                token_refs = find_tokens_in_bbox(
                    bounds,
                    page_idx,
                    spatial_indices.get(page_idx),
                    token_indices_by_page.get(page_idx),
                    tokens_by_page.get(page_idx),
                )

                # For figure/image types, find matching image tokens or crop the region
                image_token_refs = []  # list[TokenIdPythonType]
                if is_image_type and pdf_bytes and extract_images:
                    # Find image tokens in the tokens array that overlap with bounds
                    image_token_refs = find_image_tokens_in_bounds(
                        bounds,
                        page_idx,
                        images_by_page.get(page_idx, []),
                        image_token_offsets.get(page_idx, 0),
                    )
                    # If no embedded image found, crop the region
                    if not image_token_refs:
                        # Get the current token count for the new image token index
                        current_token_count = 0
                        if page_idx < len(pawls_pages) and isinstance(
                            pawls_pages[page_idx], dict
                        ):
                            current_token_count = len(
                                pawls_pages[page_idx].get("tokens", [])
                            )
                        cropped_image = crop_image_from_pdf(
                            pdf_bytes,
                            page_idx,
                            bounds,
                            page_width,
                            page_height,
                            image_format=cast(
                                Literal["jpeg", "png"], self.image_format
                            ),
                            jpeg_quality=self.image_quality,
                            dpi=self.image_dpi,
                            storage_path=image_storage_path,
                            img_idx=current_token_count,
                        )
                        if cropped_image:
                            # Add cropped image as unified token to the page
                            if page_idx < len(pawls_pages) and isinstance(
                                pawls_pages[page_idx], dict
                            ):
                                new_token_idx = len(
                                    pawls_pages[page_idx].get("tokens", [])
                                )
                                unified_token = self._build_image_token(cropped_image)
                                pawls_pages[page_idx]["tokens"].append(unified_token)
                                image_token_refs = [
                                    {"pageIndex": page_idx, "tokenIndex": new_token_idx}
                                ]
                                logger.debug(
                                    f"Cropped image for {item_type} annotation "
                                    f"on page {page_idx}"
                                )

                # Create annotation with combined token refs (text + image)
                label = self.ELEMENT_TYPE_MAPPING.get(item_type, "Text Block")
                # Combine text token refs and image token refs
                all_token_refs = token_refs + image_token_refs
                annotation = self._create_annotation(
                    annotation_id=str(annotation_id_counter),
                    label=label,
                    raw_text=item_text or f"[{item_type}]",
                    page_idx=page_idx,
                    bounds=bounds,
                    token_refs=all_token_refs,
                    has_text_tokens=bool(token_refs),
                    has_image_tokens=bool(image_token_refs),
                )
                annotations.append(annotation)
                annotation_id_counter += 1

            # If no items but we have layout, process layout elements
            if not items and layout_elements:
                for element in layout_elements:
                    element_type = element.get("label", "text").lower()
                    bbox = element.get(
                        "bBox", element.get("bbox", element.get("bounding_box", {}))
                    )
                    element_text = element.get("text", "")
                    is_image_type = element_type in [
                        "figure",
                        "image",
                        "chart",
                        "diagram",
                    ]

                    if not element_text and not is_image_type:
                        continue

                    _, bounds = self._create_pawls_tokens_from_bbox(
                        element_text or f"[{element_type}]",
                        bbox,
                        page_width,
                        page_height,
                        annotation_id_counter,
                    )

                    # Find tokens that intersect with this annotation's bounding box
                    token_refs = find_tokens_in_bbox(
                        bounds,
                        page_idx,
                        spatial_indices.get(page_idx),
                        token_indices_by_page.get(page_idx),
                        tokens_by_page.get(page_idx),
                    )

                    # For figure/image types, find matching image tokens or crop region
                    image_token_refs = []  # list[TokenIdPythonType]
                    if is_image_type and pdf_bytes and extract_images:
                        # Find image tokens in the tokens array that overlap with bounds
                        image_token_refs = find_image_tokens_in_bounds(
                            bounds,
                            page_idx,
                            images_by_page.get(page_idx, []),
                            image_token_offsets.get(page_idx, 0),
                        )
                        # If no embedded image found, crop the region
                        if not image_token_refs:
                            # Get the current token count for the new image token index
                            current_token_count = 0
                            if page_idx < len(pawls_pages) and isinstance(
                                pawls_pages[page_idx], dict
                            ):
                                current_token_count = len(
                                    pawls_pages[page_idx].get("tokens", [])
                                )
                            cropped_image = crop_image_from_pdf(
                                pdf_bytes,
                                page_idx,
                                bounds,
                                page_width,
                                page_height,
                                image_format=cast(
                                    Literal["jpeg", "png"], self.image_format
                                ),
                                jpeg_quality=self.image_quality,
                                dpi=self.image_dpi,
                                storage_path=image_storage_path,
                                img_idx=current_token_count,
                            )
                            if cropped_image:
                                # Add cropped image as unified token to the page
                                if page_idx < len(pawls_pages) and isinstance(
                                    pawls_pages[page_idx], dict
                                ):
                                    new_token_idx = len(
                                        pawls_pages[page_idx].get("tokens", [])
                                    )
                                    unified_token = self._build_image_token(
                                        cropped_image
                                    )
                                    pawls_pages[page_idx]["tokens"].append(
                                        unified_token
                                    )
                                    image_token_refs = [
                                        {
                                            "pageIndex": page_idx,
                                            "tokenIndex": new_token_idx,
                                        }
                                    ]

                    label = self.ELEMENT_TYPE_MAPPING.get(element_type, "Text Block")
                    # Combine text token refs and image token refs
                    all_token_refs = token_refs + image_token_refs
                    annotation = self._create_annotation(
                        annotation_id=str(annotation_id_counter),
                        label=label,
                        raw_text=element_text or f"[{element_type}]",
                        page_idx=page_idx,
                        bounds=bounds,
                        token_refs=all_token_refs,
                        has_text_tokens=bool(token_refs),
                        has_image_tokens=bool(image_token_refs),
                    )
                    annotations.append(annotation)
                    annotation_id_counter += 1

        # Combine all text
        full_text = "\n\n".join(full_text_parts)

        # Build the export
        export: OpenContractDocExport = {
            "title": document.title or "",
            "content": full_text,
            "description": document.description or "",
            "pawls_file_content": pawls_pages,
            "page_count": len(pages),
            "doc_labels": [],
            "labelled_text": annotations,
            "relationships": [],
        }

        # Log summary - count text tokens and image tokens separately
        total_tokens = sum(len(p.get("tokens", [])) for p in pawls_pages)
        total_image_tokens = sum(
            sum(bool(t.get("is_image")) for t in p.get("tokens", []))
            for p in pawls_pages
        )
        total_text_tokens = total_tokens - total_image_tokens
        annotations_with_tokens = sum(
            1
            for a in annotations
            if isinstance(a.get("annotation_json"), dict)
            and cast(dict[str, Any], a["annotation_json"])
            .get(str(a.get("page", 0)), {})
            .get("tokensJsons")
        )
        annotations_with_images = sum(
            1
            for a in annotations
            if a.get("content_modalities")
            and "IMAGE" in a.get("content_modalities", [])
        )
        logger.info(
            f"Converted LlamaParse output: {len(pages)} pages, "
            f"{len(annotations)} annotations, {total_text_tokens} text tokens, "
            f"{total_image_tokens} image tokens, "
            f"{annotations_with_tokens} annotations with token refs, "
            f"{annotations_with_images} annotations with image content"
        )

        return export

    def _convert_text_to_opencontracts(
        self,
        document: Document,
        llama_documents: list[Any],
    ) -> OpenContractDocExport:
        """
        Convert simple text/markdown LlamaParse output to OpenContracts format.

        This is used when layout extraction is not enabled.

        Args:
            document: The Document model instance.
            llama_documents: List of LlamaIndex Document objects.

        Returns:
            OpenContractDocExport with parsed data.
        """
        # Combine text from all documents
        full_text = "\n\n".join(doc.text for doc in llama_documents if doc.text)

        # Without layout data, we create a minimal export
        export: OpenContractDocExport = {
            "title": document.title or "",
            "content": full_text,
            "description": document.description or "",
            "pawls_file_content": [],
            "page_count": len(llama_documents) or 1,
            "doc_labels": [],
            "labelled_text": [],
            "relationships": [],
        }

        logger.info(
            f"Converted LlamaParse text output: {len(llama_documents)} documents, "
            f"{len(full_text)} characters"
        )

        return export

    def _create_pawls_tokens_from_bbox(
        self,
        text: str,
        bbox: dict[str, Any],
        page_width: float,
        page_height: float,
        start_token_idx: int,
    ) -> tuple[list[PawlsTokenPythonType], BoundingBoxPythonType]:
        """
        Create PAWLS tokens from text and bounding box.

        LlamaParse returns bounding boxes as fractions (0-1) of page dimensions.
        We need to convert these to absolute coordinates.

        Args:
            text: The text content.
            bbox: Bounding box dict with keys like 'x', 'y', 'width', 'height' or
                  'left', 'top', 'right', 'bottom' (as fractions 0-1).
            page_width: Page width in points.
            page_height: Page height in points.
            start_token_idx: Starting token index.

        Returns:
            Tuple of (list of PAWLS tokens, overall bounding box).
        """
        tokens: list[PawlsTokenPythonType] = []

        # Default margin constant (1 inch = 72 points)
        DEFAULT_MARGIN: float = 72.0
        # Default bottom position for fallback bounding boxes (~1.4 inches from top)
        # This provides reasonable vertical space for a single-line text element
        DEFAULT_BOTTOM: float = 100.0
        # Coordinates are kept as float throughout so fractional <-> absolute
        # arithmetic (e.g. ``x1 * page_width``) doesn't narrow them back to int.
        left: float
        top: float
        right: float
        bottom: float

        # Parse bounding box - handle different formats from LlamaParse
        # LlamaParse may return fractional coordinates (0-1) or absolute coordinates
        bbox_format = "none"
        is_fractional = False

        if not bbox:
            # No bbox, create a default one with standard margins
            bbox_format = "default/empty"
            left, top = DEFAULT_MARGIN, DEFAULT_MARGIN
            right, bottom = page_width - DEFAULT_MARGIN, DEFAULT_BOTTOM
        elif "x1" in bbox and "y1" in bbox:
            # Format: {x1, y1, x2, y2} - corner coordinates
            bbox_format = "x1/y1/x2/y2"
            x1 = float(bbox.get("x1", 0))
            y1 = float(bbox.get("y1", 0))
            x2 = float(bbox.get("x2", 0))
            y2 = float(bbox.get("y2", 0))

            # Check if fractional
            is_fractional = all(0 <= v <= 1.0 for v in [x1, y1, x2, y2])
            if is_fractional:
                left = x1 * page_width
                top = y1 * page_height
                right = x2 * page_width
                bottom = y2 * page_height
            else:
                left, top, right, bottom = x1, y1, x2, y2
        elif "x" in bbox and "y" in bbox:
            # Format: {x, y, width/w, height/h}
            # LlamaParse uses 'w' and 'h' shorthand
            bbox_format = "x/y/w/h"
            x = float(bbox.get("x", 0))
            y = float(bbox.get("y", 0))
            w = float(bbox.get("w", bbox.get("width", 0.1)))
            h = float(bbox.get("h", bbox.get("height", 0.02)))

            # Check if values are fractions (0-1) or absolute
            # Heuristic: if both corners (x,y) and (x+w,y+h) are in [0,1], treat as fractional
            is_fractional = (
                0 <= x <= 1.0
                and 0 <= y <= 1.0
                and 0 <= (x + w) <= 1.0
                and 0 <= (y + h) <= 1.0
            )
            if is_fractional:
                left = x * page_width
                top = y * page_height
                right = (x + w) * page_width
                bottom = (y + h) * page_height
            else:
                left, top = x, y
                right = x + w
                bottom = y + h
        elif "left" in bbox:
            # Format: {left, top, right, bottom}
            bbox_format = "left/top/right/bottom"
            bbox_l = float(bbox.get("left", 0))
            bbox_t = float(bbox.get("top", 0))
            bbox_r = float(bbox.get("right", 1))
            bbox_b = float(bbox.get("bottom", 0.05))

            # Check if ALL values are in [0,1] range - indicates fractional coordinates
            is_fractional = all(0 <= v <= 1.0 for v in [bbox_l, bbox_t, bbox_r, bbox_b])
            if is_fractional:
                left = bbox_l * page_width
                top = bbox_t * page_height
                right = bbox_r * page_width
                bottom = bbox_b * page_height
            else:
                left, top, right, bottom = bbox_l, bbox_t, bbox_r, bbox_b
        elif isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
            # Format: [x1, y1, x2, y2] or [left, top, right, bottom]
            bbox_format = "array[4]"
            vals = [float(v) for v in bbox[:4]]
            # Check if ALL values are in [0,1] range - indicates fractional coordinates
            is_fractional = all(0 <= v <= 1.0 for v in vals)
            if is_fractional:
                left = vals[0] * page_width
                top = vals[1] * page_height
                right = vals[2] * page_width
                bottom = vals[3] * page_height
            else:
                left, top, right, bottom = vals
        else:
            # Unknown format, use defaults with standard margins
            bbox_format = f"unknown:{type(bbox).__name__}"
            left, top = DEFAULT_MARGIN, DEFAULT_MARGIN
            right, bottom = page_width - DEFAULT_MARGIN, DEFAULT_BOTTOM

        # Sanity checks and bounds validation
        # Ensure left < right and top < bottom (swap if needed)
        if left > right:
            left, right = right, left
        if top > bottom:
            top, bottom = bottom, top

        # Clamp to page bounds
        left = max(0, min(left, page_width))
        right = max(0, min(right, page_width))
        top = max(0, min(top, page_height))
        bottom = max(0, min(bottom, page_height))

        # Ensure minimum dimensions (at least 1 point)
        if right - left < 1:
            right = left + 1
        if bottom - top < 1:
            bottom = top + 1

        # NOTE: We do NOT create fake tokens here. LlamaParse only provides element-level
        # bounding boxes, not token-level data. Creating fake tokens by evenly distributing
        # words across the bbox produces incorrect highlights. The frontend handles
        # annotations with empty tokensJsons gracefully - it just shows the bounding box
        # without individual token highlights.

        # Create overall bounding box
        bounds: BoundingBoxPythonType = {
            "left": left,
            "top": top,
            "right": right,
            "bottom": bottom,
        }

        # Debug logging for first few conversions
        if start_token_idx < 5:
            logger.info(
                f"DEBUG bbox: format={bbox_format}, fractional={is_fractional}, "
                f"input={bbox}"
            )
            logger.info(
                f"DEBUG output: bounds=({left:.1f}, {top:.1f}, {right:.1f}, {bottom:.1f}), "
                f"page={page_width:.0f}x{page_height:.0f}"
            )

        # Return empty tokens list - we don't have real token data from LlamaParse
        return tokens, bounds

    @staticmethod
    def _build_image_token(
        source: PawlsTokenPythonType,
    ) -> PawlsTokenPythonType:
        """
        Build a unified-token dict for an extracted/cropped image.

        Optional metadata fields (``image_path``, ``content_hash``,
        ``original_width``, ``original_height``, ``image_type``) are added
        only when present so we don't violate the
        ``NotRequired``-but-non-``None`` contract of
        :class:`PawlsTokenPythonType`.
        """
        token: PawlsTokenPythonType = {
            "x": source["x"],
            "y": source["y"],
            "width": source["width"],
            "height": source["height"],
            "text": "",
            "is_image": True,
            "format": source.get("format", "jpeg"),
        }
        if source.get("image_path") is not None:
            token["image_path"] = source["image_path"]
        if source.get("content_hash") is not None:
            token["content_hash"] = source["content_hash"]
        if source.get("original_width") is not None:
            token["original_width"] = source["original_width"]
        if source.get("original_height") is not None:
            token["original_height"] = source["original_height"]
        if source.get("image_type") is not None:
            token["image_type"] = source["image_type"]
        return token

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
    ) -> OpenContractsAnnotationPythonType:
        """
        Create an OpenContracts annotation.

        In the unified token model, both text and image tokens are stored in
        the tokens[] array. Image tokens have is_image=True. The token_refs
        parameter contains references to both text and image tokens.

        Args:
            annotation_id: Unique ID for the annotation.
            label: The annotation label.
            raw_text: The text content.
            page_idx: Page index (0-based).
            bounds: Bounding box.
            token_refs: Optional list of token references ({pageIndex, tokenIndex})
                       that fall within the annotation's bounding box. This can
                       include both text tokens and image tokens (is_image=True).
                       If None or empty, the annotation will have an empty
                       tokensJsons array.
            has_text_tokens: True if any of the token_refs are text tokens.
            has_image_tokens: True if any of the token_refs are image tokens.

        Returns:
            OpenContractsAnnotationPythonType annotation.
        """
        # Use provided token references, or empty list if none provided
        tokens_jsons = token_refs if token_refs else []

        # Create page annotation with unified token references
        page_annotation: OpenContractsSinglePageAnnotationType = {
            "bounds": bounds,
            "tokensJsons": tokens_jsons,
            "rawText": raw_text,
        }

        # Determine content modalities based on token types
        content_modalities: list[str] = []
        if has_text_tokens:
            content_modalities.append("TEXT")
        if has_image_tokens:
            content_modalities.append("IMAGE")

        annotation_json: dict[
            Union[int, str], OpenContractsSinglePageAnnotationType
        ] = {
            str(page_idx): page_annotation,
        }
        annotation: OpenContractsAnnotationPythonType = {
            "id": annotation_id,
            "annotationLabel": label,
            "rawText": raw_text,
            "page": page_idx,
            "annotation_json": annotation_json,
            "parent_id": None,
            "annotation_type": TOKEN_LABEL,
            "structural": True,
        }

        # Add content_modalities if there are any
        if content_modalities:
            annotation["content_modalities"] = content_modalities

        return annotation
