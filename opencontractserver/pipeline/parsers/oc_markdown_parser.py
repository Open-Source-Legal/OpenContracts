import logging
from typing import Optional

from django.core.files.storage import default_storage

from opencontractserver.documents.models import Document
from opencontractserver.pipeline.base.file_types import FileTypeEnum
from opencontractserver.pipeline.base.parser import BaseParser
from opencontractserver.types.dicts import OpenContractDocExport

logger = logging.getLogger(__name__)


class MarkdownParser(BaseParser):
    """
    No-op parser for Markdown and CAML files.

    Stores the raw text content without creating structural annotations.
    Used for corpus article files (Readme.CAML) and other markdown documents
    that should be rendered by the frontend, not processed by the NLP pipeline.
    """

    title = "Markdown Parser"
    description = "Stores markdown/CAML files without NLP processing."
    author = "OpenContracts"
    dependencies = []
    supported_file_types = [FileTypeEnum.MD]

    def _parse_document_impl(
        self, user_id: int, doc_id: int, **all_kwargs
    ) -> Optional[OpenContractDocExport]:
        logger.info(
            f"MarkdownParser - Storing doc {doc_id} for user {user_id} (no-op parse)"
        )

        document = Document.objects.get(pk=doc_id)

        if not document.txt_extract_file.name:
            logger.error(f"No txt file found for document {doc_id}")
            return None

        txt_path = document.txt_extract_file.name
        with default_storage.open(txt_path, mode="r") as txt_file:
            # Storage backends may not support encoding= kwarg, so decode
            # the bytes explicitly to handle non-ASCII content safely.
            raw = txt_file.read()
            text_content = raw.decode("utf-8") if isinstance(raw, bytes) else raw

        result: OpenContractDocExport = {
            "title": document.title or "",
            "content": text_content,
            "description": document.description or "",
            "pawls_file_content": [],
            "page_count": 1,
            "doc_labels": [],
            "labelled_text": [],
        }
        return result
