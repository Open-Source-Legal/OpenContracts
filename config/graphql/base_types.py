"""GraphQL type definitions for shared utilities, enums, and simple types."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import graphene
from graphene.types.generic import GenericScalar
from graphql_relay import to_global_id

if TYPE_CHECKING:
    from config.graphql.annotation_types import AnnotationType
    from config.graphql.corpus_types import CorpusFolderType
    from config.graphql.user_types import UserType


def build_flat_tree(
    nodes: list[dict[str, Any]],
    type_name: str = "AnnotationType",
    text_key: str = "raw_text",
) -> list[dict[str, Any]]:
    """
    Builds a flat list of node representations from a list of dictionaries where each
    has at least 'id' and 'parent_id', plus an additional text field (default "raw_text")
    that may differ depending on the model (Annotation or Note).

    Args:
        nodes (list): A list of dicts with fields "id", "parent_id", and a text field.
        type_name (str): GraphQL type name used by to_global_id (e.g. "AnnotationType" or "NoteType").
        text_key (str): The dictionary key to use for the text field (e.g. "raw_text" or "content").

    Returns:
        list: A list of node dicts in which each node has:
            - "id" (global ID),
            - text field under "raw_text",
            - "children": list of child node global IDs.
    """
    # Map node IDs to their immediate children IDs
    id_to_children: dict[int | str, list[int | str]] = {}
    for node in nodes:
        node_id = node["id"]
        parent_id = node["parent_id"]
        if parent_id:
            id_to_children.setdefault(parent_id, []).append(node_id)

    # Build the flat list of nodes
    node_list = []
    for node in nodes:
        node_id = node["id"]
        node_id_global = to_global_id(type_name, node_id)
        # Convert child IDs to global IDs
        children_ids = id_to_children.get(node_id, [])
        children_global_ids = [to_global_id(type_name, cid) for cid in children_ids]
        # Use the appropriate text field key, defaulting to empty if missing
        node_dict = {
            "id": node_id_global,
            text_key: node.get(text_key, ""),
            "children": children_global_ids,
        }
        node_list.append(node_dict)

    return node_list


class PdfPageInfoType(graphene.ObjectType):
    page_count = graphene.Int()
    current_page = graphene.Int()
    has_next_page = graphene.Boolean()
    has_previous_page = graphene.Boolean()
    corpus_id = graphene.ID()
    document_id = graphene.ID()
    for_analysis_ids = graphene.String()
    label_type = graphene.String()


class LabelTypeEnum(graphene.Enum):
    RELATIONSHIP_LABEL = "RELATIONSHIP_LABEL"
    DOC_TYPE_LABEL = "DOC_TYPE_LABEL"
    TOKEN_LABEL = "TOKEN_LABEL"
    SPAN_LABEL = "SPAN_LABEL"


class ConversationTypeEnum(graphene.Enum):
    """Enum for conversation types."""

    CHAT = "chat"
    THREAD = "thread"


class AgentTypeEnum(graphene.Enum):
    """Enum for agent types in messages."""

    DOCUMENT_AGENT = "document_agent"
    CORPUS_AGENT = "corpus_agent"


class DocumentProcessingStatusEnum(graphene.Enum):
    """Enum for document processing status in the parsing pipeline."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# -------------------- Versioning Types (Phase 1) -------------------- #


class PathActionEnum(graphene.Enum):
    """Enum for document path lifecycle actions."""

    IMPORTED = "IMPORTED"
    MOVED = "MOVED"
    RENAMED = "RENAMED"
    DELETED = "DELETED"
    RESTORED = "RESTORED"
    UPDATED = "UPDATED"


class VersionChangeTypeEnum(graphene.Enum):
    """Enum for types of version changes."""

    INITIAL = "INITIAL"
    CONTENT_UPDATE = "CONTENT_UPDATE"
    MINOR_EDIT = "MINOR_EDIT"
    MAJOR_REVISION = "MAJOR_REVISION"


class DocumentVersionType(graphene.ObjectType):
    """Represents a single version in the document's content history."""

    id = graphene.ID(required=True, description="Global ID of the document version")
    version_number = graphene.Int(
        required=True, description="Sequential version number"
    )
    hash = graphene.String(required=True, description="SHA-256 hash of PDF content")
    created_at = graphene.DateTime(
        required=True, description="When version was created"
    )
    created_by = graphene.Field(
        lambda: _get_user_type(),
        required=True,
        description="User who created this version",
    )
    size_bytes = graphene.Int(description="File size in bytes")
    change_type = graphene.Field(
        VersionChangeTypeEnum,
        required=True,
        description="Type of change from previous version",
    )
    parent_version = graphene.Field(
        lambda: DocumentVersionType, description="Previous version in content tree"
    )


class VersionHistoryType(graphene.ObjectType):
    """Complete version history for a document."""

    versions = graphene.List(
        graphene.NonNull(DocumentVersionType),
        required=True,
        description="All versions of this document",
    )
    current_version = graphene.Field(
        DocumentVersionType, required=True, description="The current active version"
    )
    version_tree = GenericScalar(description="Tree structure of version relationships")


class PathEventType(graphene.ObjectType):
    """A single event in the document's path history."""

    id = graphene.ID(required=True, description="Global ID of the path event")
    action = graphene.Field(
        PathActionEnum, required=True, description="Type of path action"
    )
    path = graphene.String(required=True, description="Path at time of event")
    folder = graphene.Field(
        lambda: _get_corpus_folder_type(),
        description="Folder at time of event (null if at root)",
    )
    timestamp = graphene.DateTime(required=True, description="When this event occurred")
    user = graphene.Field(
        lambda: _get_user_type(),
        required=True,
        description="User who performed the action",
    )
    version_number = graphene.Int(
        required=True, description="Content version at time of event"
    )


class PathHistoryType(graphene.ObjectType):
    """Complete path history for a document in a corpus."""

    events = graphene.List(
        graphene.NonNull(PathEventType),
        required=True,
        description="All path events in chronological order",
    )
    current_path = graphene.String(
        required=True, description="Current path of document"
    )
    original_path = graphene.String(required=True, description="Original import path")
    move_count = graphene.Int(
        required=True, description="Number of move/rename operations"
    )


class CorpusVersionInfoType(graphene.ObjectType):
    """Version information for a document within a specific corpus.

    Used by the version selector UI to show available versions and allow
    switching between them via the ?v= URL parameter.
    """

    version_number = graphene.Int(
        required=True, description="Version number in this corpus"
    )
    document_id = graphene.ID(
        required=True, description="Global ID of the Document at this version"
    )
    document_slug = graphene.String(
        description="Slug of the Document at this version (for URL building)"
    )
    created = graphene.DateTime(
        required=True, description="When this version was created"
    )
    is_current = graphene.Boolean(
        required=True, description="Whether this is the current (latest) version"
    )


class PageAwareAnnotationType(graphene.ObjectType):
    pdf_page_info = graphene.Field(PdfPageInfoType)
    page_annotations = graphene.List(lambda: _get_annotation_type())


def _get_user_type() -> type[UserType]:
    from config.graphql.user_types import UserType

    return UserType


def _get_corpus_folder_type() -> type[CorpusFolderType]:
    from config.graphql.corpus_types import CorpusFolderType

    return CorpusFolderType


def _get_annotation_type() -> type[AnnotationType]:
    from config.graphql.annotation_types import AnnotationType

    return AnnotationType
