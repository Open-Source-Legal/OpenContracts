"""Authenticated readiness observations and targeted repairs."""

from django.shortcuts import get_object_or_404
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from opencontractserver.constants.readiness import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from opencontractserver.corpuses.models import Corpus
from opencontractserver.corpuses.services.corpus_documents import CorpusDocumentService
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.documents.readiness import (
    assess_document,
    assess_documents,
    request_repair,
)
from opencontractserver.shared.services.base import BaseService
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.worker_uploads.auth import WorkerTokenAuthentication
from opencontractserver.worker_uploads.models import WorkerDocumentUpload
from opencontractserver.worker_uploads.views import IsValidWorkerToken


def require_access(request, obj, permission):
    if not BaseService.user_has(obj, request.user, permission, request=request):
        raise NotFound()


def corpus_page(request, documents, corpus):
    try:
        after = int(request.query_params.get("after", 0))
        limit = int(request.query_params.get("limit", DEFAULT_PAGE_SIZE))
        if after < 0 or not 1 <= limit <= MAX_PAGE_SIZE:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValidationError(
            f"after must be nonnegative; limit must be between 1 and {MAX_PAGE_SIZE}"
        )
    page = list(documents.filter(pk__gt=after).order_by("pk")[: limit + 1])
    return Response(
        {
            "schema_version": 1,
            "scope": "document_page",
            "corpus_id": corpus.pk,
            "documents": assess_documents(page[:limit], corpus),
            "next_after": page[limit - 1].pk if len(page) > limit else None,
        }
    )


class DocumentReadinessView(APIView):
    def _corpus(self, request, document):
        paths = DocumentPath.objects.select_related("corpus").filter(
            document=document, is_current=True, is_deleted=False
        )
        requested = request.query_params.get("corpus")
        if requested is not None:
            try:
                paths = paths.filter(corpus_id=int(requested))
            except (TypeError, ValueError):
                raise ValidationError("corpus must be an integer id")
            path = paths.first()
            if path is None:
                raise NotFound()
            return path.corpus
        # A document may hold a current path in several corpora at once.
        # Without an explicit choice, observe the newest path so repeated
        # calls report the same corpus instead of whichever row Postgres
        # happens to return first.
        path = paths.order_by("-created", "-pk").first()
        return path.corpus if path else None

    def _context(self, request, document_id):
        document = get_object_or_404(Document, pk=document_id)
        require_access(request, document, PermissionTypes.READ)
        corpus = self._corpus(request, document)
        if corpus:
            require_access(request, corpus, PermissionTypes.READ)
        return document, corpus

    def get(self, request, document_id):
        document, corpus = self._context(request, document_id)
        return Response(assess_document(document, corpus))

    def post(self, request, document_id):
        document, corpus = self._context(request, document_id)
        try:
            result = request_repair(document, corpus, user=request.user)
        except PermissionError:
            raise NotFound() from None
        return Response(result, status=202)


class CorpusReadinessView(APIView):
    def get(self, request, corpus_id):
        corpus = get_object_or_404(Corpus, pk=corpus_id)
        require_access(request, corpus, PermissionTypes.READ)
        documents = CorpusDocumentService.get_corpus_documents_visible_to_user(
            request.user, corpus, request=request
        )
        return corpus_page(request, documents, corpus)


class WorkerReadinessView(APIView):
    authentication_classes = [WorkerTokenAuthentication]
    permission_classes = [IsValidWorkerToken]

    def _document(self, request, upload_id):
        upload = get_object_or_404(
            WorkerDocumentUpload.objects.select_related("result_document", "corpus"),
            pk=upload_id,
            corpus_access_token=request.auth,
        )
        return upload

    def get(self, request, upload_id):
        upload = self._document(request, upload_id)
        if upload.result_document_id is None:
            return Response(
                {
                    "schema_version": 1,
                    "upload_id": str(upload.pk),
                    "state": "unavailable",
                    "generation": None,
                    "reasons": ["result_document_unavailable"],
                }
            )
        result = assess_document(upload.result_document, upload.corpus)
        result["upload_id"] = str(upload.pk)
        return Response(result)

    def post(self, request, upload_id):
        upload = self._document(request, upload_id)
        if upload.result_document_id is None:
            raise ValidationError("The upload has no result document to repair")
        result = request_repair(
            upload.result_document, upload.corpus, user=request.user, token=request.auth
        )
        result["upload_id"] = str(upload.pk)
        return Response(result, status=202)


class WorkerCorpusReadinessView(APIView):
    authentication_classes = [WorkerTokenAuthentication]
    permission_classes = [IsValidWorkerToken]

    def get(self, request):
        # The token's receipts define its authority, matching the status endpoint.
        documents = Document.objects.filter(
            pk__in=WorkerDocumentUpload.objects.filter(
                corpus_access_token=request.auth
            ).values("result_document_id")
        )
        return corpus_page(request, documents, request.auth.corpus)
