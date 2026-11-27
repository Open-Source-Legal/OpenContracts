"""LiteParse (OCRia-nano) PDF parser (REST client).

Delegates PDF parsing to the optional ``compose/liteparse`` microservice, which
runs LlamaIndex's `LiteParse <https://github.com/run-llama/liteparse>`_ with the
OCRia-nano OCR/layout models. Pages that already have a text layer use the
PDF's own text; only pages that need OCR go through OCRia-nano.

The service returns LiteParse's word boxes and layout blocks as plain JSON;
:func:`~opencontractserver.pipeline.parsers.liteparse_conversion.liteparse_response_to_export`
turns that into the OpenContracts export (so Django never imports
``liteparse``). Like :class:`WarpIngestParser`, the whole document is sent in
one request (no page-range chunking), which keeps heading hierarchies that span
pages intact. Setup and licensing: ``docs/pipelines/liteparse_parser.md``.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Optional, cast

import requests
from django.core.files.storage import default_storage
from requests.exceptions import RequestException

from opencontractserver.constants.document_processing import (
    LITEPARSE_API_KEY_HEADER,
    LITEPARSE_MAX_FILE_SIZE_MB,
    LITEPARSE_PARSER_REQUEST_TIMEOUT_SECONDS,
)
from opencontractserver.pipeline.base.exceptions import DocumentParsingError
from opencontractserver.pipeline.base.file_types import FileTypeEnum
from opencontractserver.pipeline.base.parser import BaseParser
from opencontractserver.pipeline.base.settings_schema import (
    PipelineSetting,
    SettingType,
)
from opencontractserver.pipeline.parsers.liteparse_conversion import (
    liteparse_response_to_export,
)
from opencontractserver.types.dicts import OpenContractDocExport
from opencontractserver.utils.cloud import maybe_add_cloud_run_auth
from opencontractserver.utils.parser_service_http import (
    decode_parser_service_json,
    parser_service_request_error,
    safe_pdf_filename,
)

logger = logging.getLogger(__name__)

# Service name used in classified error messages.
LITEPARSE_SERVICE_NAME = "LiteParse"

_BYTES_PER_MB = 1024 * 1024


class LiteParseParser(BaseParser):
    """Parse PDFs via the LiteParse (OCRia-nano) microservice.

    Settings are loaded from the ``PipelineSettings`` database singleton (seeded
    from environment via ``migrate_pipeline_settings``); the dataclass defaults
    are the runtime fallback when nothing is stored.
    """

    title = "LiteParse Parser (OCRia-nano, REST)"
    description = (
        "Layout-aware PDF parser using a LiteParse microservice. Pages with a "
        "text layer use the PDF's own text; scanned pages are OCR'd with "
        "LlamaIndex's OCRia-nano models."
    )
    author = "OpenContracts Team"
    dependencies = ["requests"]
    supported_file_types = [FileTypeEnum.PDF]

    @dataclass
    class Settings:
        """Configuration schema for LiteParseParser."""

        service_url: str = field(
            default="http://liteparse:8000/parse",
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.REQUIRED,
                    required=True,
                    description="URL of the LiteParse service /parse endpoint",
                    env_var="LITEPARSE_PARSER_SERVICE_URL",
                )
            },
        )
        api_key: str = field(
            default="",
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.SECRET,
                    description=(
                        "API key sent in the X-API-Key header; must match the "
                        "service's LITEPARSE_API_KEY. The service always "
                        "requires one, so a blank value yields a 401."
                    ),
                    env_var="LITEPARSE_API_KEY",
                )
            },
        )
        request_timeout: int = field(
            default=LITEPARSE_PARSER_REQUEST_TIMEOUT_SECONDS,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Request timeout in seconds",
                    env_var="LITEPARSE_PARSER_TIMEOUT",
                )
            },
        )
        use_cloud_run_iam_auth: bool = field(
            default=False,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Force Google Cloud Run IAM authentication",
                    env_var="LITEPARSE_USE_CLOUD_RUN_IAM_AUTH",
                )
            },
        )
        max_file_size_mb: int = field(
            default=LITEPARSE_MAX_FILE_SIZE_MB,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description=(
                        "Maximum PDF size in MB. The whole file is buffered in "
                        "memory and POSTed in one request, so this caps a "
                        "worker's peak memory per parse."
                    ),
                    env_var="LITEPARSE_MAX_FILE_SIZE_MB",
                )
            },
        )

    def __init__(self, **kwargs):
        """Initialize the LiteParse REST parser with settings from PipelineSettings."""
        super().__init__(**kwargs)
        s = self.settings if self.settings is not None else self.Settings()

        self.service_url = s.service_url
        self.api_key = s.api_key
        self.request_timeout = s.request_timeout
        self.use_cloud_run_iam_auth = s.use_cloud_run_iam_auth
        self.max_file_size_mb = s.max_file_size_mb

        logger.info(
            f"LiteParseParser initialized with service URL: {self.service_url}, "
            f"max_file_size_mb={self.max_file_size_mb}"
        )

    def _parse_document_impl(
        self, user_id: int, doc_id: int, **all_kwargs
    ) -> Optional[OpenContractDocExport]:
        """Read the Document's PDF and parse it through the LiteParse service."""
        from opencontractserver.documents.models import Document

        logger.info(f"LiteParseParser - Parsing doc {doc_id} for user {user_id}")
        document = Document.objects.get(pk=doc_id)

        if not document.pdf_file.name:
            raise DocumentParsingError(
                f"Document {doc_id} has no PDF file associated",
                is_transient=False,
            )

        # Reject oversized files from storage metadata before buffering them.
        file_size_mb = default_storage.size(document.pdf_file.name) / _BYTES_PER_MB
        if file_size_mb > self.max_file_size_mb:
            raise DocumentParsingError(
                f"PDF for document {doc_id} is {file_size_mb:.1f} MB, exceeding "
                f"the {self.max_file_size_mb} MB LiteParse limit. Adjust "
                "LITEPARSE_MAX_FILE_SIZE_MB to raise it.",
                is_transient=False,
            )

        with default_storage.open(document.pdf_file.name, "rb") as f:
            pdf_bytes = f.read()

        return self.parse_pdf_bytes(
            pdf_bytes, title=document.title or "", doc_id=doc_id, **all_kwargs
        )

    def parse_pdf_bytes(
        self, pdf_bytes: bytes, *, title: str = "", doc_id: int = 0, **all_kwargs
    ) -> OpenContractDocExport:
        """Parse raw PDF bytes without reading a Document or storage fields."""
        if len(pdf_bytes) > self.max_file_size_mb * _BYTES_PER_MB:
            raise DocumentParsingError(
                f"PDF exceeds the {self.max_file_size_mb} MB LiteParse limit. "
                "Adjust LITEPARSE_MAX_FILE_SIZE_MB to raise it.",
                is_transient=False,
            )

        headers: dict[str, str | bytes] = {}
        if self.api_key:
            headers[LITEPARSE_API_KEY_HEADER] = self.api_key
        headers = maybe_add_cloud_run_auth(
            self.service_url, headers, force=self.use_cloud_run_iam_auth
        )

        logger.info(
            f"Sending PDF (doc {doc_id}) to LiteParse service: {self.service_url}"
        )
        try:
            response = requests.post(
                self.service_url,
                files={
                    "file": (
                        safe_pdf_filename(title, doc_id),
                        pdf_bytes,
                        "application/pdf",
                    )
                },
                # ``requests`` types headers as MutableMapping[str, str | bytes].
                headers=cast(Any, headers),
                timeout=self.request_timeout,
            )
            response.raise_for_status()
        except RequestException as e:
            raise parser_service_request_error(
                e,
                service_name=LITEPARSE_SERVICE_NAME,
                service_url=self.service_url,
                timeout=self.request_timeout,
                doc_id=doc_id,
            ) from e

        payload = decode_parser_service_json(
            response, service_name=LITEPARSE_SERVICE_NAME, doc_id=doc_id
        )
        return liteparse_response_to_export(payload, title=title, doc_id=doc_id)
