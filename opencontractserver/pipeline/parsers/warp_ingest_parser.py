"""Warp-Ingest parser: a pure-Python, in-process PDF parser.

`Warp-Ingest <https://github.com/Open-Source-Legal/Warp-Ingest>`_ is a
rule-based (non-ML, no-GPU) PDF layout engine built on ``pdfplumber``. It turns
a PDF into layout-aware structure — word/block bounding boxes, structural labels
(section header, paragraph, list item, table row) and the parent ↔ child heading
hierarchy — and renders it directly as an OpenContracts structural export
(``pdf_ingestor.parse_to_opencontracts``): PAWLS word tokens, one structural
annotation per block, and the heading hierarchy as ``OC_PARENT_CHILD``
relationships.

Because it runs entirely in-process (optional CPU-only OCR via
``rapidocr-onnxruntime`` for scanned pages) with no microservice and no torch,
it is the parser used by the single-user *desktop* build to replace the
Docling parsing microservice. It is registered here for any deployment, but is
only selected when ``PREFERRED_PARSERS`` / ``PipelineSettings`` point at it (the
docker-compose default remains Docling).

``warp-ingest`` is an OPTIONAL dependency — it is imported lazily inside
:meth:`WarpIngestParser._parse_document_impl` so pipeline auto-discovery keeps
working when the package is not installed. Install it (and its OCR extra for
scanned PDFs) with ``pip install "warp-ingest[ocr]"``. The ``nltk`` ``stopwords``
and ``punkt`` corpora must be available (Warp-Ingest imports them at module
load); the desktop bootstrap downloads them on first run.
"""

import logging
import os
import tempfile
from dataclasses import dataclass, field
from typing import Optional

from django.core.files.storage import default_storage

from opencontractserver.documents.models import Document
from opencontractserver.pipeline.base.exceptions import DocumentParsingError
from opencontractserver.pipeline.base.file_types import FileTypeEnum
from opencontractserver.pipeline.base.parser import BaseParser
from opencontractserver.pipeline.base.settings_schema import (
    PipelineSetting,
    SettingType,
)
from opencontractserver.types.dicts import OpenContractDocExport

logger = logging.getLogger(__name__)


class WarpIngestParser(BaseParser):
    """Parse PDFs to an ``OpenContractDocExport`` with the Warp-Ingest engine."""

    title = "Warp-Ingest Parser"
    description = (
        "Rule-based, in-process PDF parser (Warp-Ingest). Emits PAWLS tokens, "
        "structural annotations and the heading hierarchy with no ML model, no "
        "GPU and no external microservice."
    )
    author = "Open Source Legal"
    # Optional dependency: imported lazily so pipeline discovery does not require
    # it. Declared here for documentation / the migrate_pipeline_settings audit.
    dependencies = ["warp-ingest"]
    supported_file_types = [FileTypeEnum.PDF]

    @dataclass
    class Settings:
        """Configuration schema for :class:`WarpIngestParser`."""

        apply_ocr: bool = field(
            default=False,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description=(
                        "Force OCR on every page. When False (default), "
                        "Warp-Ingest auto-routes only scanned/sparse pages to "
                        "OCR and keeps born-digital pages on their text layer. "
                        "Requires the 'ocr' extra (rapidocr-onnxruntime)."
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
                    description=(
                        "Never OCR: keep every page on its embedded text layer "
                        "even when it looks scanned. Mutually exclusive with "
                        "apply_ocr; avoids pulling the OCR extra."
                    ),
                    env_var="WARP_INGEST_DISABLE_OCR",
                )
            },
        )
        semantic_units: bool = field(
            default=False,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description=(
                        "Append Warp-Ingest's additive Semantic-Unit clause "
                        "layer to the structural annotations."
                    ),
                    env_var="WARP_INGEST_SEMANTIC_UNITS",
                )
            },
        )

    def _parse_document_impl(
        self, user_id: int, doc_id: int, **all_kwargs
    ) -> Optional[OpenContractDocExport]:
        """Parse ``doc_id``'s PDF into an ``OpenContractDocExport``.

        Reads the document's stored PDF, hands it to Warp-Ingest and returns the
        structural export ready for :meth:`BaseParser.save_parsed_data`.
        Returns ``None`` when the document has no PDF file. Raises
        :class:`DocumentParsingError` (permanent) on a genuine parse failure or a
        missing ``warp-ingest`` install — Warp-Ingest is deterministic and local,
        so a failure will not succeed on retry.
        """
        logger.info(
            f"WarpIngestParser - parsing doc {doc_id} for user {user_id} "
            f"with effective kwargs: {all_kwargs}"
        )

        document = Document.objects.get(pk=doc_id)

        if not document.pdf_file or not document.pdf_file.name:
            logger.error(f"No pdf_file found for document {doc_id}")
            return None

        # Warp-Ingest's front-end consumes a filesystem path, so stream the
        # stored PDF (which may live in object storage) to a temp file.
        with default_storage.open(document.pdf_file.name, mode="rb") as pdf_file:
            pdf_bytes = pdf_file.read()

        tmp_path: Optional[str] = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_pdf:
                tmp_pdf.write(pdf_bytes)
                tmp_path = tmp_pdf.name

            try:
                from warp_ingest.ingestor import pdf_ingestor
            except ImportError as exc:  # pragma: no cover - env-dependent
                raise DocumentParsingError(
                    "warp-ingest is not installed. Install it with "
                    "'pip install \"warp-ingest[ocr]\"' to use WarpIngestParser.",
                    is_transient=False,
                ) from exc

            parse_options = {
                "apply_ocr": bool(all_kwargs.get("apply_ocr", False)),
                "disable_ocr": bool(all_kwargs.get("disable_ocr", False)),
                "semantic_units": bool(all_kwargs.get("semantic_units", False)),
            }

            try:
                export: OpenContractDocExport = pdf_ingestor.parse_to_opencontracts(
                    tmp_path, parse_options
                )
            except (ConnectionError, TimeoutError) as exc:
                # e.g. a first-run OCR model download (rapidocr) over a flaky
                # network — retryable, not a permanent content failure.
                raise DocumentParsingError(
                    f"Warp-Ingest transient failure on document {doc_id}: {exc}",
                    is_transient=True,
                ) from exc
            except Exception as exc:
                # Deterministic local parse of a bad/unsupported PDF — permanent.
                raise DocumentParsingError(
                    f"Warp-Ingest failed to parse document {doc_id}: {exc}",
                    is_transient=False,
                ) from exc
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:  # pragma: no cover - best-effort cleanup
                    logger.warning(f"Could not remove temp PDF {tmp_path}")

        # Warp-Ingest derives the title from the PDF metadata; fall back to the
        # document's own title/description when it comes back empty.
        if not export.get("title"):
            export["title"] = document.title or ""
        if not export.get("description"):
            export["description"] = document.description or ""

        logger.info(
            f"WarpIngestParser - doc {doc_id}: "
            f"{len(export.get('labelled_text', []))} structural annotation(s), "
            f"{len(export.get('relationships', []))} relationship(s), "
            f"{export.get('page_count')} page(s)."
        )
        return export
