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




@strawberry.type(name="VersionHistoryType", description='Complete version history for a document.')
class VersionHistoryType:
    @strawberry.field(name="versions", description='All versions of this document')
    def versions(self, info: strawberry.Info) -> list["DocumentVersionType"]:
        return resolve_django_list(self, info, getattr(self, "versions"), "DocumentVersionType")
    current_version: "DocumentVersionType" = strawberry.field(name="currentVersion", description='The current active version', default=None)
    version_tree: Optional[GenericScalar] = strawberry.field(name="versionTree", description='Tree structure of version relationships', default=None)


register_type("VersionHistoryType", VersionHistoryType, model=None)


@strawberry.type(name="DocumentVersionType", description="Represents a single version in the document's content history.")
class DocumentVersionType:
    @strawberry.field(name="id", description='Global ID of the document version')
    def id(self, info: strawberry.Info) -> strawberry.ID:
        return coerce_str(getattr(self, "id", None))
    version_number: int = strawberry.field(name="versionNumber", description='Sequential version number', default=None)
    @strawberry.field(name="hash", description='SHA-256 hash of PDF content')
    def hash(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "hash", None))
    created_at: datetime.datetime = strawberry.field(name="createdAt", description='When version was created', default=None)
    created_by: Annotated["UserType", strawberry.lazy("config.graphql.user_types")] = strawberry.field(name="createdBy", description='User who created this version', default=None)
    size_bytes: Optional[int] = strawberry.field(name="sizeBytes", description='File size in bytes', default=None)
    @strawberry.field(name="changeType", description='Type of change from previous version')
    def change_type(self, info: strawberry.Info) -> enums.VersionChangeTypeEnum:
        return coerce_enum(enums.VersionChangeTypeEnum, getattr(self, "change_type", None))
    parent_version: Optional["DocumentVersionType"] = strawberry.field(name="parentVersion", description='Previous version in content tree', default=None)


register_type("DocumentVersionType", DocumentVersionType, model=None)


@strawberry.type(name="PathHistoryType", description='Complete path history for a document in a corpus.')
class PathHistoryType:
    @strawberry.field(name="events", description='All path events in chronological order')
    def events(self, info: strawberry.Info) -> list["PathEventType"]:
        return resolve_django_list(self, info, getattr(self, "events"), "PathEventType")
    @strawberry.field(name="currentPath", description='Current path of document')
    def current_path(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "current_path", None))
    @strawberry.field(name="originalPath", description='Original import path')
    def original_path(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "original_path", None))
    move_count: int = strawberry.field(name="moveCount", description='Number of move/rename operations', default=None)


register_type("PathHistoryType", PathHistoryType, model=None)


@strawberry.type(name="PathEventType", description="A single event in the document's path history.")
class PathEventType:
    @strawberry.field(name="id", description='Global ID of the path event')
    def id(self, info: strawberry.Info) -> strawberry.ID:
        return coerce_str(getattr(self, "id", None))
    @strawberry.field(name="action", description='Type of path action')
    def action(self, info: strawberry.Info) -> enums.PathActionEnum:
        return coerce_enum(enums.PathActionEnum, getattr(self, "action", None))
    @strawberry.field(name="path", description='Path at time of event')
    def path(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "path", None))
    folder: Optional[Annotated["CorpusFolderType", strawberry.lazy("config.graphql.corpus_types")]] = strawberry.field(name="folder", description='Folder at time of event (null if at root)', default=None)
    timestamp: datetime.datetime = strawberry.field(name="timestamp", description='When this event occurred', default=None)
    user: Annotated["UserType", strawberry.lazy("config.graphql.user_types")] = strawberry.field(name="user", description='User who performed the action', default=None)
    version_number: int = strawberry.field(name="versionNumber", description='Content version at time of event', default=None)


register_type("PathEventType", PathEventType, model=None)


@strawberry.type(name="CorpusVersionInfoType", description='Version information for a document within a specific corpus.\n\nUsed by the version selector UI to show available versions and allow\nswitching between them via the ?v= URL parameter.')
class CorpusVersionInfoType:
    version_number: int = strawberry.field(name="versionNumber", description='Version number in this corpus', default=None)
    @strawberry.field(name="documentId", description='Global ID of the Document at this version')
    def document_id(self, info: strawberry.Info) -> strawberry.ID:
        return coerce_str(getattr(self, "document_id", None))
    @strawberry.field(name="documentSlug", description='Slug of the Document at this version (for URL building)')
    def document_slug(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "document_slug", None))
    created: datetime.datetime = strawberry.field(name="created", description='When this version was created', default=None)
    is_current: bool = strawberry.field(name="isCurrent", description='Whether this is the current (latest) version', default=None)


register_type("CorpusVersionInfoType", CorpusVersionInfoType, model=None)


@strawberry.type(name="PageAwareAnnotationType")
class PageAwareAnnotationType:
    pdf_page_info: Optional["PdfPageInfoType"] = strawberry.field(name="pdfPageInfo", default=None)
    @strawberry.field(name="pageAnnotations")
    def page_annotations(self, info: strawberry.Info) -> Optional[list[Optional[Annotated["AnnotationType", strawberry.lazy("config.graphql.annotation_types")]]]]:
        return resolve_django_list(self, info, getattr(self, "page_annotations"), "AnnotationType")


register_type("PageAwareAnnotationType", PageAwareAnnotationType, model=None)


@strawberry.type(name="PdfPageInfoType")
class PdfPageInfoType:
    page_count: Optional[int] = strawberry.field(name="pageCount", default=None)
    current_page: Optional[int] = strawberry.field(name="currentPage", default=None)
    has_next_page: Optional[bool] = strawberry.field(name="hasNextPage", default=None)
    has_previous_page: Optional[bool] = strawberry.field(name="hasPreviousPage", default=None)
    @strawberry.field(name="corpusId")
    def corpus_id(self, info: strawberry.Info) -> Optional[strawberry.ID]:
        return coerce_str(getattr(self, "corpus_id", None))
    @strawberry.field(name="documentId")
    def document_id(self, info: strawberry.Info) -> Optional[strawberry.ID]:
        return coerce_str(getattr(self, "document_id", None))
    @strawberry.field(name="forAnalysisIds")
    def for_analysis_ids(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "for_analysis_ids", None))
    @strawberry.field(name="labelType")
    def label_type(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "label_type", None))


register_type("PdfPageInfoType", PdfPageInfoType, model=None)

