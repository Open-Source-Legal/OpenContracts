"""Generated strawberry GraphQL module (graphene migration).

Shape-generated from the graphene schema; stub functions marked PORT(...)
carry the ported business logic. See config/graphql_new/manifest.json.
"""
from __future__ import annotations

import datetime
import decimal
import uuid
from typing import Annotated, Any, Optional

import strawberry

from config.graphql.core import permissions as core_permissions
from config.graphql.core.filtering import filterset_factory, setup_filterset
from config.graphql.core.mutations import drf_deletion, drf_mutation
from config.graphql.core.relay import (
    Node,
    get_node_from_global_id,
    make_connection_types,
    register_type,
    resolve_django_connection,
    resolve_django_list,
)
from config.graphql.core.scalars import BigInt, GenericScalar, JSONString
from config.graphql._util import coerce_enum, coerce_str, strip_unset
from config.graphql import enums

from opencontractserver.agents.models import AgentConfiguration
from opencontractserver.annotations.models import Annotation
from opencontractserver.annotations.models import Note
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.users.models import User


def _resolve_Query_search_corpuses_for_mention(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/ratelimit/decorators.py:96

    Port of SearchQueryMixin.resolve_search_corpuses_for_mention
    """
    raise NotImplementedError("_resolve_Query_search_corpuses_for_mention not yet ported — see manifest")


def q_search_corpuses_for_mention(info: strawberry.Info, text_search: Annotated[Optional[str], strawberry.argument(name="textSearch", description='Search query to find corpuses by title or description')] = strawberry.UNSET, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Optional[Annotated["CorpusTypeConnection", strawberry.lazy("config.graphql.corpus_types")]]:
    kwargs = strip_unset({"text_search": text_search, "offset": offset, "before": before, "after": after, "first": first, "last": last})
    resolved = _resolve_Query_search_corpuses_for_mention(None, info, **kwargs)
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="CorpusType", default_manager=Corpus._default_manager, )


def _resolve_Query_search_documents_for_mention(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/ratelimit/decorators.py:148

    Port of SearchQueryMixin.resolve_search_documents_for_mention
    """
    raise NotImplementedError("_resolve_Query_search_documents_for_mention not yet ported — see manifest")


def q_search_documents_for_mention(info: strawberry.Info, text_search: Annotated[Optional[str], strawberry.argument(name="textSearch", description='Search query to find documents by title or description')] = strawberry.UNSET, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId", description='Optional corpus ID to scope search to documents in specific corpus')] = strawberry.UNSET, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Optional[Annotated["DocumentTypeConnection", strawberry.lazy("config.graphql.document_types")]]:
    kwargs = strip_unset({"text_search": text_search, "corpus_id": corpus_id, "offset": offset, "before": before, "after": after, "first": first, "last": last})
    resolved = _resolve_Query_search_documents_for_mention(None, info, **kwargs)
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="DocumentType", default_manager=Document._default_manager, )


def _resolve_Query_search_annotations_for_mention(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/ratelimit/decorators.py:279

    Port of SearchQueryMixin.resolve_search_annotations_for_mention
    """
    raise NotImplementedError("_resolve_Query_search_annotations_for_mention not yet ported — see manifest")


def q_search_annotations_for_mention(info: strawberry.Info, text_search: Annotated[Optional[str], strawberry.argument(name="textSearch", description='Search query to find annotations by label text or raw content')] = strawberry.UNSET, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId", description='Optional corpus ID to scope search to specific corpus')] = strawberry.UNSET, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Optional[Annotated["AnnotationTypeConnection", strawberry.lazy("config.graphql.annotation_types")]]:
    kwargs = strip_unset({"text_search": text_search, "corpus_id": corpus_id, "offset": offset, "before": before, "after": after, "first": first, "last": last})
    resolved = _resolve_Query_search_annotations_for_mention(None, info, **kwargs)
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AnnotationType", default_manager=Annotation._default_manager, )


def _resolve_Query_search_users_for_mention(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/ratelimit/decorators.py:360

    Port of SearchQueryMixin.resolve_search_users_for_mention
    """
    raise NotImplementedError("_resolve_Query_search_users_for_mention not yet ported — see manifest")


def q_search_users_for_mention(info: strawberry.Info, text_search: Annotated[Optional[str], strawberry.argument(name="textSearch", description='Search query to find users by slug or display handle')] = strawberry.UNSET, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Optional[Annotated["UserTypeConnection", strawberry.lazy("config.graphql.user_types")]]:
    kwargs = strip_unset({"text_search": text_search, "offset": offset, "before": before, "after": after, "first": first, "last": last})
    resolved = _resolve_Query_search_users_for_mention(None, info, **kwargs)
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="UserType", default_manager=User._default_manager, )


def _resolve_Query_search_agents_for_mention(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/ratelimit/decorators.py:408

    Port of SearchQueryMixin.resolve_search_agents_for_mention
    """
    raise NotImplementedError("_resolve_Query_search_agents_for_mention not yet ported — see manifest")


def q_search_agents_for_mention(info: strawberry.Info, text_search: Annotated[Optional[str], strawberry.argument(name="textSearch", description='Search query to find agents by name, slug, or description')] = strawberry.UNSET, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId", description='Corpus ID to scope agent search (includes global + corpus agents)')] = strawberry.UNSET, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Optional[Annotated["AgentConfigurationTypeConnection", strawberry.lazy("config.graphql.agent_types")]]:
    kwargs = strip_unset({"text_search": text_search, "corpus_id": corpus_id, "offset": offset, "before": before, "after": after, "first": first, "last": last})
    resolved = _resolve_Query_search_agents_for_mention(None, info, **kwargs)
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AgentConfigurationType", default_manager=AgentConfiguration._default_manager, )


def _resolve_Query_search_notes_for_mention(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/ratelimit/decorators.py:447

    Port of SearchQueryMixin.resolve_search_notes_for_mention
    """
    raise NotImplementedError("_resolve_Query_search_notes_for_mention not yet ported — see manifest")


def q_search_notes_for_mention(info: strawberry.Info, text_search: Annotated[Optional[str], strawberry.argument(name="textSearch", description='Search query to find notes by title or content')] = strawberry.UNSET, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId", description='Optional corpus ID to scope search to notes in specific corpus')] = strawberry.UNSET, document_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="documentId", description='Optional document ID to scope search to notes on a specific document')] = strawberry.UNSET, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Optional[Annotated["NoteTypeConnection", strawberry.lazy("config.graphql.annotation_types")]]:
    kwargs = strip_unset({"text_search": text_search, "corpus_id": corpus_id, "document_id": document_id, "offset": offset, "before": before, "after": after, "first": first, "last": last})
    resolved = _resolve_Query_search_notes_for_mention(None, info, **kwargs)
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="NoteType", default_manager=Note._default_manager, )


def _resolve_Query_semantic_search(root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:547

    Port of SearchQueryMixin.resolve_semantic_search
    """
    raise NotImplementedError("_resolve_Query_semantic_search not yet ported — see manifest")


def q_semantic_search(info: strawberry.Info, query: Annotated[str, strawberry.argument(name="query", description='Search query text')] = strawberry.UNSET, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId", description='Optional corpus ID to search within')] = strawberry.UNSET, document_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="documentId", description='Optional document ID to search within')] = strawberry.UNSET, modalities: Annotated[Optional[list[Optional[str]]], strawberry.argument(name="modalities", description='Filter by content modalities (TEXT, IMAGE)')] = strawberry.UNSET, label_text: Annotated[Optional[str], strawberry.argument(name="labelText", description='Filter by annotation label text (case-insensitive substring match)')] = strawberry.UNSET, raw_text_contains: Annotated[Optional[str], strawberry.argument(name="rawTextContains", description='Filter by raw_text content (case-insensitive substring match)')] = strawberry.UNSET, limit: Annotated[Optional[int], strawberry.argument(name="limit", description='Maximum number of results to return (default: 50, max: 200)')] = 50, offset: Annotated[Optional[int], strawberry.argument(name="offset", description='Number of results to skip for pagination')] = 0) -> Optional[list[Optional[Annotated["SemanticSearchResultType", strawberry.lazy("config.graphql.social_types")]]]]:
    kwargs = strip_unset({"query": query, "corpus_id": corpus_id, "document_id": document_id, "modalities": modalities, "label_text": label_text, "raw_text_contains": raw_text_contains, "limit": limit, "offset": offset})
    return _resolve_Query_semantic_search(None, info, **kwargs)


def _resolve_Query_semantic_search_relationships(root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:830

    Port of SearchQueryMixin.resolve_semantic_search_relationships
    """
    raise NotImplementedError("_resolve_Query_semantic_search_relationships not yet ported — see manifest")


def q_semantic_search_relationships(info: strawberry.Info, query: Annotated[str, strawberry.argument(name="query", description='Search query text')] = strawberry.UNSET, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId", description='Optional corpus ID to scope search within')] = strawberry.UNSET, document_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="documentId", description='Optional document ID to scope search within')] = strawberry.UNSET, limit: Annotated[Optional[int], strawberry.argument(name="limit", description='Maximum number of results to return (default: 50, max: 200)')] = 50, offset: Annotated[Optional[int], strawberry.argument(name="offset", description='Number of results to skip for pagination')] = 0) -> Optional[list[Optional[Annotated["SemanticSearchRelationshipResultType", strawberry.lazy("config.graphql.social_types")]]]]:
    kwargs = strip_unset({"query": query, "corpus_id": corpus_id, "document_id": document_id, "limit": limit, "offset": offset})
    return _resolve_Query_semantic_search_relationships(None, info, **kwargs)



QUERY_FIELDS = {
    "search_corpuses_for_mention": strawberry.field(resolver=q_search_corpuses_for_mention, name="searchCorpusesForMention"),
    "search_documents_for_mention": strawberry.field(resolver=q_search_documents_for_mention, name="searchDocumentsForMention"),
    "search_annotations_for_mention": strawberry.field(resolver=q_search_annotations_for_mention, name="searchAnnotationsForMention"),
    "search_users_for_mention": strawberry.field(resolver=q_search_users_for_mention, name="searchUsersForMention"),
    "search_agents_for_mention": strawberry.field(resolver=q_search_agents_for_mention, name="searchAgentsForMention"),
    "search_notes_for_mention": strawberry.field(resolver=q_search_notes_for_mention, name="searchNotesForMention"),
    "semantic_search": strawberry.field(resolver=q_semantic_search, name="semanticSearch", description='Hybrid search combining vector similarity with text filters. Uses the default embedder for global cross-corpus search. Results are first filtered by text criteria, then ranked by similarity.'),
    "semantic_search_relationships": strawberry.field(resolver=q_semantic_search_relationships, name="semanticSearchRelationships", description="Vector search across embedded Relationship rows — currently the materialised OC_SUBTREE_GROUP subtrees. Returns each relationship's source/target annotation IDs so the document viewer can scroll to and select the whole block in one go."),
}
