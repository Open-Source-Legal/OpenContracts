"""
Import tasks for corpus import with V2 format support.

Handles backward compatibility with V1 format while supporting all V2 features.
Uses shared helpers from utils/importing.py for DRY document/label/annotation
creation, and corpus.add_document() for proper corpus isolation.
"""

from __future__ import annotations

import json
import logging
import zipfile
from typing import TYPE_CHECKING, Any

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from config import celery_app
from opencontractserver.annotations.models import (
    RELATIONSHIP_LABEL,
    Annotation,
    AnnotationLabel,
    LabelSet,
    Relationship,
    StructuralAnnotationSet,
)
from opencontractserver.corpuses.models import Corpus, TemporaryFileHandle
from opencontractserver.documents.models import (
    Document,
    IngestionSource,
    IngestionSourceCategory,
)
from opencontractserver.types.dicts import (
    DocumentPathExport,
    IngestionSourceExport,
    OpenContractsExportDataJsonPythonType,
    OpenContractsExportDataJsonV2Type,
    OpenContractsRelationshipPythonType,
)
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.import_v2 import (
    import_agent_config,
    import_conversations,
    import_corpus_folders,
    import_md_description_revisions,
    import_structural_annotation_set,
)
from opencontractserver.utils.importing import (
    create_document_from_export_data,
    import_doc_annotations,
    prepare_import_labels,
)
from opencontractserver.utils.packaging import (
    unpack_corpus_from_export,
    unpack_label_set_from_export,
)
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

User = get_user_model()


@celery_app.task()
def import_corpus_v2(
    temporary_file_handle_id: str | int,
    user_id: int,
    seed_corpus_id: int | None,
) -> int | None:
    """
    Import corpus with support for both V1 and V2 export formats.

    Detects format version from data.json and routes to appropriate handler.
    Both formats share the same core logic via _import_corpus(); V2 adds
    structural sets, folders, relationships, agent config, etc.

    Args:
        temporary_file_handle_id: ID of TemporaryFileHandle with ZIP
        user_id: User performing import
        seed_corpus_id: Optional corpus ID to merge into

    Returns:
        Corpus ID on success, None on failure
    """
    try:
        logger.info("import_corpus_v2() - for user_id: %s", user_id)

        temporary_file_handle = TemporaryFileHandle.objects.get(
            id=temporary_file_handle_id
        )
        user_obj = User.objects.get(id=user_id)

        with temporary_file_handle.file.open("rb") as import_file, zipfile.ZipFile(
            import_file, mode="r"
        ) as import_zip:
            files = import_zip.namelist()
            logger.info("import_corpus_v2() - Files in ZIP: %s", len(files))

            if "data.json" not in files:
                logger.error("import_corpus_v2() - data.json not found in ZIP")
                return None

            # Load data.json
            with import_zip.open("data.json") as corpus_data:
                data_json = json.loads(corpus_data.read().decode("UTF-8"))

            # Detect version - both share the unified import path
            version = data_json.get("version", "1.0")
            logger.info("Detected export format version: %s", version)

            return _import_corpus(
                data_json, import_zip, user_obj, seed_corpus_id, version
            )

    except Exception as e:
        logger.error("import_corpus_v2() - Exception: %s", e, exc_info=True)
        return None


def _setup_corpus_and_labels(
    data_json: (
        OpenContractsExportDataJsonPythonType | OpenContractsExportDataJsonV2Type
    ),
    user_obj: AbstractBaseUser,
    seed_corpus_id: int | None,
) -> tuple[
    Corpus,
    LabelSet,
    dict[str, AnnotationLabel],
    dict[str, AnnotationLabel],
]:
    """
    Shared setup for both V1 and V2 imports: create labelset, corpus, and labels.

    Returns:
        Tuple of (corpus_obj, labelset_obj, label_lookup, doc_label_lookup)
    """
    label_set_data = {**data_json["label_set"]}
    label_set_data.pop("id", None)

    labelset_obj = unpack_label_set_from_export(label_set_data, user_obj)
    logger.info("LabelSet created: %s", labelset_obj)

    corpus_data = {**data_json["corpus"]}
    corpus_data.pop("id", None)

    corpus_obj = unpack_corpus_from_export(
        data=corpus_data,
        user=user_obj,
        label_set_id=labelset_obj.id,
        corpus_id=seed_corpus_id if seed_corpus_id else None,
    )
    logger.info("Created corpus: %s", corpus_obj)

    label_lookup, doc_label_lookup = prepare_import_labels(
        data_json, user_obj.id, labelset_obj
    )

    return corpus_obj, labelset_obj, label_lookup, doc_label_lookup


def _import_document_with_annotations(
    doc_filename: str,
    doc_data: dict[str, Any],
    import_zip: zipfile.ZipFile,
    user_obj: AbstractBaseUser,
    corpus_obj: Corpus,
    label_lookup: dict[str, AnnotationLabel],
    doc_label_lookup: dict[str, AnnotationLabel],
    structural_sets: dict[str, StructuralAnnotationSet] | None = None,
) -> tuple[Document | None, dict[str, int]]:
    """
    Import a single document into a corpus, handling:
    - Document creation (standalone) via shared create_document_from_export_data
    - Adding to corpus via corpus.add_document() (creates corpus-isolated copy)
    - Importing all annotations onto the corpus copy via shared import_doc_annotations

    Args:
        doc_filename: The filename of the document in the ZIP.
        doc_data: The document data dict from the export.
        import_zip: The open ZIP file.
        user_obj: The importing user.
        corpus_obj: The target corpus.
        label_lookup: Combined label lookup.
        doc_label_lookup: Doc-type label lookup.
        structural_sets: Optional mapping of content_hash -> StructuralAnnotationSet
            (V2 only).

    Returns:
        Tuple of (corpus_doc, annot_id_map) where corpus_doc is the
        corpus-isolated document copy and annot_id_map maps old annotation IDs
        to new PKs. Returns (None, {}) on failure.
    """
    try:
        with import_zip.open(doc_filename) as pdf_file_handle:
            # Check for structural annotation set (V2 feature)
            structural_set = None
            struct_hash = doc_data.get("structural_set_hash")
            if structural_sets and struct_hash and struct_hash in structural_sets:
                structural_set = structural_sets[struct_hash]

            # Create standalone document using shared helper
            doc_obj = create_document_from_export_data(
                doc_data=doc_data,
                pdf_file_handle=pdf_file_handle,
                doc_filename=doc_filename,
                user_obj=user_obj,
            )

            # Attach structural annotation set if present
            if structural_set:
                doc_obj.structural_annotation_set = structural_set
                doc_obj.save(update_fields=["structural_annotation_set"])

            # Add to corpus - creates corpus-isolated copy with DocumentPath
            corpus_doc, _status, _doc_path = corpus_obj.add_document(
                document=doc_obj, user=user_obj
            )

            # Import annotations onto the corpus copy using shared helper
            annot_id_map, _doc_labels_count = import_doc_annotations(
                doc_data=doc_data,
                corpus_doc=corpus_doc,
                corpus_obj=corpus_obj,
                user_id=user_obj.id,
                label_lookup=label_lookup,
                doc_label_lookup=doc_label_lookup,
            )

            # Unlock original document
            doc_obj.backend_lock = False
            doc_obj.save(update_fields=["backend_lock"])

            return corpus_doc, annot_id_map

    except Exception as e:
        logger.error("Error importing document %s: %s", doc_filename, e)
        return None, {}


def _import_corpus(
    data_json: (
        OpenContractsExportDataJsonPythonType | OpenContractsExportDataJsonV2Type
    ),
    import_zip: zipfile.ZipFile,
    user_obj: AbstractBaseUser,
    seed_corpus_id: int | None,
    version: str = "1.0",
) -> int | None:
    """
    Unified import handler for both V1 and V2 formats.

    V1 imports: labels, corpus, documents with annotations.
    V2 imports: all of V1 plus structural sets, folders, relationships,
    agent config, markdown descriptions, and conversations.
    """
    is_v2 = version == "2.0"
    logger.info("Using %s import format", "V2" if is_v2 else "V1")

    try:
        # ===== Shared: Setup corpus, labelset, and labels =====
        corpus_obj, labelset_obj, label_lookup, doc_label_lookup = (
            _setup_corpus_and_labels(data_json, user_obj, seed_corpus_id)
        )

        # Build a (text, label_type)-keyed label lookup for structural
        # annotations and relationships, which reference labels by text
        # rather than PK.  The compound key prevents collisions when
        # different label types share the same text.
        label_lookup_by_text = {
            (label.text, label.label_type): label for label in label_lookup.values()
        }

        # ===== V2 only: Import structural annotation sets =====
        structural_sets: dict[str, StructuralAnnotationSet] = {}
        if is_v2:
            struct_sets_data = data_json.get("structural_annotation_sets", {})
            for content_hash, struct_data in struct_sets_data.items():
                struct_set = import_structural_annotation_set(
                    struct_data, label_lookup_by_text, user_obj
                )
                if struct_set:
                    structural_sets[content_hash] = struct_set
            logger.info("Imported %s structural annotation sets", len(structural_sets))

        # ===== Shared: Import documents =====
        all_annot_id_maps: dict[str, int] = {}  # aggregated old_id -> new_id
        # Track doc_hash -> corpus_doc for DocumentPath reconstruction
        doc_hash_to_corpus_doc: dict[str, Document] = {}

        for doc_filename, doc_data in data_json["annotated_docs"].items():
            logger.info("Importing document: %s", doc_filename)
            corpus_doc, annot_id_map = _import_document_with_annotations(
                doc_filename=doc_filename,
                doc_data=doc_data,
                import_zip=import_zip,
                user_obj=user_obj,
                corpus_obj=corpus_obj,
                label_lookup=label_lookup,
                doc_label_lookup=doc_label_lookup,
                structural_sets=structural_sets if is_v2 else None,
            )

            if corpus_doc:
                all_annot_id_maps.update(annot_id_map)
                # Build hash mapping for DocumentPath reconstruction
                if corpus_doc.pdf_file_hash:
                    doc_hash_to_corpus_doc[corpus_doc.pdf_file_hash] = corpus_doc
                # Also map by filename (fallback when hash is unavailable).
                # The export side uses the same filename as its fallback
                # document_ref in package_document_paths().
                doc_hash_to_corpus_doc[doc_filename] = corpus_doc

        # ===== V2 only: Import additional features =====
        if is_v2:
            # Import folders
            folders_data = data_json.get("folders", [])
            import_corpus_folders(folders_data, corpus_obj, user_obj)

            # Import ingestion sources and reconstruct DocumentPaths
            ingestion_sources_data = data_json.get("ingestion_sources", [])
            source_name_map = _import_ingestion_sources(
                ingestion_sources_data, user_obj
            )

            document_paths_data = data_json.get("document_paths", [])
            if document_paths_data:
                _reconstruct_document_paths(
                    document_paths_data,
                    corpus_obj,
                    doc_hash_to_corpus_doc,
                    source_name_map,
                )

            # Import relationships (corpus-level, non-structural)
            relationships_data = data_json.get("relationships", [])
            if relationships_data:
                _import_v2_relationships(
                    relationships_data,
                    corpus_obj,
                    all_annot_id_maps,
                    label_lookup_by_text,
                    user_obj,
                )

            # Import agent config
            agent_config = data_json.get("agent_config", {})
            if agent_config:
                import_agent_config(agent_config, corpus_obj)

            # Import markdown description
            md_description = data_json.get("md_description")
            md_revisions = data_json.get("md_description_revisions", [])
            if md_description or md_revisions:
                import_md_description_revisions(
                    md_description, md_revisions, corpus_obj, user_obj
                )

            # Import conversations (if present)
            if "conversations" in data_json:
                conversations = data_json.get("conversations", [])
                messages = data_json.get("messages", [])
                votes = data_json.get("message_votes", [])
                import_conversations(
                    conversations,
                    messages,
                    votes,
                    corpus_obj,
                    user_obj,
                    doc_hash_to_doc=doc_hash_to_corpus_doc,
                )

        logger.info("Import completed successfully for corpus %s", corpus_obj.id)
        return corpus_obj.id

    except Exception as e:
        logger.error("Import failed: %s", e, exc_info=True)
        return None


def _import_v2_relationships(
    relationships_data: list[OpenContractsRelationshipPythonType],
    corpus_obj: Corpus,
    annot_id_map: dict[str, int],
    label_lookup: dict[
        tuple[str, str], AnnotationLabel
    ],  # key: (label_text, label_type)
    user_obj: AbstractBaseUser,
) -> None:
    """
    Import V2 corpus-level relationships, skipping structural ones (handled
    by structural annotation sets).

    Infers the document from the first source annotation for each relationship.
    """
    for rel_data in relationships_data:
        # Skip structural relationships (handled by structural sets)
        if rel_data.get("structural"):
            continue

        label_text = rel_data.get("relationshipLabel", "")
        label_obj = label_lookup.get((label_text, RELATIONSHIP_LABEL))
        if not label_obj:
            logger.warning("Relationship label '%s' not found", label_text)
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
            first_source_annot = Annotation.objects.get(id=source_ids[0])
            document = first_source_annot.document

            rel = Relationship.objects.create(
                corpus=corpus_obj,
                document=document,
                relationship_label=label_obj,
                structural=False,
                creator=user_obj,
            )
            rel.source_annotations.set(source_ids)
            rel.target_annotations.set(target_ids)
            set_permissions_for_obj_to_user(user_obj, rel, [PermissionTypes.ALL])


def _import_ingestion_sources(
    sources_data: list[IngestionSourceExport],
    user_obj: AbstractBaseUser,
) -> dict[str, IngestionSource]:
    """
    Import or get-or-create IngestionSource records from exported data.

    Uses get_or_create keyed on (creator, name) so re-importing the same
    corpus doesn't duplicate sources.

    Note: ``get_or_create`` only applies ``source_type``, ``config``, and
    ``active`` on *creation*.  If a source with the same (creator, name)
    already exists locally, its current field values are preserved — the
    export's values are intentionally not applied ("don't clobber local
    changes").  This avoids surprises when a re-import would silently
    reactivate a source the user deactivated, or overwrite a config they
    customised after the initial import.

    Args:
        sources_data: List of IngestionSourceExport dicts from data.json.
        user_obj: The importing user (becomes creator of new sources).

    Returns:
        Mapping of source name -> IngestionSource instance.
    """
    source_map: dict[str, IngestionSource] = {}

    for src in sources_data:
        name = src.get("name")
        if not name:
            continue

        try:
            with transaction.atomic():
                source, created = IngestionSource.objects.get_or_create(
                    creator=user_obj,
                    name=name,
                    defaults={
                        "source_type": src.get(
                            "source_type", IngestionSourceCategory.MANUAL
                        ),
                        "config": src.get("config") or {},
                        "active": src.get("active", True),
                    },
                )
        except IntegrityError as exc:
            logger.debug("IntegrityError on create, falling back to get: %s", exc)
            # Guard the fallback: in the rare case where a concurrent request
            # created-then-deleted the row between the IntegrityError and this
            # .get(), skip the source rather than aborting the entire corpus
            # import with an unhandled DoesNotExist.
            try:
                source = IngestionSource.objects.get(creator=user_obj, name=name)
            except IngestionSource.DoesNotExist:
                logger.warning(
                    "IngestionSource '%s' for user %s vanished between "
                    "IntegrityError and fallback get; skipping.",
                    name,
                    user_obj.id,
                )
                continue
            created = False
        source_map[name] = source

        if created:
            set_permissions_for_obj_to_user(user_obj, source, [PermissionTypes.CRUD])
            logger.debug("Created IngestionSource '%s' for user %s", name, user_obj.id)
        else:
            logger.debug("Reusing existing IngestionSource '%s'", name)

    return source_map


def _reconstruct_document_paths(
    document_paths_data: list[DocumentPathExport],
    corpus_obj: Corpus,
    doc_hash_to_corpus_doc: dict[str, Document],
    source_name_map: dict[str, IngestionSource] | None = None,
) -> None:
    """
    Update DocumentPaths created by corpus.add_document() to match the exported
    path, version_number, folder assignments, and ingestion lineage.

    Only current, non-deleted paths from the export are applied since historical
    versions don't have file content in the export. This ensures the document
    tree structure matches the original corpus.

    Args:
        document_paths_data: List of exported DocumentPath dicts.
        corpus_obj: The target corpus.
        doc_hash_to_corpus_doc: Mapping of document_ref (hash or old ID) to
            the imported corpus-isolated Document.
        source_name_map: Mapping of source name -> IngestionSource instance
            (from _import_ingestion_sources).
    """
    from opencontractserver.corpuses.models import CorpusFolder
    from opencontractserver.documents.models import DocumentPath

    if source_name_map is None:
        source_name_map = {}

    # Pre-build a folder path lookup to avoid repeated DB queries + linear
    # scans inside the loop.
    all_folders = CorpusFolder.objects.filter(corpus=corpus_obj)
    folder_path_map = {f.get_path(): f for f in all_folders}

    # Pre-build a document -> DocumentPath lookup to avoid N queries in the loop
    path_by_doc_id = {
        p.document_id: p
        for p in DocumentPath.objects.filter(
            corpus=corpus_obj, document__in=doc_hash_to_corpus_doc.values()
        )
    }

    for path_data in document_paths_data:
        # Only reconstruct current, non-deleted paths
        if not path_data.get("is_current", True) or path_data.get("is_deleted", False):
            continue

        doc_ref = path_data.get("document_ref")
        corpus_doc = doc_hash_to_corpus_doc.get(doc_ref)
        if not corpus_doc:
            logger.debug(
                "DocumentPath reconstruction: no matching doc for ref %s", doc_ref
            )
            continue

        # Find the DocumentPath created by add_document() for this corpus_doc
        existing_path = path_by_doc_id.get(corpus_doc.pk)
        if not existing_path:
            continue

        # Update path and version_number to match export
        updates: dict[str, Any] = {}
        exported_path = path_data.get("path")
        if exported_path and exported_path != existing_path.path:
            updates["path"] = exported_path

        exported_version = path_data.get("version_number")
        if exported_version and exported_version != existing_path.version_number:
            updates["version_number"] = exported_version

        # Update folder assignment if folder_path is specified
        folder_path = path_data.get("folder_path")
        if folder_path:
            folder = folder_path_map.get(folder_path)
            if folder:
                updates["folder"] = folder

        # Restore ingestion lineage fields
        source_name = path_data.get("ingestion_source_name")
        if source_name and source_name in source_name_map:
            updates["ingestion_source"] = source_name_map[source_name]
        elif source_name:
            logger.warning(
                "DocumentPath references unknown ingestion source '%s' "
                "— lineage not restored",
                source_name,
            )

        external_id = path_data.get("external_id")
        if external_id is not None:
            updates["external_id"] = external_id

        # Asymmetry note: export omits ``ingestion_metadata`` entirely when
        # the value is falsy (see ``package_document_paths``), so a missing
        # key here is the expected "empty" signal.  An explicit ``None`` is
        # treated the same as absent — we only restore a dict payload when
        # the exporter actually wrote one.
        ingestion_metadata = path_data.get("ingestion_metadata")
        if ingestion_metadata is not None:
            updates["ingestion_metadata"] = ingestion_metadata

        if updates:
            for key, value in updates.items():
                setattr(existing_path, key, value)
            existing_path.save(update_fields=list(updates.keys()))
            logger.debug("Updated DocumentPath for doc %s: %s", corpus_doc.id, updates)
