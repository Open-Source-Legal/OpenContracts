"""
Base class for file converters — pipeline components that convert uploads in
formats the pipeline does not natively parse (e.g. .doc, .rtf, .odt) into PDF
*before* the parser stage runs.

Conversion is an optional, extension-keyed step: an admin selects a converter
(``PipelineSettings.default_file_converter``) and optionally narrows the set of
extensions it handles via the converter's ``convert_extensions`` component
setting. Once a document is converted, its ``file_type`` flips to
``application/pdf`` and the existing PDF parser/thumbnailer/embedder machinery
takes over — converters never need FileTypeEnum members for their source
formats.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from typing import ClassVar

from django.core.files.base import ContentFile

from opencontractserver.constants.document_processing import (
    OCTET_STREAM_MIME_TYPE,
    PDF_MIME_TYPE,
)
from opencontractserver.pipeline.base.exceptions import FileConversionError
from opencontractserver.pipeline.base.file_types import NATIVE_PIPELINE_EXTENSIONS

from .base_component import PipelineComponentBase

logger = logging.getLogger(__name__)

_OLE_COMPOUND_DOCUMENT_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_MS_WORD_EXTENSIONS = frozenset({"doc", "dot"})


def normalize_extension(value: str) -> str:
    """Normalize a file extension: strip whitespace and leading dots, lowercase."""
    return value.strip().lstrip(".").lower()


def extension_for_filename(filename: str) -> str:
    """Return the normalized extension of ``filename`` ('' when it has none)."""
    return normalize_extension(os.path.splitext(filename or "")[1])


def source_mime_type_for_conversion(
    filename: str, stored_file_type: str, source_bytes: bytes
) -> str:
    """Return safe provenance MIME for a successfully converted source file.

    Convertible uploads are intentionally stored as ``application/octet-stream``
    before conversion so browser-active source formats cannot be served with an
    executable content type. Preserve that safety boundary for ambiguous input,
    but recover the useful Word provenance for genuine OLE Compound Document
    uploads.
    """
    if stored_file_type != OCTET_STREAM_MIME_TYPE:
        return stored_file_type

    if extension_for_filename(
        filename
    ) in _MS_WORD_EXTENSIONS and source_bytes.startswith(_OLE_COMPOUND_DOCUMENT_MAGIC):
        return "application/msword"

    return stored_file_type


class BaseFileConverter(PipelineComponentBase, ABC):
    """
    Abstract base file converter. Converters should inherit from this class.

    Subclasses declare ``supported_extensions`` (the formats they can turn
    into PDF) and implement :meth:`_convert_to_pdf_impl`. The active set of
    extensions is further narrowed by the ``convert_extensions`` component
    setting (comma-separated; empty = all supported) and always excludes
    :data:`NATIVE_PIPELINE_EXTENSIONS` so natively-parsed formats (pdf, txt,
    docx, md) can never be routed through conversion.
    """

    # Lowercase extensions WITHOUT a leading dot (e.g. "doc", "rtf").
    supported_extensions: ClassVar[list[str]] = []

    def __init__(self, **kwargs):
        """
        Initializes the converter.
        Kwargs are passed to the superclass constructor (PipelineComponentBase).
        """
        super().__init__(**kwargs)

    @abstractmethod
    def _convert_to_pdf_impl(
        self, file_bytes: bytes, filename: str, **all_kwargs
    ) -> bytes | None:
        """
        Abstract internal method to convert a file to PDF.
        Concrete subclasses must implement this method.

        Args:
            file_bytes: Raw bytes of the source file.
            filename: Original filename (its extension tells the conversion
                backend which import filter to use).
            **all_kwargs: All keyword arguments, including component settings
                and direct call-time arguments.

        Returns:
            The converted PDF bytes, or None if conversion produced nothing.

        Raises:
            FileConversionError: On conversion failure (with ``is_transient``
                set per the transient/permanent contract).
        """
        pass

    def convert_to_pdf(
        self, file_bytes: bytes, filename: str, **direct_kwargs
    ) -> bytes | None:
        """
        Convert a file to PDF, automatically injecting component settings.

        Args:
            file_bytes: Raw bytes of the source file.
            filename: Original filename.
            **direct_kwargs: Call-time arguments that override component
                settings.

        Returns:
            The converted PDF bytes, or None if conversion failed.
        """
        merged_kwargs = {**self.get_component_settings(), **direct_kwargs}
        return self._convert_to_pdf_impl(file_bytes, filename, **merged_kwargs)

    def get_enabled_extensions(self) -> frozenset[str]:
        """
        Resolve the set of extensions this converter is active for.

        Intersection of ``supported_extensions`` with the ``convert_extensions``
        component setting (comma-separated extension list; empty means "every
        supported extension"), always excluding native pipeline extensions.

        Returns:
            Frozen set of normalized extensions (no leading dots).
        """
        supported = {
            normalize_extension(ext) for ext in self.supported_extensions
        } - NATIVE_PIPELINE_EXTENSIONS

        configured_raw = ""
        settings_obj = self.settings
        if settings_obj is not None:
            configured_raw = getattr(settings_obj, "convert_extensions", "") or ""

        requested = {
            normalize_extension(part)
            for part in configured_raw.split(",")
            if part.strip()
        }
        if not requested:
            return frozenset(supported)
        return frozenset(supported & requested)

    def convert_document(self, user_id: int, doc_id: int, **kwargs) -> bool:
        """
        Convert a Document's stored file to PDF in place.

        Reads the source bytes from ``Document.pdf_file`` (the generic binary
        storage field for all non-text uploads), converts them, then:

        - re-points ``original_file`` at the existing source blob (a reference
          assignment — the original bytes are never copied or deleted),
        - records the pre-conversion MIME type in ``original_file_type``,
        - saves the converted PDF into ``pdf_file``,
        - flips ``file_type`` to ``application/pdf`` and refreshes
          ``pdf_file_hash``,

        so the downstream parser/thumbnailer stages see an ordinary PDF.

        Args:
            user_id: ID of the user the document is being ingested for.
            doc_id: ID of the document to convert.
            **kwargs: Call-time overrides forwarded to :meth:`convert_to_pdf`.

        Returns:
            True when the document was converted; False when conversion was a
            no-op (already a PDF, no binary file, or extension not enabled).

        Raises:
            FileConversionError: If conversion fails.
        """
        from opencontractserver.documents.models import Document

        document = Document.objects.get(pk=doc_id)

        if document.file_type == PDF_MIME_TYPE:
            return False
        if not document.pdf_file or not document.pdf_file.name:
            # Text uploads live in txt_extract_file and are parsed natively.
            return False

        original_name = os.path.basename(document.pdf_file.name)
        extension = extension_for_filename(original_name)
        if extension not in self.get_enabled_extensions():
            logger.debug(
                f"[convert_document] Extension '{extension}' of document "
                f"{doc_id} not enabled for {self.__class__.__name__}; skipping."
            )
            return False

        logger.info(
            f"[convert_document] Converting document {doc_id} "
            f"('{original_name}', {document.file_type}) to PDF with "
            f"{self.__class__.__name__} for user {user_id}"
        )

        with document.pdf_file.open("rb") as source:
            file_bytes = source.read()

        pdf_bytes = self.convert_to_pdf(file_bytes, original_name, **kwargs)
        if not pdf_bytes:
            raise FileConversionError(
                f"Converter {self.__class__.__name__} returned no PDF for "
                f"document {doc_id}",
                is_transient=True,
            )

        # Preserve the source upload: point original_file at the blob that
        # pdf_file currently references (no storage copy), then write the
        # converted PDF as a NEW blob. The source blob stays referenced, so
        # delete-time blob GC (Document.blob_field_names) still covers it.
        document.original_file.name = document.pdf_file.name
        document.original_file_type = source_mime_type_for_conversion(
            original_name, document.file_type, file_bytes
        )

        stem = os.path.splitext(original_name)[0] or f"doc_{doc_id}"
        document.pdf_file.save(f"{stem}.pdf", ContentFile(pdf_bytes), save=False)
        document.file_type = PDF_MIME_TYPE
        document.save(
            update_fields=[
                "original_file",
                "original_file_type",
                "pdf_file",
                "file_type",
            ]
        )
        document.update_pdf_hash()

        logger.info(
            f"[convert_document] Document {doc_id} converted to PDF "
            f"({len(pdf_bytes)} bytes); original retained as "
            f"'{document.original_file.name}'"
        )
        return True
