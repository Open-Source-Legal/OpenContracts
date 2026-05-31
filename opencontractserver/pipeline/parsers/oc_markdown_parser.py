import logging
from typing import Optional

from opencontractserver.documents.models import Document
from opencontractserver.pipeline.base.file_types import FileTypeEnum
from opencontractserver.pipeline.base.parser import BaseParser
from opencontractserver.types.dicts import OpenContractDocExport
from opencontractserver.utils.files import read_field_file_text

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

        text_content = read_field_file_text(document.txt_extract_file)

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
