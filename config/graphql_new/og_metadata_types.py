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
from config.graphql_new._util import coerce_enum, coerce_str, strip_unset
from config.graphql_new import enums




@strawberry.type(name="OGCorpusMetadataType", description='Minimal corpus metadata for Open Graph previews - public entities only.')
class OGCorpusMetadataType:
    @strawberry.field(name="title", description='Corpus title')
    def title(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "title", None))
    @strawberry.field(name="description", description='Corpus description (truncated)')
    def description(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "description", None))
    @strawberry.field(name="iconUrl", description='URL to corpus icon/thumbnail')
    def icon_url(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "icon_url", None))
    document_count: Optional[int] = strawberry.field(name="documentCount", description='Number of documents in corpus')
    @strawberry.field(name="creatorName", description='Public slug of corpus creator')
    def creator_name(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "creator_name", None))
    is_public: Optional[bool] = strawberry.field(name="isPublic", description='Always True for returned entities')


register_type("OGCorpusMetadataType", OGCorpusMetadataType, model=None)


@strawberry.type(name="OGDocumentMetadataType", description='Minimal document metadata for Open Graph previews - public entities only.')
class OGDocumentMetadataType:
    @strawberry.field(name="title", description='Document title')
    def title(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "title", None))
    @strawberry.field(name="description", description='Document description (truncated)')
    def description(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "description", None))
    @strawberry.field(name="iconUrl", description='URL to document thumbnail')
    def icon_url(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "icon_url", None))
    @strawberry.field(name="corpusTitle", description='Title of parent corpus (if document is in a corpus)')
    def corpus_title(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "corpus_title", None))
    @strawberry.field(name="corpusDescription", description='Description of parent corpus (if document is in a corpus)')
    def corpus_description(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "corpus_description", None))
    @strawberry.field(name="creatorName", description='Public slug of document creator')
    def creator_name(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "creator_name", None))
    is_public: Optional[bool] = strawberry.field(name="isPublic", description='Always True for returned entities')


register_type("OGDocumentMetadataType", OGDocumentMetadataType, model=None)


@strawberry.type(name="OGThreadMetadataType", description='Minimal discussion thread metadata for Open Graph previews.')
class OGThreadMetadataType:
    @strawberry.field(name="title", description="Thread title or default 'Discussion'")
    def title(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "title", None))
    @strawberry.field(name="corpusTitle", description='Title of parent corpus')
    def corpus_title(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "corpus_title", None))
    message_count: Optional[int] = strawberry.field(name="messageCount", description='Number of messages in thread')
    @strawberry.field(name="creatorName", description='Public slug of thread creator')
    def creator_name(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "creator_name", None))
    is_public: Optional[bool] = strawberry.field(name="isPublic", description='Always True for returned entities')


register_type("OGThreadMetadataType", OGThreadMetadataType, model=None)


@strawberry.type(name="OGExtractMetadataType", description='Minimal extract metadata for Open Graph previews.')
class OGExtractMetadataType:
    @strawberry.field(name="name", description='Extract name')
    def name(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "name", None))
    @strawberry.field(name="corpusTitle", description='Title of source corpus')
    def corpus_title(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "corpus_title", None))
    @strawberry.field(name="fieldsetName", description='Name of fieldset used for extraction')
    def fieldset_name(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "fieldset_name", None))
    @strawberry.field(name="creatorName", description='Public slug of extract creator')
    def creator_name(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "creator_name", None))
    is_public: Optional[bool] = strawberry.field(name="isPublic", description='Always True for returned entities')


register_type("OGExtractMetadataType", OGExtractMetadataType, model=None)

