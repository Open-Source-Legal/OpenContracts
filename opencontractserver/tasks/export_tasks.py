from __future__ import annotations

import base64
import io
import json
import logging
import zipfile

from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone

from opencontractserver.corpuses.models import Corpus
from opencontractserver.notifications.models import (
    Notification,
    NotificationTypeChoices,
)
from opencontractserver.notifications.signals import (
    broadcast_notification_via_websocket,
)
from opencontractserver.pipeline.utils import run_post_processors
from opencontractserver.types.dicts import (
    AnnotationLabelPythonType,
    FunsdAnnotationType,
    OpenContractDocExport,
    OpenContractsExportDataJsonPythonType,
)
from opencontractserver.users.models import UserExport
from opencontractserver.utils.packaging import (
    package_corpus_for_export,
    package_label_set_for_export,
)
from opencontractserver.utils.text import only_alphanumeric_chars

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def _create_export_notification(export: UserExport, corpus_title: str) -> None:
    """
    Create a notification for export completion.

    Issue #624: Real-time notifications for export completion.

    Args:
        export: The UserExport instance
        corpus_title: The title of the corpus being exported
    """
    try:
        if export.creator:
            notification = Notification.objects.create(
                recipient=export.creator,
                notification_type=NotificationTypeChoices.EXPORT_COMPLETE,
                data={
                    "export_id": export.id,
                    "export_name": export.name,
                    "corpus_name": corpus_title,
                    "format": export.format,
                },
            )
            broadcast_notification_via_websocket(notification)
            logger.debug(
                f"Created EXPORT_COMPLETE notification for {export.creator.username}"
            )
    except Exception as e:
        logger.warning(f"Failed to create export notification: {e}")


def finalize_export(
    export_id: int,
    filename: str,
    output_bytes: io.BytesIO,
    corpus_title: str,
) -> None:
    """
    Save the export ZIP file and mark the export as complete.

    Shared finalization logic for all export formats (V1, V2, FUNSD).

    Args:
        export_id: The UserExport PK.
        filename: The filename for the saved ZIP.
        output_bytes: The BytesIO buffer containing the ZIP data.
        corpus_title: The corpus title (used for the notification).
    """
    output_bytes.seek(io.SEEK_SET)
    export = UserExport.objects.get(pk=export_id)
    export.file.save(filename, ContentFile(output_bytes.read()))
    export.finished = timezone.now()
    export.backend_lock = False
    export.save()
    _create_export_notification(export, corpus_title)


User = get_user_model()


@shared_task
def on_demand_post_processors(
    export_id: int,
    corpus_pk: int,
) -> None:
    """
    If user has selected some optional post-processors to run on the final
    ZIP, we perform them here. The annotation_filter_mode and analysis_ids
    are mostly relevant if the post-processor itself wants to consult or
    further refine data. Typically, though, it uses the final data.json
    as-is.
    """
    try:
        export = UserExport.objects.get(pk=export_id)
        corpus = Corpus.objects.get(pk=corpus_pk)

        if export.post_processors:

            # Get the current zip bytes
            if not export.file.name:
                raise RuntimeError(
                    f"Export {export_id} is missing its zip file; cannot post-process."
                )
            with default_storage.open(export.file.name, "rb") as export_file:
                current_zip_bytes = export_file.read()

            with zipfile.ZipFile(io.BytesIO(current_zip_bytes), "r") as input_zip:
                input_data = json.loads(input_zip.read("data.json").decode("utf-8"))

            # Run post-processors
            modified_zip_bytes, modified_export_data = run_post_processors(
                export.post_processors,
                current_zip_bytes,
                input_data,
                export.input_kwargs,
            )

            # Create new zip file with modified data
            output_buffer = io.BytesIO(modified_zip_bytes)
            finalize_export(
                export_id,
                f"{corpus.title} EXPORT.zip",
                output_buffer,
                corpus.title,
            )

    except Exception as e:
        logger.error(f"Error running post-processors for export {export_id}: {str(e)}")
        raise


# @celery_app.task(bind=True)
@shared_task
def package_annotated_docs(
    burned_docs: tuple[
        tuple[
            str,
            str,
            OpenContractDocExport | None,
            dict[str, AnnotationLabelPythonType],
            dict[str, AnnotationLabelPythonType],
        ],
        ...,
    ],
    export_id: int,
    corpus_pk: int,
    analysis_pk_list: list[int] | None = None,
    annotation_filter_mode: str = "CORPUS_LABELSET_ONLY",
) -> None:
    """
    Gathers the partial doc exports from burn_doc_annotations() and compiles
    the final zip (with pdf/image data + data.json). If annotation_filter_mode
    is "CORPUS_LABELSET_ONLY", we rely exclusively on data from the corpus label set.
    Otherwise, we handle combined or analysis-only data, which should already be
    reflected in burned_docs.

    Because burned_docs is already filtered, we mostly just package what's provided.
    """
    logger.info(f"Package corpus for export {export_id}...")

    annotated_docs: dict[str, OpenContractDocExport] = {}
    doc_labels: dict[str, AnnotationLabelPythonType] | None = None
    text_labels: dict[str, AnnotationLabelPythonType] | None = None

    corpus = Corpus.objects.get(id=corpus_pk)

    output_bytes = io.BytesIO()
    zip_file = zipfile.ZipFile(output_bytes, mode="w", compression=zipfile.ZIP_DEFLATED)

    for doc in burned_docs:

        doc_name, base64_file, doc_export, doc_text_labels, doc_doc_labels = doc

        # build_document_export returns ("", "", None, {}, {}) when the per-doc
        # export failed (e.g. the underlying file could not be loaded). Skip
        # those placeholders so we don't emit an empty-keyed / None-valued
        # entry into the final zip and data.json.
        if not doc_name or doc_export is None:
            logger.warning(
                f"Skipping failed burned doc in export {export_id}: "
                f"doc_name={doc_name!r}, has_export={doc_export is not None}"
            )
            continue

        if not doc_labels:
            doc_labels = doc_doc_labels

        if not text_labels:
            text_labels = doc_text_labels

        base64_img_bytes = base64_file.encode("utf-8")
        decoded_file_data = base64.decodebytes(base64_img_bytes)

        zip_file.writestr(doc_name, decoded_file_data)

        annotated_docs[doc_name] = doc_export

    corpus_pkg = package_corpus_for_export(corpus)
    label_set_pkg = package_label_set_for_export(corpus.label_set)
    if corpus_pkg is None or label_set_pkg is None:
        raise RuntimeError(
            f"Failed to package corpus or label set for export of corpus {corpus_pk}"
        )
    export_file_data: OpenContractsExportDataJsonPythonType = {
        "annotated_docs": annotated_docs,
        "corpus": corpus_pkg,
        "label_set": label_set_pkg,
        "doc_labels": doc_labels or {},
        "text_labels": text_labels or {},
    }

    # Run any configured post-processors
    if corpus.post_processors:
        try:
            # Get the current zip bytes
            zip_file.close()
            output_bytes.seek(io.SEEK_SET)
            current_zip_bytes = output_bytes.getvalue()

            # Run post-processors
            modified_zip_bytes, modified_export_data = run_post_processors(
                corpus.post_processors, current_zip_bytes, export_file_data
            )

            # Create new zip file with modified data
            output_bytes = io.BytesIO(modified_zip_bytes)
            zip_file = zipfile.ZipFile(
                output_bytes, mode="a", compression=zipfile.ZIP_DEFLATED
            )
            export_file_data = modified_export_data
        except Exception as e:
            logger.error(
                f"Error running post-processors for corpus {corpus_pk}: {str(e)}"
            )
            raise

    # Write the final data.json
    json_str = json.dumps(export_file_data) + "\n"
    json_bytes = json_str.encode("utf-8")
    zip_file.writestr("data.json", json_bytes)
    zip_file.close()

    finalize_export(export_id, f"{corpus.title} EXPORT.zip", output_bytes, corpus.title)
    logger.info(f"Export {export_id} is completed.")


@shared_task
def package_funsd_exports(
    funsd_data: tuple[
        tuple[
            int,
            dict[int, list[FunsdAnnotationType]],
            list[tuple[int, str, str]],
        ]
    ],
    export_id: int,
    corpus_pk: int,
    analysis_pk_list: list[int] | None = None,
) -> None:
    """
    Similar to package_annotated_docs, but for FUNSD exports. The key difference
    is we store per-page images and annotations in separate files. The
    annotation_filter_mode logic should already be applied upstream, so we just
    need to handle the final packaging.
    """
    logger.info(f"package_funsd_exports() - data:\n{json.dumps(funsd_data, indent=4)}")

    s3 = None

    corpus = Corpus.objects.get(id=corpus_pk)

    output_bytes = io.BytesIO()
    zip_file = zipfile.ZipFile(output_bytes, mode="w", compression=zipfile.ZIP_DEFLATED)

    if settings.STORAGE_BACKEND == "AWS":
        import boto3

        logger.info("process_pdf_page() - Load obj from S3")
        s3 = boto3.client("s3")
    elif settings.STORAGE_BACKEND == "GCP":
        from google.cloud import storage as gcs

        logger.info("process_pdf_page() - Load obj from GCS")
        gcs_client = gcs.Client(project=settings.GS_PROJECT_ID)
        gcs_bucket = gcs_client.bucket(settings.GS_BUCKET_NAME)

    for doc_data in funsd_data:

        doc_id, funsd_annotations, page_image_paths = doc_data

        for index, page_meta in enumerate(page_image_paths):

            doc_id, page_path, file_type = page_meta

            # Load page image
            if settings.STORAGE_BACKEND == "AWS":
                # ``assert`` would be stripped under ``python -O`` so use a
                # real RuntimeError. ``s3`` is set in the AWS branch above;
                # this branch only runs when the same condition holds, so
                # the guard is a defensive belt-and-suspenders for a code
                # path that production Celery does run with optimisations.
                if s3 is None:
                    raise RuntimeError(
                        "S3 client is None despite STORAGE_BACKEND='AWS'; "
                        "the boto3 client construction above did not run."
                    )
                page_obj = s3.get_object(
                    Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=page_path
                )
                page_bytes = page_obj["Body"].read()
            elif settings.STORAGE_BACKEND == "GCP":
                blob = gcs_bucket.blob(page_path)
                page_bytes = blob.download_as_bytes()
            else:
                with open(page_path, "rb") as page_file:
                    page_bytes = page_file.read()

            # Write page image
            zip_file.writestr(f"images/doc_{doc_id}-pg_{index}.{file_type}", page_bytes)

            # Load page funds annots
            if index in funsd_annotations:
                annots = funsd_annotations[index]
            else:
                annots = []

            page_annots = {"form": annots}

            # Write page funds annot
            zip_file.writestr(
                f"annotations/doc_{doc_id}-pg_{index}.json",
                json.dumps(page_annots, indent=4),
            )

    zip_file.close()

    finalize_export(
        export_id,
        f"{only_alphanumeric_chars(corpus.title)} FUNSD EXPORT.zip",
        output_bytes,
        corpus.title,
    )
