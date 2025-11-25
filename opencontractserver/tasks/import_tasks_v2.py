"""
Import tasks for corpus import with V2 format support.

Handles backward compatibility with V1 format while supporting all V2 features.
"""

from __future__ import annotations

import hashlib
import json
import logging
import zipfile

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile, File

from config import celery_app
from opencontractserver.annotations.models import (
    TOKEN_LABEL,
    Annotation,
)
from opencontractserver.corpuses.models import TemporaryFileHandle
from opencontractserver.documents.models import Document
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.import_v2 import (
    import_agent_config,
    import_conversations,
    import_corpus_folders,
    import_document_paths,
    import_md_description_revisions,
    import_relationships,
    import_structural_annotation_set,
)
from opencontractserver.utils.importing import import_annotations, load_or_create_labels
from opencontractserver.utils.packaging import (
    unpack_corpus_from_export,
    unpack_label_set_from_export,
)
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

User = get_user_model()


@celery_app.task()
def import_corpus_v2(
    temporary_file_handle_id: str | int,
    user_id: int,
    seed_corpus_id: int | None,
) -> str | None:
    """
    Import corpus with support for both V1 and V2 export formats.

    Detects format version from data.json and routes to appropriate handler.

    Args:
        temporary_file_handle_id: ID of TemporaryFileHandle with ZIP
        user_id: User performing import
        seed_corpus_id: Optional corpus ID to merge into

    Returns:
        Corpus ID on success, None on failure
    """
    try:
        logger.info(f"import_corpus_v2() - for user_id: {user_id}")

        temporary_file_handle = TemporaryFileHandle.objects.get(
            id=temporary_file_handle_id
        )
        user_obj = User.objects.get(id=user_id)

        with temporary_file_handle.file.open("rb") as import_file, zipfile.ZipFile(
            import_file, mode="r"
        ) as import_zip:
            files = import_zip.namelist()
            logger.info(f"import_corpus_v2() - Files in ZIP: {len(files)}")

            if "data.json" not in files:
                logger.error("import_corpus_v2() - data.json not found in ZIP")
                return None

            # Load data.json
            with import_zip.open("data.json") as corpus_data:
                data_json = json.loads(corpus_data.read().decode("UTF-8"))

            # Detect version
            version = data_json.get("version", "1.0")
            logger.info(f"Detected export format version: {version}")

            if version == "2.0":
                return _import_corpus_v2(
                    data_json, import_zip, user_obj, seed_corpus_id
                )
            else:
                # V1 format - use original import logic
                return _import_corpus_v1(
                    data_json, import_zip, user_obj, seed_corpus_id
                )

    except Exception as e:
        logger.error(f"import_corpus_v2() - Exception: {e}", exc_info=True)
        return None


def _import_corpus_v1(
    data_json: dict,
    import_zip: zipfile.ZipFile,
    user_obj: User,
    seed_corpus_id: int | None,
) -> str | None:
    """
    Import V1 format corpus (original format).

    This is the backward-compatible import path.
    """
    logger.info("Using V1 import format")

    try:
        text_labels = data_json["text_labels"]
        doc_labels = data_json["doc_labels"]
        label_set_data = {**data_json["label_set"]}
        label_set_data.pop("id", None)
        corpus_data_json = {**data_json["corpus"]}
        corpus_data_json.pop("id", None)

        # Create LabelSet
        labelset_obj = unpack_label_set_from_export(label_set_data, user_obj)
        logger.info(f"LabelSet created: {labelset_obj}")

        # Create Corpus
        corpus_kwargs = {
            "data": corpus_data_json,
            "user": user_obj,
            "label_set_id": labelset_obj.id,
            "corpus_id": seed_corpus_id if seed_corpus_id else None,
        }
        corpus_obj = unpack_corpus_from_export(**corpus_kwargs)
        logger.info(f"Created corpus_obj: {corpus_obj}")

        # Load or create labels
        text_label_data_dict = {
            label_name: label_info for label_name, label_info in text_labels.items()
        }
        doc_label_data_dict = {
            label_name: label_info for label_name, label_info in doc_labels.items()
        }

        existing_text_labels = load_or_create_labels(
            user_id=user_obj.id,
            labelset_obj=labelset_obj,
            label_data_dict=text_label_data_dict,
            existing_labels={},
        )

        existing_doc_labels = load_or_create_labels(
            user_id=user_obj.id,
            labelset_obj=labelset_obj,
            label_data_dict=doc_label_data_dict,
            existing_labels={},
        )

        doc_label_lookup = {label.text: label for label in existing_doc_labels.values()}
        label_lookup = {**existing_text_labels, **existing_doc_labels}

        # Import documents
        for doc_filename in data_json["annotated_docs"]:
            logger.info(f"Importing document: {doc_filename}")
            doc_data = data_json["annotated_docs"][doc_filename]

            try:
                with import_zip.open(doc_filename) as pdf_file_handle:
                    pdf_file = File(pdf_file_handle, doc_filename)

                    pawls_parse_file = ContentFile(
                        json.dumps(doc_data["pawls_file_content"]).encode("utf-8"),
                        name="pawls_tokens.json",
                    )

                    txt_extract_file = ContentFile(
                        doc_data["content"].encode("utf-8"),
                        name="extracted_text.txt",
                    )

                    # Create Document
                    doc_obj = Document.objects.create(
                        title=doc_data["title"],
                        description=doc_data.get("description", ""),
                        pdf_file=pdf_file,
                        pawls_parse_file=pawls_parse_file,
                        txt_extract_file=txt_extract_file,
                        backend_lock=True,
                        creator=user_obj,
                        page_count=len(doc_data["pawls_file_content"]),
                    )

                    set_permissions_for_obj_to_user(
                        user_obj, doc_obj, [PermissionTypes.ALL]
                    )

                    # Add to corpus using new versioned system
                    corpus_obj.add_document(doc_obj, user=user_obj)

                    # Import doc-level annotations
                    for doc_label_name in doc_data.get("doc_labels", []):
                        label_obj = doc_label_lookup.get(doc_label_name)
                        if label_obj:
                            Annotation.objects.create(
                                annotation_label=label_obj,
                                document=doc_obj,
                                corpus=corpus_obj,
                                creator=user_obj,
                            )

                    # Import text annotations
                    import_annotations(
                        user_id=user_obj.id,
                        doc_obj=doc_obj,
                        corpus_obj=corpus_obj,
                        annotations_data=doc_data.get("labelled_text", []),
                        label_lookup=label_lookup,
                        label_type=TOKEN_LABEL,
                    )

                    doc_obj.backend_lock = False
                    doc_obj.save()

            except Exception as e:
                logger.error(f"Error importing document {doc_filename}: {e}")

        return corpus_obj.id

    except Exception as e:
        logger.error(f"V1 import failed: {e}", exc_info=True)
        return None


def _import_corpus_v2(
    data_json: dict,
    import_zip: zipfile.ZipFile,
    user_obj: User,
    seed_corpus_id: int | None,
) -> str | None:
    """
    Import V2 format corpus (new comprehensive format).
    """
    logger.info("Using V2 import format")

    try:
        # ===== PART 1: Import LabelSet and Corpus =====
        label_set_data = {**data_json["label_set"]}
        label_set_data.pop("id", None)

        labelset_obj = unpack_label_set_from_export(label_set_data, user_obj)
        logger.info(f"LabelSet created: {labelset_obj}")

        # Import corpus with V2 fields
        corpus_data = {**data_json["corpus"]}
        corpus_data.pop("id", None)

        corpus_obj = unpack_corpus_from_export(
            data=corpus_data,
            user=user_obj,
            label_set_id=labelset_obj.id,
            corpus_id=seed_corpus_id,
        )
        logger.info(f"Created corpus: {corpus_obj}")

        # ===== PART 2: Import Labels =====
        text_labels = data_json["text_labels"]
        doc_labels = data_json["doc_labels"]

        text_label_data_dict = {name: info for name, info in text_labels.items()}
        doc_label_data_dict = {name: info for name, info in doc_labels.items()}

        existing_text_labels = load_or_create_labels(
            user_id=user_obj.id,
            labelset_obj=labelset_obj,
            label_data_dict=text_label_data_dict,
            existing_labels={},
        )

        existing_doc_labels = load_or_create_labels(
            user_id=user_obj.id,
            labelset_obj=labelset_obj,
            label_data_dict=doc_label_data_dict,
            existing_labels={},
        )

        label_lookup = {**existing_text_labels, **existing_doc_labels}
        doc_label_lookup = {label.text: label for label in existing_doc_labels.values()}

        # ===== PART 3: Import Structural Annotation Sets =====
        structural_sets = {}
        struct_sets_data = data_json.get("structural_annotation_sets", {})

        for content_hash, struct_data in struct_sets_data.items():
            struct_set = import_structural_annotation_set(
                struct_data, label_lookup, user_obj
            )
            if struct_set:
                structural_sets[content_hash] = struct_set

        logger.info(f"Imported {len(structural_sets)} structural annotation sets")

        # ===== PART 4: Import Documents =====
        document_map = {}  # document_ref -> Document
        annot_id_map = {}  # old_annot_id -> new_annot_id

        for doc_filename, doc_data in data_json["annotated_docs"].items():
            logger.info(f"Importing document: {doc_filename}")

            try:
                with import_zip.open(doc_filename) as pdf_file_handle:
                    pdf_file = File(pdf_file_handle, doc_filename)

                    # Get structural annotation set if referenced
                    structural_set = None
                    struct_hash = doc_data.get("structural_set_hash")
                    if struct_hash and struct_hash in structural_sets:
                        structural_set = structural_sets[struct_hash]
                        # Use files from structural set
                        pawls_parse_file = None
                        txt_extract_file = None
                    else:
                        # Inline files (V1 style)
                        pawls_parse_file = ContentFile(
                            json.dumps(doc_data["pawls_file_content"]).encode("utf-8"),
                            name="pawls_tokens.json",
                        )
                        txt_extract_file = ContentFile(
                            doc_data["content"].encode("utf-8"),
                            name="extracted_text.txt",
                        )

                    # Create Document
                    doc_obj = Document.objects.create(
                        title=doc_data["title"],
                        description=doc_data.get("description", ""),
                        pdf_file=pdf_file,
                        pawls_parse_file=pawls_parse_file,
                        txt_extract_file=txt_extract_file,
                        structural_annotation_set=structural_set,
                        backend_lock=True,
                        creator=user_obj,
                        page_count=doc_data["page_count"],
                    )

                    # Set PDF hash - use structural set content_hash if available,
                    # otherwise calculate from PDF content
                    if not doc_obj.pdf_file_hash:
                        if structural_set:
                            # Use structural set's content hash as document hash
                            doc_obj.pdf_file_hash = structural_set.content_hash
                        else:
                            # Calculate from PDF content
                            doc_obj.pdf_file.open("rb")
                            pdf_content = doc_obj.pdf_file.read()
                            doc_obj.pdf_file_hash = hashlib.md5(pdf_content).hexdigest()
                            doc_obj.pdf_file.close()
                        doc_obj.save()

                    set_permissions_for_obj_to_user(
                        user_obj, doc_obj, [PermissionTypes.ALL]
                    )

                    # Track for DocumentPath import
                    doc_ref = doc_obj.pdf_file_hash or str(doc_obj.id)
                    document_map[doc_ref] = doc_obj

                    # Import doc-level annotations
                    for doc_label_name in doc_data.get("doc_labels", []):
                        label_obj = doc_label_lookup.get(doc_label_name)
                        if label_obj:
                            Annotation.objects.create(
                                annotation_label=label_obj,
                                document=doc_obj,
                                corpus=corpus_obj,
                                creator=user_obj,
                            )

                    # Import text annotations
                    for annot_data in doc_data.get("labelled_text", []):
                        label_text = label_lookup.get(
                            str(annot_data.get("annotationLabel", ""))
                        )
                        if not label_text:
                            continue

                        old_id = annot_data.get("id")

                        annot = Annotation.objects.create(
                            annotation_label=label_text,
                            document=doc_obj,
                            corpus=corpus_obj,
                            raw_text=annot_data.get("rawText", ""),
                            page=annot_data.get("page", 0),
                            json=annot_data.get("annotation_json", {}),
                            annotation_type=annot_data.get("annotation_type", ""),
                            structural=annot_data.get("structural", False),
                            creator=user_obj,
                        )

                        if old_id:
                            annot_id_map[str(old_id)] = annot.id

                    doc_obj.backend_lock = False
                    doc_obj.save()

            except Exception as e:
                logger.error(f"Error importing document {doc_filename}: {e}")

        # ===== PART 5: Import Folders =====
        folders_data = data_json.get("folders", [])
        folder_map = import_corpus_folders(folders_data, corpus_obj, user_obj)

        # ===== PART 6: Import DocumentPaths =====
        paths_data = data_json.get("document_paths", [])
        import_document_paths(
            paths_data, corpus_obj, document_map, folder_map, user_obj
        )

        # ===== PART 7: Import Relationships =====
        relationships_data = data_json.get("relationships", [])
        import_relationships(
            relationships_data,
            corpus_obj,
            document_map,
            annot_id_map,
            label_lookup,
            user_obj,
        )

        # ===== PART 8: Import Agent Config =====
        agent_config = data_json.get("agent_config", {})
        if agent_config:
            import_agent_config(agent_config, corpus_obj)

        # ===== PART 9: Import Markdown Description =====
        md_description = data_json.get("md_description")
        md_revisions = data_json.get("md_description_revisions", [])
        if md_description or md_revisions:
            import_md_description_revisions(
                md_description, md_revisions, corpus_obj, user_obj
            )

        # ===== PART 10: Import Conversations (if present) =====
        if "conversations" in data_json:
            conversations = data_json.get("conversations", [])
            messages = data_json.get("messages", [])
            votes = data_json.get("message_votes", [])
            import_conversations(conversations, messages, votes, corpus_obj, user_obj)

        logger.info(f"V2 import completed successfully for corpus {corpus_obj.id}")
        return corpus_obj.id

    except Exception as e:
        logger.error(f"V2 import failed: {e}", exc_info=True)
        return None
