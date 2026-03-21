from __future__ import annotations

import json
import logging
import mimetypes
from typing import TYPE_CHECKING

from django.core.files.base import ContentFile, File
from django.utils import timezone

if TYPE_CHECKING:
    from opencontractserver.documents.models import Document

from config.graphql.annotation_serializers import AnnotationLabelSerializer
from opencontractserver.annotations.models import (
    DOC_TYPE_LABEL,
    TOKEN_LABEL,
    Annotation,
    AnnotationLabel,
    Relationship,
)
from opencontractserver.types.dicts import (
    OpenContractsAnnotationPythonType,
    OpenContractsRelationshipPythonType,
)
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.compact_pawls import compact_pawls_pages
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

logger = logging.getLogger(__name__)


def load_or_create_labels(
    user_id: int,
    labelset_obj,
    label_data_dict: dict[str, dict],
    existing_labels: dict[str, AnnotationLabel] = {},
) -> dict[str, AnnotationLabel]:
    """
    Load existing labels or create new ones if they don't exist.

    Args:
        user_id (int): The ID of the user.
        labelset_obj: The LabelSet object to which labels should be added.
        label_data_dict (Dict[str, Dict]): Label data mapped by label name.
        existing_labels (Dict[str, AnnotationLabel]): Existing labels.

    Returns:
        Dict[str, AnnotationLabel]: Updated existing labels.
    """
    for label_name, label_data in label_data_dict.items():
        if label_name not in existing_labels:
            logger.info(f"Creating new label: {label_name}")
            label_data = label_data.copy()
            label_data.pop("id", None)
            label_data["creator_id"] = user_id

            label_serializer = AnnotationLabelSerializer(data=label_data)
            label_serializer.is_valid(raise_exception=True)
            label_obj = label_serializer.save()
            set_permissions_for_obj_to_user(user_id, label_obj, [PermissionTypes.ALL])

            if labelset_obj:
                labelset_obj.annotation_labels.add(label_obj)

            existing_labels[label_name] = label_obj
    return existing_labels


def import_annotations(
    user_id: int,
    doc_obj,
    corpus_obj,
    annotations_data: list[OpenContractsAnnotationPythonType],
    label_lookup: dict[str, AnnotationLabel],
    label_type: str = TOKEN_LABEL,
    pawls_data: list[dict] = None,
) -> dict[str | int, int]:
    """
    Import annotations, handling parent relationships, and return a mapping of old IDs
    to newly created Annotation database primary keys.

    Args:
        user_id (int): The ID of the user.
        doc_obj: The Document object to which annotations belong.
        corpus_obj: The Corpus object, if any.
        annotations_data (List[OpenContractsAnnotationPythonType]): List of annotation data.
        label_lookup (Dict[str, AnnotationLabel]): Mapping of label names to AnnotationLabel objects.
        label_type (str): The type of the annotations if not specified in data.
        pawls_data (List[dict]): Optional PAWLs data for extracting image content.
            If provided, annotations with IMAGE modality will have their images
            pre-extracted for faster embedding.

    Returns:
        Dict[Union[str, int], int]: A dictionary mapping the "id" field from each incoming annotation
        (which may be string or int) to the newly created Annotation's DB primary key.
    """
    logger.info(f"Importing annotations with label type: {label_type}")

    old_id_to_new_pk: dict[str | int, int] = {}

    # First pass: Create annotations without parents
    for annotation_data in annotations_data:
        label_name: str = annotation_data["annotationLabel"]
        label_obj = label_lookup.get(label_name)
        if label_obj is None:
            logger.warning(
                f"Skipping annotation: label '{label_name}' not found in label_lookup"
            )
            continue

        # Ensure annotation_type is never None by falling back to label_type
        # if the field is missing or explicitly None
        final_annotation_type = annotation_data.get("annotation_type") or label_type

        annot_obj = Annotation.objects.create(
            raw_text=annotation_data["rawText"],
            page=annotation_data.get("page", 1),
            json=annotation_data["annotation_json"],
            annotation_label=label_obj,
            document=doc_obj,
            corpus=corpus_obj,
            creator_id=user_id,
            annotation_type=final_annotation_type,
            structural=annotation_data.get("structural", False),
            content_modalities=annotation_data.get("content_modalities", []),
        )

        set_permissions_for_obj_to_user(user_id, annot_obj, [PermissionTypes.ALL])

        old_id = annotation_data.get("id")
        if old_id is not None:
            old_id_to_new_pk[old_id] = annot_obj.pk

    # Second pass: Set parent relationships
    for annotation_data in annotations_data:
        old_id = annotation_data.get("id")
        parent_old_id = annotation_data.get("parent_id")
        if parent_old_id is not None and old_id is not None:
            annot_pk = old_id_to_new_pk.get(old_id)
            parent_pk = old_id_to_new_pk.get(parent_old_id)
            if annot_pk and parent_pk:
                annot_obj = Annotation.objects.get(pk=annot_pk)
                parent_annot_obj = Annotation.objects.get(pk=parent_pk)
                annot_obj.parent = parent_annot_obj
                annot_obj.save()

    # Third pass: Extract and store image content for IMAGE modality annotations
    # This pre-extracts images so embedding tasks don't need to reload PAWLs
    if pawls_data and old_id_to_new_pk:
        from opencontractserver.types.enums import ContentModality
        from opencontractserver.utils.multimodal_embeddings import (
            batch_extract_annotation_images,
        )

        # Get all created annotations with IMAGE modality
        created_pks = list(old_id_to_new_pk.values())
        image_annotations = Annotation.objects.filter(
            pk__in=created_pks,
            content_modalities__contains=[ContentModality.IMAGE.value],
        )

        if image_annotations.exists():
            count = batch_extract_annotation_images(list(image_annotations), pawls_data)
            logger.info(f"Pre-extracted images for {count} annotations")

    return old_id_to_new_pk


def import_relationships(
    user_id: int,
    doc_obj,
    corpus_obj,
    relationships_data: list[OpenContractsRelationshipPythonType],
    label_lookup: dict[str, AnnotationLabel],
    annotation_id_map: dict[str | int, int],
) -> dict[str | int, Relationship]:
    """
    Import relationships for the given document and corpus, referencing the
    appropriate Annotation objects using the annotation_id_map (returned from import_annotations),
    and labeling them with the appropriate label from label_lookup.

    Args:
        user_id (int): The ID of the user performing the import.
        doc_obj: The Document to which the relationships belong.
        corpus_obj: The Corpus object, if any.
        relationships_data (List[OpenContractsRelationshipPythonType]): The relationship data to import.
        label_lookup (Dict[str, AnnotationLabel]): Mapping from relationship label names to AnnotationLabel objects.
        annotation_id_map (Dict[Union[str, int], int]): Mapping of 'old' annotation IDs (strings or ints) to
            new DB annotation IDs, as returned from import_annotations.

    Returns:
        Dict[Union[str, int], Relationship]: A dictionary mapping of old relationship IDs to the newly created
                                             Relationship objects.
    """
    logger.info("Importing relationships...")
    old_id_to_new_relationship: dict[str | int, Relationship] = {}

    for relationship_data in relationships_data:
        label_name = relationship_data["relationshipLabel"]
        structural = relationship_data.get("structural", False)
        label_obj = label_lookup.get(label_name)
        if label_obj is None:
            logger.warning(
                f"Skipping relationship: label '{label_name}' not found in label_lookup"
            )
            continue

        new_relationship = Relationship.objects.create(
            relationship_label=label_obj,
            document=doc_obj,
            corpus=corpus_obj,
            creator_id=user_id,
            structural=structural,
        )
        set_permissions_for_obj_to_user(
            user_id, new_relationship, [PermissionTypes.ALL]
        )

        # Map source annotations
        for old_source_id in relationship_data.get("source_annotation_ids", []):
            if old_source_id in annotation_id_map:
                source_annot_obj = Annotation.objects.get(
                    id=annotation_id_map[old_source_id]
                )
                new_relationship.source_annotations.add(source_annot_obj)

        # Map target annotations
        for old_target_id in relationship_data.get("target_annotation_ids", []):
            if old_target_id in annotation_id_map:
                target_annot_obj = Annotation.objects.get(
                    id=annotation_id_map[old_target_id]
                )
                new_relationship.target_annotations.add(target_annot_obj)

        old_rel_id = relationship_data.get("id")
        if old_rel_id is not None:
            old_id_to_new_relationship[old_rel_id] = new_relationship

    logger.info("Finished importing relationships.")
    return old_id_to_new_relationship


def prepare_import_labels(
    data_json: dict,
    user_id: int,
    labelset_obj,
) -> tuple[dict[str, AnnotationLabel], dict[str, AnnotationLabel]]:
    """
    Load or create text and doc labels from export data.json, returning both
    a combined label_lookup (keyed by label ID string) and a doc_label_lookup
    (keyed by label text).

    Args:
        data_json: The parsed data.json from the export ZIP.
        user_id: The ID of the importing user.
        labelset_obj: The LabelSet to associate labels with.

    Returns:
        Tuple of (label_lookup, doc_label_lookup) where:
        - label_lookup: {label_id_string: AnnotationLabel} for all labels
        - doc_label_lookup: {label_text: AnnotationLabel} for doc-type labels only
    """
    text_labels = data_json.get("text_labels", {})
    doc_labels = data_json.get("doc_labels", {})

    existing_text_labels = load_or_create_labels(
        user_id=user_id,
        labelset_obj=labelset_obj,
        label_data_dict=text_labels,
        existing_labels={},
    )

    existing_doc_labels = load_or_create_labels(
        user_id=user_id,
        labelset_obj=labelset_obj,
        label_data_dict=doc_labels,
        existing_labels={},
    )

    label_lookup = {**existing_text_labels, **existing_doc_labels}
    doc_label_lookup = {label.text: label for label in existing_doc_labels.values()}

    return label_lookup, doc_label_lookup


def create_document_from_export_data(
    doc_data: dict,
    pdf_file_handle,
    doc_filename: str,
    user_obj,
) -> Document:
    """
    Create a standalone Document from export data and a file handle.

    The document is created with backend_lock=True and needs to be unlocked
    after annotations are imported. The caller is responsible for adding
    the document to a corpus via corpus.add_document().

    Args:
        doc_data: The document data dict from the export.
        pdf_file_handle: An open file handle for the document file.
        doc_filename: The filename for the document.
        user_obj: The user creating the document.

    Returns:
        The created Document instance (backend_lock=True).
    """
    from opencontractserver.documents.models import Document

    pdf_file = File(pdf_file_handle, doc_filename)

    pawls_parse_file = ContentFile(
        json.dumps(compact_pawls_pages(doc_data["pawls_file_content"])).encode("utf-8"),
        name="pawls_tokens.json",
    )

    txt_extract_file = ContentFile(
        doc_data["content"].encode("utf-8"),
        name="extracted_text.txt",
    )

    doc_obj = Document.objects.create(
        title=doc_data["title"],
        description=doc_data.get("description", ""),
        pdf_file=pdf_file,
        pawls_parse_file=pawls_parse_file,
        txt_extract_file=txt_extract_file,
        file_type=doc_data.get("file_type")
        or mimetypes.guess_type(doc_filename)[0]
        or "application/pdf",
        backend_lock=True,
        creator=user_obj,
        page_count=doc_data.get("page_count") or len(doc_data["pawls_file_content"]),
        # Already has PAWLS data from export — skip the ingest signal
        processing_started=timezone.now(),
    )

    set_permissions_for_obj_to_user(user_obj, doc_obj, [PermissionTypes.ALL])
    return doc_obj


def import_doc_annotations(
    doc_data: dict,
    corpus_doc,
    corpus_obj,
    user_id: int,
    label_lookup: dict[str, AnnotationLabel],
    doc_label_lookup: dict[str, AnnotationLabel],
) -> tuple[dict[str | int, int], int]:
    """
    Import both document-level and text-level annotations for a document.

    Args:
        doc_data: The document data dict from the export.
        corpus_doc: The corpus-isolated document copy to attach annotations to.
        corpus_obj: The corpus instance.
        user_id: The ID of the importing user.
        label_lookup: Combined label lookup (text + doc labels).
        doc_label_lookup: Doc-type label lookup keyed by label text.

    Returns:
        Tuple of (annot_id_map, doc_labels_created) where:
        - annot_id_map: Mapping of old annotation IDs to new annotation PKs.
        - doc_labels_created: Number of doc-level annotations actually created.
    """
    # Import document-level annotations
    doc_labels_created = 0
    for doc_label_name in doc_data.get("doc_labels", []):
        label_obj = doc_label_lookup.get(doc_label_name)
        if label_obj:
            annot_obj = Annotation.objects.create(
                annotation_label=label_obj,
                annotation_type=DOC_TYPE_LABEL,
                document=corpus_doc,
                corpus=corpus_obj,
                creator_id=user_id,
            )
            set_permissions_for_obj_to_user(user_id, annot_obj, [PermissionTypes.ALL])
            doc_labels_created += 1

    # Import text annotations
    annot_id_map = import_annotations(
        user_id=user_id,
        doc_obj=corpus_doc,
        corpus_obj=corpus_obj,
        annotations_data=doc_data.get("labelled_text", []),
        label_lookup=label_lookup,
        label_type=TOKEN_LABEL,
    )

    return annot_id_map, doc_labels_created
