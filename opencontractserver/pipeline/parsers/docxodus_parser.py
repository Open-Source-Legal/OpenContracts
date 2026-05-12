import base64
import logging
from dataclasses import dataclass, field
from typing import Any, Optional, cast

import requests
from django.core.files.storage import default_storage
from requests.exceptions import ConnectionError, RequestException, Timeout

from opencontractserver.annotations.models import LABEL_TYPES
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


class DocxodusServiceParser(BaseParser):
    """
    Parser that delegates DOCX processing to a Docxodus microservice via REST API.

    The microservice wraps Docxodus's OpenContractExporter.Export(), which produces
    OpenContractDocExport-compatible JSON with structural annotations and character
    offsets. Since the frontend WASM renderer also uses the same Docxodus library,
    character offsets are guaranteed to align perfectly.
    """

    title = "Docxodus Parser (REST)"
    description = "Parses DOCX documents using Docxodus microservice API."
    author = "OpenContracts Team"
    dependencies = ["requests"]
    supported_file_types = [FileTypeEnum.DOCX]

    @dataclass
    class Settings:
        """Configuration schema for DocxodusServiceParser."""

        service_url: str = field(
            default="http://docxodus-parser:8080/parse",
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.REQUIRED,
                    required=True,
                    description="URL of the Docxodus parser microservice",
                    env_var="DOCXODUS_PARSER_SERVICE_URL",
                )
            },
        )
        request_timeout: int = field(
            default=120,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Request timeout in seconds",
                    env_var="DOCXODUS_PARSER_TIMEOUT",
                )
            },
        )
        use_cloud_run_iam_auth: bool = field(
            default=False,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Force Google Cloud Run IAM authentication",
                    env_var="DOCXODUS_USE_CLOUD_RUN_IAM_AUTH",
                )
            },
        )
        max_file_size_mb: int = field(
            default=50,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Maximum DOCX file size in MB before base64 encoding",
                    env_var="DOCXODUS_MAX_FILE_SIZE_MB",
                )
            },
        )

    def __init__(self):
        """Initialize the Docxodus REST parser with settings from PipelineSettings."""
        super().__init__()
        s = self.settings if self.settings is not None else self.Settings()
        self.service_url = s.service_url
        self.request_timeout = s.request_timeout
        self.use_cloud_run_iam_auth = s.use_cloud_run_iam_auth
        self.max_file_size_mb = s.max_file_size_mb

        logger.info(
            f"DocxodusServiceParser initialized with service URL: {self.service_url}"
        )

    def _parse_document_impl(
        self, user_id: int, doc_id: int, **all_kwargs
    ) -> Optional[OpenContractDocExport]:
        """
        Send a DOCX document to the Docxodus microservice for parsing.

        Args:
            user_id: The ID of the user parsing the document.
            doc_id: The ID of the target Document in the database.
            **all_kwargs: Additional optional arguments.

        Returns:
            OpenContractDocExport with structural annotations and character offsets.
        """
        from opencontractserver.documents.models import Document

        logger.info(f"DocxodusServiceParser - Parsing doc {doc_id} for user {user_id}")

        document = Document.objects.get(pk=doc_id)

        # pdf_file is the generic storage field for all uploaded documents
        # (PDF, DOCX, TXT, etc.) — the name is historical, not format-specific.
        if not document.pdf_file.name:
            logger.error(f"No DOCX file found for document {doc_id}")
            return None

        # Read DOCX bytes from storage
        with default_storage.open(document.pdf_file.name, "rb") as f:
            docx_bytes = f.read()

        # Reject files exceeding the configured size limit
        file_size_mb = len(docx_bytes) / (1024 * 1024)
        if file_size_mb > self.max_file_size_mb:
            raise DocumentParsingError(
                f"DOCX file for document {doc_id} is {file_size_mb:.1f} MB, "
                f"exceeding the {self.max_file_size_mb} MB limit. "
                f"Adjust DOCXODUS_MAX_FILE_SIZE_MB to increase the limit.",
                is_transient=False,
            )

        # Base64-encode for JSON transport
        docx_base64 = base64.b64encode(docx_bytes).decode("utf-8")

        payload = {
            "filename": document.title or f"doc_{doc_id}.docx",
            "docx_base64": docx_base64,
        }

        try:
            headers: dict[str, str] = {"Content-Type": "application/json"}
            headers = maybe_add_cloud_run_auth(
                self.service_url, headers, force=self.use_cloud_run_iam_auth
            )

            response = requests.post(
                self.service_url,
                json=cast(Any, payload),
                headers=headers,
                timeout=self.request_timeout,
            )
            response.raise_for_status()

        except Timeout:
            msg = (
                f"Request to Docxodus parser service timed out after "
                f"{self.request_timeout}s for document {doc_id}"
            )
            logger.error(msg)
            raise DocumentParsingError(msg, is_transient=True)

        except ConnectionError:
            msg = (
                f"Failed to connect to Docxodus parser service at "
                f"{self.service_url} for document {doc_id}"
            )
            logger.error(msg)
            raise DocumentParsingError(msg, is_transient=True)

        except RequestException as e:
            is_transient = True
            status_code = None
            response_text = ""

            if hasattr(e, "response") and e.response is not None:
                status_code = e.response.status_code
                response_text = e.response.text[:500]
                if 400 <= status_code < 500:
                    is_transient = False

            msg = (
                f"Request to Docxodus parser service failed for document {doc_id}: {e}"
            )
            if status_code:
                msg += f" (status={status_code})"
            if response_text:
                msg += f" - Response: {response_text}"

            logger.error(msg)
            raise DocumentParsingError(msg, is_transient=is_transient)

        # Parse and normalize the response
        result = response.json()
        normalized = self._normalize_response(result)

        logger.info(
            f"Successfully processed DOCX document {doc_id} through Docxodus service"
        )
        return cast(OpenContractDocExport, normalized)

    @staticmethod
    def _normalize_response(response_data: dict[str, Any]) -> dict[str, Any]:
        """
        Normalize the microservice response from camelCase to snake_case field names.

        Args:
            response_data: Raw JSON response from the microservice.

        Returns:
            Normalized response compatible with OpenContractDocExport.
        """
        field_mappings = {
            "pawlsFileContent": "pawls_file_content",
            "pageCount": "page_count",
            "docLabels": "doc_labels",
            "labelledText": "labelled_text",
            "textLabels": "text_labels",
            "fileType": "file_type",
            "structuralSetHash": "structural_set_hash",
        }

        # Validate required fields before normalizing
        has_content = "content" in response_data
        has_labelled = (
            "labelledText" in response_data or "labelled_text" in response_data
        )
        if not has_content or not has_labelled:
            missing = []
            if not has_content:
                missing.append("content")
            if not has_labelled:
                missing.append("labelledText")
            raise DocumentParsingError(
                f"Docxodus response missing required fields: {', '.join(missing)}",
                is_transient=False,
            )

        normalized: dict[str, Any] = {}

        for key, value in response_data.items():
            normalized_key = field_mappings.get(key, key)
            normalized[normalized_key] = value

        # Normalize nested annotation fields (camelCase → snake_case)
        if "labelled_text" in normalized:
            normalized["labelled_text"] = [
                DocxodusServiceParser._normalize_annotation(ann)
                for ann in normalized["labelled_text"]
            ]

        # Normalize relationship fields
        if "relationships" in normalized:
            normalized["relationships"] = [
                DocxodusServiceParser._normalize_relationship(rel)
                for rel in normalized["relationships"]
            ]

        return normalized

    @staticmethod
    def _normalize_annotation(ann: dict[str, Any]) -> dict[str, Any]:
        """Normalize annotation fields to match the OpenContractDocExport format.

        The export format uses a mix of camelCase and snake_case:
        - annotationLabel, rawText stay camelCase (used by import_annotations)
        - annotationJson → annotation_json (snake_case in import code)
        - annotationType → annotation_type (dropped if not a valid LABEL_TYPES value)
        - contentModalities → content_modalities
        - parentId → parent_id
        """
        valid_annotation_types = {choice[0] for choice in LABEL_TYPES}

        ann_mappings = {
            "annotationJson": "annotation_json",
            "parentId": "parent_id",
            "annotationType": "annotation_type",
            "contentModalities": "content_modalities",
        }

        normalized: dict[str, Any] = {}
        for key, value in ann.items():
            normalized_key = ann_mappings.get(key, key)
            normalized[normalized_key] = value

        # Drop invalid annotation_type so import_annotations falls back to
        # the label_type determined by file type (e.g. SPAN_LABEL for DOCX).
        if normalized.get("annotation_type") not in valid_annotation_types:
            normalized.pop("annotation_type", None)

        return normalized

    @staticmethod
    def _normalize_relationship(rel: dict[str, Any]) -> dict[str, Any]:
        """Normalize a single relationship dict from camelCase to snake_case."""
        rel_mappings = {
            "sourceAnnotationIds": "source_annotation_ids",
            "targetAnnotationIds": "target_annotation_ids",
        }

        normalized: dict[str, Any] = {}
        for key, value in rel.items():
            normalized_key = rel_mappings.get(key, key)
            normalized[normalized_key] = value

        return normalized
