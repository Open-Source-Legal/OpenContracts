import base64
import io
import json
import logging
import os
import traceback
import uuid

from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.db.models import Q
from pydantic import TypeAdapter, ValidationError, create_model
from typing_extensions import TypedDict

from opencontractserver.annotations.models import (
    DOC_TYPE_LABEL,
    RELATIONSHIP_LABEL,
    SPAN_LABEL,
    TOKEN_LABEL,
    Annotation,
    AnnotationLabel,
    Relationship,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.types.dicts import (
    AnnotationLabelPythonType,
    BoundingBoxPythonType,
    LabelLookupPythonType,
    OpenContractDocExport,
    OpenContractsSinglePageAnnotationType,
    PawlsPagePythonType,
)
from opencontractserver.types.enums import AnnotationFilterMode

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

User = get_user_model()


def build_label_lookups(
    corpus_id: str,
    analysis_ids: list[int] | None = None,
    annotation_filter_mode: AnnotationFilterMode = AnnotationFilterMode.CORPUS_LABELSET_ONLY,
) -> LabelLookupPythonType:
    """
    Build a label lookup dictionary for the specified corpus. Optionally filter
    out labels to only those found in certain analyses or combine with corpus label set.

    Args:
        corpus_id (str): The primary key (UUID string) of the corpus.
        analysis_ids (list[int] | None): Optional list of Analysis PKs.
        annotation_filter_mode (str): One of:
          - "CORPUS_LABELSET_ONLY"
          - "CORPUS_LABELSET_PLUS_ANALYSES"
          - "ANALYSES_ONLY"

    Returns:
        LabelLookupPythonType: A dictionary with two keys:
            "text_labels": A dict of all token/text labels keyed by label PK.
            "doc_labels": A dict of all doc-type labels keyed by label PK.
    """
    logger.info(f"build_label_lookups for corpus id #{corpus_id}")

    # Base first: only labels within the corpus
    corpus_label_ids = (
        Annotation.objects.filter(corpus_id=corpus_id, analysis__isnull=True)
        .values_list("annotation_label", flat=True)
        .distinct()
    )

    if annotation_filter_mode == "ANALYSES_ONLY":
        logger.info("Using ANALYSES_ONLY mode for label filtering")
        # If analyses are specified, gather only labels used by those analyses
        if analysis_ids:
            analyses_label_ids = (
                Annotation.objects.filter(analysis_id__in=analysis_ids)
                .values_list("annotation_label", flat=True)
                .distinct()
            )
            label_ids = analyses_label_ids
        else:
            # If user wants only analyses but there are none, no labels
            label_ids = []
    elif annotation_filter_mode == "CORPUS_LABELSET_PLUS_ANALYSES":
        logger.info("Using CORPUS_LABELSET_PLUS_ANALYSES mode for label filtering")
        # Combine corpus' label set with any from the analyses
        if analysis_ids:
            analyses_label_ids = (
                Annotation.objects.filter(analysis_id__in=analysis_ids)
                .values_list("annotation_label", flat=True)
                .distinct()
            )
            label_ids = corpus_label_ids.union(analyses_label_ids)
        else:
            label_ids = corpus_label_ids
    else:  # Default: "CORPUS_LABELSET_ONLY"
        logger.info("Using CORPUS_LABELSET_ONLY mode for label filtering")
        label_ids = corpus_label_ids

    # Also gather labels used on Relationship objects (RELATIONSHIP_LABEL type)
    # These are not captured by Annotation queries since they live on Relationship
    if annotation_filter_mode == "ANALYSES_ONLY":
        if analysis_ids:
            relationship_label_ids = (
                Relationship.objects.filter(
                    corpus_id=corpus_id, analysis_id__in=analysis_ids
                )
                .values_list("relationship_label", flat=True)
                .distinct()
            )
        else:
            relationship_label_ids = Relationship.objects.none().values_list(
                "relationship_label", flat=True
            )
    elif annotation_filter_mode == "CORPUS_LABELSET_PLUS_ANALYSES":
        corpus_rel_label_ids = (
            Relationship.objects.filter(corpus_id=corpus_id, analysis__isnull=True)
            .values_list("relationship_label", flat=True)
            .distinct()
        )
        if analysis_ids:
            analysis_rel_label_ids = (
                Relationship.objects.filter(
                    corpus_id=corpus_id, analysis_id__in=analysis_ids
                )
                .values_list("relationship_label", flat=True)
                .distinct()
            )
            relationship_label_ids = corpus_rel_label_ids.union(analysis_rel_label_ids)
        else:
            relationship_label_ids = corpus_rel_label_ids
    else:
        relationship_label_ids = (
            Relationship.objects.filter(corpus_id=corpus_id, analysis__isnull=True)
            .values_list("relationship_label", flat=True)
            .distinct()
        )

    # Merge annotation label IDs with relationship label IDs.
    # Materialize to a list so len() and filter(pk__in=) don't each
    # trigger separate DB evaluations of a union queryset.
    if isinstance(label_ids, list):
        all_label_ids = list(label_ids) + list(relationship_label_ids)
    else:
        all_label_ids = list(label_ids.union(relationship_label_ids))

    logger.info(f"Found {len(all_label_ids)} labels in corpus label set")

    # Pull the corresponding AnnotationLabel objects
    labels = AnnotationLabel.objects.filter(pk__in=all_label_ids)

    text_labels = {}
    doc_labels = {}

    # Export all label types: TOKEN_LABEL, SPAN_LABEL, and RELATIONSHIP_LABEL
    # go into text_labels; DOC_TYPE_LABEL goes into doc_labels.
    # Each entry preserves its actual label_type for correct reconstruction on import.
    text_label_queryset = labels.filter(
        label_type__in=[TOKEN_LABEL, SPAN_LABEL, RELATIONSHIP_LABEL]
    )
    doc_type_labels_queryset = labels.filter(label_type=DOC_TYPE_LABEL)

    for tl in text_label_queryset:
        hex_color = getattr(tl, "color", "#9ACD32")
        text_labels[str(tl.pk)] = {
            "id": str(tl.pk),
            "color": hex_color,
            "description": tl.description,
            "icon": tl.icon,
            "text": tl.text,
            "label_type": tl.label_type,
        }

    for dl in doc_type_labels_queryset:
        hex_color = getattr(dl, "color", "#9ACD32")
        doc_labels[str(dl.pk)] = {
            "id": str(dl.pk),
            "color": hex_color,
            "description": dl.description,
            "icon": dl.icon,
            "text": dl.text,
            "label_type": DOC_TYPE_LABEL,
        }

    return {
        "text_labels": text_labels,
        "doc_labels": doc_labels,
    }


def build_document_export(
    label_lookups: LabelLookupPythonType,
    doc_id: int,
    corpus_id: int,
    analysis_ids: list[int] | None = None,
    annotation_filter_mode: AnnotationFilterMode = AnnotationFilterMode.CORPUS_LABELSET_ONLY,
) -> tuple[
    str | None,
    str | None,
    OpenContractDocExport | None,
    dict[str | int, AnnotationLabelPythonType],
    dict[str | int, AnnotationLabelPythonType],
]:
    """
    Build an export for a given corpus on a given doc. For PDF files, this will burn in annotations
    by adding highlights and labels to the PDF. For non-PDF files, this will still export the
    annotation data in JSON format but skip the PDF processing.

    Additional args:
        analysis_ids: Optional list of analysis PKs to include in annotation selection
        annotation_filter_mode: How to filter annotations - "CORPUS_LABELSET_ONLY" (default),
            "CORPUS_LABELSET_PLUS_ANALYSES", or "ANALYSES_ONLY"
    """

    logger.info(f"burn_doc_annotations - label_lookups: {label_lookups}")

    try:

        text_labels = label_lookups["text_labels"]
        doc_labels = label_lookups["doc_labels"]

        doc = Document.objects.get(pk=doc_id)
        doc_name: str = (
            os.path.basename(doc.pdf_file.name) if doc.pdf_file else "document"
        )

        corpus = Corpus.objects.get(pk=corpus_id)

        # Check if document is a PDF
        is_pdf = doc.file_type == "application/pdf"
        logger.info(f"Document {doc_id} file_type: {doc.file_type}, is_pdf: {is_pdf}")

        extracted_document_content_json = ""
        try:
            with default_storage.open(doc.txt_extract_file.name) as content_file:
                extracted_document_content_json = content_file.read().decode("utf-8")
        except Exception as e:
            logger.warning(f"Could not export doc text for doc {doc_id}: {e}")

        pawls_tokens: list[PawlsPagePythonType] = []
        try:
            with default_storage.open(doc.pawls_parse_file.name) as pawls_file:
                pawls_tokens = json.loads(pawls_file.read().decode("utf-8"))
        except Exception as e:
            logger.warning(f"Could not export pawls tokens for doc {doc_id}: {e}")

        annotated_pdf_bytes = io.BytesIO()
        doc_annotations = Annotation.objects.filter(document=doc, corpus=corpus)

        if annotation_filter_mode == AnnotationFilterMode.ANALYSES_ONLY:
            if analysis_ids:
                doc_annotations = doc_annotations.filter(analysis_id__in=analysis_ids)
            else:
                doc_annotations = Annotation.objects.none()

        elif (
            annotation_filter_mode == AnnotationFilterMode.CORPUS_LABELSET_PLUS_ANALYSES
        ):
            corpus_label_pks = (
                label_lookups.get("doc_labels", {}).keys()
                | label_lookups.get("text_labels", {}).keys()
            )
            corpus_label_ids = [int(pk) for pk in corpus_label_pks]

            if analysis_ids:
                doc_annotations = doc_annotations.filter(
                    Q(annotation_label_id__in=corpus_label_ids)
                    | Q(analysis_id__in=analysis_ids)
                )
            else:
                doc_annotations = doc_annotations.filter(
                    annotation_label_id__in=corpus_label_ids
                )

        elif (
            annotation_filter_mode == AnnotationFilterMode.CORPUS_LABELSET_ONLY
        ):  # "CORPUS_LABELSET_ONLY"
            corpus_label_pks = (
                label_lookups.get("doc_labels", {}).keys()
                | label_lookups.get("text_labels", {}).keys()
            )
            corpus_label_ids = [int(pk) for pk in corpus_label_pks]
            doc_annotations = doc_annotations.filter(
                annotation_label_id__in=corpus_label_ids
            )

        else:
            raise ValueError(
                f"Invalid annotation_filter_mode: {annotation_filter_mode}"
            )

        # Initialize document annotation JSON structure (used for both PDF and non-PDF)
        doc_annotation_json: OpenContractDocExport = {
            "doc_labels": [],
            "labelled_text": [],
            "title": doc.title,
            "description": doc.description,
            "content": extracted_document_content_json,
            "pawls_file_content": pawls_tokens,
            "page_count": doc.page_count,
            "file_type": doc.file_type,
        }

        page_highlights = {}
        page_sizes = {}

        if pawls_tokens:
            page_sizes = {
                pawls_page["page"]["index"]: pawls_page["page"]
                for pawls_page in pawls_tokens
            }

        labelled_text = []
        labels_for_doc = []

        for annot in doc_annotations:
            if annot.annotation_label.label_type == DOC_TYPE_LABEL:
                labels_for_doc.append(f"{annot.annotation_label.text}")

            if annot.annotation_label.label_type in [TOKEN_LABEL, SPAN_LABEL]:
                annot_export = {
                    "id": f"{annot.id}",
                    "annotationLabel": f"{annot.annotation_label.id}",
                    "rawText": annot.raw_text,
                    "page": annot.page,
                    "annotation_json": annot.json,
                    "parent_id": annot.parent.id if annot.parent else None,
                    "annotation_type": annot.annotation_type,
                    "structural": annot.structural,
                }
                if annot.content_modalities:
                    annot_export["content_modalities"] = annot.content_modalities
                labelled_text.append(annot_export)

                annotation_json: dict[str, OpenContractsSinglePageAnnotationType] = (
                    annot.json
                )

                for targ_page_num in annotation_json:
                    logger.info(
                        f"Processing annotation {annot.id} on page {targ_page_num}"
                    )
                    highlight = annotation_json[targ_page_num]
                    logger.info(f"Highlight: {highlight}")

                    if targ_page_num in page_highlights:
                        if annot.annotation_label.id in page_highlights[targ_page_num]:
                            page_highlights[targ_page_num][
                                annot.annotation_label.id
                            ].append(highlight["bounds"])
                        else:
                            page_highlights[targ_page_num][
                                annot.annotation_label.id
                            ] = [highlight["bounds"]]
                    else:
                        page_highlights[targ_page_num] = {
                            annot.annotation_label.id: [highlight["bounds"]]
                        }

        doc_annotation_json["doc_labels"] = labels_for_doc
        doc_annotation_json["labelled_text"] = labelled_text

        # PDF-specific processing: burn annotations into PDF
        base64_encoded_message = ""
        if is_pdf and doc.pdf_file:
            logger.info(f"Processing as PDF document: {doc_id}")

            from pypdf import PdfReader, PdfWriter

            from opencontractserver.utils.files import (
                add_highlight_to_new_page,
                createHighlight,
            )

            try:
                pdf_input = PdfReader(doc.pdf_file.open(mode="rb"))
                pdf_output = PdfWriter()

                total_page_count = len(pdf_input.pages)

                logger.debug("Page_highlights: %s", page_highlights)
                logger.debug("Page_sizes: %s", page_sizes)

                for i in range(0, total_page_count):
                    page = pdf_input.pages[i]
                    page_box = page.mediabox

                    page_height = page_box.upper_left[1]
                    page_width = page_box.lower_right[0]

                    if f"{i + 1}" in page_highlights:
                        data_height = page_sizes[i + 1]["height"]
                        data_width = page_sizes[i + 1]["width"]

                        y_scale = float(page_height) / float(data_height)
                        x_scale = float(page_width) / float(data_width)

                        for label_id in page_highlights[f"{i + 1}"]:

                            label = text_labels[f"{label_id}"]

                            for rect in page_highlights[f"{i + 1}"][label_id]:
                                highlight = createHighlight(
                                    round(x_scale * rect["left"]),
                                    round(float(page_height) - y_scale * rect["top"]),
                                    round(x_scale * rect["right"]),
                                    round(
                                        float(page_height) - y_scale * rect["bottom"]
                                    ),
                                    {"author": "Label:", "contents": label["text"]},
                                    color=tuple(
                                        int(label["color"].lstrip("#")[i : i + 2], 16)
                                        / 256
                                        for i in (0, 2, 4)
                                    ),
                                )

                                add_highlight_to_new_page(highlight, page, pdf_output)

                    pdf_output.add_page(page)

                pdf_output.write(annotated_pdf_bytes)
                base64_encoded_data = base64.b64encode(annotated_pdf_bytes.getvalue())
                base64_encoded_message = base64_encoded_data.decode("utf-8")

            except Exception as e:
                logger.error(f"Could not process PDF due to error: {e}")
                logger.error(f"Stack trace: {traceback.format_exc()}")
                # Continue with empty PDF bytes for non-PDF or failed PDF processing
        else:
            logger.info(
                f"Skipping PDF processing for non-PDF document: {doc_id} (file_type: {doc.file_type})"
            )

        return (
            doc_name,
            base64_encoded_message,
            doc_annotation_json,
            text_labels,
            doc_labels,
        )

    except Exception as e:
        logger.error(f"Error building annotated doc for {doc_id}: {e}")
        logger.error(f"Stack trace: {traceback.format_exc()}")
        return "", "", None, {}, {}


def is_dict_instance_of_typed_dict(instance: dict, typed_dict: type[TypedDict]):
    # validate with pydantic
    try:
        TypeAdapter(typed_dict).validate_python(instance)
        return True

    except ValidationError:
        return False


def pawls_bbox_to_funsd_box(
    pawls_bbox: BoundingBoxPythonType,
) -> tuple[float, float, float, float]:
    return (
        pawls_bbox["left"],
        pawls_bbox["top"],
        pawls_bbox["right"],
        pawls_bbox["bottom"],
    )


def parse_model_or_primitive(value: str) -> type:
    """
    Parse a string value as either a Pydantic model or a primitive type.

    This function attempts to parse the given string value as a Pydantic model by dynamically creating
    a model with the specified fields. If the value represents a primitive type name ("int", "float",
    "str", "bool"), it returns the corresponding type object.

    Args:
        value (str): The string value to parse as either a Pydantic model or a primitive type.

    Returns:
        Type: The dynamically created Pydantic model or the corresponding primitive type.

    Raises:
        ValueError: If the value is neither a valid model definition nor a supported primitive type.
    """
    logger.info(f"Attempting to parse model or primitive from value: {value}")

    # Check for primitive types
    if value == "int":
        logger.info("Parsed value as int type")
        return int
    elif value == "float":
        logger.info("Parsed value as float type")
        return float
    elif value == "str":
        logger.info("Parsed value as str type")
        return str
    elif value == "bool":
        logger.info("Parsed value as bool type")
        return bool

    # Process as a model definition
    elif ":" in value:
        logger.info("Value appears to be a model definition, attempting to parse...")
        try:
            props = {}
            lines = value.split("\n")
            logger.debug(f"Split model definition into {len(lines)} lines")

            # Define allowed types
            allowed_types = {
                "str": str,
                "int": int,
                "float": float,
                "bool": bool,
                # Add more types as needed
            }

            for index, line in enumerate(lines):
                logger.debug(f"Processing line {index+1}: {line}")
                line = line.strip()
                if line == "":
                    logger.debug(f"Skipping empty line {index+1}")
                    continue
                # Skip class definitions or non-field lines
                if line.startswith("class") or "(" in line or ")" in line:
                    logger.debug(f"Skipping class definition or non-field line: {line}")
                    continue
                if "=" in line:
                    logger.error(
                        f"Found default value in line {line} which is not supported"
                    )
                    raise ValueError("We don't support default values, sorry.")
                elif ":" not in line:
                    logger.error(f"Missing type annotation in line: {line}")
                    raise ValueError("Every property needs to be typed!")

                parts = line.split(":")
                if len(parts) != 2:
                    logger.error(f"Invalid line format at line {index+1}: {line}")
                    raise ValueError(
                        f"There is an error in line {index+1} of your model"
                    )

                field_name = parts[0].strip()
                field_type_str = parts[1].strip()
                logger.debug(
                    f"Attempting to parse field '{field_name}' with type '{field_type_str}'"
                )

                # Get the actual type from allowed_types
                if field_type_str in allowed_types:
                    field_type = allowed_types[field_type_str]
                    logger.debug(
                        f"Successfully parsed type for field '{field_name}': {field_type}"
                    )
                else:
                    logger.error(
                        f"Unsupported type '{field_type_str}' for field '{field_name}'"
                    )
                    raise ValueError(
                        f"Unsupported type '{field_type_str}' for field '{field_name}'"
                    )

                props[field_name] = (field_type, ...)
                logger.debug(f"Added field '{field_name}' to model properties")

            # Generate a valid Python identifier for the model name
            model_name = f"DynamicModel_{uuid.uuid4().hex}"
            logger.info(
                f"Creating model with name {model_name} and properties: {props}"
            )
            model = create_model(model_name, **props)
            logger.info("Successfully created model")
            return model

        except Exception as e:
            logger.error(f"Failed to parse model definition: {str(e)}", exc_info=True)
            raise ValueError(f"Failed to parse model from value due to error: {e}")
    else:
        logger.error(
            f"Value '{value}' is neither a primitive type nor a valid model definition"
        )
        raise ValueError(f"Invalid model or primitive type: {value}")
