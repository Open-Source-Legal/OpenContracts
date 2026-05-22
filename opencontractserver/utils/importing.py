from __future__ import annotations

import json
import logging
import mimetypes
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from django.core.files.base import ContentFile, File
from django.utils import timezone

if TYPE_CHECKING:
    from opencontractserver.documents.models import Document

from config.graphql.annotation_serializers import AnnotationLabelSerializer
from opencontractserver.annotations.models import (
    DOC_TYPE_LABEL,
    RELATIONSHIP_LABEL,
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
    label_data_dict: Mapping[str, Mapping[str, Any]],
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
            label_data_copy = dict(label_data)
            label_data_copy.pop("id", None)
            label_data_copy["creator_id"] = user_id

            label_serializer = AnnotationLabelSerializer(data=label_data_copy)
            label_serializer.is_valid(raise_exception=True)
            label_obj = label_serializer.save()
            set_permissions_for_obj_to_user(
                user_id, label_obj, [PermissionTypes.ALL], is_new=True
            )

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
    pawls_data: list[dict] | None = None,
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

    # First pass: Build all Annotation instances in memory then bulk-create.
    #
    # Why bulk_create rather than per-row .create:
    #   * Per-row .create fires the Annotation post_save signal, which
    #     dispatches one ``calculate_embedding_for_annotation_text`` celery
    #     task per annotation. Under ``force_celery_eager()`` (benchmark
    #     harness, tests) and with a single-worker celery deployment, that
    #     means one synchronous embedding HTTP round-trip per annotation —
    #     ~400ms each times thousands of paragraph chunks per cuad-style
    #     contract is the dominant bottleneck.
    #   * bulk_create skips signals, so we explicitly dispatch one
    #     ``calculate_embeddings_for_annotation_batch`` task at the end,
    #     covering every newly-created annotation in a single call. The
    #     batch task internally sub-batches via ``EMBEDDING_API_BATCH_SIZE``
    #     and (for OpenAI) hits the embeddings endpoint with array input
    #     so ⌈N/batch_size⌉ HTTP calls cover N annotations.
    #   * The badges signal (also post_save) is also skipped here; an
    #     ingest-time badge tick per annotation is not load-bearing
    #     anywhere — corpus-level badge checks fire from other paths.
    instances: list[Annotation] = []
    parallel_old_ids: list[str | int | None] = []
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

        instances.append(
            Annotation(
                raw_text=annotation_data["rawText"],
                long_description=annotation_data.get("long_description"),
                page=annotation_data.get("page", 1),
                json=annotation_data["annotation_json"],
                annotation_label=label_obj,
                document=doc_obj,
                corpus=corpus_obj,
                creator_id=user_id,
                annotation_type=final_annotation_type,
                structural=annotation_data.get("structural", False),
                content_modalities=annotation_data.get("content_modalities", []),
                # OC_URL annotations carry a click-through ``link_url`` that
                # must survive round-trip through bulk import. Falsy /
                # missing values stay NULL on the column.
                link_url=annotation_data.get("link_url") or None,
            )
        )
        parallel_old_ids.append(annotation_data.get("id"))

    if instances:
        Annotation.objects.bulk_create(instances)
        # NB: We deliberately do NOT call set_permissions_for_obj_to_user on
        # individual annotations. The annotation visibility/permission model
        # is derived from doc + corpus (+ structural flag, creator,
        # analysis/extract privacy) — see:
        #   * AnnotationQuerySet.visible_to_user (shared/QuerySets.py)
        #   * AnnotationService._compute_effective_permissions
        #   * AnnotationManager.user_can (special-cases annotations)
        # None of those consult AnnotationUserObjectPermission rows, so
        # writing ~14 DB ops per annotation here is dead work. Locked in
        # by ``test_no_per_annotation_guardian_rows_are_required`` in
        # ``test_import_utils.py`` — that test deletes any pre-existing
        # rows and re-asserts visibility outcomes are unchanged.
        for instance, old_id in zip(instances, parallel_old_ids):
            if old_id is not None:
                old_id_to_new_pk[old_id] = instance.pk

        # Dispatch batch embedding task(s) covering every annotation we
        # just created. ``calculate_embeddings_for_annotation_batch`` only
        # takes the fast ``embed_texts_batch`` path when ``embedder_path``
        # is supplied explicitly (otherwise it falls through to a
        # per-annotation dual-embedding loop, which is exactly the
        # bottleneck we're trying to avoid). Mirror the dual-embedding
        # strategy here: dispatch one batch task with the default embedder
        # for global search, plus a second batch task with the corpus's
        # preferred embedder when it differs.
        from opencontractserver.constants.document_processing import (
            EMBEDDING_BATCH_SIZE,
        )
        from opencontractserver.pipeline.utils import get_default_embedder_path
        from opencontractserver.tasks.embeddings_task import (
            calculate_embeddings_for_annotation_batch,
        )

        annotation_ids = [a.pk for a in instances]
        corpus_id_for_batch = corpus_obj.id if corpus_obj is not None else None

        embedder_paths_to_dispatch: list[str] = []
        default_embedder_path = get_default_embedder_path()
        if default_embedder_path:
            embedder_paths_to_dispatch.append(default_embedder_path)
        # If the corpus has a different preferred embedder, dual-embed too.
        if corpus_obj is not None:
            corpus_pref = getattr(corpus_obj, "preferred_embedder", None)
            if corpus_pref and corpus_pref != default_embedder_path:
                embedder_paths_to_dispatch.append(corpus_pref)

        # Sub-batch by EMBEDDING_BATCH_SIZE to match corpus_tasks dispatch
        # pattern; the embedder's own ``embed_texts_batch`` further
        # sub-batches by EMBEDDING_API_BATCH_SIZE for the wire request.
        for embedder_path in embedder_paths_to_dispatch:
            for i in range(0, len(annotation_ids), EMBEDDING_BATCH_SIZE):
                chunk = annotation_ids[i : i + EMBEDDING_BATCH_SIZE]
                calculate_embeddings_for_annotation_batch.delay(
                    annotation_ids=chunk,
                    corpus_id=corpus_id_for_batch,
                    embedder_path=embedder_path,
                )

    # Second pass: Set parent relationships.
    # Legacy V1 exports — and V2 exports written before parent_id was
    # consistently stringified — emit ``parent_id`` as an int while ``id``
    # is a string.  The map is keyed by whatever the ``id`` field carries,
    # so we try the raw value first and fall back to its string form to
    # cover that asymmetry.  Both ``str`` and ``int`` lookups go through
    # this helper.
    def _lookup_pk(raw: Any) -> int | None:
        if raw is None:
            return None
        pk = old_id_to_new_pk.get(raw)
        if pk is not None:
            return pk
        return old_id_to_new_pk.get(str(raw))

    for annotation_data in annotations_data:
        old_id = annotation_data.get("id")
        parent_old_id = annotation_data.get("parent_id")
        if parent_old_id is not None and old_id is not None:
            annot_pk = _lookup_pk(old_id)
            parent_pk = _lookup_pk(parent_old_id)
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
            user_id, new_relationship, [PermissionTypes.ALL], is_new=True
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


VALID_LABEL_TYPES_FOR_IMPORT = {TOKEN_LABEL, DOC_TYPE_LABEL, RELATIONSHIP_LABEL}


def validate_labels_data(labels_data: object) -> list[str]:
    """
    Validate the schema of parsed labels.json data before processing.

    Checks:
    - Top-level value is a dict
    - ``text_labels`` and ``doc_labels``, if present, are dicts (not lists)
    - Each label entry is a dict containing a non-empty ``text`` field (str)
    - ``label_type``, ``color``, ``icon``, and ``description`` have correct types
      when present
    - ``label_type`` is one of the recognised values when present

    Returns a list of human-readable error strings (empty == valid).
    """
    errors: list[str] = []

    if not isinstance(labels_data, dict):
        errors.append(
            f"labels.json must be a JSON object, got {type(labels_data).__name__}"
        )
        return errors

    for section in ("text_labels", "doc_labels"):
        value = labels_data.get(section)
        if value is None:
            continue
        if not isinstance(value, dict):
            errors.append(
                f"labels.json '{section}' must be a JSON object (dict), "
                f"got {type(value).__name__}"
            )
            continue

        for label_key, label_entry in value.items():
            prefix = f"labels.json {section}[{label_key!r}]"

            if not isinstance(label_entry, dict):
                errors.append(
                    f"{prefix}: each label must be a JSON object, "
                    f"got {type(label_entry).__name__}"
                )
                continue

            # Required field: text (non-empty string)
            text_val = label_entry.get("text")
            if text_val is None:
                errors.append(f"{prefix}: missing required field 'text'")
            elif not isinstance(text_val, str) or not text_val.strip():
                errors.append(f"{prefix}: 'text' must be a non-empty string")

            # Optional typed fields
            label_type = label_entry.get("label_type")
            if label_type is not None:
                if not isinstance(label_type, str):
                    errors.append(
                        f"{prefix}: 'label_type' must be a string, "
                        f"got {type(label_type).__name__}"
                    )
                elif label_type not in VALID_LABEL_TYPES_FOR_IMPORT:
                    errors.append(
                        f"{prefix}: invalid label_type {label_type!r} "
                        f"(expected one of {sorted(VALID_LABEL_TYPES_FOR_IMPORT)})"
                    )

            color = label_entry.get("color")
            if color is not None and not isinstance(color, str):
                errors.append(
                    f"{prefix}: 'color' must be a string, "
                    f"got {type(color).__name__}"
                )

            icon = label_entry.get("icon")
            if icon is not None and not isinstance(icon, str):
                errors.append(
                    f"{prefix}: 'icon' must be a string, " f"got {type(icon).__name__}"
                )

            description = label_entry.get("description")
            if description is not None and not isinstance(description, str):
                errors.append(
                    f"{prefix}: 'description' must be a string, "
                    f"got {type(description).__name__}"
                )

    return errors


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
        # Preserve the source-file hash from the export when present.
        # Required so the corpus-isolated copy created by ``add_document``
        # (which inherits ``pdf_file_hash`` from this doc) carries the hash
        # forward — DocumentPath reconstruction and document-level
        # conversation relinking both key off it.
        pdf_file_hash=doc_data.get("pdf_file_hash") or None,
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

    set_permissions_for_obj_to_user(
        user_obj, doc_obj, [PermissionTypes.ALL], is_new=True
    )
    return doc_obj


def import_doc_annotations(
    doc_data: Mapping[str, Any],
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
            set_permissions_for_obj_to_user(
                user_id, annot_obj, [PermissionTypes.ALL], is_new=True
            )
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
