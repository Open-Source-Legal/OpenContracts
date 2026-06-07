"""
GraphQL query composition for the OpenContracts platform.

This module imports query mixins from domain-specific modules and
composes them into the root Query class used by the GraphQL schema.
"""

import graphene
from django.conf import settings
from graphene_django.debug import DjangoDebug

from config.graphql.action_queries import ActionQueryMixin
from config.graphql.annotation_queries import AnnotationQueryMixin
from config.graphql.conversation_queries import ConversationQueryMixin
from config.graphql.corpus_queries import CorpusQueryMixin
from config.graphql.discover_queries import DiscoverSearchQueryMixin
from config.graphql.document_queries import DocumentQueryMixin
from config.graphql.extract_queries import (
    DocumentMetadataResultType,
    ExtractQueryMixin,
    MetadataCompletionStatusType,
)
from config.graphql.ingestion_admin_queries import IngestionAdminQueryMixin
from config.graphql.og_metadata_queries import OGMetadataQueryMixin
from config.graphql.pipeline_queries import PipelineQueryMixin
from config.graphql.research_queries import ResearchQueryMixin
from config.graphql.search_queries import SearchQueryMixin
from config.graphql.slug_queries import SlugQueryMixin
from config.graphql.social_queries import SocialQueryMixin
from config.graphql.stats_queries import StatsQueryMixin
from config.graphql.user_queries import UserQueryMixin
from config.graphql.worker_queries import WorkerQueryMixin


class Query(
    UserQueryMixin,
    SlugQueryMixin,
    AnnotationQueryMixin,
    DocumentQueryMixin,
    CorpusQueryMixin,
    ExtractQueryMixin,
    ConversationQueryMixin,
    SearchQueryMixin,
    DiscoverSearchQueryMixin,
    SocialQueryMixin,
    ActionQueryMixin,
    PipelineQueryMixin,
    OGMetadataQueryMixin,
    WorkerQueryMixin,
    ResearchQueryMixin,
    StatsQueryMixin,
    IngestionAdminQueryMixin,
    graphene.ObjectType,
):
    if settings.ALLOW_GRAPHQL_DEBUG:
        debug = graphene.Field(DjangoDebug, name="_debug")


# Re-export helper types for backward compatibility
__all__ = [
    "Query",
    "MetadataCompletionStatusType",
    "DocumentMetadataResultType",
]
