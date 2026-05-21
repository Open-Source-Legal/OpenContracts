"""Base class for enrichers — chainable transforms over a parsed document.

An enricher runs at ingest time, between a parser's ``parse_document()`` and
``save_parsed_data()``. It accepts the parser's ``OpenContractDocExport`` and
returns an ``OpenContractDocExport`` (same type in, same type out), so several
enrichers compose in sequence — each receives the output of the previous one.

This is the ingest-time analogue of the export-time ``BasePostProcessor``
chain. Enrichment is purely additive and OPTIONAL: a failing enricher must
never fail document ingestion. The chain runner (``run_enrichers`` in
``opencontractserver.pipeline.utils``) wraps every enricher call and skips one
that raises, so the document is still saved with whatever the parser produced.
"""

import logging
from abc import ABC, abstractmethod
from typing import ClassVar

from opencontractserver.pipeline.base.file_types import FileTypeEnum
from opencontractserver.types.dicts import OpenContractDocExport
from opencontractserver.utils.logging import redact_sensitive_kwargs

from .base_component import PipelineComponentBase

logger = logging.getLogger(__name__)


class BaseEnricher(PipelineComponentBase, ABC):
    """
    Base class for ingest-time enrichers. Concrete enrichers inherit from this
    class and implement ``_enrich_document_impl``.

    Handles automatic loading of settings from the ``PipelineSettings``
    database singleton (via ``PipelineComponentBase``).

    Annotations emitted by an enricher should generally be created with
    ``structural=False``. Unlike a parser's deterministic structural output,
    enricher annotations are derived heuristically (fuzzy matching, inference)
    and may be wrong, so a user must be able to edit or delete them —
    structural annotations are read-only for non-superusers.
    """

    supported_file_types: ClassVar[list[FileTypeEnum]] = []

    @abstractmethod
    def _enrich_document_impl(
        self,
        user_id: int,
        doc_id: int,
        export_data: OpenContractDocExport,
        **all_kwargs,
    ) -> OpenContractDocExport:
        """
        Abstract internal method to enrich a parsed document's export data.
        Concrete subclasses must implement this method.

        Args:
            user_id: ID of the user the document is being ingested for.
            doc_id: ID of the document being ingested.
            export_data: The parsed document data produced by the parser
                (and possibly already transformed by earlier enrichers).
            **all_kwargs: All keyword arguments, including those from
                PipelineSettings component settings and direct call-time
                arguments.

        Returns:
            OpenContractDocExport: The enriched document data. Implementations
            may mutate and return ``export_data`` or return a new dict, but
            MUST return an ``OpenContractDocExport``.
        """
        ...

    def enrich_document(
        self,
        user_id: int,
        doc_id: int,
        export_data: OpenContractDocExport,
        **direct_kwargs,
    ) -> OpenContractDocExport:
        """
        Enrich a parsed document, automatically injecting settings from
        PipelineSettings.

        Args:
            user_id: ID of the user the document is being ingested for.
            doc_id: ID of the document being ingested.
            export_data: The parsed document data to enrich.
            **direct_kwargs: Arbitrary keyword arguments provided at call time.
                These override settings loaded from PipelineSettings.

        Returns:
            OpenContractDocExport: The enriched document data.
        """
        merged_kwargs = {**self.get_component_settings(), **direct_kwargs}
        logger.info(
            f"Calling _enrich_document_impl for doc_id {doc_id} with merged "
            f"kwargs: {redact_sensitive_kwargs(merged_kwargs)}"
        )
        return self._enrich_document_impl(user_id, doc_id, export_data, **merged_kwargs)
