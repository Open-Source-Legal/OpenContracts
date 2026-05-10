"""
GraphQL query mixin for Open Graph metadata queries.

These queries are used by Cloudflare Workers to generate
Open Graph meta tags for social media link previews.
They only return data for public entities (is_public=True).
See: docs/architecture/social-media-previews.md
"""

from __future__ import annotations

import logging

import graphene
from graphql_relay import from_global_id

from config.graphql.og_metadata_types import (
    OGCorpusMetadataType,
    OGDocumentMetadataType,
    OGExtractMetadataType,
    OGThreadMetadataType,
)
from config.graphql.ratelimits import graphql_ratelimit
from config.graphql.user_types import redacted_handle
from opencontractserver.conversations.models import Conversation
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document

logger = logging.getLogger(__name__)


class OGMetadataQueryMixin:
    """Query fields and resolvers for Open Graph metadata queries (public, no auth)."""

    og_corpus_metadata = graphene.Field(
        OGCorpusMetadataType,
        user_slug=graphene.String(required=True),
        corpus_slug=graphene.String(required=True),
        description="Public OG metadata for corpus - no auth required",
    )

    og_document_metadata = graphene.Field(
        OGDocumentMetadataType,
        user_slug=graphene.String(required=True),
        document_slug=graphene.String(required=True),
        description="Public OG metadata for standalone document - no auth required",
    )

    og_document_in_corpus_metadata = graphene.Field(
        OGDocumentMetadataType,
        user_slug=graphene.String(required=True),
        corpus_slug=graphene.String(required=True),
        document_slug=graphene.String(required=True),
        description="Public OG metadata for document in corpus - no auth required",
    )

    og_thread_metadata = graphene.Field(
        OGThreadMetadataType,
        user_slug=graphene.String(required=True),
        corpus_slug=graphene.String(required=True),
        thread_id=graphene.String(required=True),
        description="Public OG metadata for discussion thread - no auth required",
    )

    og_extract_metadata = graphene.Field(
        OGExtractMetadataType,
        extract_id=graphene.String(required=True),
        description="Public OG metadata for data extract - no auth required",
    )

    @graphql_ratelimit(key="ip", rate="60/m", group="og_metadata")
    def resolve_og_corpus_metadata(
        self, info: graphene.ResolveInfo, user_slug: str, corpus_slug: str
    ) -> OGCorpusMetadataType | None:
        """
        Public OG metadata for corpus - no auth required.
        Only returns data for public corpuses (is_public=True).

        Used by Cloudflare Workers for social media link previews.
        Rate limited to 60 requests/minute per IP to prevent abuse.
        """
        from django.contrib.auth import get_user_model
        from django.db.models import Count

        User = get_user_model()
        try:
            user = User.objects.get(slug=user_slug)
            # Use annotate to count documents via DocumentPath instead of M2M
            corpus = (
                Corpus.objects.annotate(doc_count=Count("document_paths"))
                .select_related("creator")
                .get(creator=user, slug=corpus_slug, is_public=True)
            )

            # Build icon URL if available
            icon_url = None
            if corpus.icon:
                icon_url = info.context.build_absolute_uri(corpus.icon.url)

            return OGCorpusMetadataType(
                title=corpus.title,
                description=corpus.description or "",
                icon_url=icon_url,
                document_count=corpus.doc_count,
                creator_name=corpus.creator.slug or redacted_handle(corpus.creator),
                is_public=True,
            )
        except (User.DoesNotExist, Corpus.DoesNotExist):
            return None

    @graphql_ratelimit(key="ip", rate="60/m", group="og_metadata")
    def resolve_og_document_metadata(
        self, info: graphene.ResolveInfo, user_slug: str, document_slug: str
    ) -> OGDocumentMetadataType | None:
        """
        Public OG metadata for standalone document - no auth required.
        Only returns data for public documents (is_public=True).
        Rate limited to 60 requests/minute per IP to prevent abuse.
        """
        from django.contrib.auth import get_user_model

        User = get_user_model()
        try:
            user = User.objects.get(slug=user_slug)
            document = Document.objects.get(
                creator=user, slug=document_slug, is_public=True
            )

            # Build icon URL if available
            icon_url = None
            if document.icon:
                icon_url = info.context.build_absolute_uri(document.icon.url)

            return OGDocumentMetadataType(
                title=document.title,
                description=document.description or "",
                icon_url=icon_url,
                corpus_title=None,
                corpus_description=None,
                creator_name=document.creator.slug or redacted_handle(document.creator),
                is_public=True,
            )
        except (User.DoesNotExist, Document.DoesNotExist):
            return None

    @graphql_ratelimit(key="ip", rate="60/m", group="og_metadata")
    def resolve_og_document_in_corpus_metadata(
        self,
        info: graphene.ResolveInfo,
        user_slug: str,
        corpus_slug: str,
        document_slug: str,
    ) -> OGDocumentMetadataType | None:
        """
        Public OG metadata for document in corpus context - no auth required.
        Only returns data if both corpus and document are public.
        Rate limited to 60 requests/minute per IP to prevent abuse.
        """
        from django.contrib.auth import get_user_model

        User = get_user_model()
        try:
            user = User.objects.get(slug=user_slug)
            corpus = Corpus.objects.get(creator=user, slug=corpus_slug, is_public=True)
            document = (
                corpus.get_documents()
                .filter(slug=document_slug, is_public=True)
                .first()
            )
            if not document:
                raise Document.DoesNotExist()

            # Build icon URL if available
            icon_url = None
            if document.icon:
                icon_url = info.context.build_absolute_uri(document.icon.url)

            return OGDocumentMetadataType(
                title=document.title,
                description=document.description or "",
                icon_url=icon_url,
                corpus_title=corpus.title,
                corpus_description=corpus.description or "",
                creator_name=document.creator.slug or redacted_handle(document.creator),
                is_public=True,
            )
        except (User.DoesNotExist, Corpus.DoesNotExist, Document.DoesNotExist):
            return None

    @graphql_ratelimit(key="ip", rate="60/m", group="og_metadata")
    def resolve_og_thread_metadata(
        self,
        info: graphene.ResolveInfo,
        user_slug: str,
        corpus_slug: str,
        thread_id: str,
    ) -> OGThreadMetadataType | None:
        """
        Public OG metadata for discussion thread - no auth required.
        Only returns data if parent corpus is public.
        Rate limited to 60 requests/minute per IP to prevent abuse.
        """
        from django.contrib.auth import get_user_model
        from django.db.models import Count

        User = get_user_model()
        try:
            user = User.objects.get(slug=user_slug)
            corpus = Corpus.objects.get(creator=user, slug=corpus_slug, is_public=True)

            # Decode thread ID if base64 encoded (GraphQL relay ID)
            try:
                _, pk = from_global_id(thread_id)
                # from_global_id returns empty strings for invalid base64
                if not pk:
                    pk = thread_id
            except Exception:
                pk = thread_id

            # Use annotate to avoid N+1 query for message count
            thread = (
                Conversation.objects.annotate(msg_count=Count("chat_messages"))
                .select_related("creator")
                .get(pk=pk, chat_with_corpus=corpus)
            )

            return OGThreadMetadataType(
                title=thread.title or "Discussion",
                corpus_title=corpus.title,
                message_count=thread.msg_count,
                creator_name=(
                    (thread.creator.slug or redacted_handle(thread.creator))
                    if thread.creator
                    else "Anonymous"
                ),
                is_public=True,
            )
        except (User.DoesNotExist, Corpus.DoesNotExist, Conversation.DoesNotExist):
            return None

    @graphql_ratelimit(key="ip", rate="60/m", group="og_metadata")
    def resolve_og_extract_metadata(
        self, info: graphene.ResolveInfo, extract_id: str
    ) -> OGExtractMetadataType | None:
        """
        Public OG metadata for data extract - no auth required.
        Only returns data if parent corpus is public.
        Rate limited to 60 requests/minute per IP to prevent abuse.
        """
        from opencontractserver.extracts.models import Extract

        try:
            # Decode extract ID if base64 encoded (GraphQL relay ID)
            try:
                _, pk = from_global_id(extract_id)
                # from_global_id returns empty strings for invalid base64
                if not pk:
                    pk = extract_id
            except Exception:
                pk = extract_id

            extract = Extract.objects.select_related(
                "corpus", "fieldset", "creator"
            ).get(pk=pk)

            # Extracts inherit corpus visibility. Corpus is nullable
            # (SET_NULL on delete), so guard against a missing parent.
            corpus = extract.corpus
            if corpus is None or not corpus.is_public:
                return None

            return OGExtractMetadataType(
                name=extract.name,
                corpus_title=corpus.title,
                fieldset_name=extract.fieldset.name if extract.fieldset else "Custom",
                creator_name=(
                    (extract.creator.slug or redacted_handle(extract.creator))
                    if extract.creator
                    else "System"
                ),
                is_public=True,
            )
        except Extract.DoesNotExist:
            return None
