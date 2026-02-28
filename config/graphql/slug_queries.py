"""
GraphQL query mixin for slug-based entity lookups.
"""

import graphene
from django.db.models.functions import Coalesce

from config.graphql.corpus_queries import _corpus_count_subqueries
from config.graphql.graphene_types import (
    CorpusType,
    DocumentType,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document


class SlugQueryMixin:
    """Query fields and resolvers for slug-based entity lookups."""

    corpus_by_slugs = graphene.Field(
        CorpusType,
        user_slug=graphene.String(required=True),
        corpus_slug=graphene.String(required=True),
    )
    document_by_slugs = graphene.Field(
        DocumentType,
        user_slug=graphene.String(required=True),
        document_slug=graphene.String(required=True),
    )
    document_in_corpus_by_slugs = graphene.Field(
        DocumentType,
        user_slug=graphene.String(required=True),
        corpus_slug=graphene.String(required=True),
        document_slug=graphene.String(required=True),
        version_number=graphene.Int(
            required=False,
            description=(
                "Optional version number to resolve a specific historical version. "
                "When omitted, returns the current (latest) version."
            ),
        ),
    )

    def resolve_corpus_by_slugs(self, info, user_slug, corpus_slug):
        from django.contrib.auth import get_user_model
        from django.db.models import Subquery

        User = get_user_model()
        try:
            owner = User.objects.get(slug=user_slug)
        except User.DoesNotExist:
            return None
        qs = Corpus.objects.filter(creator=owner, slug=corpus_slug)
        qs = qs.visible_to_user(info.context.user)

        # Add count annotations for efficient documentCount/annotationCount
        # resolution without N+1 queries. Coalesce ensures 0 instead of NULL.
        doc_sq, annot_sq = _corpus_count_subqueries()
        qs = qs.annotate(
            _document_count=Coalesce(Subquery(doc_sq), 0),
            _annotation_count=Coalesce(Subquery(annot_sq), 0),
        )

        return qs.first()

    def resolve_document_by_slugs(self, info, user_slug, document_slug):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        try:
            owner = User.objects.get(slug=user_slug)
        except User.DoesNotExist:
            return None
        qs = Document.objects.filter(creator=owner, slug=document_slug)
        qs = qs.visible_to_user(info.context.user)
        return qs.first()

    def resolve_document_in_corpus_by_slugs(
        self, info, user_slug, corpus_slug, document_slug, version_number=None
    ):
        from django.contrib.auth import get_user_model

        from opencontractserver.documents.models import DocumentPath

        User = get_user_model()
        try:
            owner = User.objects.get(slug=user_slug)
        except User.DoesNotExist:
            return None
        corpus = (
            Corpus.objects.filter(creator=owner, slug=corpus_slug)
            .visible_to_user(info.context.user)
            .first()
        )
        if not corpus:
            return None
        # Resolve document via corpus membership (DocumentPath), not by
        # creator.  Documents in a corpus may have been uploaded by any
        # user with write access, not necessarily the corpus owner.
        # Filter by corpus membership to avoid ambiguity when documents
        # in different corpuses share the same slug.
        # Explicit ordering ensures deterministic results when multiple
        # documents share the same slug in this corpus (different creators).
        #
        # When version_number is provided, skip is_current=True because the
        # caller wants a historical version.  The slug may belong to an older
        # version whose path record has is_current=False; we just need to
        # confirm the document has *any* non-deleted path in this corpus.
        path_filter = {
            "slug": document_slug,
            "path_records__corpus": corpus,
            "path_records__is_deleted": False,
        }
        if version_number is None:
            path_filter["path_records__is_current"] = True

        doc = (
            Document.objects.filter(**path_filter)
            .visible_to_user(info.context.user)
            .order_by("pk")
            .first()
        )
        if not doc:
            return None

        if version_number is not None:
            # Resolve a specific historical version via version_tree_id.
            # A document's slug may change between versions, so we must
            # traverse by version_tree_id (which groups all versions of
            # the same logical document) rather than filtering by slug.
            visible_version_docs = (
                Document.objects.filter(version_tree_id=doc.version_tree_id)
                .visible_to_user(info.context.user)
                .only("pk")
            )
            path_record = (
                DocumentPath.objects.filter(
                    document__in=visible_version_docs,
                    corpus=corpus,
                    version_number=version_number,
                    is_deleted=False,
                )
                .select_related("document")
                .first()
            )
            if not path_record:
                return None
            return path_record.document

        # Default: doc already satisfies corpus membership, visibility,
        # and is_current constraints from the initial query above.
        return doc
