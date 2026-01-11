"""
Forking utilities and configuration for corpus forking.

This module provides an enumerable, configuration-driven forking system that
allows easy updates to what gets forked when creating a corpus copy.

Usage:
    from opencontractserver.utils.fork_utils import (
        ForkableModelType,
        ForkContext,
        get_default_fork_config,
    )

    # Get models to fork
    config = get_default_fork_config()

    # Create a fork context for tracking ID mappings
    ctx = ForkContext(
        source_corpus_id=123,
        target_corpus_id=456,
        user_id=1,
    )

    # Fork documents
    fork_documents(ctx, doc_ids)
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class ForkableModelType(Enum):
    """
    Enumeration of all model types that can be forked.

    This enum serves as a registry of forkable models and their ordering.
    The order matters - models with dependencies must be forked after
    their dependencies.
    """

    # ========== Core Organization Models (Fork First) ==========
    LABEL_SET = "label_set"
    ANNOTATION_LABEL = "annotation_label"
    CORPUS_FOLDER = "corpus_folder"

    # ========== Content Models ==========
    DOCUMENT = "document"
    ANNOTATION = "annotation"
    RELATIONSHIP = "relationship"

    # ========== Extract-related Models ==========
    FIELDSET = "fieldset"
    COLUMN = "column"
    EXTRACT = "extract"
    DATACELL = "datacell"

    # ========== Conversation Models ==========
    CONVERSATION = "conversation"
    CHAT_MESSAGE = "chat_message"

    # ========== Notes Models ==========
    NOTE = "note"
    NOTE_REVISION = "note_revision"

    # ========== Models NOT to Fork (excluded by default) ==========
    # These are listed for documentation but excluded from DEFAULT_FORK_CONFIG
    # ANALYSIS = "analysis"  # Excluded - created by analyzers
    # ANALYZER = "analyzer"  # Excluded - system config
    # AGENT_CONFIG = "agent_config"  # Excluded - system config
    # CORPUS_ACTION = "corpus_action"  # Excluded - system config
    # MODERATION_ACTION = "moderation_action"  # Excluded - audit trail
    # USER_REPUTATION = "user_reputation"  # Excluded - user-specific
    # CORPUS_MODERATOR = "corpus_moderator"  # Excluded - permissions


@dataclass
class ForkModelConfig:
    """
    Configuration for forking a specific model type.

    Attributes:
        model_type: The type of model this config applies to
        enabled: Whether this model type should be forked
        requires_permission_grant: Whether to call set_permissions_for_obj_to_user()
                                   Per permission guide, inherited models don't need this
        has_file_fields: List of FileField names that need file copying
        id_mapping_key: Key name for storing ID mappings (old_id -> new_id)
        depends_on: List of model types that must be forked first
        filter_kwargs: Filter criteria for selecting objects to fork
        batch_size: Number of objects to process in each batch (for bulk operations)
        use_bulk_create: Whether to use bulk_create for performance
    """

    model_type: ForkableModelType
    enabled: bool = True
    requires_permission_grant: bool = False
    has_file_fields: list[str] = field(default_factory=list)
    id_mapping_key: Optional[str] = None
    depends_on: list[ForkableModelType] = field(default_factory=list)
    filter_kwargs: dict = field(default_factory=dict)
    batch_size: int = 500
    use_bulk_create: bool = True


@dataclass
class ForkContext:
    """
    Context object for tracking state during a fork operation.

    This is passed between fork handlers to share ID mappings and state.
    """

    source_corpus_id: int
    target_corpus_id: int
    user_id: int

    # ID mappings: old_id -> new_id
    doc_map: dict[int, int] = field(default_factory=dict)
    label_map: dict[int, int] = field(default_factory=dict)
    annotation_map: dict[int, int] = field(default_factory=dict)
    folder_map: dict[int, int] = field(default_factory=dict)
    fieldset_map: dict[int, int] = field(default_factory=dict)
    column_map: dict[int, int] = field(default_factory=dict)
    extract_map: dict[int, int] = field(default_factory=dict)
    conversation_map: dict[int, int] = field(default_factory=dict)
    note_map: dict[int, int] = field(default_factory=dict)

    # Statistics
    documents_forked: int = 0
    annotations_forked: int = 0
    relationships_forked: int = 0
    extracts_forked: int = 0
    conversations_forked: int = 0
    notes_forked: int = 0


@dataclass
class ForkResult:
    """
    Result of a fork operation.
    """

    success: bool
    new_corpus_id: Optional[int] = None
    error_message: Optional[str] = None
    context: Optional[ForkContext] = None

    # Statistics
    documents_forked: int = 0
    annotations_forked: int = 0
    relationships_forked: int = 0
    fieldsets_forked: int = 0
    extracts_forked: int = 0
    datacells_forked: int = 0
    conversations_forked: int = 0
    messages_forked: int = 0
    notes_forked: int = 0
    folders_forked: int = 0


def get_default_fork_config() -> dict[ForkableModelType, ForkModelConfig]:
    """
    Get the default fork configuration.

    This defines what models get forked and how. Modify this to change
    default forking behavior.

    Returns:
        Dictionary mapping model types to their fork configurations.
    """
    return {
        # ========== Organization Models ==========
        ForkableModelType.LABEL_SET: ForkModelConfig(
            model_type=ForkableModelType.LABEL_SET,
            enabled=True,
            requires_permission_grant=False,  # Permissions via corpus
            has_file_fields=["icon"],
            batch_size=1,  # Only one per corpus
            use_bulk_create=False,
        ),
        ForkableModelType.ANNOTATION_LABEL: ForkModelConfig(
            model_type=ForkableModelType.ANNOTATION_LABEL,
            enabled=True,
            requires_permission_grant=False,
            id_mapping_key="label_map",
            depends_on=[ForkableModelType.LABEL_SET],
            batch_size=100,
            use_bulk_create=True,
        ),
        ForkableModelType.CORPUS_FOLDER: ForkModelConfig(
            model_type=ForkableModelType.CORPUS_FOLDER,
            enabled=True,
            requires_permission_grant=False,  # Permissions via corpus
            id_mapping_key="folder_map",
            batch_size=100,
            use_bulk_create=False,  # Need to preserve hierarchy
        ),
        # ========== Content Models ==========
        ForkableModelType.DOCUMENT: ForkModelConfig(
            model_type=ForkableModelType.DOCUMENT,
            enabled=True,
            requires_permission_grant=True,  # Direct permission model
            has_file_fields=["txt_extract_file", "pawls_parse_file"],
            id_mapping_key="doc_map",
            depends_on=[ForkableModelType.CORPUS_FOLDER],
            batch_size=50,  # Lower due to file operations
            use_bulk_create=False,  # Files need individual handling
        ),
        ForkableModelType.ANNOTATION: ForkModelConfig(
            model_type=ForkableModelType.ANNOTATION,
            enabled=True,
            requires_permission_grant=False,  # Inherited from doc+corpus
            id_mapping_key="annotation_map",
            depends_on=[
                ForkableModelType.DOCUMENT,
                ForkableModelType.ANNOTATION_LABEL,
            ],
            filter_kwargs={"analysis__isnull": True},  # Only non-analysis annotations
            batch_size=1000,
            use_bulk_create=True,
        ),
        ForkableModelType.RELATIONSHIP: ForkModelConfig(
            model_type=ForkableModelType.RELATIONSHIP,
            enabled=True,
            requires_permission_grant=False,  # Inherited from doc+corpus
            depends_on=[ForkableModelType.ANNOTATION],
            filter_kwargs={"analysis__isnull": True},  # Only non-analysis relationships
            batch_size=1000,
            use_bulk_create=False,  # M2M fields need individual handling
        ),
        # ========== Extract Models ==========
        ForkableModelType.FIELDSET: ForkModelConfig(
            model_type=ForkableModelType.FIELDSET,
            enabled=True,
            requires_permission_grant=True,  # Direct permission model
            id_mapping_key="fieldset_map",
            batch_size=10,
            use_bulk_create=False,
        ),
        ForkableModelType.COLUMN: ForkModelConfig(
            model_type=ForkableModelType.COLUMN,
            enabled=True,
            requires_permission_grant=False,  # Via fieldset
            id_mapping_key="column_map",
            depends_on=[ForkableModelType.FIELDSET],
            batch_size=100,
            use_bulk_create=True,
        ),
        ForkableModelType.EXTRACT: ForkModelConfig(
            model_type=ForkableModelType.EXTRACT,
            enabled=True,
            requires_permission_grant=True,  # Hybrid permission model
            id_mapping_key="extract_map",
            depends_on=[ForkableModelType.FIELDSET, ForkableModelType.DOCUMENT],
            batch_size=50,
            use_bulk_create=False,  # M2M documents field
        ),
        ForkableModelType.DATACELL: ForkModelConfig(
            model_type=ForkableModelType.DATACELL,
            enabled=True,
            requires_permission_grant=False,  # Via extract
            depends_on=[
                ForkableModelType.EXTRACT,
                ForkableModelType.COLUMN,
                ForkableModelType.DOCUMENT,
            ],
            batch_size=1000,
            use_bulk_create=True,
        ),
        # ========== Conversation Models ==========
        ForkableModelType.CONVERSATION: ForkModelConfig(
            model_type=ForkableModelType.CONVERSATION,
            enabled=True,
            requires_permission_grant=True,
            id_mapping_key="conversation_map",
            depends_on=[ForkableModelType.DOCUMENT],
            # Only fork CHAT type (agent conversations), not THREAD (discussions)
            filter_kwargs={"conversation_type": "chat"},
            batch_size=100,
            use_bulk_create=False,
        ),
        ForkableModelType.CHAT_MESSAGE: ForkModelConfig(
            model_type=ForkableModelType.CHAT_MESSAGE,
            enabled=True,
            requires_permission_grant=False,  # Via conversation
            depends_on=[
                ForkableModelType.CONVERSATION,
                ForkableModelType.DOCUMENT,
                ForkableModelType.ANNOTATION,
            ],
            batch_size=500,
            use_bulk_create=True,
        ),
        # ========== Notes Models ==========
        ForkableModelType.NOTE: ForkModelConfig(
            model_type=ForkableModelType.NOTE,
            enabled=True,
            requires_permission_grant=False,  # Inherited via document
            id_mapping_key="note_map",
            depends_on=[ForkableModelType.DOCUMENT, ForkableModelType.ANNOTATION],
            batch_size=500,
            use_bulk_create=False,  # Hierarchy needs ordering
        ),
        ForkableModelType.NOTE_REVISION: ForkModelConfig(
            model_type=ForkableModelType.NOTE_REVISION,
            enabled=True,
            requires_permission_grant=False,
            depends_on=[ForkableModelType.NOTE],
            batch_size=1000,
            use_bulk_create=True,
        ),
    }


def get_fork_order(
    config: dict[ForkableModelType, ForkModelConfig],
) -> list[ForkableModelType]:
    """
    Get the ordered list of model types to fork based on dependencies.

    Uses topological sort to ensure dependencies are forked first.

    Args:
        config: Fork configuration dictionary

    Returns:
        Ordered list of model types to fork
    """
    # Build dependency graph
    enabled_types = {t for t, c in config.items() if c.enabled}
    result = []
    visited = set()
    temp_visited = set()

    def visit(model_type: ForkableModelType):
        if model_type in temp_visited:
            raise ValueError(f"Circular dependency detected for {model_type}")
        if model_type in visited:
            return

        temp_visited.add(model_type)

        model_config = config.get(model_type)
        if model_config:
            for dep in model_config.depends_on:
                if dep in enabled_types:
                    visit(dep)

        temp_visited.remove(model_type)
        visited.add(model_type)
        result.append(model_type)

    for model_type in enabled_types:
        if model_type not in visited:
            visit(model_type)

    return result
