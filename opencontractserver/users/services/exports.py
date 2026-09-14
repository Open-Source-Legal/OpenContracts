"""Requester and corpus scope for queued export stages."""

from opencontractserver.corpuses.models import Corpus
from opencontractserver.corpuses.services.corpus_documents import CorpusDocumentService
from opencontractserver.documents.models import Document
from opencontractserver.shared.services import BaseService
from opencontractserver.users.models import UserExport


class UserExportService(BaseService):
    @staticmethod
    def get_for_processing(export_id: int) -> UserExport:
        """Load the stored requester afresh; rejection never becomes anonymous."""
        export = UserExport.objects.select_related("creator").get(pk=export_id)
        if export.creator is None or not export.creator.is_active:
            raise PermissionError("Export requester is inactive or missing")
        return export

    @classmethod
    def get_corpus_context(
        cls, export_id: int, corpus_id: int
    ) -> tuple[UserExport, Corpus]:
        """Recheck StartCorpusExport's corpus READ gate at stage execution.

        The queued corpus argument remains the scope. Archive contents retain
        their existing full-source policy; this adds no per-document/source gate.
        """
        export = cls.get_for_processing(export_id)
        corpus = cls.get_or_none(Corpus, corpus_id, export.creator)
        if corpus is None:
            raise Corpus.DoesNotExist("Corpus matching query does not exist.")
        return export, corpus

    @classmethod
    def get_document_context(
        cls, export_id: int, corpus_id: int, document_id: int
    ) -> tuple[UserExport, Corpus, Document]:
        """Recheck the active path selected at enqueue, including CAML sources."""
        export, corpus = cls.get_corpus_context(export_id, corpus_id)
        document = CorpusDocumentService._build_corpus_documents_queryset(
            corpus, include_caml=True
        ).get(pk=document_id)
        return export, corpus, document
