"""
Fork handlers for individual model types.

Each handler is responsible for forking a specific model type and updating
the ForkContext with ID mappings.
"""

import logging
from pathlib import Path
from typing import Optional

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction

from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.fork_utils import ForkContext
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

logger = logging.getLogger(__name__)
User = get_user_model()


def fork_label_set(
    ctx: ForkContext,
    source_label_set_id: Optional[int],
) -> Optional[int]:
    """
    Fork a LabelSet and return the new LabelSet ID.

    Args:
        ctx: Fork context with user_id and target corpus
        source_label_set_id: ID of the LabelSet to fork (can be None)

    Returns:
        New LabelSet ID or None if no label set to fork
    """
    if not source_label_set_id:
        logger.info("No label set to fork")
        return None

    from opencontractserver.annotations.models import LabelSet
    from opencontractserver.corpuses.models import Corpus

    try:
        old_label_set = LabelSet.objects.get(pk=source_label_set_id)
    except LabelSet.DoesNotExist:
        logger.warning(f"LabelSet {source_label_set_id} not found")
        return None

    # Create new label set
    new_label_set = LabelSet(
        creator_id=ctx.user_id,
        title=f"[FORK] {old_label_set.title}",
        description=old_label_set.description,
    )
    new_label_set.save()
    logger.info(f"Created forked LabelSet: {new_label_set.id}")

    # Copy icon file if present
    if old_label_set.icon and old_label_set.icon.name:
        try:
            icon_obj = default_storage.open(old_label_set.icon.name)
            icon_file = ContentFile(icon_obj.read())
            new_label_set.icon.save(Path(old_label_set.icon.name).name, icon_file)
            new_label_set.save()
            logger.info("Copied label set icon")
        except Exception as e:
            logger.warning(f"Could not copy label set icon: {e}")

    # Update target corpus to use new label set
    target_corpus = Corpus.objects.get(pk=ctx.target_corpus_id)
    target_corpus.label_set = new_label_set
    target_corpus.save(update_fields=["label_set", "modified"])

    return new_label_set.id


def fork_annotation_labels(
    ctx: ForkContext,
    source_label_set_id: Optional[int],
    new_label_set_id: Optional[int],
) -> int:
    """
    Fork all AnnotationLabels from a LabelSet.

    Updates ctx.label_map with old_id -> new_id mappings.

    Args:
        ctx: Fork context
        source_label_set_id: Original LabelSet ID
        new_label_set_id: New LabelSet ID to add labels to

    Returns:
        Number of labels forked
    """
    if not source_label_set_id or not new_label_set_id:
        return 0

    from opencontractserver.annotations.models import AnnotationLabel, LabelSet

    try:
        old_label_set = LabelSet.objects.get(pk=source_label_set_id)
        new_label_set = LabelSet.objects.get(pk=new_label_set_id)
    except LabelSet.DoesNotExist:
        return 0

    old_labels = list(old_label_set.annotation_labels.all())
    count = 0

    for old_label in old_labels:
        try:
            new_label = AnnotationLabel(
                creator_id=ctx.user_id,
                label_type=old_label.label_type,
                color=old_label.color,
                description=old_label.description,
                icon=old_label.icon,
                text=old_label.text,
            )
            new_label.save()

            # Store mapping
            ctx.label_map[old_label.id] = new_label.id

            # Add to new label set
            new_label_set.annotation_labels.add(new_label)
            count += 1

        except Exception as e:
            logger.error(f"Error forking label {old_label.id}: {e}")

    logger.info(f"Forked {count} annotation labels")
    return count


def fork_corpus_folders(ctx: ForkContext) -> int:
    """
    Fork all CorpusFolders from source corpus to target corpus.

    Preserves folder hierarchy by processing root folders first, then children.
    Updates ctx.folder_map with old_id -> new_id mappings.

    Args:
        ctx: Fork context

    Returns:
        Number of folders forked
    """
    from opencontractserver.corpuses.models import Corpus, CorpusFolder

    source_corpus = Corpus.objects.get(pk=ctx.source_corpus_id)
    target_corpus = Corpus.objects.get(pk=ctx.target_corpus_id)

    # Get all folders - we'll process them in dependency order
    all_folders = list(CorpusFolder.objects.filter(corpus=source_corpus))

    # Build a map of folder_id -> folder and parent_id -> children
    folder_by_id = {f.id: f for f in all_folders}
    children_by_parent = {}
    root_folders = []

    for folder in all_folders:
        if folder.parent_id is None:
            root_folders.append(folder)
        else:
            if folder.parent_id not in children_by_parent:
                children_by_parent[folder.parent_id] = []
            children_by_parent[folder.parent_id].append(folder)

    count = 0

    def fork_folder_recursive(old_folder, new_parent_id):
        """Fork a folder and its children recursively."""
        nonlocal count

        try:
            new_folder = CorpusFolder(
                name=old_folder.name,
                corpus=target_corpus,
                parent_id=new_parent_id,
                description=old_folder.description,
                color=old_folder.color,
                icon=old_folder.icon,
                tags=old_folder.tags.copy() if old_folder.tags else [],
                is_public=old_folder.is_public,
                creator_id=ctx.user_id,
            )
            new_folder.save()

            ctx.folder_map[old_folder.id] = new_folder.id
            count += 1

            # Fork children
            children = children_by_parent.get(old_folder.id, [])
            for child in children:
                fork_folder_recursive(child, new_folder.id)

        except Exception as e:
            logger.error(f"Error forking folder {old_folder.id}: {e}")

    # Start with root folders
    for root_folder in root_folders:
        fork_folder_recursive(root_folder, None)

    logger.info(f"Forked {count} corpus folders")
    return count


def fork_documents(
    ctx: ForkContext,
    doc_ids: list[int],
) -> int:
    """
    Fork documents from source corpus to target corpus.

    Uses the Corpus.add_document() method which handles corpus isolation.
    Updates ctx.doc_map with old_id -> new_id mappings.

    Args:
        ctx: Fork context
        doc_ids: List of document IDs to fork

    Returns:
        Number of documents forked
    """
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.documents.models import Document, DocumentPath

    target_corpus = Corpus.objects.get(pk=ctx.target_corpus_id)
    user = User.objects.get(pk=ctx.user_id)

    count = 0
    for doc_id in doc_ids:
        try:
            old_doc = Document.objects.get(pk=doc_id)

            # Get the folder mapping if document was in a folder
            old_path = DocumentPath.objects.filter(
                corpus_id=ctx.source_corpus_id,
                document_id=doc_id,
                is_current=True,
                is_deleted=False,
            ).first()

            new_folder = None
            if old_path and old_path.folder_id:
                new_folder_id = ctx.folder_map.get(old_path.folder_id)
                if new_folder_id:
                    from opencontractserver.corpuses.models import CorpusFolder

                    new_folder = CorpusFolder.objects.get(pk=new_folder_id)

            # Use add_document which handles corpus isolation properly
            new_doc, status, new_path = target_corpus.add_document(
                document=old_doc,
                user=user,
                folder=new_folder,
                title=f"[FORK] {old_doc.title}",
            )

            # Store mapping
            ctx.doc_map[doc_id] = new_doc.id
            count += 1

            logger.debug(f"Forked document {doc_id} -> {new_doc.id}")

        except Exception as e:
            logger.error(f"Error forking document {doc_id}: {e}")
            raise

    ctx.documents_forked = count
    logger.info(f"Forked {count} documents")
    return count


def fork_annotations(
    ctx: ForkContext,
    annotation_ids: list[int],
) -> int:
    """
    Fork annotations to target corpus.

    Updates ctx.annotation_map with old_id -> new_id mappings.
    Note: Per permission guide, annotations inherit permissions from doc+corpus,
    so we don't set explicit permissions.

    Args:
        ctx: Fork context
        annotation_ids: List of annotation IDs to fork

    Returns:
        Number of annotations forked
    """
    from opencontractserver.annotations.models import Annotation

    # Process in batches to avoid memory issues
    batch_size = 1000
    count = 0
    new_annotations = []

    for i in range(0, len(annotation_ids), batch_size):
        batch_ids = annotation_ids[i : i + batch_size]
        old_annotations = Annotation.objects.filter(pk__in=batch_ids).select_related(
            "annotation_label", "document"
        )

        for old_ann in old_annotations:
            # Skip if we don't have the document mapping
            new_doc_id = ctx.doc_map.get(old_ann.document_id)
            if not new_doc_id:
                logger.warning(
                    f"Skipping annotation {old_ann.id}: document {old_ann.document_id} not forked"
                )
                continue

            # Skip if we don't have the label mapping (for labeled annotations)
            new_label_id = None
            if old_ann.annotation_label_id:
                new_label_id = ctx.label_map.get(old_ann.annotation_label_id)
                if not new_label_id:
                    logger.warning(
                        f"Skipping annotation {old_ann.id}: label {old_ann.annotation_label_id} not forked"
                    )
                    continue

            try:
                # Create new annotation
                new_ann = Annotation(
                    page=old_ann.page,
                    raw_text=old_ann.raw_text,
                    tokens_jsons=old_ann.tokens_jsons,
                    bounding_box=old_ann.bounding_box,
                    json=old_ann.json,
                    annotation_type=old_ann.annotation_type,
                    annotation_label_id=new_label_id,
                    document_id=new_doc_id,
                    corpus_id=ctx.target_corpus_id,
                    structural=old_ann.structural,
                    is_public=old_ann.is_public,
                    creator_id=ctx.user_id,
                )
                new_annotations.append((old_ann.id, new_ann))

            except Exception as e:
                logger.error(f"Error preparing annotation {old_ann.id}: {e}")

        # Bulk create annotations in this batch
        if new_annotations:
            # Can't use bulk_create because we need IDs for mapping
            for old_id, new_ann in new_annotations:
                new_ann.save()
                ctx.annotation_map[old_id] = new_ann.id
                count += 1

            new_annotations = []

    ctx.annotations_forked = count
    logger.info(f"Forked {count} annotations")
    return count


def fork_relationships(ctx: ForkContext) -> int:
    """
    Fork relationships between annotations.

    Relationships link source and target annotations. We need to remap
    both the source and target annotation IDs.

    Args:
        ctx: Fork context

    Returns:
        Number of relationships forked
    """
    from opencontractserver.annotations.models import Relationship

    # Get relationships from source corpus where analysis is null
    old_relationships = Relationship.objects.filter(
        corpus_id=ctx.source_corpus_id,
        analysis__isnull=True,
    ).prefetch_related("source_annotations", "target_annotations")

    count = 0
    for old_rel in old_relationships:
        try:
            # Get new document ID
            new_doc_id = ctx.doc_map.get(old_rel.document_id)
            if not new_doc_id and old_rel.document_id:
                logger.warning(
                    f"Skipping relationship {old_rel.id}: document not forked"
                )
                continue

            # Get new label ID
            new_label_id = None
            if old_rel.relationship_label_id:
                new_label_id = ctx.label_map.get(old_rel.relationship_label_id)
                if not new_label_id:
                    logger.warning(
                        f"Skipping relationship {old_rel.id}: label not forked"
                    )
                    continue

            # Create new relationship
            new_rel = Relationship(
                relationship_label_id=new_label_id,
                corpus_id=ctx.target_corpus_id,
                document_id=new_doc_id,
                structural=old_rel.structural,
                is_public=old_rel.is_public,
                creator_id=ctx.user_id,
            )
            new_rel.save()

            # Map source annotations
            source_ann_ids = []
            for old_source in old_rel.source_annotations.all():
                new_source_id = ctx.annotation_map.get(old_source.id)
                if new_source_id:
                    source_ann_ids.append(new_source_id)
            if source_ann_ids:
                new_rel.source_annotations.set(source_ann_ids)

            # Map target annotations
            target_ann_ids = []
            for old_target in old_rel.target_annotations.all():
                new_target_id = ctx.annotation_map.get(old_target.id)
                if new_target_id:
                    target_ann_ids.append(new_target_id)
            if target_ann_ids:
                new_rel.target_annotations.set(target_ann_ids)

            count += 1

        except Exception as e:
            logger.error(f"Error forking relationship {old_rel.id}: {e}")

    ctx.relationships_forked = count
    logger.info(f"Forked {count} relationships")
    return count


def fork_fieldsets(ctx: ForkContext) -> int:
    """
    Fork fieldsets (extraction schemas) from source corpus.

    Only forks fieldsets that are linked to the source corpus as metadata_schema.
    Updates ctx.fieldset_map with old_id -> new_id mappings.

    Args:
        ctx: Fork context

    Returns:
        Number of fieldsets forked
    """
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.extracts.models import Fieldset

    source_corpus = Corpus.objects.get(pk=ctx.source_corpus_id)
    target_corpus = Corpus.objects.get(pk=ctx.target_corpus_id)

    # Check if source corpus has a metadata schema
    if not hasattr(source_corpus, "metadata_schema") or not source_corpus.metadata_schema:
        logger.info("No metadata schema to fork")
        return 0

    old_fieldset = source_corpus.metadata_schema

    # Create new fieldset for target corpus
    new_fieldset = Fieldset(
        name=f"[FORK] {old_fieldset.name}",
        description=old_fieldset.description,
        corpus=target_corpus,  # Link to new corpus
        creator_id=ctx.user_id,
        is_public=old_fieldset.is_public,
    )
    new_fieldset.save()

    # Set permissions
    set_permissions_for_obj_to_user(ctx.user_id, new_fieldset, [PermissionTypes.CRUD])

    ctx.fieldset_map[old_fieldset.id] = new_fieldset.id
    logger.info(f"Forked fieldset {old_fieldset.id} -> {new_fieldset.id}")
    return 1


def fork_columns(ctx: ForkContext) -> int:
    """
    Fork columns from forked fieldsets.

    Updates ctx.column_map with old_id -> new_id mappings.

    Args:
        ctx: Fork context

    Returns:
        Number of columns forked
    """
    from opencontractserver.extracts.models import Column, Fieldset

    if not ctx.fieldset_map:
        return 0

    count = 0
    for old_fieldset_id, new_fieldset_id in ctx.fieldset_map.items():
        old_columns = Column.objects.filter(fieldset_id=old_fieldset_id).order_by(
            "display_order"
        )

        for old_col in old_columns:
            try:
                new_col = Column(
                    name=old_col.name,
                    fieldset_id=new_fieldset_id,
                    query=old_col.query,
                    match_text=old_col.match_text,
                    must_contain_text=old_col.must_contain_text,
                    output_type=old_col.output_type,
                    limit_to_label=old_col.limit_to_label,
                    instructions=old_col.instructions,
                    extract_is_list=old_col.extract_is_list,
                    task_name=old_col.task_name,
                    data_type=old_col.data_type,
                    validation_config=old_col.validation_config,
                    is_manual_entry=old_col.is_manual_entry,
                    default_value=old_col.default_value,
                    help_text=old_col.help_text,
                    display_order=old_col.display_order,
                    creator_id=ctx.user_id,
                    is_public=old_col.is_public,
                )
                new_col.save()

                ctx.column_map[old_col.id] = new_col.id
                count += 1

            except Exception as e:
                logger.error(f"Error forking column {old_col.id}: {e}")

    logger.info(f"Forked {count} columns")
    return count


def fork_extracts(ctx: ForkContext) -> int:
    """
    Fork extracts from source corpus.

    Updates ctx.extract_map with old_id -> new_id mappings.

    Args:
        ctx: Fork context

    Returns:
        Number of extracts forked
    """
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.extracts.models import Extract

    source_corpus = Corpus.objects.get(pk=ctx.source_corpus_id)

    # Get extracts for source corpus
    old_extracts = Extract.objects.filter(corpus=source_corpus).prefetch_related(
        "documents"
    )

    count = 0
    for old_extract in old_extracts:
        # Check if we have the fieldset mapping
        new_fieldset_id = ctx.fieldset_map.get(old_extract.fieldset_id)
        if not new_fieldset_id:
            logger.warning(
                f"Skipping extract {old_extract.id}: fieldset not forked"
            )
            continue

        try:
            new_extract = Extract(
                corpus_id=ctx.target_corpus_id,
                name=f"[FORK] {old_extract.name}",
                fieldset_id=new_fieldset_id,
                started=old_extract.started,
                finished=old_extract.finished,
                error=old_extract.error,
                creator_id=ctx.user_id,
                is_public=old_extract.is_public,
            )
            new_extract.save()

            # Set permissions
            set_permissions_for_obj_to_user(
                ctx.user_id, new_extract, [PermissionTypes.CRUD]
            )

            # Map documents M2M
            new_doc_ids = []
            for old_doc in old_extract.documents.all():
                new_doc_id = ctx.doc_map.get(old_doc.id)
                if new_doc_id:
                    new_doc_ids.append(new_doc_id)
            if new_doc_ids:
                new_extract.documents.set(new_doc_ids)

            ctx.extract_map[old_extract.id] = new_extract.id
            count += 1

        except Exception as e:
            logger.error(f"Error forking extract {old_extract.id}: {e}")

    ctx.extracts_forked = count
    logger.info(f"Forked {count} extracts")
    return count


def fork_datacells(ctx: ForkContext) -> int:
    """
    Fork datacells from forked extracts.

    Args:
        ctx: Fork context

    Returns:
        Number of datacells forked
    """
    from opencontractserver.extracts.models import Datacell

    if not ctx.extract_map:
        return 0

    count = 0
    for old_extract_id, new_extract_id in ctx.extract_map.items():
        old_datacells = Datacell.objects.filter(
            extract_id=old_extract_id
        ).prefetch_related("sources")

        for old_cell in old_datacells:
            # Get new document ID
            new_doc_id = ctx.doc_map.get(old_cell.document_id)
            if not new_doc_id:
                continue

            # Get new column ID
            new_col_id = ctx.column_map.get(old_cell.column_id)
            if not new_col_id:
                continue

            try:
                new_cell = Datacell(
                    extract_id=new_extract_id,
                    column_id=new_col_id,
                    document_id=new_doc_id,
                    data=old_cell.data,
                    data_definition=old_cell.data_definition,
                    started=old_cell.started,
                    completed=old_cell.completed,
                    failed=old_cell.failed,
                    stacktrace=old_cell.stacktrace,
                    corrected_data=old_cell.corrected_data,
                    creator_id=ctx.user_id,
                    is_public=old_cell.is_public,
                )
                new_cell.save()

                # Map sources M2M (annotations)
                new_source_ids = []
                for old_source in old_cell.sources.all():
                    new_source_id = ctx.annotation_map.get(old_source.id)
                    if new_source_id:
                        new_source_ids.append(new_source_id)
                if new_source_ids:
                    new_cell.sources.set(new_source_ids)

                count += 1

            except Exception as e:
                logger.error(f"Error forking datacell {old_cell.id}: {e}")

    logger.info(f"Forked {count} datacells")
    return count


def fork_conversations(ctx: ForkContext) -> int:
    """
    Fork conversations (chats) from source corpus.

    Only forks CHAT type conversations (agent chats), not THREAD (discussions).
    Updates ctx.conversation_map with old_id -> new_id mappings.

    Args:
        ctx: Fork context

    Returns:
        Number of conversations forked
    """
    from opencontractserver.conversations.models import Conversation

    # Get chat-type conversations for source corpus or its documents
    old_conversations = Conversation.objects.filter(
        conversation_type="chat",
    ).filter(
        # Corpus-level chats OR document-level chats for forked documents
        chat_with_corpus_id=ctx.source_corpus_id
    ) | Conversation.objects.filter(
        conversation_type="chat",
        chat_with_document_id__in=list(ctx.doc_map.keys()),
    )

    count = 0
    for old_conv in old_conversations.distinct():
        try:
            # Determine new corpus/document references
            new_corpus_id = None
            new_doc_id = None

            if old_conv.chat_with_corpus_id == ctx.source_corpus_id:
                new_corpus_id = ctx.target_corpus_id

            if old_conv.chat_with_document_id:
                new_doc_id = ctx.doc_map.get(old_conv.chat_with_document_id)
                if not new_doc_id:
                    logger.warning(
                        f"Skipping conversation {old_conv.id}: document not forked"
                    )
                    continue

            new_conv = Conversation(
                title=f"[FORK] {old_conv.title}" if old_conv.title else "",
                description=old_conv.description,
                conversation_type=old_conv.conversation_type,
                chat_with_corpus_id=new_corpus_id,
                chat_with_document_id=new_doc_id,
                is_public=old_conv.is_public,
                creator_id=ctx.user_id,
            )
            new_conv.save()

            # Set permissions
            set_permissions_for_obj_to_user(
                ctx.user_id, new_conv, [PermissionTypes.CRUD]
            )

            ctx.conversation_map[old_conv.id] = new_conv.id
            count += 1

        except Exception as e:
            logger.error(f"Error forking conversation {old_conv.id}: {e}")

    ctx.conversations_forked = count
    logger.info(f"Forked {count} conversations")
    return count


def fork_chat_messages(ctx: ForkContext) -> int:
    """
    Fork chat messages from forked conversations.

    Maintains message hierarchy (parent_message relationships).

    Args:
        ctx: Fork context

    Returns:
        Number of messages forked
    """
    from opencontractserver.conversations.models import ChatMessage

    if not ctx.conversation_map:
        return 0

    count = 0
    message_map = {}  # old_id -> new_id for parent references

    for old_conv_id, new_conv_id in ctx.conversation_map.items():
        # Get messages ordered by creation time (parents first)
        old_messages = ChatMessage.objects.filter(
            conversation_id=old_conv_id
        ).order_by("created_at")

        for old_msg in old_messages:
            try:
                # Get new parent message ID
                new_parent_id = None
                if old_msg.parent_message_id:
                    new_parent_id = message_map.get(old_msg.parent_message_id)

                # Get new source document ID
                new_source_doc_id = None
                if old_msg.source_document_id:
                    new_source_doc_id = ctx.doc_map.get(old_msg.source_document_id)

                new_msg = ChatMessage(
                    conversation_id=new_conv_id,
                    msg_type=old_msg.msg_type,
                    agent_type=old_msg.agent_type,
                    parent_message_id=new_parent_id,
                    content=old_msg.content,
                    data=old_msg.data,
                    source_document_id=new_source_doc_id,
                    state=old_msg.state,
                    creator_id=ctx.user_id,
                )
                new_msg.save()

                # Map source_annotations M2M
                new_source_ann_ids = []
                for old_ann in old_msg.source_annotations.all():
                    new_ann_id = ctx.annotation_map.get(old_ann.id)
                    if new_ann_id:
                        new_source_ann_ids.append(new_ann_id)
                if new_source_ann_ids:
                    new_msg.source_annotations.set(new_source_ann_ids)

                # Map created_annotations M2M
                new_created_ann_ids = []
                for old_ann in old_msg.created_annotations.all():
                    new_ann_id = ctx.annotation_map.get(old_ann.id)
                    if new_ann_id:
                        new_created_ann_ids.append(new_ann_id)
                if new_created_ann_ids:
                    new_msg.created_annotations.set(new_created_ann_ids)

                message_map[old_msg.id] = new_msg.id
                count += 1

            except Exception as e:
                logger.error(f"Error forking message {old_msg.id}: {e}")

    logger.info(f"Forked {count} chat messages")
    return count


def fork_notes(ctx: ForkContext) -> int:
    """
    Fork notes from source corpus documents.

    Maintains note hierarchy (parent relationships).
    Updates ctx.note_map with old_id -> new_id mappings.

    Args:
        ctx: Fork context

    Returns:
        Number of notes forked
    """
    from opencontractserver.annotations.models import Note

    # Get notes for documents in the source corpus
    old_notes = Note.objects.filter(
        document_id__in=list(ctx.doc_map.keys())
    ).order_by("created")  # Process parents first

    count = 0
    for old_note in old_notes:
        try:
            # Get new document ID
            new_doc_id = ctx.doc_map.get(old_note.document_id)
            if not new_doc_id:
                continue

            # Get new parent note ID
            new_parent_id = None
            if old_note.parent_id:
                new_parent_id = ctx.note_map.get(old_note.parent_id)

            # Get new annotation ID
            new_ann_id = None
            if old_note.annotation_id:
                new_ann_id = ctx.annotation_map.get(old_note.annotation_id)

            new_note = Note(
                title=f"[FORK] {old_note.title}",
                content=old_note.content,
                parent_id=new_parent_id,
                corpus_id=ctx.target_corpus_id,
                document_id=new_doc_id,
                annotation_id=new_ann_id,
                is_public=old_note.is_public,
                creator_id=ctx.user_id,
            )
            # Use skip_revision to avoid creating revision during fork
            new_note.save(skip_revision=True)

            ctx.note_map[old_note.id] = new_note.id
            count += 1

        except Exception as e:
            logger.error(f"Error forking note {old_note.id}: {e}")

    ctx.notes_forked = count
    logger.info(f"Forked {count} notes")
    return count


def fork_note_revisions(ctx: ForkContext) -> int:
    """
    Fork note revisions from forked notes.

    Args:
        ctx: Fork context

    Returns:
        Number of note revisions forked
    """
    from opencontractserver.annotations.models import NoteRevision

    if not ctx.note_map:
        return 0

    count = 0
    for old_note_id, new_note_id in ctx.note_map.items():
        old_revisions = NoteRevision.objects.filter(note_id=old_note_id).order_by(
            "version"
        )

        for old_rev in old_revisions:
            try:
                new_rev = NoteRevision(
                    note_id=new_note_id,
                    author_id=ctx.user_id,
                    version=old_rev.version,
                    diff=old_rev.diff,
                    snapshot=old_rev.snapshot,
                    checksum_base=old_rev.checksum_base,
                    checksum_full=old_rev.checksum_full,
                )
                new_rev.save()
                count += 1

            except Exception as e:
                logger.error(f"Error forking note revision {old_rev.id}: {e}")

    logger.info(f"Forked {count} note revisions")
    return count
