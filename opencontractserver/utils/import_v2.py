"""
Import utilities for V2 corpus import format.

Handles import of new features added since original import design:
- Structural annotation sets (with deduplication)
- Corpus folders (reconstruct hierarchy)
- Agent configurations
- Markdown descriptions with revisions
- Conversations and messages (optional)

Note: DocumentPath creation is handled by corpus.add_document() and
corpus-level relationship import is handled by _import_v2_relationships
in import_tasks_v2.py.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.utils import timezone

if TYPE_CHECKING:
    from opencontractserver.documents.models import Document

from opencontractserver.annotations.models import (
    RELATIONSHIP_LABEL,
    SPAN_LABEL,
    TOKEN_LABEL,
    Annotation,
    Relationship,
    StructuralAnnotationSet,
)
from opencontractserver.corpuses.models import (
    Corpus,
    CorpusDescriptionRevision,
    CorpusFolder,
)
from opencontractserver.types.dicts import (
    AgentConfigExport,
    CorpusFolderExport,
    DescriptionRevisionExport,
    StructuralAnnotationSetExport,
)
from opencontractserver.utils.compact_pawls import compact_pawls_pages

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
            pawls_content = json.dumps(
                compact_pawls_pages(struct_data["pawls_file_content"])
            ).encode("utf-8")
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
            label_obj = label_lookup.get((label_text, TOKEN_LABEL)) or label_lookup.get(
                (label_text, SPAN_LABEL)
            )

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
            label_obj = label_lookup.get((label_text, RELATIONSHIP_LABEL))

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
    Uses DocumentFolderService.create_folder() for folder creation.

    Args:
        folders_data: List of CorpusFolderExport dicts
        corpus: Target Corpus instance
        user_obj: User performing import

    Returns:
        Mapping of export IDs to created CorpusFolder instances
    """
    from opencontractserver.corpuses.folder_service import DocumentFolderService

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

            # Create folder using service
            folder, error = DocumentFolderService.create_folder(
                user=user_obj,
                corpus=corpus,
                name=folder_data["name"],
                parent=parent_folder,
                description=folder_data.get("description", ""),
                color=folder_data.get("color", "#05313d"),
                icon=folder_data.get("icon", "folder"),
                tags=folder_data.get("tags", []),
                is_public=folder_data.get("is_public", False),
            )

            if error:
                logger.error(f"Error creating folder {folder_data['name']}: {error}")
                continue

            folder_map[export_id] = folder
            logger.info(f"Created folder: {folder.get_path()}")

    except Exception as e:
        logger.error(f"Error importing folders: {e}")

    return folder_map


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
    doc_filename_to_doc: dict[str, Document] | None = None,
    annot_old_id_to_new_pk: dict[str | int, int] | None = None,
) -> None:
    """
    Import markdown description and revision history.

    If ``doc_filename_to_doc`` and/or ``annot_old_id_to_new_pk`` are provided,
    ``oc-import://`` placeholder links in the current ``md_description`` are
    rewritten to live URLs that reference the imported documents and
    annotations.  Revision snapshots / diffs are intentionally left untouched
    because their ``checksum_base`` / ``checksum_full`` fields refer to that
    historical content; rewriting would invalidate the chain.  Bulk-import
    authors only write the current README, so this is a deliberate scope
    choice — see ``utils/caml_rewrite.py``.

    Args:
        md_description: Current markdown description content
        revisions_data: List of revision dicts
        corpus: Target Corpus instance
        user_obj: User performing import
        doc_filename_to_doc: Optional mapping of zip filename to imported
            Document instance.  Used to rewrite document references.
        annot_old_id_to_new_pk: Optional mapping of old annotation id (string
            or int, as in ``data.json``) to new annotation pk.  Used to
            rewrite annotation references.
    """
    try:
        # Rewrite oc-import:// links if maps are supplied (bulk-import path).
        if md_description and (doc_filename_to_doc or annot_old_id_to_new_pk):
            from opencontractserver.utils.caml_rewrite import rewrite_oc_import_links

            # Stats are already logged inside rewrite_oc_import_links and the
            # import task has no caller to surface them to, so we discard the
            # tuple's second element here.
            md_description, _stats = rewrite_oc_import_links(
                content=md_description,
                corpus=corpus,
                doc_filename_to_doc=doc_filename_to_doc or {},
                annot_old_id_to_new_pk=annot_old_id_to_new_pk or {},
            )

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
    doc_hash_to_doc: dict | None = None,
) -> None:
    """
    Import conversations, messages, and votes.

    Handles:
    - Corpus-level and document-level conversations
    - Preserving original timestamps (auto_now_add fields are patched post-create)
    - Threaded replies via parent_message re-linking
    - Message data (JSON) field

    Args:
        conversations_data: List of conversation dicts
        messages_data: List of message dicts
        votes_data: List of vote dicts
        corpus: Target Corpus instance
        user_obj: User performing import
        doc_hash_to_doc: Optional mapping of document hash strings to imported
            Document instances, used to re-link document-level conversations.
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

            # Determine corpus vs document linkage
            chat_with_corpus = (
                corpus if conv_data.get("chat_with_corpus", True) else None
            )
            chat_with_document = None
            doc_hash = conv_data.get("chat_with_document_hash")
            if doc_hash_to_doc and doc_hash:
                chat_with_document = doc_hash_to_doc.get(doc_hash)

            conv = Conversation.objects.create(
                chat_with_corpus=chat_with_corpus,
                chat_with_document=chat_with_document,
                title=conv_data.get("title", ""),
                description=conv_data.get("description", ""),
                conversation_type=conv_data.get("conversation_type", "chat"),
                is_public=conv_data.get("is_public", False),
                is_locked=conv_data.get("is_locked", False),
                is_pinned=conv_data.get("is_pinned", False),
                creator=creator,
            )

            # Patch auto_now_add / auto_now timestamps using QuerySet.update()
            # to bypass the auto_now behavior that ignores values in create().
            timestamp_updates = {}
            if "created" in conv_data:
                timestamp_updates["created_at"] = datetime.fromisoformat(
                    conv_data["created"].replace("Z", "+00:00")
                )
            if "modified" in conv_data:
                timestamp_updates["updated_at"] = datetime.fromisoformat(
                    conv_data["modified"].replace("Z", "+00:00")
                )
            if timestamp_updates:
                Conversation.all_objects.filter(pk=conv.pk).update(**timestamp_updates)

            conv_map[conv_data["id"]] = conv
            logger.info(f"Created conversation: {conv.title}")

        # Build message ID mapping — two passes:
        # Pass 1: create all messages (without parent links)
        # Pass 2: re-link parent_message references
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

            message = ChatMessage.objects.create(
                conversation=conversation,
                content=msg_data.get("content", ""),
                msg_type=msg_data.get("msg_type", "HUMAN"),
                state=msg_data.get("state", "completed"),
                agent_type=msg_data.get("agent_type"),
                data=msg_data.get("data"),
                creator=creator,
            )

            # Patch auto_now_add timestamp
            if "created" in msg_data:
                created_ts = datetime.fromisoformat(
                    msg_data["created"].replace("Z", "+00:00")
                )
                ChatMessage.all_objects.filter(pk=message.pk).update(
                    created_at=created_ts
                )

            msg_map[msg_data["id"]] = message

        # Pass 2: Re-link parent_message references
        messages_to_update = []
        for msg_data in messages_data:
            parent_id = msg_data.get("parent_message_id")
            if parent_id:
                message = msg_map.get(msg_data["id"])
                parent = msg_map.get(parent_id)
                if message and parent:
                    message.parent_message = parent
                    messages_to_update.append(message)
        if messages_to_update:
            ChatMessage.objects.bulk_update(messages_to_update, ["parent_message"])

        # Import votes
        for vote_data in votes_data:
            msg_export_id = vote_data.get("message_id")
            message = msg_map.get(msg_export_id)

            if not message:
                continue

            creator_email = vote_data.get("creator_email", "")
            creator = User.objects.filter(email=creator_email).first() or user_obj

            vote = MessageVote.objects.create(
                message=message,
                vote_type=vote_data.get("vote_type", "upvote"),
                creator=creator,
            )

            # Patch auto_now_add timestamp.
            # Note: MessageVote uses .objects (not .all_objects) because it has
            # no soft-delete support — its default manager is unfiltered.
            if "created" in vote_data:
                created_ts = datetime.fromisoformat(
                    vote_data["created"].replace("Z", "+00:00")
                )
                MessageVote.objects.filter(pk=vote.pk).update(created_at=created_ts)

        logger.info(
            "Imported %d conversations, %d messages, %d votes",
            len(conversations_data),
            len(messages_data),
            len(votes_data),
        )

    except Exception as e:
        logger.error("Error importing conversations: %s", e)
