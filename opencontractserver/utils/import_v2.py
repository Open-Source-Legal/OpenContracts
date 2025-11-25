"""
Import utilities for V2 corpus import format.

Handles import of new features added since original import design:
- Structural annotation sets (with deduplication)
- Corpus folders (reconstruct hierarchy)
- DocumentPath version trees (preserve history)
- Relationships (with ID mapping)
- Agent configurations
- Markdown descriptions with revisions
- Conversations and messages (optional)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.utils import timezone

from opencontractserver.annotations.models import (
    Annotation,
    Relationship,
    StructuralAnnotationSet,
)
from opencontractserver.corpuses.models import (
    Corpus,
    CorpusDescriptionRevision,
    CorpusFolder,
)
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.types.dicts import (
    AgentConfigExport,
    CorpusFolderExport,
    DescriptionRevisionExport,
    DocumentPathExport,
    OpenContractsRelationshipPythonType,
    StructuralAnnotationSetExport,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

User = get_user_model()


def import_structural_annotation_set(
    struct_data: StructuralAnnotationSetExport,
    label_lookup: dict,
    user_obj: User,
) -> StructuralAnnotationSet | None:
    """
    Import or retrieve existing StructuralAnnotationSet.

    Uses content_hash for deduplication - if a set with this hash already exists,
    returns it instead of creating a new one.

    Args:
        struct_data: StructuralAnnotationSetExport dict
        label_lookup: Mapping of label text to AnnotationLabel instances
        user_obj: User performing the import

    Returns:
        StructuralAnnotationSet instance or None on error
    """
    try:
        content_hash = struct_data["content_hash"]

        # Check if this structural set already exists
        existing_set = StructuralAnnotationSet.objects.filter(
            content_hash=content_hash
        ).first()

        if existing_set:
            logger.info(f"Structural set {content_hash} already exists, reusing it")
            return existing_set

        logger.info(f"Creating new structural annotation set {content_hash}")

        # Create files
        pawls_file = None
        if struct_data.get("pawls_file_content"):
            pawls_content = json.dumps(struct_data["pawls_file_content"]).encode(
                "utf-8"
            )
            pawls_file = ContentFile(pawls_content, name="pawls_tokens.json")

        txt_file = None
        if struct_data.get("txt_content"):
            txt_content = struct_data["txt_content"].encode("utf-8")
            txt_file = ContentFile(txt_content, name="extracted_text.txt")

        # Create StructuralAnnotationSet
        struct_set = StructuralAnnotationSet.objects.create(
            content_hash=content_hash,
            parser_name=struct_data.get("parser_name"),
            parser_version=struct_data.get("parser_version"),
            page_count=struct_data.get("page_count"),
            token_count=struct_data.get("token_count"),
            pawls_parse_file=pawls_file,
            txt_extract_file=txt_file,
            creator=user_obj,
        )

        # Build annotation ID mapping (old export ID -> new DB ID)
        annot_id_map = {}

        # Create structural annotations
        for annot_data in struct_data.get("structural_annotations", []):
            label_text = annot_data.get("annotationLabel", "")
            label_obj = label_lookup.get(label_text)

            if not label_obj:
                logger.warning(
                    f"Label '{label_text}' not found in lookup, skipping annotation"
                )
                continue

            old_id = annot_data.get("id")

            annot = Annotation.objects.create(
                structural_set=struct_set,
                annotation_label=label_obj,
                raw_text=annot_data.get("rawText", ""),
                page=annot_data.get("page", 0),
                json=annot_data.get("annotation_json", {}),
                annotation_type=annot_data.get("annotation_type", ""),
                structural=True,
                creator=user_obj,
            )

            if old_id:
                annot_id_map[str(old_id)] = annot.id

        # Second pass: set parent relationships
        for annot_data in struct_data.get("structural_annotations", []):
            old_id = annot_data.get("id")
            parent_old_id = annot_data.get("parent_id")

            if old_id and parent_old_id and str(parent_old_id) in annot_id_map:
                new_id = annot_id_map[str(old_id)]
                parent_new_id = annot_id_map[str(parent_old_id)]

                annot = Annotation.objects.get(id=new_id)
                annot.parent_id = parent_new_id
                annot.save(update_fields=["parent"])

        # Create structural relationships
        for rel_data in struct_data.get("structural_relationships", []):
            label_text = rel_data.get("relationshipLabel", "")
            label_obj = label_lookup.get(label_text)

            if not label_obj:
                logger.warning(f"Relationship label '{label_text}' not found, skipping")
                continue

            # Map old annotation IDs to new ones
            source_ids = [
                annot_id_map.get(str(old_id))
                for old_id in rel_data.get("source_annotation_ids", [])
                if str(old_id) in annot_id_map
            ]
            target_ids = [
                annot_id_map.get(str(old_id))
                for old_id in rel_data.get("target_annotation_ids", [])
                if str(old_id) in annot_id_map
            ]

            if source_ids and target_ids:
                rel = Relationship.objects.create(
                    structural_set=struct_set,
                    relationship_label=label_obj,
                    structural=True,
                    creator=user_obj,
                )
                rel.source_annotations.set(source_ids)
                rel.target_annotations.set(target_ids)

        logger.info(f"Created structural set {content_hash} with annotations")
        return struct_set

    except Exception as e:
        logger.error(f"Error importing structural annotation set: {e}")
        return None


def import_corpus_folders(
    folders_data: list[CorpusFolderExport],
    corpus: Corpus,
    user_obj: User,
) -> dict[str, CorpusFolder]:
    """
    Import corpus folder hierarchy.

    Reconstructs tree structure from flat list with parent references.

    Args:
        folders_data: List of CorpusFolderExport dicts
        corpus: Target Corpus instance
        user_obj: User performing import

    Returns:
        Mapping of export IDs to created CorpusFolder instances
    """
    folder_map = {}

    try:
        # Sort folders by path depth (ensures parents created before children)
        sorted_folders = sorted(folders_data, key=lambda f: f["path"].count("/"))

        for folder_data in sorted_folders:
            export_id = folder_data["id"]

            # Get parent folder if specified
            parent_folder = None
            parent_export_id = folder_data.get("parent_id")
            if parent_export_id and parent_export_id in folder_map:
                parent_folder = folder_map[parent_export_id]

            # Create folder
            folder = CorpusFolder.objects.create(
                corpus=corpus,
                name=folder_data["name"],
                description=folder_data.get("description", ""),
                color=folder_data.get("color", "#05313d"),
                icon=folder_data.get("icon", "folder"),
                tags=folder_data.get("tags", []),
                is_public=folder_data.get("is_public", False),
                parent=parent_folder,
                creator=user_obj,
            )

            folder_map[export_id] = folder
            logger.info(f"Created folder: {folder.get_path()}")

    except Exception as e:
        logger.error(f"Error importing folders: {e}")

    return folder_map


def import_document_paths(
    paths_data: list[DocumentPathExport],
    corpus: Corpus,
    document_map: dict[str, Document],
    folder_map: dict[str, CorpusFolder],
    user_obj: User,
) -> None:
    """
    Import DocumentPath version trees.

    Reconstructs complete version history preserving parent relationships.

    Args:
        paths_data: List of DocumentPathExport dicts
        corpus: Target Corpus instance
        document_map: Mapping of document references to Document instances
        folder_map: Mapping of folder paths to CorpusFolder instances
        user_obj: User performing import
    """
    try:
        # Sort by path and version number to ensure proper order
        sorted_paths = sorted(
            paths_data, key=lambda p: (p["path"], p["version_number"])
        )

        # Track created paths for parent lookup
        path_map = {}  # (path, version_number) -> DocumentPath

        for path_data in sorted_paths:
            doc_ref = path_data["document_ref"]
            document = document_map.get(doc_ref)

            if not document:
                logger.warning(f"Document {doc_ref} not found, skipping path")
                continue

            # Get folder if specified
            folder = None
            folder_path = path_data.get("folder_path")
            if folder_path:
                # Find folder by path
                folder = (
                    CorpusFolder.objects.filter(corpus=corpus)
                    .filter(
                        # Match by reconstructing path
                    )
                    .first()
                )
                # Simplified: use folder_map if we have exact match
                for fpath, fobj in folder_map.items():
                    if fobj.get_path() == folder_path:
                        folder = fobj
                        break

            # Get parent DocumentPath if specified
            parent_path = None
            parent_version = path_data.get("parent_version_number")
            if parent_version is not None:
                path_key = (path_data["path"], parent_version)
                parent_path = path_map.get(path_key)

            # Create DocumentPath
            doc_path = DocumentPath.objects.create(
                document=document,
                corpus=corpus,
                folder=folder,
                path=path_data["path"],
                version_number=path_data["version_number"],
                parent=parent_path,
                is_current=path_data.get("is_current", True),
                is_deleted=path_data.get("is_deleted", False),
                creator=user_obj,
            )

            # Track for parent lookup
            path_key = (path_data["path"], path_data["version_number"])
            path_map[path_key] = doc_path

            logger.info(
                f"Created DocumentPath: {doc_path.path} v{doc_path.version_number}"
            )

    except Exception as e:
        logger.error(f"Error importing document paths: {e}")


def import_relationships(
    relationships_data: list[OpenContractsRelationshipPythonType],
    corpus: Corpus,
    document_map: dict[str, Document],
    annot_id_map: dict[str, int],
    label_lookup: dict,
    user_obj: User,
) -> None:
    """
    Import relationships with ID mapping.

    Args:
        relationships_data: List of relationship dicts
        corpus: Target Corpus instance
        document_map: Mapping of document references to Documents
        annot_id_map: Mapping of old annotation IDs to new IDs
        label_lookup: Mapping of label text to AnnotationLabel instances
        user_obj: User performing import
    """
    try:
        for rel_data in relationships_data:
            label_text = rel_data.get("relationshipLabel", "")
            label_obj = label_lookup.get(label_text)

            if not label_obj:
                logger.warning(f"Relationship label '{label_text}' not found")
                continue

            # Skip structural relationships (handled by structural sets)
            if rel_data.get("structural"):
                continue

            # Map annotation IDs
            source_ids = [
                annot_id_map.get(str(old_id))
                for old_id in rel_data.get("source_annotation_ids", [])
                if str(old_id) in annot_id_map
            ]
            target_ids = [
                annot_id_map.get(str(old_id))
                for old_id in rel_data.get("target_annotation_ids", [])
                if str(old_id) in annot_id_map
            ]

            if source_ids and target_ids:
                # Get document from first source annotation
                from opencontractserver.annotations.models import Annotation

                first_source_annot = Annotation.objects.get(id=source_ids[0])
                document = first_source_annot.document

                rel = Relationship.objects.create(
                    corpus=corpus,
                    document=document,
                    relationship_label=label_obj,
                    structural=False,
                    creator=user_obj,
                )
                rel.source_annotations.set(source_ids)
                rel.target_annotations.set(target_ids)

                logger.info(f"Created relationship with label '{label_text}'")

    except Exception as e:
        logger.error(f"Error importing relationships: {e}")


def import_agent_config(
    agent_config: AgentConfigExport,
    corpus: Corpus,
) -> None:
    """
    Import agent configuration.

    Args:
        agent_config: AgentConfigExport dict
        corpus: Target Corpus instance
    """
    try:
        corpus.corpus_agent_instructions = agent_config.get("corpus_agent_instructions")
        corpus.document_agent_instructions = agent_config.get(
            "document_agent_instructions"
        )
        corpus.save(
            update_fields=[
                "corpus_agent_instructions",
                "document_agent_instructions",
                "modified",
            ]
        )
        logger.info("Imported agent configuration")
    except Exception as e:
        logger.error(f"Error importing agent config: {e}")


def import_md_description_revisions(
    md_description: str | None,
    revisions_data: list[DescriptionRevisionExport],
    corpus: Corpus,
    user_obj: User,
) -> None:
    """
    Import markdown description and revision history.

    Args:
        md_description: Current markdown description content
        revisions_data: List of revision dicts
        corpus: Target Corpus instance
        user_obj: User performing import
    """
    try:
        # Import current description
        if md_description:
            filename = "description.md"
            corpus.md_description.save(
                filename, ContentFile(md_description.encode("utf-8")), save=True
            )

        # Import revision history
        for revision_data in revisions_data:
            # Try to get original author, fall back to import user
            author_email = revision_data.get("author_email", "")
            author = User.objects.filter(email=author_email).first() or user_obj

            # Parse timestamp
            created_str = revision_data.get("created", "")
            created = timezone.now()
            if created_str:
                try:
                    created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                except Exception:
                    pass

            CorpusDescriptionRevision.objects.create(
                corpus=corpus,
                author=author,
                version=revision_data["version"],
                diff=revision_data.get("diff", ""),
                snapshot=revision_data.get("snapshot"),
                checksum_base=revision_data.get("checksum_base", ""),
                checksum_full=revision_data.get("checksum_full", ""),
                created=created,
            )

        logger.info(f"Imported {len(revisions_data)} description revisions")

    except Exception as e:
        logger.error(f"Error importing markdown description: {e}")


def import_conversations(
    conversations_data: list,
    messages_data: list,
    votes_data: list,
    corpus: Corpus,
    user_obj: User,
) -> None:
    """
    Import conversations, messages, and votes.

    Args:
        conversations_data: List of conversation dicts
        messages_data: List of message dicts
        votes_data: List of vote dicts
        corpus: Target Corpus instance
        user_obj: User performing import
    """
    from opencontractserver.conversations.models import (
        ChatMessage,
        Conversation,
        MessageVote,
    )

    try:
        # Build conversation ID mapping
        conv_map = {}

        for conv_data in conversations_data:
            # Get creator user
            creator_email = conv_data.get("creator_email", "")
            creator = User.objects.filter(email=creator_email).first() or user_obj

            # Parse timestamps
            created = datetime.fromisoformat(
                conv_data["created"].replace("Z", "+00:00")
            )
            modified = datetime.fromisoformat(
                conv_data["modified"].replace("Z", "+00:00")
            )

            conv = Conversation.objects.create(
                chat_with_corpus=corpus,
                title=conv_data.get("title", ""),
                conversation_type=conv_data.get("conversation_type", "chat"),
                is_public=conv_data.get("is_public", False),
                creator=creator,
                created_at=created,
                updated_at=modified,
            )

            conv_map[conv_data["id"]] = conv
            logger.info(f"Created conversation: {conv.title}")

        # Build message ID mapping
        msg_map = {}

        for msg_data in messages_data:
            conv_export_id = msg_data.get("conversation_id")
            conversation = conv_map.get(conv_export_id)

            if not conversation:
                logger.warning(f"Conversation {conv_export_id} not found")
                continue

            # Get creator
            creator_email = msg_data.get("creator_email", "")
            creator = User.objects.filter(email=creator_email).first() or user_obj

            created = datetime.fromisoformat(msg_data["created"].replace("Z", "+00:00"))

            message = ChatMessage.objects.create(
                conversation=conversation,
                content=msg_data.get("content", ""),
                msg_type=msg_data.get("msg_type", "HUMAN"),
                state=msg_data.get("state", "completed"),
                agent_type=msg_data.get("agent_type"),
                creator=creator,
                created_at=created,
            )

            msg_map[msg_data["id"]] = message

        # Import votes
        for vote_data in votes_data:
            msg_export_id = vote_data.get("message_id")
            message = msg_map.get(msg_export_id)

            if not message:
                continue

            creator_email = vote_data.get("creator_email", "")
            creator = User.objects.filter(email=creator_email).first() or user_obj

            created = datetime.fromisoformat(
                vote_data["created"].replace("Z", "+00:00")
            )

            MessageVote.objects.create(
                message=message,
                vote_type=vote_data.get("vote_type", "upvote"),
                creator=creator,
                created_at=created,
            )

        logger.info(
            "Imported %d conversations, %d messages, %d votes",
            len(conversations_data),
            len(messages_data),
            len(votes_data),
        )

    except Exception as e:
        logger.error("Error importing conversations: %s", e)
