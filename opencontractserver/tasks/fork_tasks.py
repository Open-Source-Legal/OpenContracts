import logging
from pathlib import Path
from typing import Any, Optional

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction

from config import celery_app
from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
    LabelSet,
    Relationship,
    StructuralAnnotationSet,
)
from opencontractserver.corpuses.models import Corpus, CorpusFolder
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.extracts.models import Column, Datacell, Fieldset
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

# Excellent django logging guidance here: https://docs.python.org/3/howto/logging-cookbook.html
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

User = get_user_model()


@celery_app.task()
def fork_corpus(
    new_corpus_id: str,
    doc_ids: list[str],
    label_set_id: str,
    annotation_ids: list[str],
    folder_ids: list[str],
    relationship_ids: list[str],
    user_id: str,
    metadata_column_ids: Optional[list[str]] = None,
    metadata_datacell_ids: Optional[list[str]] = None,
) -> Optional[str]:

    # Handle None defaults for backward compatibility with queued tasks
    if metadata_column_ids is None:
        metadata_column_ids = []
    if metadata_datacell_ids is None:
        metadata_datacell_ids = []

    logger.info(
        f"Start fork_corpus -----\n\tnew_corpus_id: {new_corpus_id}\n\tdoc_ids: "
        f"{doc_ids}\n\tannotation_ids: {annotation_ids}\n\tmetadata_column_ids: "
        f"{len(metadata_column_ids)}\n\tmetadata_datacell_ids: {len(metadata_datacell_ids)}"
        f"\n\tuser_id: {user_id}"
    )

    # We need reference to corpus model so we can unlock it upon completion
    corpus = Corpus.objects.get(pk=new_corpus_id)

    # Get the User object for operations that need it (e.g., add_document)
    user = User.objects.get(pk=user_id)

    with transaction.atomic():

        try:

            label_map = {}
            doc_map = {}
            label_ids = []

            # Only clone label set if one exists
            if label_set_id:
                try:
                    # Create the label set copy first.
                    old_label_set = LabelSet.objects.get(pk=label_set_id)
                    label_ids = list(
                        old_label_set.annotation_labels.all().values_list(
                            "id", flat=True
                        )
                    )

                    label_set = LabelSet(
                        creator_id=user_id,
                        title=f"[FORK] {old_label_set.title}",
                        description=old_label_set.description,
                    )
                    label_set.save()
                    logger.info(f"Cloned labelset: {label_set}")

                    # If there's an icon... copy it to a new file
                    if old_label_set.icon and old_label_set.icon.name:
                        icon_name = old_label_set.icon.name
                        icon_obj = default_storage.open(icon_name)
                        icon_file = ContentFile(icon_obj.read())
                        logger.info(f"Label set icon name: {Path(icon_name).name}")
                        label_set.icon.save(Path(icon_name).name, icon_file)
                        label_set.save()

                except Exception as e:
                    logger.error(
                        f"ERROR forking label_set for corpus {new_corpus_id}: {e}"
                    )
                    raise e

                # Get old label objs (can't just get these earlier as manytomany
                # values are cleared by django when we call clear(), it seems)
                # Copy labels and add new labels to label_set
                logger.info("Cloning labels")
                try:
                    for old_label in AnnotationLabel.objects.filter(pk__in=label_ids):

                        try:
                            new_label = AnnotationLabel(
                                creator_id=user_id,
                                label_type=old_label.label_type,
                                color=old_label.color,
                                description=old_label.description,
                                icon=old_label.icon,
                                text=old_label.text,
                            )
                            new_label.save()

                            # store map of old id to new id
                            label_map[old_label.id] = new_label.id

                            # Add to new labelset
                            label_set.annotation_labels.add(new_label)

                        except Exception as e:
                            logger.error(
                                f"ERROR - could not fork label for labelset "
                                f"{label_set_id}: {e}"
                            )

                    # Save label_set
                    label_set.save()

                    # Update corpus LabelSet to point to cloned copy of original:
                    corpus.label_set = label_set

                except Exception as e:
                    logger.error(
                        f"ERROR - could not populate labels for labelset "
                        f"{label_set_id}: {e}"
                    )
                    raise e
            else:
                logger.info("No label set to clone - corpus has no label set")

            # ============================================================
            # Clone metadata schema (Fieldset + Columns)
            # ============================================================
            column_map = {}  # old_column_id -> new_column_id

            if metadata_column_ids:
                logger.info(
                    f"Cloning metadata schema with {len(metadata_column_ids)} columns"
                )

                try:
                    # Get the source fieldset from the first column
                    first_column = Column.objects.get(pk=metadata_column_ids[0])
                    old_fieldset = first_column.fieldset

                    # Create new fieldset for the forked corpus
                    new_fieldset = Fieldset(
                        name=f"[FORK] {old_fieldset.name}",
                        description=old_fieldset.description,
                        corpus_id=new_corpus_id,  # Link to new corpus
                        creator_id=user_id,
                    )
                    new_fieldset.save()

                    set_permissions_for_obj_to_user(
                        user_id, new_fieldset, [PermissionTypes.CRUD]
                    )
                    logger.info(f"Created metadata fieldset: {new_fieldset.pk}")

                    # Clone columns (preserve display order)
                    for old_column in Column.objects.filter(
                        pk__in=metadata_column_ids
                    ).order_by("display_order"):
                        new_column = Column(
                            name=old_column.name,
                            fieldset_id=new_fieldset.pk,
                            output_type=old_column.output_type,
                            data_type=old_column.data_type,
                            validation_config=(
                                old_column.validation_config.copy()
                                if old_column.validation_config
                                else None
                            ),
                            is_manual_entry=True,
                            default_value=old_column.default_value,
                            help_text=old_column.help_text,
                            display_order=old_column.display_order,
                            creator_id=user_id,
                            # Extraction fields not needed for metadata columns
                            query=None,
                            match_text=None,
                        )
                        new_column.save()
                        column_map[old_column.pk] = new_column.pk

                        set_permissions_for_obj_to_user(
                            user_id, new_column, [PermissionTypes.CRUD]
                        )
                        logger.info(
                            f"Cloned column {old_column.name} -> {new_column.pk}"
                        )

                except Exception as e:
                    logger.error(f"ERROR cloning metadata schema: {e}")
                    raise e
            else:
                logger.info("No metadata schema to clone")

            # ============================================================
            # Clone folder structure (must be before documents)
            # ============================================================
            folder_map: dict[int, int] = {}  # old_folder_id -> new_folder_id

            logger.info(f"Cloning {len(folder_ids)} folders")
            # Note: with_tree_fields() provides default tree_ordering which ensures parents before children
            for old_folder in CorpusFolder.objects.filter(
                pk__in=folder_ids
            ).with_tree_fields():
                try:
                    new_folder = CorpusFolder(
                        name=old_folder.name,
                        corpus_id=new_corpus_id,
                        description=old_folder.description,
                        color=old_folder.color,
                        icon=old_folder.icon,
                        tags=old_folder.tags.copy() if old_folder.tags else [],
                        is_public=old_folder.is_public,
                        creator_id=user_id,
                        # Map parent to new folder ID (None if root)
                        parent_id=folder_map.get(old_folder.parent_id),
                    )
                    new_folder.save()
                    folder_map[old_folder.pk] = new_folder.pk

                    set_permissions_for_obj_to_user(
                        user_id, new_folder, [PermissionTypes.CRUD]
                    )
                    logger.info(f"Cloned folder {old_folder.name} -> {new_folder.pk}")

                except Exception as e:
                    logger.error(f"ERROR cloning folder {old_folder.pk}: {e}")
                    raise e

            # ============================================================
            # Clone documents
            # ============================================================
            # Track duplicated structural_annotation_sets to preserve sharing
            # (docs with same content hash should share the same set after forking)
            structural_set_map: dict[int, StructuralAnnotationSet] = (
                {}
            )  # old_structural_set_id -> new_structural_set

            for document in Document.objects.filter(pk__in=doc_ids):

                try:
                    logger.info(f"Clone document: {document}")
                    old_id = document.pk

                    # Get original DocumentPath to preserve folder and path
                    original_corpus_id = corpus.parent_id
                    original_path = DocumentPath.objects.filter(
                        corpus_id=original_corpus_id,
                        document_id=old_id,
                        is_current=True,
                        is_deleted=False,
                    ).first()

                    # Map folder to new folder ID
                    target_folder = None
                    original_path_str = None
                    if original_path:
                        original_path_str = original_path.path
                        if original_path.folder_id:
                            new_folder_id = folder_map.get(original_path.folder_id)
                            if new_folder_id:
                                target_folder = CorpusFolder.objects.get(
                                    pk=new_folder_id
                                )

                    # Check if we should reuse an already-duplicated structural_annotation_set
                    add_doc_kwargs: dict[str, Any] = {
                        "title": f"[FORK] {document.title}"
                    }
                    old_struct_set_id = document.structural_annotation_set_id
                    if old_struct_set_id and old_struct_set_id in structural_set_map:
                        # Reuse the already-duplicated set
                        add_doc_kwargs["structural_annotation_set"] = (
                            structural_set_map[old_struct_set_id]
                        )
                        logger.info(
                            f"Reusing duplicated structural_set for doc {old_id}"
                        )

                    # Use add_document to create corpus-isolated copy directly from original.
                    # add_document handles: new version_tree_id, file blob sharing,
                    # source_document provenance, and DocumentPath creation.
                    corpus_doc, status, doc_path = corpus.add_document(
                        document=document,
                        user=user,
                        folder=target_folder,
                        path=original_path_str,
                        **add_doc_kwargs,
                    )

                    # Track the duplicated structural_annotation_set for future docs
                    if (
                        old_struct_set_id
                        and old_struct_set_id not in structural_set_map
                    ):
                        structural_set_map[old_struct_set_id] = (
                            corpus_doc.structural_annotation_set
                        )

                    # Store map of old id to new corpus document id
                    doc_map[old_id] = corpus_doc.pk

                    # Set permissions on the corpus-isolated document
                    set_permissions_for_obj_to_user(
                        user_id, corpus_doc, [PermissionTypes.CRUD]
                    )

                    logger.info(f"Forked document {old_id} -> {corpus_doc.pk}")

                except Exception as e:
                    logger.error(f"ERROR - could not fork document {document}: {e}")
                    raise e

            # Save updated corpus with docs and new LabelSet.
            corpus.save()

            # ============================================================
            # Clone annotations
            # ============================================================
            logger.info("Start Annotations...")
            logger.info(f"Label map: {label_map}")

            annotation_map = {}  # old_annotation_id -> new_annotation_id

            # Fetch annotations and map to new docs, labels and corpus
            for annotation in Annotation.objects.filter(pk__in=annotation_ids):

                try:
                    old_annotation_id = annotation.pk  # Save before clearing
                    logger.info(f"Clone annotation: {annotation}")

                    # Skip annotations without a document reference
                    if not annotation.document_id:
                        logger.warning(
                            f"Skipping annotation {old_annotation_id}: no document_id"
                        )
                        continue

                    # Skip annotations whose document wasn't forked
                    if annotation.document_id not in doc_map:
                        logger.warning(
                            f"Skipping annotation {old_annotation_id}: "
                            f"document {annotation.document_id} not in forked documents"
                        )
                        continue

                    # Copy the annotation, update label and doc object references using our
                    # object maps of old objs to new objs
                    annotation.pk = None
                    annotation.creator_id = user_id
                    annotation.corpus_id = new_corpus_id
                    annotation.document_id = doc_map[annotation.document_id]

                    # Map annotation label if it exists and has a mapping
                    if annotation.annotation_label_id and label_map:
                        annotation.annotation_label_id = label_map.get(
                            annotation.annotation_label_id
                        )
                    else:
                        annotation.annotation_label_id = None

                    annotation.save()

                    # Track mapping for relationship cloning
                    annotation_map[old_annotation_id] = annotation.pk

                    set_permissions_for_obj_to_user(
                        user_id, annotation, [PermissionTypes.CRUD]
                    )

                except Exception as e:
                    logger.error(f"ERROR - could not fork annotation {annotation}: {e}")
                    raise e

            logger.info("Annotations completed...")

            # ============================================================
            # Clone metadata datacells
            # ============================================================
            if metadata_datacell_ids and column_map:
                logger.info(f"Cloning {len(metadata_datacell_ids)} metadata datacells")

                for old_datacell in Datacell.objects.filter(
                    pk__in=metadata_datacell_ids
                ):
                    try:
                        # Map to new document and column
                        new_doc_id = doc_map.get(old_datacell.document_id)
                        new_column_id = column_map.get(old_datacell.column_id)

                        if not new_doc_id or not new_column_id:
                            logger.warning(
                                f"Skipping datacell {old_datacell.pk}: "
                                f"missing doc ({new_doc_id}) or column ({new_column_id}) mapping"
                            )
                            continue

                        new_datacell = Datacell(
                            column_id=new_column_id,
                            document_id=new_doc_id,
                            data=(
                                old_datacell.data.copy() if old_datacell.data else None
                            ),
                            data_definition=old_datacell.data_definition,
                            extract=None,  # Manual metadata has no extract
                            creator_id=user_id,
                            # Don't copy approval status - forked data starts fresh
                            approved_by=None,
                            rejected_by=None,
                            corrected_data=None,
                        )
                        new_datacell.save()

                        set_permissions_for_obj_to_user(
                            user_id, new_datacell, [PermissionTypes.CRUD]
                        )
                        logger.info(
                            f"Cloned datacell {old_datacell.pk} -> {new_datacell.pk}"
                        )

                    except Exception as e:
                        logger.error(f"ERROR cloning datacell {old_datacell.pk}: {e}")
                        raise e

                logger.info("Metadata datacells completed...")
            else:
                logger.info("No metadata datacells to clone")

            # ============================================================
            # Clone relationships
            # ============================================================
            logger.info(f"Cloning {len(relationship_ids)} relationships")

            # Use prefetch_related to avoid N+1 queries when accessing M2M fields
            for old_relationship in Relationship.objects.filter(
                pk__in=relationship_ids
            ).prefetch_related("source_annotations", "target_annotations"):
                try:
                    # Get source and target annotation IDs
                    old_source_ids = list(
                        old_relationship.source_annotations.values_list("id", flat=True)
                    )
                    old_target_ids = list(
                        old_relationship.target_annotations.values_list("id", flat=True)
                    )

                    # Map to new annotation IDs (skip if mapping is missing)
                    new_source_ids = [
                        annotation_map[old_id]
                        for old_id in old_source_ids
                        if old_id in annotation_map
                    ]
                    new_target_ids = [
                        annotation_map[old_id]
                        for old_id in old_target_ids
                        if old_id in annotation_map
                    ]

                    # Only create relationship if we have BOTH source and target mappings
                    # A relationship with only source OR only target is invalid
                    if not new_source_ids or not new_target_ids:
                        logger.warning(
                            f"Skipping relationship {old_relationship.pk}: "
                            f"missing {'source' if not new_source_ids else 'target'} annotations"
                        )
                        continue

                    # Map document and label
                    new_doc_id = None
                    if old_relationship.document_id:
                        new_doc_id = doc_map.get(old_relationship.document_id)

                    new_label_id = None
                    if old_relationship.relationship_label_id:
                        new_label_id = label_map.get(
                            old_relationship.relationship_label_id
                        )

                    # Create new relationship
                    new_relationship = Relationship(
                        creator_id=user_id,
                        corpus_id=new_corpus_id,
                        document_id=new_doc_id,
                        relationship_label_id=new_label_id,
                    )
                    new_relationship.save()

                    # Set M2M relationships
                    if new_source_ids:
                        new_relationship.source_annotations.set(new_source_ids)
                    if new_target_ids:
                        new_relationship.target_annotations.set(new_target_ids)

                    set_permissions_for_obj_to_user(
                        user_id, new_relationship, [PermissionTypes.CRUD]
                    )

                    logger.info(
                        f"Cloned relationship {old_relationship.pk} -> {new_relationship.pk}"
                    )

                except Exception as e:
                    logger.error(
                        f"ERROR cloning relationship {old_relationship.pk}: {e}"
                    )
                    raise e

            logger.info("Relationships completed...")

            # Unlock the corpus
            corpus.backend_lock = False
            corpus.save()

            return corpus.id

        except Exception as e:
            logger.error(f"ERROR - Unable to fork corpus: {e}")
            corpus.backend_lock = False
            corpus.error = True
            corpus.save()
            return None
