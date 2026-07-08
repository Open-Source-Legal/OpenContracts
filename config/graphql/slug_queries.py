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

from typing import Annotated

import strawberry
from django.db.models.functions import Coalesce

from config.graphql._util import strip_unset
from config.graphql.corpus_queries import _corpus_count_subqueries
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.shared.services.base import BaseService


def _resolve_Query_corpus_by_slugs(root, info, user_slug: str, corpus_slug: str):
    """PORT: /home/user/oc-graphene-ref/config/graphql/slug_queries.py:47

    Port of SlugQueryMixin.resolve_corpus_by_slugs
    """
    from django.contrib.auth import get_user_model
    from django.db.models import Subquery

    User = get_user_model()
    try:
        owner = User.objects.get(slug=user_slug)
    except User.DoesNotExist:
        return None
    qs = BaseService.filter_visible(
        Corpus, info.context.user, request=info.context
    ).filter(creator=owner, slug=corpus_slug)

    # Add count annotations for efficient documentCount/annotationCount
    # resolution without N+1 queries. Coalesce ensures 0 instead of NULL.
    doc_sq, annot_sq = _corpus_count_subqueries()
    qs = qs.annotate(
        _document_count=Coalesce(Subquery(doc_sq), 0),
        _annotation_count=Coalesce(Subquery(annot_sq), 0),
    )

    return qs.first()


def q_corpus_by_slugs(
    info: strawberry.Info,
    user_slug: Annotated[str, strawberry.argument(name="userSlug")] = strawberry.UNSET,
    corpus_slug: Annotated[
        str, strawberry.argument(name="corpusSlug")
    ] = strawberry.UNSET,
) -> Annotated[CorpusType, strawberry.lazy("config.graphql.corpus_types")] | None:
    kwargs = strip_unset({"user_slug": user_slug, "corpus_slug": corpus_slug})
    return _resolve_Query_corpus_by_slugs(None, info, **kwargs)


def _resolve_Query_document_by_slugs(root, info, user_slug: str, document_slug: str):
    """PORT: /home/user/oc-graphene-ref/config/graphql/slug_queries.py:72

    Port of SlugQueryMixin.resolve_document_by_slugs
    """
    from django.contrib.auth import get_user_model

    User = get_user_model()
    try:
        owner = User.objects.get(slug=user_slug)
    except User.DoesNotExist:
        return None
    return (
        BaseService.filter_visible(Document, info.context.user, request=info.context)
        .filter(creator=owner, slug=document_slug)
        .first()
    )


def q_document_by_slugs(
    info: strawberry.Info,
    user_slug: Annotated[str, strawberry.argument(name="userSlug")] = strawberry.UNSET,
    document_slug: Annotated[
        str, strawberry.argument(name="documentSlug")
    ] = strawberry.UNSET,
) -> None | (Annotated[DocumentType, strawberry.lazy("config.graphql.document_types")]):
    kwargs = strip_unset({"user_slug": user_slug, "document_slug": document_slug})
    return _resolve_Query_document_by_slugs(None, info, **kwargs)


def _resolve_Query_document_in_corpus_by_slugs(
    root,
    info,
    user_slug: str,
    corpus_slug: str,
    document_slug: str,
    version_number: int | None = None,
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/slug_queries.py:90

    Port of SlugQueryMixin.resolve_document_in_corpus_by_slugs
    """
    from django.contrib.auth import get_user_model

    from opencontractserver.documents.models import DocumentPath

    User = get_user_model()
    try:
        owner = User.objects.get(slug=user_slug)
    except User.DoesNotExist:
        return None
    corpus = (
        BaseService.filter_visible(Corpus, info.context.user, request=info.context)
        .filter(creator=owner, slug=corpus_slug)
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
        BaseService.filter_visible(Document, info.context.user, request=info.context)
        .filter(**path_filter)
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
            BaseService.filter_visible(
                Document, info.context.user, request=info.context
            )
            .filter(version_tree_id=doc.version_tree_id)
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


def q_document_in_corpus_by_slugs(
    info: strawberry.Info,
    user_slug: Annotated[str, strawberry.argument(name="userSlug")] = strawberry.UNSET,
    corpus_slug: Annotated[
        str, strawberry.argument(name="corpusSlug")
    ] = strawberry.UNSET,
    document_slug: Annotated[
        str, strawberry.argument(name="documentSlug")
    ] = strawberry.UNSET,
    version_number: Annotated[
        int | None,
        strawberry.argument(
            name="versionNumber",
            description="Optional version number to resolve a specific historical version. When omitted, returns the current (latest) version.",
        ),
    ] = strawberry.UNSET,
) -> None | (Annotated[DocumentType, strawberry.lazy("config.graphql.document_types")]):
    kwargs = strip_unset(
        {
            "user_slug": user_slug,
            "corpus_slug": corpus_slug,
            "document_slug": document_slug,
            "version_number": version_number,
        }
    )
    return _resolve_Query_document_in_corpus_by_slugs(None, info, **kwargs)


QUERY_FIELDS = {
    "corpus_by_slugs": strawberry.field(
        resolver=q_corpus_by_slugs, name="corpusBySlugs"
    ),
    "document_by_slugs": strawberry.field(
        resolver=q_document_by_slugs, name="documentBySlugs"
    ),
    "document_in_corpus_by_slugs": strawberry.field(
        resolver=q_document_in_corpus_by_slugs, name="documentInCorpusBySlugs"
    ),
}
