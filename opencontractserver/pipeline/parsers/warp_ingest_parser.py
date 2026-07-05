"""Warp-Ingest PDF parser (REST client).

Delegates PDF parsing to a `Warp-Ingest <https://github.com/Open-Source-Legal/Warp-Ingest>`_
microservice via its REST API. Warp-Ingest is a deterministic, rule-based PDF
parser (pdfplumber word boxes + font/graphics heuristics, optional RapidOCR for
scanned pages) that renders directly to the OpenContracts structural export
format — PAWLS word tokens, per-block structural annotations, and a heading
hierarchy expressed as ``parent_id`` links + explicit relationships.

This mirrors the :class:`~opencontractserver.pipeline.parsers.docling_parser_rest.DoclingParser`
pattern: the heavy parsing dependencies live in an isolated container (run the
official ``ghcr.io/open-source-legal/warp-ingest`` image, see
``docs/pipelines/warp_ingest_parser.md``) and OpenContracts talks to it over
HTTP, so the Django image stays slim.

Unlike Docling, Warp-Ingest is **not** chunked here: it is CPU-only (no per-page
GPU layout model) and its native API accepts a whole PDF, and it performs
cross-page structure joining (heading hierarchies, tables and lists that span
page boundaries) that page-range chunking would fragment. The whole document is
sent in a single request, matching :class:`DocxodusServiceParser`'s non-chunked
REST shape.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Optional, cast

import requests
from django.core.files.storage import default_storage
from requests.exceptions import ConnectionError, RequestException, Timeout

from opencontractserver.constants.document_processing import (
    WARP_INGEST_PARSER_REQUEST_TIMEOUT_SECONDS,
)
from opencontractserver.pipeline.base.exceptions import DocumentParsingError
from opencontractserver.pipeline.base.file_types import FileTypeEnum
from opencontractserver.pipeline.base.parser import BaseParser
from opencontractserver.pipeline.base.settings_schema import (
    PipelineSetting,
    SettingType,
)
from opencontractserver.types.dicts import OpenContractDocExport
from opencontractserver.utils.cloud import maybe_add_cloud_run_auth

logger = logging.getLogger(__name__)

# Header Warp-Ingest reads the API key from. We send the key here (rather than
# ``Authorization: Bearer <key>``, which Warp-Ingest also accepts) so the
# ``Authorization`` header stays free for a Google Cloud Run IAM id_token when
# the service runs behind Cloud Run IAM (see ``maybe_add_cloud_run_auth``).
WARP_INGEST_API_KEY_HEADER = "X-API-Key"

# render_format the client requests: Warp-Ingest emits an OpenContractDocExport
# directly under the ``result`` key for this value.
WARP_INGEST_RENDER_FORMAT = "opencontracts"


class WarpIngestParser(BaseParser):
    """Parse PDFs via a Warp-Ingest microservice and return an OpenContractDocExport.

    Settings are loaded from the ``PipelineSettings`` database singleton (seeded
    from environment via the ``migrate_pipeline_settings`` management command);
    the dataclass defaults are the runtime fallback when nothing is stored.
    """

    title = "Warp-Ingest Parser (REST)"
    description = (
        "Parses PDF documents using a Warp-Ingest microservice — a deterministic, "
        "rule-based parser that renders directly to the OpenContracts format."
    )
    author = "OpenContracts Team"
    dependencies = ["requests"]
    supported_file_types = [FileTypeEnum.PDF]

    @dataclass
    class Settings:
        """Configuration schema for WarpIngestParser."""

        service_url: str = field(
            default="http://warp-ingest:5001/api/parse",
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.REQUIRED,
                    required=True,
                    description="URL of the Warp-Ingest /api/parse endpoint",
                    env_var="WARP_INGEST_PARSER_SERVICE_URL",
                )
            },
        )
        api_key: str = field(
            default="",
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.SECRET,
                    description=(
                        "API key sent in the X-API-Key header (Warp-Ingest "
                        "WARP_API_KEY). Leave blank if the service is unauthenticated."
                    ),
                    env_var="WARP_INGEST_API_KEY",
                )
            },
        )
        request_timeout: int = field(
            default=WARP_INGEST_PARSER_REQUEST_TIMEOUT_SECONDS,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Request timeout in seconds",
                    env_var="WARP_INGEST_PARSER_TIMEOUT",
                )
            },
        )
        use_cloud_run_iam_auth: bool = field(
            default=False,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Force Google Cloud Run IAM authentication",
                    env_var="WARP_INGEST_USE_CLOUD_RUN_IAM_AUTH",
                )
            },
        )
        apply_ocr: bool = field(
            default=False,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description=(
                        "Force OCR on every page. Leave False to let Warp-Ingest "
                        "auto-detect pages that lack an embedded text layer."
                    ),
                    env_var="WARP_INGEST_APPLY_OCR",
                )
            },
        )
        disable_ocr: bool = field(
            default=False,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Disable OCR entirely (mutually exclusive with apply_ocr)",
                    env_var="WARP_INGEST_DISABLE_OCR",
                )
            },
        )
        semantic_units: bool = field(
            default=False,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Append Warp-Ingest's Semantic-Unit clause annotation layer",
                    env_var="WARP_INGEST_SEMANTIC_UNITS",
                )
            },
        )
        include_images: bool = field(
            default=False,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description=(
                        "Embed extracted images in the export for multimodal "
                        "processing (increases payload size)."
                    ),
                    env_var="WARP_INGEST_INCLUDE_IMAGES",
                )
            },
        )

    def __init__(self):
        """Initialize the Warp-Ingest REST parser with settings from PipelineSettings."""
        super().__init__()  # Loads settings via PipelineComponentBase
        s = self.settings if self.settings is not None else self.Settings()

        self.service_url = s.service_url
        self.api_key = s.api_key
        self.request_timeout = s.request_timeout
        self.use_cloud_run_iam_auth = s.use_cloud_run_iam_auth
        self.apply_ocr = s.apply_ocr
        self.disable_ocr = s.disable_ocr
        self.semantic_units = s.semantic_units
        self.include_images = s.include_images

        logger.info(
            f"WarpIngestParser initialized with service URL: {self.service_url}, "
            f"apply_ocr={self.apply_ocr}, disable_ocr={self.disable_ocr}, "
            f"semantic_units={self.semantic_units}, include_images={self.include_images}"
        )

    def _parse_document_impl(
        self, user_id: int, doc_id: int, **all_kwargs
    ) -> Optional[OpenContractDocExport]:
        """Send a PDF to the Warp-Ingest microservice and return the parsed export.

        Args:
            user_id: The ID of the user parsing the document.
            doc_id: The ID of the target Document in the database.
            **all_kwargs: Effective settings + call-time overrides
                (``apply_ocr``, ``disable_ocr``, ``semantic_units``,
                ``include_images``).

        Returns:
            OpenContractDocExport with structural annotations, relationships and
            PAWLS tokens produced by Warp-Ingest.
        """
        from opencontractserver.documents.models import Document

        logger.info(f"WarpIngestParser - Parsing doc {doc_id} for user {user_id}")

        document = Document.objects.get(pk=doc_id)

        # ``pdf_file`` is the generic storage field for every uploaded document
        # (the name is historical, not format-specific).
        if not document.pdf_file.name:
            raise DocumentParsingError(
                f"Document {doc_id} has no PDF file associated",
                is_transient=False,
            )

        # Resolve per-call overrides on top of the component settings.
        apply_ocr = all_kwargs.get("apply_ocr", self.apply_ocr)
        disable_ocr = all_kwargs.get("disable_ocr", self.disable_ocr)
        semantic_units = all_kwargs.get("semantic_units", self.semantic_units)
        include_images = all_kwargs.get("include_images", self.include_images)

        # Warp-Ingest returns 422 when both are set; fail fast with a clear,
        # non-transient message instead of round-tripping to the service.
        if apply_ocr and disable_ocr:
            raise DocumentParsingError(
                f"WarpIngestParser misconfigured for document {doc_id}: "
                "apply_ocr and disable_ocr are mutually exclusive.",
                is_transient=False,
            )

        with default_storage.open(document.pdf_file.name, "rb") as f:
            pdf_bytes = f.read()

        # A ``.pdf`` filename + explicit content type satisfy Warp-Ingest's
        # media-type check (it returns 415 for non-PDF uploads).
        filename = document.title or f"doc_{doc_id}.pdf"
        if not filename.lower().endswith(".pdf"):
            filename = f"{filename}.pdf"

        params = {
            "render_format": WARP_INGEST_RENDER_FORMAT,
            # Serialize as lowercase strings so FastAPI's bool coercion is
            # unambiguous ("true"/"false").
            "apply_ocr": str(apply_ocr).lower(),
            "disable_ocr": str(disable_ocr).lower(),
            "semantic_units": str(semantic_units).lower(),
            "include_images": str(include_images).lower(),
        }

        headers: dict[str, str | bytes] = {}
        if self.api_key:
            headers[WARP_INGEST_API_KEY_HEADER] = self.api_key
        # Attach a Cloud Run IAM id_token when the service runs behind Cloud Run
        # IAM (or when forced). This sets ``Authorization``; the API key rides on
        # its own ``X-API-Key`` header so the two never collide.
        headers = maybe_add_cloud_run_auth(
            self.service_url, headers, force=self.use_cloud_run_iam_auth
        )

        logger.info(
            f"Sending PDF (doc {doc_id}) to Warp-Ingest parser service: "
            f"{self.service_url}"
        )
        try:
            response = requests.post(
                self.service_url,
                params=params,
                files={"file": (filename, pdf_bytes, "application/pdf")},
                # ``requests`` types headers as MutableMapping[str, str | bytes];
                # cast widens our narrower dict for the call (see docling parser).
                headers=cast(Any, headers),
                timeout=self.request_timeout,
            )
            response.raise_for_status()
        except Timeout:
            msg = (
                f"Request to Warp-Ingest parser service timed out after "
                f"{self.request_timeout}s for document {doc_id}"
            )
            logger.error(msg)
            raise DocumentParsingError(msg, is_transient=True)
        except ConnectionError:
            msg = (
                f"Failed to connect to Warp-Ingest parser service at "
                f"{self.service_url} for document {doc_id}"
            )
            logger.error(msg)
            raise DocumentParsingError(msg, is_transient=True)
        except RequestException as e:
            # 4xx (bad request, unsupported media type, auth) are permanent;
            # 5xx (server error, unavailable) are transient and worth retrying.
            is_transient = True
            status_code = None
            response_text = ""
            if hasattr(e, "response") and e.response is not None:
                status_code = e.response.status_code
                response_text = e.response.text[:500]
                if 400 <= status_code < 500:
                    is_transient = False

            msg = f"Request to Warp-Ingest parser service failed for document {doc_id}: {e}"
            if status_code:
                msg += f" (status={status_code})"
            if response_text:
                msg += f" - Response: {response_text}"

            logger.error(msg)
            raise DocumentParsingError(msg, is_transient=is_transient)

        export = self._extract_export(response.json(), doc_id)

        logger.info(
            f"Successfully processed document {doc_id} through Warp-Ingest service "
            f"({export.get('page_count')} pages, "
            f"{len(export.get('labelled_text', []))} annotations, "
            f"{len(export.get('relationships', []))} relationships)"
        )
        return export

    @staticmethod
    def _extract_export(
        response_data: dict[str, Any], doc_id: int
    ) -> OpenContractDocExport:
        """Pull the OpenContractDocExport out of a Warp-Ingest response.

        Warp-Ingest wraps the export as ``{"page_dim": ..., "num_pages": ...,
        "result": <OpenContractDocExport>}`` for ``render_format=opencontracts``.
        We read ``result`` but fall back to the top-level body if a future API
        revision returns the export unwrapped — either way we validate that it
        carries the fields ``save_parsed_data`` needs before handing it on, so a
        shape change surfaces as a clear parse error rather than a silent empty
        document.

        The export already uses the OpenContracts field names (snake_case
        top-level keys, camelCase ``annotationLabel``/``rawText`` within
        annotations), so no key normalization is required.
        """
        if not isinstance(response_data, dict):
            raise DocumentParsingError(
                f"Warp-Ingest returned a non-object response for document {doc_id}",
                is_transient=False,
            )

        export = response_data.get("result", response_data)

        if not isinstance(export, dict) or not any(
            key in export for key in ("content", "pawls_file_content", "labelled_text")
        ):
            snippet = str(response_data)[:500]
            raise DocumentParsingError(
                f"Warp-Ingest response for document {doc_id} is missing the "
                f"OpenContracts export payload. Response: {snippet}",
                is_transient=False,
            )

        return cast(OpenContractDocExport, export)
