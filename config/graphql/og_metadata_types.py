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




@strawberry.type(name="OGCorpusMetadataType", description='Minimal corpus metadata for Open Graph previews - public entities only.')
class OGCorpusMetadataType:
    title: Optional[str] = strawberry.field(name="title", description='Corpus title', default=None)
    description: Optional[str] = strawberry.field(name="description", description='Corpus description (truncated)', default=None)
    icon_url: Optional[str] = strawberry.field(name="iconUrl", description='URL to corpus icon/thumbnail', default=None)
    document_count: Optional[int] = strawberry.field(name="documentCount", description='Number of documents in corpus', default=None)
    creator_name: Optional[str] = strawberry.field(name="creatorName", description='Public slug of corpus creator', default=None)
    is_public: Optional[bool] = strawberry.field(name="isPublic", description='Always True for returned entities', default=None)


register_type("OGCorpusMetadataType", OGCorpusMetadataType, model=None)


@strawberry.type(name="OGDocumentMetadataType", description='Minimal document metadata for Open Graph previews - public entities only.')
class OGDocumentMetadataType:
    title: Optional[str] = strawberry.field(name="title", description='Document title', default=None)
    description: Optional[str] = strawberry.field(name="description", description='Document description (truncated)', default=None)
    icon_url: Optional[str] = strawberry.field(name="iconUrl", description='URL to document thumbnail', default=None)
    corpus_title: Optional[str] = strawberry.field(name="corpusTitle", description='Title of parent corpus (if document is in a corpus)', default=None)
    corpus_description: Optional[str] = strawberry.field(name="corpusDescription", description='Description of parent corpus (if document is in a corpus)', default=None)
    creator_name: Optional[str] = strawberry.field(name="creatorName", description='Public slug of document creator', default=None)
    is_public: Optional[bool] = strawberry.field(name="isPublic", description='Always True for returned entities', default=None)


register_type("OGDocumentMetadataType", OGDocumentMetadataType, model=None)


@strawberry.type(name="OGThreadMetadataType", description='Minimal discussion thread metadata for Open Graph previews.')
class OGThreadMetadataType:
    title: Optional[str] = strawberry.field(name="title", description="Thread title or default 'Discussion'", default=None)
    corpus_title: Optional[str] = strawberry.field(name="corpusTitle", description='Title of parent corpus', default=None)
    message_count: Optional[int] = strawberry.field(name="messageCount", description='Number of messages in thread', default=None)
    creator_name: Optional[str] = strawberry.field(name="creatorName", description='Public slug of thread creator', default=None)
    is_public: Optional[bool] = strawberry.field(name="isPublic", description='Always True for returned entities', default=None)


register_type("OGThreadMetadataType", OGThreadMetadataType, model=None)


@strawberry.type(name="OGExtractMetadataType", description='Minimal extract metadata for Open Graph previews.')
class OGExtractMetadataType:
    name: Optional[str] = strawberry.field(name="name", description='Extract name', default=None)
    corpus_title: Optional[str] = strawberry.field(name="corpusTitle", description='Title of source corpus', default=None)
    fieldset_name: Optional[str] = strawberry.field(name="fieldsetName", description='Name of fieldset used for extraction', default=None)
    creator_name: Optional[str] = strawberry.field(name="creatorName", description='Public slug of extract creator', default=None)
    is_public: Optional[bool] = strawberry.field(name="isPublic", description='Always True for returned entities', default=None)


register_type("OGExtractMetadataType", OGExtractMetadataType, model=None)

