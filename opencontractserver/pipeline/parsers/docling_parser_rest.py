import base64
import logging
from dataclasses import dataclass, field
from typing import Any, Literal, Optional, cast

import requests
from requests.exceptions import ConnectionError, RequestException, Timeout

from opencontractserver.constants import (
    DEFAULT_MAX_CONCURRENT_CHUNKS,
    DEFAULT_MAX_PAGES_PER_CHUNK,
    DEFAULT_MIN_PAGES_FOR_CHUNKING,
)
from opencontractserver.pipeline.base.chunked_parser import BaseChunkedParser
from opencontractserver.pipeline.base.exceptions import DocumentParsingError
from opencontractserver.pipeline.base.file_types import FileTypeEnum
from opencontractserver.pipeline.base.settings_schema import (
    PipelineSetting,
    SettingType,
)
from opencontractserver.types.dicts import (
    BoundingBoxPythonType,
    OpenContractDocExport,
    PawlsTokenPythonType,
    TokenIdPythonType,
)
from opencontractserver.utils.cloud import maybe_add_cloud_run_auth
from opencontractserver.utils.pdf_token_extraction import (
    crop_image_from_pdf,
    extract_images_from_pdf,
)

logger = logging.getLogger(__name__)


class DoclingParser(BaseChunkedParser):
    """
    A parser that delegates PDF document parsing to a Docling microservice via REST API
    instead of running the processing locally. This helps isolate complex dependencies
    and improves performance by offloading processing to a dedicated container.

    For large documents (above ``min_pages_for_chunking`` pages), the PDF is
    automatically split into page-range chunks that are parsed independently
    and reassembled.  Image extraction runs once on the full PDF after
    reassembly via :meth:`_post_reassemble_hook`.
    """

    title = "Docling Parser (REST)"
    description = "Parses PDF documents using Docling microservice API."
    author = "OpenContracts Team"
    dependencies = ["requests"]
    supported_file_types = [FileTypeEnum.PDF]

    @dataclass
    class Settings:
        """Configuration schema for DoclingParser."""

        service_url: str = field(
            default="",
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.REQUIRED,
                    required=True,
                    description="URL of the Docling parser microservice",
                    env_var="DOCLING_PARSER_SERVICE_URL",
                )
            },
        )
        request_timeout: int = field(
            default=300,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Request timeout in seconds",
                    env_var="DOCLING_PARSER_TIMEOUT",
                )
            },
        )
        use_cloud_run_iam_auth: bool = field(
            default=False,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Force Google Cloud Run IAM authentication",
                )
            },
        )
        extract_images: bool = field(
            default=True,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Extract images from PDF for multimodal processing",
                    env_var="DOCLING_EXTRACT_IMAGES",
                )
            },
        )
        image_format: str = field(
            default="jpeg",
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Format for extracted images (jpeg, png, webp)",
                    env_var="DOCLING_IMAGE_FORMAT",
                )
            },
        )
        image_quality: int = field(
            default=85,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="JPEG quality for extracted images (1-100)",
                    env_var="DOCLING_IMAGE_QUALITY",
                )
            },
        )
        image_dpi: int = field(
            default=150,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="DPI for cropped images",
                    env_var="DOCLING_IMAGE_DPI",
                )
            },
        )
        min_image_width: int = field(
            default=50,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Minimum width for extracted images (pixels)",
                    env_var="DOCLING_MIN_IMAGE_WIDTH",
                )
            },
        )
        min_image_height: int = field(
            default=50,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Minimum height for extracted images (pixels)",
                    env_var="DOCLING_MIN_IMAGE_HEIGHT",
                )
            },
        )
        max_pages_per_chunk: int = field(
            default=DEFAULT_MAX_PAGES_PER_CHUNK,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Maximum pages per parsing chunk for large documents",
                    env_var="DOCLING_MAX_PAGES_PER_CHUNK",
                )
            },
        )
        min_pages_for_chunking: int = field(
            default=DEFAULT_MIN_PAGES_FOR_CHUNKING,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description=(
                        "Page count threshold above which documents are "
                        "split into chunks for parsing"
                    ),
                    env_var="DOCLING_MIN_PAGES_FOR_CHUNKING",
                )
            },
        )
        max_concurrent_chunks: int = field(
            default=DEFAULT_MAX_CONCURRENT_CHUNKS,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Maximum concurrent chunk parsing requests",
                    env_var="DOCLING_MAX_CONCURRENT_CHUNKS",
                )
            },
        )

    def __init__(self):
        """Initialize the Docling REST parser with settings from PipelineSettings."""
        super().__init__()  # Loads settings via PipelineComponentBase

        # Access settings via the settings property (populated from PipelineSettings DB)
        # Use dataclass defaults if settings not yet loaded from database
        s = self.settings if self.settings is not None else self.Settings()

        self.service_url = s.service_url
        self.request_timeout = s.request_timeout
        self.use_cloud_run_iam_auth = s.use_cloud_run_iam_auth
        self.extract_images = s.extract_images
        self.image_format = s.image_format
        self.image_quality = s.image_quality
        self.image_dpi = s.image_dpi
        self.min_image_width = s.min_image_width
        self.min_image_height = s.min_image_height

        # Chunking settings (propagated to BaseChunkedParser attributes)
        self.max_pages_per_chunk = s.max_pages_per_chunk
        self.min_pages_for_chunking = s.min_pages_for_chunking
        self.max_concurrent_chunks = s.max_concurrent_chunks

        logger.info(
            f"DoclingParser initialized with service URL: {self.service_url}, "
            f"extract_images: {self.extract_images}, "
            f"chunking: {self.min_pages_for_chunking}+ pages -> "
            f"{self.max_pages_per_chunk} pages/chunk, "
            f"max_concurrent: {self.max_concurrent_chunks}"
        )

    @staticmethod
    def _maybe_add_cloud_run_auth(
        url: str, headers: dict[str, str], force: bool = False
    ) -> dict[str, str]:
        """
        Attach an Authorization bearer with a Google Cloud Run identity token when applicable.

        Args:
            url: The service URL we are calling (used to derive target audience).
            headers: Existing headers to be augmented.
            force: If True, force adding IAM auth regardless of the domain.

        Returns:
            A possibly augmented headers dict. If token acquisition fails, returns original headers.
        """
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            is_cloud_run = parsed.scheme == "https" and parsed.netloc.endswith(
                ".run.app"
            )
            if not (is_cloud_run or force):
                return headers

            audience = f"{parsed.scheme}://{parsed.netloc}"

            # Lazy import to avoid hard dependency in non-GCP environments
            import google.auth.transport.requests
            import google.oauth2.id_token

            request = google.auth.transport.requests.Request()
            id_token = google.oauth2.id_token.fetch_id_token(request, audience)
            if id_token:
                headers["Authorization"] = f"Bearer {id_token}"
                logger.debug(
                    "Attached Google Cloud Run IAM id_token to Docling request headers."
                )
            else:
                logger.warning(
                    "Failed to obtain Google Cloud Run IAM id_token for Docling."
                )
        except Exception as e:
            logger.warning(f"Docling Cloud Run IAM auth header not added: {e}")
        return headers

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
        Send a single PDF chunk to the Docling microservice and return the result.

        When processing a large document, :class:`BaseChunkedParser` splits the
        PDF and calls this method once per chunk.  For small documents the full
        PDF bytes are passed as a single chunk (``chunk_index=0``).

        Image extraction is intentionally **not** performed here — it runs
        once on the full PDF in :meth:`_post_reassemble_hook` so that page
        indices are globally consistent.

        Args:
            user_id: The ID of the user parsing the document.
            doc_id: The ID of the target Document in the database.
            chunk_pdf_bytes: Raw PDF bytes for this chunk.
            chunk_index: 0-based index of this chunk.
            total_chunks: Total number of chunks.
            page_offset: Global page offset for this chunk.
            **all_kwargs: Additional optional arguments (force_ocr, etc.).

        Returns:
            ``OpenContractDocExport`` with page indices local to the chunk.
        """
        chunk_label = (
            f"chunk {chunk_index + 1}/{total_chunks}" if total_chunks > 1 else "full"
        )
        logger.info(
            f"DoclingParser - Parsing doc {doc_id} ({chunk_label}) "
            f"for user {user_id} with effective kwargs: {all_kwargs}"
        )

        # Get settings from all_kwargs (which includes PIPELINE_SETTINGS and direct_kwargs)
        force_ocr = all_kwargs.get("force_ocr", False)
        roll_up_groups = all_kwargs.get(
            "roll_up_groups", True
        )  # Defaulting to True as per original PARSER_KWARGS
        llm_enhanced_hierarchy = all_kwargs.get("llm_enhanced_hierarchy", False)

        if force_ocr:
            logger.info(
                "Force OCR is enabled - this adds extra processing time and may not be necessary. "
                "We normally try to intelligently determine if OCR is needed."
            )

        try:
            # Convert PDF bytes to base64 for JSON request
            pdf_base64 = base64.b64encode(chunk_pdf_bytes).decode("utf-8")

            # Use a descriptive filename for chunk logging on the microservice side
            filename = f"doc_{doc_id}_chunk{chunk_index}.pdf"

            # Prepare the request payload
            payload = {
                "filename": filename,
                "pdf_base64": pdf_base64,
                "force_ocr": force_ocr,
                "roll_up_groups": roll_up_groups,
                "llm_enhanced_hierarchy": llm_enhanced_hierarchy,
            }

            # Send request to the microservice
            logger.info(
                f"Sending PDF ({chunk_label}) to Docling parser service: "
                f"{self.service_url}"
            )
            try:
                headers: dict[str, str | bytes] = {"Content-Type": "application/json"}
                # Attach Cloud Run IAM id_token if applicable/forced
                headers = maybe_add_cloud_run_auth(
                    self.service_url, headers, force=self.use_cloud_run_iam_auth
                )

                response = requests.post(
                    self.service_url,
                    json=payload,
                    # See cast rationale in ``docxodus_parser.py``.
                    headers=cast(Any, headers),
                    timeout=self.request_timeout,
                )
                response.raise_for_status()  # Raise exception for 4XX/5XX responses
            except Timeout:
                msg = (
                    f"Request to Docling parser service timed out after "
                    f"{self.request_timeout} seconds for document {doc_id} "
                    f"({chunk_label})"
                )
                logger.error(msg)
                raise DocumentParsingError(msg, is_transient=True)
            except ConnectionError:
                msg = (
                    f"Failed to connect to Docling parser service at "
                    f"{self.service_url} for document {doc_id} ({chunk_label})"
                )
                logger.error(msg)
                raise DocumentParsingError(msg, is_transient=True)
            except RequestException as e:
                # Determine if transient based on HTTP status code
                is_transient = True
                status_code = None
                response_text = ""

                if hasattr(e, "response") and e.response is not None:
                    status_code = e.response.status_code
                    response_text = e.response.text[:500]  # Limit error text length
                    # 4xx errors are typically permanent (bad request, unauthorized, etc.)
                    # 5xx errors are typically transient (server error, service unavailable)
                    if 400 <= status_code < 500:
                        is_transient = False

                msg = (
                    f"Request to Docling parser service failed for document {doc_id} "
                    f"({chunk_label}): {e}"
                )
                if status_code:
                    msg += f" (status={status_code})"
                if response_text:
                    msg += f" - Response: {response_text}"

                logger.error(msg)
                raise DocumentParsingError(msg, is_transient=is_transient)

            # Parse the response
            result = response.json()

            # Handle potential differences in field names (snake_case vs camelCase)
            normalized_result = self._normalize_response(result)

            logger.info(
                f"Successfully processed document {doc_id} ({chunk_label}) "
                "through Docling parser service"
            )
            return cast(OpenContractDocExport, normalized_result)

        except DocumentParsingError:
            # Re-raise our custom exceptions as-is
            raise
        except Exception as e:
            import traceback

            stacktrace = traceback.format_exc()
            msg = (
                f"Docling REST parser failed unexpectedly for document {doc_id} "
                f"({chunk_label}): {e}"
            )
            logger.error(f"{msg}\n{stacktrace}")
            # Unexpected errors default to transient (might be temporary issue)
            raise DocumentParsingError(msg, is_transient=True)

    def _post_reassemble_hook(
        self,
        user_id: int,
        doc_id: int,
        reassembled: OpenContractDocExport,
        pdf_bytes: bytes,
        **all_kwargs,
    ) -> OpenContractDocExport:
        """
        Run image extraction on the full PDF after chunk reassembly.

        This ensures image page indices are globally consistent regardless
        of whether the document was chunked.
        """
        extract_images_flag = all_kwargs.get("extract_images", self.extract_images)
        if extract_images_flag:
            image_storage_path = f"documents/{doc_id}/images"
            reassembled = cast(
                OpenContractDocExport,
                self._add_images_to_result(
                    cast(dict[str, Any], reassembled),
                    pdf_bytes,
                    storage_path=image_storage_path,
                ),
            )
        return reassembled

    def _normalize_response(self, response_data: dict[str, Any]) -> dict[str, Any]:
        """
        Normalize the response to ensure compatibility with both snake_case and camelCase field names.

        Args:
            response_data: The raw response data from the microservice

        Returns:
            A normalized response with all required fields
        """
        # Dictionary of field name mappings: camelCase -> snake_case
        field_mappings = {
            "pawlsFileContent": "pawls_file_content",
            "pageCount": "page_count",
            "docLabels": "doc_labels",
            "labelledText": "labelled_text",
        }

        # Create a normalized response with both snake_case and camelCase keys
        normalized_data = {}

        for key, value in response_data.items():
            normalized_key = field_mappings.get(key, key)
            normalized_data[normalized_key] = value

            # If we have a snake_case name but the response used camelCase,
            # ensure we also include the camelCase name for backwards compatibility
            if key != normalized_key:
                normalized_data[key] = value

        return normalized_data

    def _add_images_to_result(
        self,
        result: dict[str, Any],
        pdf_bytes: bytes,
        storage_path: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Extract images from the PDF and add them to the parsed result.

        This post-processes the Docling microservice response to add image tokens
        to the PAWLs tokens array (unified token model) and image references to
        figure/image annotations.

        Args:
            result: The normalized response from the Docling microservice.
            pdf_bytes: The raw PDF bytes for image extraction.
            storage_path: Base path for storing images (e.g., "documents/123/images").
                         If provided, images are saved to storage and referenced by path.
                         If None, images are embedded as base64 (not recommended).

        Returns:
            The result dict with image tokens added to pawls_file_content tokens[].
        """
        try:
            logger.info("Extracting images from PDF for LLM consumption...")

            # Extract embedded images from PDF
            images_by_page = extract_images_from_pdf(
                pdf_bytes,
                min_width=self.min_image_width,
                min_height=self.min_image_height,
                image_format=cast(Literal["jpeg", "png"], self.image_format),
                jpeg_quality=self.image_quality,
                storage_path=storage_path,
            )

            total_images = sum(len(imgs) for imgs in images_by_page.values())
            logger.info(
                f"Extracted {total_images} image tokens from {len(images_by_page)} pages"
            )

            # Add images as tokens to PAWLs pages (unified token model)
            pawls_pages = result.get("pawls_file_content", [])

            # Track token offsets per page for image token indices
            image_token_offsets: dict[int, int] = {}

            for page_idx, page_images in images_by_page.items():
                # Defensive checks for malformed microservice data
                if not isinstance(pawls_pages, list) or page_idx >= len(pawls_pages):
                    logger.warning(f"Invalid page index {page_idx} for pawls_pages")
                    continue

                page = pawls_pages[page_idx]
                if not isinstance(page, dict):
                    logger.warning(f"Invalid page data at index {page_idx}")
                    continue

                if page_images:
                    # Get existing token count as offset for image indices
                    if "tokens" not in page:
                        page["tokens"] = []

                    token_offset = len(page["tokens"])
                    image_token_offsets[page_idx] = token_offset

                    # Add image tokens to the tokens array
                    for img_token in page_images:
                        # Convert to unified token format with required fields.
                        # Optional metadata is added only when present so we
                        # don't violate the NotRequired-but-non-None contract
                        # of PawlsTokenPythonType.
                        unified_token: PawlsTokenPythonType = {
                            "x": img_token["x"],
                            "y": img_token["y"],
                            "width": img_token["width"],
                            "height": img_token["height"],
                            "text": "",  # Required field, empty for images
                            "is_image": True,
                            "format": img_token.get("format", "jpeg"),
                        }
                        if img_token.get("content_hash") is not None:
                            unified_token["content_hash"] = img_token["content_hash"]
                        if img_token.get("original_width") is not None:
                            unified_token["original_width"] = img_token[
                                "original_width"
                            ]
                        if img_token.get("original_height") is not None:
                            unified_token["original_height"] = img_token[
                                "original_height"
                            ]
                        if img_token.get("image_type") is not None:
                            unified_token["image_type"] = img_token["image_type"]

                        # Copy image path if present
                        if "image_path" in img_token:
                            unified_token["image_path"] = img_token["image_path"]

                        page["tokens"].append(unified_token)

            # Get page dimensions for cropping
            page_dims: dict[int, tuple[float, float]] = {}
            for page_idx, page in enumerate(pawls_pages):
                page_info = page.get("page", {})
                width = float(page_info.get("width", 612))
                height = float(page_info.get("height", 792))
                page_dims[page_idx] = (width, height)

            # Process annotations to add image references for figure/image types
            annotations = result.get("labelled_text", [])
            for annotation in annotations:
                label = annotation.get("annotationLabel", "").lower()
                if label in ["figure", "image", "chart", "diagram", "picture"]:
                    self._add_image_refs_to_annotation(
                        annotation,
                        pdf_bytes,
                        image_token_offsets,
                        page_dims,
                        pawls_pages,
                        storage_path=storage_path,
                    )

            # Log summary
            annotations_with_images = sum(
                1
                for a in annotations
                if a.get("annotation_json", {})
                .get(str(a.get("page", 0)), {})
                .get("tokensJsons")
            )
            logger.info(
                f"Added image tokens to result: {total_images} total image tokens, "
                f"{annotations_with_images} annotations with image token refs"
            )

        except Exception as e:
            logger.warning(f"Failed to extract images from PDF: {e}")

        return result

    def _add_image_refs_to_annotation(
        self,
        annotation: dict[str, Any],
        pdf_bytes: bytes,
        image_token_offsets: dict[int, int],
        page_dims: dict[int, tuple[float, float]],
        pawls_pages: list[dict[str, Any]],
        storage_path: Optional[str] = None,
    ) -> None:
        """
        Add image token references to an annotation that represents a figure/image.

        In the unified token model, images are stored in the tokens[] array with
        is_image=True. This method adds tokensJsons references to image tokens
        and sets content_modalities=["IMAGE"] on annotations with image content.

        Args:
            annotation: The annotation dict to modify.
            pdf_bytes: PDF bytes for cropping if needed.
            image_token_offsets: Dict mapping page_idx to the token index where
                                 image tokens start on that page.
            page_dims: Page dimensions dict.
            pawls_pages: PAWLs pages list (may be modified to add cropped image tokens).
            storage_path: Base path for storing cropped images.
        """
        page_idx = annotation.get("page", 0)
        annotation_json = annotation.get("annotation_json", {})
        page_data = annotation_json.get(str(page_idx), {})

        bounds = page_data.get("bounds", {})
        if not bounds:
            return

        # Find image tokens in the tokens array that overlap with this annotation
        token_offset = image_token_offsets.get(page_idx, 0)
        image_token_refs = self._find_images_in_bounds(
            bounds, page_idx, pawls_pages, token_offset
        )

        # If no embedded image found, crop the region and add as new token
        if not image_token_refs:
            page_width, page_height = page_dims.get(page_idx, (612, 792))

            # Count image tokens for storage filename indexing
            img_idx = 0
            if page_idx < len(pawls_pages) and isinstance(pawls_pages[page_idx], dict):
                for token in pawls_pages[page_idx].get("tokens", []):
                    if token.get("is_image"):
                        img_idx += 1

            cropped_image = crop_image_from_pdf(
                pdf_bytes,
                page_idx,
                bounds,
                page_width,
                page_height,
                image_format=cast(Literal["jpeg", "png"], self.image_format),
                jpeg_quality=self.image_quality,
                dpi=self.image_dpi,
                storage_path=storage_path,
                img_idx=img_idx,
            )
            if cropped_image and page_idx < len(pawls_pages):
                if "tokens" not in pawls_pages[page_idx]:
                    pawls_pages[page_idx]["tokens"] = []

                # Convert cropped image to unified token format. Optional
                # metadata is added only when present (see image-extraction
                # branch above for the same pattern).
                unified_token: PawlsTokenPythonType = {
                    "x": cropped_image["x"],
                    "y": cropped_image["y"],
                    "width": cropped_image["width"],
                    "height": cropped_image["height"],
                    "text": "",  # Required field, empty for images
                    "is_image": True,
                    "format": cropped_image.get("format", "jpeg"),
                    "image_type": cropped_image.get("image_type", "cropped"),
                }
                if cropped_image.get("content_hash") is not None:
                    unified_token["content_hash"] = cropped_image["content_hash"]
                if cropped_image.get("original_width") is not None:
                    unified_token["original_width"] = cropped_image["original_width"]
                if cropped_image.get("original_height") is not None:
                    unified_token["original_height"] = cropped_image["original_height"]

                # Copy image path if present
                if "image_path" in cropped_image:
                    unified_token["image_path"] = cropped_image["image_path"]

                new_token_idx = len(pawls_pages[page_idx]["tokens"])
                pawls_pages[page_idx]["tokens"].append(unified_token)
                image_token_refs = [
                    {"pageIndex": page_idx, "tokenIndex": new_token_idx}
                ]
                logger.debug(
                    f"Cropped image token for annotation on page {page_idx} "
                    f"at token index {new_token_idx}"
                )

        # Add image token refs to the annotation's tokensJsons
        if image_token_refs:
            # Get existing tokensJsons or create empty list
            existing_tokens = page_data.get("tokensJsons", [])
            # Add image token references
            existing_tokens.extend(image_token_refs)
            page_data["tokensJsons"] = existing_tokens
            annotation_json[str(page_idx)] = page_data
            annotation["annotation_json"] = annotation_json
            # Mark annotation as containing image content
            annotation["content_modalities"] = ["IMAGE"]

    def _find_images_in_bounds(
        self,
        bounds: BoundingBoxPythonType,
        page_idx: int,
        pawls_pages: list[dict[str, Any]],
        token_offset: int,
    ) -> list[TokenIdPythonType]:
        """
        Find image tokens that overlap with the given bounding box.

        In the unified token model, images are stored in the tokens[] array
        with is_image=True. This method searches through tokens starting from
        token_offset (where image tokens begin) to find overlapping images.

        Args:
            bounds: The annotation bounding box.
            page_idx: Page index (0-based).
            pawls_pages: The PAWLs pages list containing tokens.
            token_offset: The token index where image tokens start on this page.

        Returns:
            List of TokenIdPythonType references for overlapping image tokens.
        """
        if not isinstance(pawls_pages, list) or page_idx >= len(pawls_pages):
            return []

        page = pawls_pages[page_idx]
        if not isinstance(page, dict):
            return []

        page_tokens = page.get("tokens", [])
        if not page_tokens or token_offset >= len(page_tokens):
            return []

        token_refs: list[TokenIdPythonType] = []
        ann_left = float(bounds.get("left", 0))
        ann_top = float(bounds.get("top", 0))
        ann_right = float(bounds.get("right", 0))
        ann_bottom = float(bounds.get("bottom", 0))

        # Search through tokens starting from token_offset
        for token_idx in range(token_offset, len(page_tokens)):
            token = page_tokens[token_idx]

            # Only consider image tokens
            if not token.get("is_image"):
                continue

            img_left = float(token["x"])
            img_top = float(token["y"])
            img_right = img_left + float(token["width"])
            img_bottom = img_top + float(token["height"])

            # Check for overlap
            if (
                ann_left < img_right
                and ann_right > img_left
                and ann_top < img_bottom
                and ann_bottom > img_top
            ):
                token_refs.append({"pageIndex": page_idx, "tokenIndex": token_idx})

        return token_refs
