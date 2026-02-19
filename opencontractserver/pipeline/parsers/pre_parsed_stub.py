"""
Pre-Parsed Parser Stub

A minimal BaseParser subclass that provides access to save_parsed_data()
for importing documents that were parsed offline (e.g., on GPU workstations).

This parser does NOT perform any actual parsing. It exists solely to:
1. Provide a valid BaseParser instance for calling save_parsed_data()
2. Register as a known parser in the pipeline registry

Usage:
    stub = PreParsedParserStub()
    stub.save_parsed_data(
        user_id=user.id,
        doc_id=doc.id,
        open_contracts_data=pre_parsed_export,
        corpus_id=corpus.id,
    )
"""

import logging
from typing import Optional

from opencontractserver.pipeline.base.file_types import FileTypeEnum
from opencontractserver.pipeline.base.parser import BaseParser
from opencontractserver.types.dicts import OpenContractDocExport

logger = logging.getLogger(__name__)


class PreParsedParserStub(BaseParser):
    """
    Stub parser for importing pre-parsed documents.

    Does not perform any parsing. Used by the bulk ingestion pipeline
    to call save_parsed_data() with OpenContractDocExport data that
    was generated externally (offline parsing on GPU workstations, etc.).
    """

    title = "Pre-Parsed Import"
    description = (
        "Imports pre-parsed document data from offline parsing. "
        "Does not perform actual parsing."
    )
    author = "OpenContracts"
    supported_file_types = [
        FileTypeEnum.PDF,
        FileTypeEnum.TXT,
        FileTypeEnum.DOCX,
    ]

    def _parse_document_impl(
        self, user_id: int, doc_id: int, **all_kwargs
    ) -> Optional[OpenContractDocExport]:
        """
        Not implemented. This stub does not parse documents.

        Callers should use save_parsed_data() directly with pre-computed data.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError(
            "PreParsedParserStub does not parse documents. "
            "Use save_parsed_data() directly with pre-computed "
            "OpenContractDocExport data."
        )
