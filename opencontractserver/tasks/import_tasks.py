import base64
import json
import logging
import pathlib
import zipfile
from typing import Optional

import filetype
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile, File

from config import celery_app
from opencontractserver.annotations.models import (
    DOC_TYPE_LABEL,
    TOKEN_LABEL,
    Annotation,
)
from opencontractserver.corpuses.models import Corpus, TemporaryFileHandle
from opencontractserver.documents.models import Document
from opencontractserver.types.dicts import (
    OpenContractsAnnotatedDocumentImportType,
    OpenContractsExportDataJsonPythonType,
)
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.files import is_plaintext_content
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
def import_corpus(
    temporary_file_handle_id: str | int, user_id: int, seed_corpus_id: Optional[int]
) -> Optional[str]:
    try:
        logger.info(f"import_corpus() - for user_id: {user_id}")

        temporary_file_handle = TemporaryFileHandle.objects.get(
            id=temporary_file_handle_id
        )
        user_obj = User.objects.get(id=user_id)

        with temporary_file_handle.file.open("rb") as import_file, zipfile.ZipFile(
            import_file, mode="r"
        ) as import_zip:
            logger.info("import_corpus() - Data decoded successfully")
            files = import_zip.namelist()
            logger.info(f"import_corpus() - Raw files: {files}")

            if "data.json" in files:
                files.remove("data.json")
                with import_zip.open("data.json") as corpus_data:
                    data_json: OpenContractsExportDataJsonPythonType = json.loads(
                        corpus_data.read().decode("UTF-8")
                    )

                    text_labels = data_json["text_labels"]
                    doc_labels = data_json["doc_labels"]
                    label_set_data = {**data_json["label_set"]}
                    label_set_data.pop("id", None)
                    corpus_data_json = {**data_json["corpus"]}
                    corpus_data_json.pop("id", None)

                    # Create LabelSet
                    labelset_obj = unpack_label_set_from_export(
                        label_set_data, user_obj
                    )
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

                    # Prepare label data
                    existing_text_labels = {}
                    existing_doc_labels = {}
                    text_label_data_dict = {
                        label_name: label_info
                        for label_name, label_info in text_labels.items()
                    }
                    doc_label_data_dict = {
                        label_name: label_info
                        for label_name, label_info in doc_labels.items()
                    }

                    # Load or create labels
                    existing_text_labels = load_or_create_labels(
                        user_id=user_id,
                        labelset_obj=labelset_obj,
                        label_data_dict=text_label_data_dict,
                        existing_labels=existing_text_labels,
                    )
                    logger.info(
                        f"import_corpus() - existing_text_labels: {existing_text_labels}"
                    )
                    # This is super hacky... need to rebuild entire import / export pipeline (one day)
                    existing_doc_labels = load_or_create_labels(
                        user_id=user_id,
                        labelset_obj=labelset_obj,
                        label_data_dict=doc_label_data_dict,
                        existing_labels=existing_doc_labels,
                    )
                    doc_label_lookup = {
                        label.text: label for label in existing_doc_labels.values()
                    }
                    logger.info(
                        f"import_corpus() - existing_doc_labels: {existing_doc_labels}"
                    )
                    label_lookup = {**existing_text_labels, **existing_doc_labels}

                    # Iterate over documents
                    for doc_filename in data_json["annotated_docs"]:
                        logger.info(f"Start load for doc: {doc_filename}")
                        doc_data = data_json["annotated_docs"][doc_filename]
                        txt_content = doc_data["content"]
                        pawls_layers = doc_data["pawls_file_content"]

                        try:
                            with import_zip.open(doc_filename) as pdf_file_handle:
                                pdf_file = File(pdf_file_handle, doc_filename)
                                logger.info("pdf_file obj created in memory")

                                pawls_parse_file = ContentFile(
                                    json.dumps(pawls_layers).encode("utf-8"),
                                    name="pawls_tokens.json",
                                )
                                logger.info("Pawls parse file obj created in memory")

                                txt_extract_file = ContentFile(
                                    txt_content.encode("utf-8"),
                                    name="extracted_text.txt",
                                )
                                logger.info("Text extract file obj created in memory")

                                # Create Document instance
                                doc_obj = Document.objects.create(
                                    title=doc_data["title"],
                                    description=f"Imported document with filename {doc_filename}",
                                    pdf_file=pdf_file,
                                    pawls_parse_file=pawls_parse_file,
                                    txt_extract_file=txt_extract_file,
                                    backend_lock=True,  # Prevent immediate processing
                                    creator=user_obj,
                                    page_count=len(pawls_layers),
                                )
                                logger.info(f"Doc created: {doc_obj}")

                                set_permissions_for_obj_to_user(
                                    user_obj, doc_obj, [PermissionTypes.ALL]
                                )

                                # Link Document to Corpus
                                corpus_obj.documents.add(doc_obj)
                                corpus_obj.save()

                                # Import Document-level annotations
                                doc_labels_list = doc_data.get("doc_labels", [])
                                logger.info(
                                    f"import_corpus() - Found {len(doc_labels_list)} doc labels to import"
                                )

                                for doc_label_name in doc_labels_list:
                                    label_obj = doc_label_lookup.get(doc_label_name)
                                    logger.info(
                                        f"import_corpus() - Found doc label_obj: {label_obj}"
                                    )
                                    if label_obj:
                                        annot_obj = Annotation.objects.create(
                                            annotation_label=label_obj,
                                            document=doc_obj,
                                            corpus=corpus_obj,
                                            creator=user_obj,
                                        )
                                        set_permissions_for_obj_to_user(
                                            user_obj, annot_obj, [PermissionTypes.ALL]
                                        )

                                # Import Text annotations
                                text_annotations_data = doc_data.get(
                                    "labelled_text", []
                                )
                                logger.info(
                                    f"import_corpus() - Found {len(text_annotations_data)} text annotations to import"
                                )
                                import_annotations(
                                    user_id=user_id,
                                    doc_obj=doc_obj,
                                    corpus_obj=corpus_obj,
                                    annotations_data=text_annotations_data,
                                    label_lookup=label_lookup,
                                    label_type=TOKEN_LABEL,
                                )

                                # Unlock the document
                                doc_obj.backend_lock = False
                                doc_obj.save()
                                logger.info("Doc load complete.")

                        except Exception as e:
                            logger.error(
                                f"import_corpus() - Error loading document {doc_filename}: {e}"
                            )

                    return corpus_obj.id

            # If data.json is not found
            logger.error("import_corpus() - data.json not found in import zip.")
            return None

    except Exception as e:
        logger.error(f"import_corpus() - Exception encountered in corpus import: {e}")
        return None


@celery_app.task()
def import_document_to_corpus(
    target_corpus_id: int,
    user_id: int,
    document_import_data: OpenContractsAnnotatedDocumentImportType,
) -> Optional[str]:
    try:
        logger.info(f"import_document_to_corpus() - for user_id: {user_id}")
        logger.info(
            f"import_document_to_corpus() - target_corpus_id: {target_corpus_id}"
        )

        # Load target corpus
        corpus_obj = Corpus.objects.get(id=target_corpus_id)
        logger.info(f"Loaded corpus: {corpus_obj.title}")

        # Load labelset
        labelset_obj = corpus_obj.label_set
        logger.info(f"Loaded labelset: {labelset_obj.title}")

        # Load existing labels
        existing_text_labels = {
            label.text: label
            for label in labelset_obj.annotation_labels.filter(label_type=TOKEN_LABEL)
        }
        existing_doc_labels = {
            label.text: label
            for label in labelset_obj.annotation_labels.filter(
                label_type=DOC_TYPE_LABEL
            )
        }

        # Create new labels if needed
        existing_text_labels = load_or_create_labels(
            user_id,
            labelset_obj,
            document_import_data.get("text_labels", {}),
            existing_text_labels,
        )
        existing_doc_labels = load_or_create_labels(
            user_id,
            labelset_obj,
            document_import_data.get("doc_labels", {}),
            existing_doc_labels,
        )

        label_lookup = {
            **existing_text_labels,
            **existing_doc_labels,
        }
        logger.info(f"Label lookup: {label_lookup}")

        # Import the document
        logger.info("Starting document import")
        pdf_base64 = document_import_data["pdf_base64"]
        pdf_data = base64.b64decode(pdf_base64)

        pdf_file = ContentFile(pdf_data, name=f"{document_import_data['pdf_name']}.pdf")
        pawls_parse_file = ContentFile(
            json.dumps(document_import_data["doc_data"]["pawls_file_content"]).encode(
                "utf-8"
            ),
            name="pawls_tokens.json",
        )

        doc_obj = Document.objects.create(
            title=document_import_data["doc_data"]["title"],
            description=document_import_data["doc_data"].get(
                "description", "No Description"
            ),
            pdf_file=pdf_file,
            pawls_parse_file=pawls_parse_file,
            creator_id=user_id,
            page_count=document_import_data["doc_data"]["page_count"],
        )
        logger.info(f"Created document: {doc_obj.title}")
        set_permissions_for_obj_to_user(user_id, doc_obj, [PermissionTypes.ALL])

        # Link to corpus
        corpus_obj.documents.add(doc_obj)
        corpus_obj.save()
        logger.info(f"Linked document to corpus: {corpus_obj.title}")

        # Import text annotations
        doc_annotations_data = document_import_data["doc_data"]["labelled_text"]
        logger.info(f"Importing {len(doc_annotations_data)} text annotations")
        import_annotations(
            user_id,
            doc_obj,
            corpus_obj,
            doc_annotations_data,
            label_lookup,
            label_type=TOKEN_LABEL,
        )

        # Import document-level annotations
        doc_labels = document_import_data["doc_data"]["doc_labels"]
        logger.info(f"Importing {len(doc_labels)} doc labels")
        for doc_label in doc_labels:
            label_obj = existing_doc_labels[doc_label]
            annot_obj = Annotation.objects.create(
                annotation_label=label_obj,
                document=doc_obj,
                corpus=corpus_obj,
                creator_id=user_id,
            )
            set_permissions_for_obj_to_user(user_id, annot_obj, [PermissionTypes.ALL])

        logger.info("Document import completed successfully")
        return doc_obj.id

    except Exception as e:
        logger.error(f"Exception encountered in document import: {e}")
        return None


@celery_app.task()
def process_documents_zip(
    temporary_file_handle_id: str | int,
    user_id: int,
    job_id: str,
    title_prefix: Optional[str] = None,
    description: Optional[str] = None,
    custom_meta: Optional[dict] = None,
    make_public: bool = False,
    corpus_id: Optional[int] = None,
) -> dict:
    """
    Process a zip file containing documents, extract each file, and create Document objects
    for files with allowed MIME types.

    Args:
        temporary_file_handle_id: ID of the temporary file containing the zip
        user_id: ID of the user who uploaded the zip
        job_id: Unique ID for the job
        title_prefix: Optional prefix for document titles
        description: Optional description to apply to all documents
        custom_meta: Optional metadata to apply to all documents
        make_public: Whether the documents should be public
        corpus_id: Optional ID of corpus to link documents to

    Returns:
        Dictionary with summary of processing results
    """
    results = {
        "job_id": job_id,
        "success": False,
        "completed": False,  # Will be set to True on successful completion
        "total_files": 0,
        "processed_files": 0,
        "skipped_files": 0,
        "error_files": 0,
        "document_ids": [],
        "errors": [],
    }

    try:
        logger.info(f"process_documents_zip() - Processing started for job: {job_id}")

        # Get the temporary file and user objects
        temporary_file_handle = TemporaryFileHandle.objects.get(
            id=temporary_file_handle_id
        )
        user_obj = User.objects.get(id=user_id)

        # Check for corpus if needed
        corpus_obj = None
        if corpus_id:
            corpus_obj = Corpus.objects.get(id=corpus_id)

        # Calculate user doc limit if capped
        if user_obj.is_usage_capped:
            current_doc_count = user_obj.document_set.count()
            remaining_quota = (
                settings.USAGE_CAPPED_USER_DOC_CAP_COUNT - current_doc_count
            )
            if remaining_quota <= 0:
                results["success"] = False
                results["completed"] = True  # Task completed but failed
                results["errors"].append(
                    f"User has reached maximum document limit of {settings.USAGE_CAPPED_USER_DOC_CAP_COUNT}"
                )
                return results

        # Process the zip file
        with temporary_file_handle.file.open("rb") as import_file, zipfile.ZipFile(
            import_file, mode="r"
        ) as import_zip:
            logger.info(f"process_documents_zip() - Opened zip file for job: {job_id}")

            # Get list of files in the zip
            files = import_zip.namelist()
            logger.info(f"process_documents_zip() - Found {len(files)} files in zip")
            results["total_files"] = len(files)

            # Process each file in the zip
            for filename in files:
                # Skip directories and hidden files
                if (
                    filename.endswith("/")
                    or filename.startswith(".")
                    or "/__MACOSX/" in filename
                ):
                    results["skipped_files"] += 1
                    continue

                try:
                    # Check if we've hit the user cap
                    if user_obj.is_usage_capped:
                        current_doc_count = user_obj.document_set.count()
                        if (
                            current_doc_count
                            >= settings.USAGE_CAPPED_USER_DOC_CAP_COUNT
                        ):
                            results["errors"].append(
                                "User document limit reached during processing"
                            )
                            break

                    # Extract the file from the zip
                    with import_zip.open(filename) as file_handle:
                        file_bytes = file_handle.read()

                        # Check file type
                        kind = filetype.guess(file_bytes)
                        if kind is None:
                            # Try to detect plaintext using the improved utility
                            if is_plaintext_content(file_bytes):
                                kind = "text/plain"
                            else:  # Truly unknown/binary
                                logger.info(
                                    f"process_documents_zip() - Skipping file with unknown type: {filename}"
                                )
                                results["skipped_files"] += 1
                                continue
                        else:
                            kind = kind.mime

                        # Skip files with unsupported types
                        if kind not in settings.ALLOWED_DOCUMENT_MIMETYPES:
                            results["skipped_files"] += 1
                            continue

                        # Prepare document attributes
                        # Use only the filename part, discarding the path within the zip
                        base_filename = pathlib.Path(filename).name
                        doc_title = base_filename
                        if title_prefix:
                            doc_title = f"{title_prefix} - {base_filename}"

                        doc_description = (
                            description
                            or f"Uploaded as part of batch upload (job: {job_id})"
                        )

                        # Create the document based on file type
                        document = None

                        if kind in [
                            "application/pdf",
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        ]:
                            pdf_file = ContentFile(file_bytes, name=filename)
                            document = Document(
                                creator=user_obj,
                                title=doc_title,
                                description=doc_description,
                                custom_meta=custom_meta,
                                pdf_file=pdf_file,
                                backend_lock=True,
                                is_public=make_public,
                                file_type=kind,
                            )
                            document.save()
                        elif kind in ["text/plain", "application/txt"]:
                            txt_extract_file = ContentFile(file_bytes, name=filename)
                            document = Document(
                                creator=user_obj,
                                title=doc_title,
                                description=doc_description,
                                custom_meta=custom_meta,
                                txt_extract_file=txt_extract_file,
                                backend_lock=True,
                                is_public=make_public,
                                file_type=kind,
                            )
                            document.save()

                        if document:
                            # Set permissions for the document
                            set_permissions_for_obj_to_user(
                                user_obj, document, [PermissionTypes.CRUD]
                            )

                            # Add to corpus if needed
                            if corpus_obj:
                                corpus_obj.documents.add(document)

                            # Update results
                            results["processed_files"] += 1
                            results["document_ids"].append(str(document.id))
                            logger.info(
                                f"process_documents_zip() - Created document: {document.id} for file: {filename}"
                            )

                except Exception as e:
                    logger.error(
                        f"process_documents_zip() - Error processing file {filename}: {str(e)}"
                    )
                    results["error_files"] += 1
                    results["errors"].append(f"Error processing {filename}: {str(e)}")

        # Check if processing was stopped early due to user cap
        user_cap_reached_mid_processing = any(
            "User document limit reached during processing" in error
            for error in results["errors"]
        )

        # Clean up the temporary file
        temporary_file_handle.delete()

        results["success"] = not user_cap_reached_mid_processing
        results["completed"] = True  # Task completed, success depends on errors/cap
        logger.info(
            f"process_documents_zip() - Completed job: {job_id}, processed: {results['processed_files']}"
        )

    except Exception as e:
        logger.error(f"process_documents_zip() - Job failed with error: {str(e)}")
        results["success"] = False
        results["completed"] = True  # Task completed but failed
        results["errors"].append(f"Job failed: {str(e)}")

    return results
