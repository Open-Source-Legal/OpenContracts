"""
GraphQL query mixin for document and document-relationship queries.
"""

from __future__ import annotations

import logging
from typing import Any

import graphene
from django.conf import settings
from django.db.models import QuerySet
from graphene import relay
from graphene_django.filter import DjangoFilterConnectionField
from graphql import GraphQLError
from graphql_jwt.decorators import login_required
from graphql_relay import from_global_id

from config.graphql.document_types import INGESTION_SOURCE_GLOBAL_ID_TYPE
from config.graphql.filters import DocumentFilter, DocumentRelationshipFilter
from config.graphql.graphene_types import (
    BulkDocumentUploadStatusType,
    DocumentRelationshipType,
    DocumentType,
    IngestionSourceType,
)
from config.graphql.ratelimits import get_user_tier_rate, graphql_ratelimit_dynamic
from opencontractserver.constants.annotations import (
    DOCUMENT_RELATIONSHIP_QUERY_MAX_LIMIT,
)
from opencontractserver.documents.models import (
    Document,
    DocumentRelationship,
    IngestionSource,
)
from opencontractserver.documents.query_optimizer import (
    DocumentRelationshipQueryOptimizer,
)

logger = logging.getLogger(__name__)


class DocumentQueryMixin:
    """Query fields and resolvers for document and document-relationship queries."""

    # DOCUMENT RESOLVERS #####################################

    documents = DjangoFilterConnectionField(
        DocumentType, filterset_class=DocumentFilter
    )

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_documents(
        self, info: graphene.ResolveInfo, **kwargs: Any
    ) -> QuerySet[Document]:
        # Use lightweight mode to skip heavy prefetches (doc_annotations,
        # rows, relationships, notes) that are unnecessary for list/TOC
        # queries requesting only basic document fields.
        return Document.objects.visible_to_user(info.context.user, lightweight=True)

    document = graphene.Field(DocumentType, id=graphene.ID())

    def resolve_document(
        self, info: graphene.ResolveInfo, **kwargs: Any
    ) -> Document | None:
        document_id = kwargs.get("id")
        if not document_id:
            return None

        cache = getattr(info.context, "_resolver_cache", None)
        if cache is None:
            cache = {}
            info.context._resolver_cache = cache

        doc_cache = cache.setdefault("document", {})
        if document_id in doc_cache:
            return doc_cache[document_id]

        _, pk = from_global_id(document_id)
        document = Document.objects.visible_to_user(info.context.user).get(id=pk)

        doc_cache[document_id] = document
        return document

    # DOCUMENT RELATIONSHIP RESOLVERS #####################################
    document_relationships = DjangoFilterConnectionField(
        DocumentRelationshipType,
        filterset_class=DocumentRelationshipFilter,
        corpus_id=graphene.ID(required=False),
        document_id=graphene.ID(required=False),
        # Higher limit for Table of Contents which needs full hierarchy
        max_limit=DOCUMENT_RELATIONSHIP_QUERY_MAX_LIMIT,
    )

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_document_relationships(
        self, info: graphene.ResolveInfo, **kwargs: Any
    ) -> QuerySet[DocumentRelationship]:
        """
        Resolve document relationships with proper permission filtering.
        Uses DocumentRelationshipQueryOptimizer for consistent eager loading.
        """
        user = info.context.user

        # Parse optional filters
        corpus_id = kwargs.get("corpus_id")
        corpus_pk = int(from_global_id(corpus_id)[1]) if corpus_id else None

        document_id = kwargs.get("document_id")
        doc_pk = int(from_global_id(document_id)[1]) if document_id else None

        # Use optimizer for visibility and eager loading
        # Pass context for request-level caching of visible IDs
        if doc_pk:
            # Get relationships for specific document
            queryset = (
                DocumentRelationshipQueryOptimizer.get_relationships_for_document(
                    user=user,
                    document_id=doc_pk,
                    corpus_id=corpus_pk,
                    context=info.context,
                )
            )
        else:
            # Get all visible relationships with optional corpus filter
            queryset = DocumentRelationshipQueryOptimizer.get_visible_relationships(
                user=user,
                corpus_id=corpus_pk,
                context=info.context,
            )

        return queryset.distinct().order_by("-created")

    document_relationship = relay.Node.Field(DocumentRelationshipType)

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_document_relationship(
        self, info: graphene.ResolveInfo, **kwargs: Any
    ) -> DocumentRelationship:
        """
        Resolve a single document relationship by ID.
        Uses optimizer for IDOR-safe fetching with proper eager loading.
        """
        relay_id = kwargs.get("id")
        if relay_id is None:
            raise GraphQLError("DocumentRelationship id is required")
        django_pk = from_global_id(relay_id)[1]
        result = DocumentRelationshipQueryOptimizer.get_relationship_by_id(
            user=info.context.user,
            relationship_id=int(django_pk),
        )
        if result is None:
            raise DocumentRelationship.DoesNotExist()
        return result

    # Also add a bulk resolver similar to bulk_doc_relationships_in_corpus
    bulk_doc_relationships = graphene.Field(
        graphene.List(DocumentRelationshipType),
        corpus_id=graphene.ID(required=False),
        document_id=graphene.ID(required=True),
        relationship_type=graphene.String(required=False),
    )

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_bulk_doc_relationships(
        self, info: graphene.ResolveInfo, document_id: str, **kwargs: Any
    ) -> QuerySet[DocumentRelationship]:
        """
        Bulk resolver for document relationships involving a specific document.
        Uses DocumentRelationshipQueryOptimizer for proper eager loading.
        """
        user = info.context.user

        # Parse document_id (required)
        doc_pk = int(from_global_id(document_id)[1])

        # Parse optional corpus filter
        corpus_id = kwargs.get("corpus_id")
        corpus_pk = int(from_global_id(corpus_id)[1]) if corpus_id else None

        # Use optimizer for visibility and eager loading
        queryset = DocumentRelationshipQueryOptimizer.get_relationships_for_document(
            user=user,
            document_id=doc_pk,
            corpus_id=corpus_pk,
        )

        # Apply optional relationship_type filter
        relationship_type = kwargs.get("relationship_type")
        if relationship_type:
            queryset = queryset.filter(relationship_type=relationship_type)

        return queryset.distinct().order_by("-created")

    # BULK DOCUMENT UPLOAD STATUS QUERY ###########################################
    bulk_document_upload_status = graphene.Field(
        BulkDocumentUploadStatusType,
        job_id=graphene.String(required=True),
        description="Check the status of a bulk document upload job by job ID",
    )

    @login_required
    def resolve_bulk_document_upload_status(
        self, info: graphene.ResolveInfo, job_id: str
    ) -> BulkDocumentUploadStatusType:
        """
        Resolver for the bulk_document_upload_status query.

        This queries Redis for the status of a bulk document upload job.
        The status is stored as a result in Celery's backend.

        Args:
            info: GraphQL execution info
            job_id: The unique identifier for the upload job

        Returns:
            BulkDocumentUploadStatusType with the current job status
        """
        from config import celery_app

        try:
            # Try to get the task result from Celery
            async_result = celery_app.AsyncResult(job_id)

            # Special handling for tests with CELERY_TASK_ALWAYS_EAGER=True
            if settings.CELERY_TASK_ALWAYS_EAGER:
                logger.info(
                    f"CELERY_TASK_ALWAYS_EAGER is True, handling task {job_id} directly"
                )
                try:
                    if async_result.ready() and async_result.successful():
                        # In eager mode, even with task_store_eager_result, sometimes the result
                        # doesn't properly propagate to the backend. For tests, we'll assume completion.
                        result = async_result.get()
                        logger.info(f"Direct task result in eager mode: {result}")
                        return BulkDocumentUploadStatusType(
                            job_id=job_id,
                            success=result.get("success", True),
                            total_files=result.get("total_files", 0),
                            processed_files=result.get("processed_files", 0),
                            skipped_files=result.get("skipped_files", 0),
                            error_files=result.get("error_files", 0),
                            document_ids=result.get("document_ids", []),
                            errors=result.get("errors", []),
                            completed=result.get(
                                "completed", True
                            ),  # Use the passed completed value if available
                        )
                except Exception as e:
                    logger.info(f"Exception getting eager task result: {e}")
                    # Continue with normal flow

            if async_result.ready():
                # Task is finished
                if async_result.successful():
                    result = async_result.get()
                    # Ensure it has the right structure
                    return BulkDocumentUploadStatusType(
                        job_id=job_id,
                        success=result.get("success", False),
                        total_files=result.get("total_files", 0),
                        processed_files=result.get("processed_files", 0),
                        skipped_files=result.get("skipped_files", 0),
                        error_files=result.get("error_files", 0),
                        document_ids=result.get("document_ids", []),
                        errors=result.get("errors", []),
                        completed=result.get(
                            "completed", True
                        ),  # Use the completed field from result if available
                    )
                else:
                    # Task failed
                    return BulkDocumentUploadStatusType(
                        job_id=job_id,
                        success=False,
                        completed=True,
                        errors=["Task failed with an exception"],
                    )
            else:
                # Task is still running
                return BulkDocumentUploadStatusType(
                    job_id=job_id,
                    success=False,
                    completed=False,
                    errors=["Task is still running"],
                )

        except Exception as e:
            logger.error(f"Error checking bulk upload status: {str(e)}")
            return BulkDocumentUploadStatusType(
                job_id=job_id,
                success=False,
                completed=False,
                errors=[f"Error checking status: {str(e)}"],
            )

    # INGESTION SOURCE RESOLVERS ###########################################

    # NOTE: Uses graphene.List (not ConnectionField) intentionally.
    # Ingestion sources are owner-scoped and expected to be a small set
    # per user (< 50). Relay pagination adds complexity without benefit here.
    ingestion_sources = graphene.List(
        IngestionSourceType,
        active_only=graphene.Boolean(
            required=False,
            default_value=False,
            description="If true, only return active sources",
        ),
        description="List ingestion sources owned by the current user",
    )

    @login_required
    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_ingestion_sources(
        self,
        info: graphene.ResolveInfo,
        active_only: bool = False,
        **kwargs: Any,
    ) -> QuerySet[IngestionSource]:
        qs = IngestionSource.objects.visible_to_user(info.context.user)
        if active_only:
            qs = qs.filter(active=True)
        return qs.order_by("name")

    ingestion_source = graphene.Field(
        IngestionSourceType,
        id=graphene.ID(required=True),
        description="Get a single ingestion source by ID",
    )

    @login_required
    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_ingestion_source(
        self, info: graphene.ResolveInfo, id: str, **kwargs: Any
    ) -> IngestionSource | None:
        try:
            type_name, pk = from_global_id(id)
            if not pk or type_name != INGESTION_SOURCE_GLOBAL_ID_TYPE:
                return None
        except (ValueError, TypeError):
            return None
        try:
            return IngestionSource.objects.visible_to_user(info.context.user).get(pk=pk)
        except (IngestionSource.DoesNotExist, ValueError, TypeError):
            return None
