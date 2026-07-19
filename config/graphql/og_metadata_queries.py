"""Generated strawberry GraphQL module (graphene migration).

Shape-generated from the graphene schema; stub functions marked PORT(...)
carry the ported business logic. See config/graphql_new/manifest.json.
"""

# mypy: disable-error-code="name-defined, valid-type, arg-type"
#   Code-generation artifacts of the strawberry schema bindings that
#   mypy's static pass cannot resolve, NOT real typing defects:
#     name-defined / valid-type — ``Annotated["XType", strawberry.lazy(...)]``
#       forward-reference strings + the runtime-generated ``*Connection``
#       types (``make_connection_types``).
#     arg-type — resolvers construct result types with ``to_global_id()``
#       (``str``) for ``strawberry.ID`` fields and return Django MODEL
#       instances where the field annotation names the strawberry type
#       (the graphene-django resolver contract). Both are correct at
#       runtime. Hand-written config/graphql/core/* stays fully checked.
# flake8: noqa: E501, F821 — generated strawberry schema module.
# E501: long GraphQL field/argument ``description=`` strings and the
# single-line generated resolver signatures (black cannot split string
# literals). F821: ``Annotated["XType", strawberry.lazy(...)]`` /
# ``cast("QuerySet", ...)`` forward-reference STRINGS that pyflakes
# resolves as names — the whole point of strawberry.lazy is to avoid the
# import (which would then be F401). Both are code-generation artifacts,
# not defects; hand-written modules (config/graphql/core/*, security.py,
# testing.py, filters.py, …) stay fully linted.

from __future__ import annotations

import logging
from typing import Annotated

import strawberry
from graphql_relay import from_global_id

from config.graphql._util import strip_unset
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
from opencontractserver.corpuses.services import CorpusDocumentService
from opencontractserver.documents.models import Document

logger = logging.getLogger(__name__)


@graphql_ratelimit(key="ip", rate="60/m", group="og_metadata")
def _resolve_Query_og_corpus_metadata(root, info, user_slug, corpus_slug):
    """Public OG metadata for corpus - no auth required.

    Only returns data for public corpuses (is_public=True). Used by
    Cloudflare Workers for social media link previews. Rate limited to 60
    requests/minute per IP to prevent abuse.
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


def q_og_corpus_metadata(
    info: strawberry.Info,
    user_slug: Annotated[str, strawberry.argument(name="userSlug")] = strawberry.UNSET,
    corpus_slug: Annotated[
        str, strawberry.argument(name="corpusSlug")
    ] = strawberry.UNSET,
) -> None | (
    Annotated[OGCorpusMetadataType, strawberry.lazy("config.graphql.og_metadata_types")]
):
    kwargs = strip_unset({"user_slug": user_slug, "corpus_slug": corpus_slug})
    return _resolve_Query_og_corpus_metadata(None, info, **kwargs)


@graphql_ratelimit(key="ip", rate="60/m", group="og_metadata")
def _resolve_Query_og_document_metadata(root, info, user_slug, document_slug):
    """Public OG metadata for standalone document - no auth required."""
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


def q_og_document_metadata(
    info: strawberry.Info,
    user_slug: Annotated[str, strawberry.argument(name="userSlug")] = strawberry.UNSET,
    document_slug: Annotated[
        str, strawberry.argument(name="documentSlug")
    ] = strawberry.UNSET,
) -> None | (
    Annotated[
        OGDocumentMetadataType, strawberry.lazy("config.graphql.og_metadata_types")
    ]
):
    kwargs = strip_unset({"user_slug": user_slug, "document_slug": document_slug})
    return _resolve_Query_og_document_metadata(None, info, **kwargs)


@graphql_ratelimit(key="ip", rate="60/m", group="og_metadata")
def _resolve_Query_og_document_in_corpus_metadata(
    root, info, user_slug, corpus_slug, document_slug
):
    """Public OG metadata for document in corpus context - no auth required."""
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import AnonymousUser

    User = get_user_model()
    try:
        user = User.objects.get(slug=user_slug)
        corpus = Corpus.objects.get(creator=user, slug=corpus_slug, is_public=True)
        # Anonymous access (public OG metadata, no auth) — corpus.is_public
        # is already enforced by the ``Corpus.objects.get(... is_public=True)``
        # above (load-bearing — without that filter, AnonymousUser would
        # match any public corpus via the service's READ check). The
        # ``is_public=True`` doc filter below preserves the document-level
        # public gate so private documents inside an otherwise-public
        # corpus remain hidden from the OG endpoint.
        document = (
            CorpusDocumentService.get_corpus_documents(
                user=AnonymousUser(), corpus=corpus
            )
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


def q_og_document_in_corpus_metadata(
    info: strawberry.Info,
    user_slug: Annotated[str, strawberry.argument(name="userSlug")] = strawberry.UNSET,
    corpus_slug: Annotated[
        str, strawberry.argument(name="corpusSlug")
    ] = strawberry.UNSET,
    document_slug: Annotated[
        str, strawberry.argument(name="documentSlug")
    ] = strawberry.UNSET,
) -> None | (
    Annotated[
        OGDocumentMetadataType, strawberry.lazy("config.graphql.og_metadata_types")
    ]
):
    kwargs = strip_unset(
        {
            "user_slug": user_slug,
            "corpus_slug": corpus_slug,
            "document_slug": document_slug,
        }
    )
    return _resolve_Query_og_document_in_corpus_metadata(None, info, **kwargs)


@graphql_ratelimit(key="ip", rate="60/m", group="og_metadata")
def _resolve_Query_og_thread_metadata(root, info, user_slug, corpus_slug, thread_id):
    """Public OG metadata for discussion thread - no auth required."""
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


def q_og_thread_metadata(
    info: strawberry.Info,
    user_slug: Annotated[str, strawberry.argument(name="userSlug")] = strawberry.UNSET,
    corpus_slug: Annotated[
        str, strawberry.argument(name="corpusSlug")
    ] = strawberry.UNSET,
    thread_id: Annotated[str, strawberry.argument(name="threadId")] = strawberry.UNSET,
) -> None | (
    Annotated[OGThreadMetadataType, strawberry.lazy("config.graphql.og_metadata_types")]
):
    kwargs = strip_unset(
        {"user_slug": user_slug, "corpus_slug": corpus_slug, "thread_id": thread_id}
    )
    return _resolve_Query_og_thread_metadata(None, info, **kwargs)


@graphql_ratelimit(key="ip", rate="60/m", group="og_metadata")
def _resolve_Query_og_extract_metadata(root, info, extract_id):
    """Public OG metadata for data extract - no auth required."""
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

        extract = Extract.objects.select_related("corpus", "fieldset", "creator").get(
            pk=pk
        )

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


def q_og_extract_metadata(
    info: strawberry.Info,
    extract_id: Annotated[
        str, strawberry.argument(name="extractId")
    ] = strawberry.UNSET,
) -> None | (
    Annotated[
        OGExtractMetadataType, strawberry.lazy("config.graphql.og_metadata_types")
    ]
):
    kwargs = strip_unset({"extract_id": extract_id})
    return _resolve_Query_og_extract_metadata(None, info, **kwargs)


QUERY_FIELDS = {
    "og_corpus_metadata": strawberry.field(
        resolver=q_og_corpus_metadata,
        name="ogCorpusMetadata",
        description="Public OG metadata for corpus - no auth required",
    ),
    "og_document_metadata": strawberry.field(
        resolver=q_og_document_metadata,
        name="ogDocumentMetadata",
        description="Public OG metadata for standalone document - no auth required",
    ),
    "og_document_in_corpus_metadata": strawberry.field(
        resolver=q_og_document_in_corpus_metadata,
        name="ogDocumentInCorpusMetadata",
        description="Public OG metadata for document in corpus - no auth required",
    ),
    "og_thread_metadata": strawberry.field(
        resolver=q_og_thread_metadata,
        name="ogThreadMetadata",
        description="Public OG metadata for discussion thread - no auth required",
    ),
    "og_extract_metadata": strawberry.field(
        resolver=q_og_extract_metadata,
        name="ogExtractMetadata",
        description="Public OG metadata for data extract - no auth required",
    ),
}
