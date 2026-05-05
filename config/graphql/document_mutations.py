"""
GraphQL mutations for document CRUD, upload, import/export, and versioning operations.
"""

import base64
import json
import logging
import uuid

import graphene
from celery import chain, chord, group
from django.conf import settings
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone
from filetype import filetype
from graphene.types.generic import GenericScalar
from graphql import GraphQLError
from graphql_jwt.decorators import login_required
from graphql_relay import from_global_id

from config.graphql.base import DRFDeletion, DRFMutation
from config.graphql.document_types import INGESTION_SOURCE_GLOBAL_ID_TYPE
from config.graphql.graphene_types import (
    CorpusType,
    DocumentType,
    UserExportType,
)
from config.graphql.ratelimits import (
    RateLimits,
    get_user_tier_rate,
    graphql_ratelimit,
    graphql_ratelimit_dynamic,
)
from config.graphql.serializers import DocumentSerializer
from config.telemetry import record_event
from opencontractserver.constants.zip_import import (
    BULK_UPLOAD_OWNER_CACHE_PREFIX,
    BULK_UPLOAD_OWNER_CACHE_TTL_SECONDS,
    ZIP_MAX_TOTAL_SIZE_BYTES,
)
from opencontractserver.corpuses.models import Corpus, CorpusFolder, TemporaryFileHandle
from opencontractserver.documents.models import Document, DocumentPath, IngestionSource
from opencontractserver.extracts.models import Extract
from opencontractserver.pipeline.registry import get_allowed_mime_types
from opencontractserver.tasks import (
    build_label_lookups_task,
    burn_doc_annotations,
    import_corpus,
    import_document_to_corpus,
    package_annotated_docs,
    process_documents_zip,
)
from opencontractserver.tasks.doc_tasks import convert_doc_to_funsd
from opencontractserver.tasks.export_tasks import (
    on_demand_post_processors,
    package_funsd_exports,
)
from opencontractserver.tasks.export_tasks_v2 import package_corpus_export_v2
from opencontractserver.types.dicts import OpenContractsAnnotatedDocumentImportType
from opencontractserver.types.enums import (
    AnnotationFilterMode,
    ExportType,
    PermissionTypes,
)
from opencontractserver.users.models import UserExport
from opencontractserver.utils.etl import is_dict_instance_of_typed_dict
from opencontractserver.utils.files import is_plaintext_content
from opencontractserver.utils.permissioning import (
    set_permissions_for_obj_to_user,
    user_can_modify_corpus,
    user_has_permission_for_obj,
)

logger = logging.getLogger(__name__)


class UploadDocument(graphene.Mutation):
    class Arguments:
        base64_file_string = graphene.String(
            required=True, description="Base64-encoded file string for the file."
        )
        # base64_file_string = graphene.Base64(required=True, description="Base64-encoded file string for the file.")
        filename = graphene.String(
            required=True, description="Filename of the document."
        )
        title = graphene.String(required=True, description="Title of the document.")
        description = graphene.String(
            required=True, description="Description of the document."
        )
        custom_meta = GenericScalar(required=False, description="")
        add_to_corpus_id = graphene.ID(
            required=False,
            description="If provided, successfully uploaded document will "
            "be uploaded to corpus with specified id",
        )
        add_to_extract_id = graphene.ID(
            required=False,
            description="If provided, successfully uploaded document will be added to extract with specified id",
        )
        add_to_folder_id = graphene.ID(
            required=False,
            description="If provided along with add_to_corpus_id, the document "
            "will be assigned to this folder within the corpus",
        )
        make_public = graphene.Boolean(
            required=True,
            description="If True, document is immediately public. "
            "Defaults to False.",
        )
        slug = graphene.String(required=False)
        ingestion_source_id = graphene.ID(
            required=False,
            description="Global ID of the IngestionSource that produced this document",
        )
        external_id = graphene.String(
            required=False,
            description="Identifier in the external system (e.g. 'alpha:contract-123')",
        )
        ingestion_metadata = GenericScalar(
            required=False,
            description="Arbitrary source-specific metadata (URL, crawl job ID, etc.)",
        )

    ok = graphene.Boolean()
    message = graphene.String()
    document = graphene.Field(DocumentType)

    @login_required
    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("WRITE_HEAVY"))
    def mutate(
        root,
        info,
        base64_file_string,
        filename,
        title,
        description,
        custom_meta,
        make_public,
        add_to_corpus_id=None,
        add_to_extract_id=None,
        add_to_folder_id=None,
        slug=None,
        ingestion_source_id=None,
        external_id=None,
        ingestion_metadata=None,
    ) -> "UploadDocument":
        if add_to_corpus_id is not None and add_to_extract_id is not None:
            return UploadDocument(
                message="Cannot simultaneously add document to both corpus and extract",
                ok=False,
                document=None,
            )

        ok = False
        document = None

        # Was going to user a user_passes_test decorator, but I wanted a custom error message
        # that could be easily reflected to user in the GUI.
        if (
            info.context.user.is_usage_capped
            and info.context.user.document_set.count()
            > settings.USAGE_CAPPED_USER_DOC_CAP_COUNT - 1
        ):
            raise PermissionError(
                f"Your usage is capped at {settings.USAGE_CAPPED_USER_DOC_CAP_COUNT} documents. "
                f"Try deleting an existing document first or contact the admin for a higher limit."
            )

        try:
            message = "Success"

            file_bytes = base64.b64decode(base64_file_string)

            # Check file type
            kind = filetype.guess(file_bytes)
            if kind is None:

                if is_plaintext_content(file_bytes):
                    # Detect markdown/CAML files by extension
                    if filename and filename.lower().endswith(
                        (".caml", ".md", ".markdown")
                    ):
                        kind = "text/markdown"
                    else:
                        kind = "text/plain"
                else:
                    return UploadDocument(
                        message="Unable to determine file type", ok=False, document=None
                    )
            else:
                kind = kind.mime

            if kind not in get_allowed_mime_types():
                return UploadDocument(
                    message=f"Unallowed filetype: {kind}", ok=False, document=None
                )

            user = info.context.user

            # Determine target corpus and folder
            if add_to_corpus_id is not None:
                # Unified message prevents enumeration of corpus IDs the caller cannot see
                corpus_not_found_msg = (
                    "Corpus not found or you do not have permission to add "
                    "documents to it"
                )
                try:
                    corpus = Corpus.objects.visible_to_user(user).get(
                        id=from_global_id(add_to_corpus_id)[1]
                    )
                except Corpus.DoesNotExist:
                    return UploadDocument(
                        message=corpus_not_found_msg,
                        ok=False,
                        document=None,
                    )

                # ``visible_to_user`` only enforces READ; we still need an EDIT
                # check to gate writes. A user with READ-but-not-EDIT collapses
                # into the same unified message as no-access at all (intentional
                # IDOR posture).
                if not user_has_permission_for_obj(user, corpus, PermissionTypes.EDIT):
                    return UploadDocument(
                        message=corpus_not_found_msg,
                        ok=False,
                        document=None,
                    )

                folder = None
                if add_to_folder_id is not None:
                    try:
                        folder_pk = from_global_id(add_to_folder_id)[1]
                        folder = CorpusFolder.objects.get(pk=folder_pk, corpus=corpus)
                    except CorpusFolder.DoesNotExist:
                        return UploadDocument(
                            message="Folder not found in the specified corpus",
                            ok=False,
                            document=None,
                        )
            else:
                corpus = Corpus.get_or_create_personal_corpus(user)
                folder = None

            # Resolve ingestion source if provided
            ingestion_source = None
            if ingestion_source_id is not None:
                try:
                    type_name, source_pk = from_global_id(ingestion_source_id)
                    if type_name != INGESTION_SOURCE_GLOBAL_ID_TYPE:
                        raise IngestionSource.DoesNotExist
                    ingestion_source = IngestionSource.objects.get(
                        pk=source_pk, creator=user
                    )
                except (IngestionSource.DoesNotExist, ValueError, TypeError):
                    return UploadDocument(
                        message="Ingestion source not found",
                        ok=False,
                        document=None,
                    )

            # Build lineage kwargs for DocumentPath
            lineage_kwargs = {}
            if ingestion_source is not None:
                lineage_kwargs["ingestion_source"] = ingestion_source
            if external_id is not None:
                lineage_kwargs["external_id"] = external_id
            if ingestion_metadata is not None:
                lineage_kwargs["ingestion_metadata"] = ingestion_metadata

            # Import document - import_content handles path generation
            # from filename and routes based on file_type
            try:
                document, status, path_record = corpus.import_content(
                    content=file_bytes,
                    user=user,
                    filename=filename,
                    folder=folder,
                    file_type=kind,
                    title=title,
                    description=description,
                    custom_meta=custom_meta,
                    backend_lock=True,
                    is_public=make_public,
                    slug=slug,
                    **lineage_kwargs,
                )

                set_permissions_for_obj_to_user(user, document, [PermissionTypes.CRUD])

                logger.info(
                    f"[UPLOAD] Document {document.id} ({status}) "
                    f"uploaded to corpus {corpus.id}"
                )

            except Exception as e:
                logger.error(f"[UPLOAD] Error importing document: {e}")
                message = f"Upload failed due to error: {e}"
                return UploadDocument(message=message, ok=False, document=None)

            # Handle linking to extract (mutually exclusive with corpus)
            if add_to_extract_id is not None:
                try:
                    extract = Extract.objects.get(
                        Q(pk=from_global_id(add_to_extract_id)[1])
                        & (Q(creator=user) | Q(is_public=True))
                    )
                    if extract.finished is not None:
                        raise ValueError("Cannot add document to a finished extract")
                    transaction.on_commit(lambda: extract.documents.add(document))
                except Exception as e:
                    message = f"Adding to extract failed due to error: {e}"

            ok = True

        except Exception as e:
            message = f"Error on upload: {e}"

        return UploadDocument(message=message, ok=ok, document=document)


class UpdateDocument(DRFMutation):
    class IOSettings:
        lookup_field = "id"
        serializer = DocumentSerializer
        model = Document
        graphene_model = DocumentType

    class Arguments:
        id = graphene.String(required=True)
        title = graphene.String(required=False)
        description = graphene.String(required=False)
        pdf_file = graphene.String(required=False)
        custom_meta = GenericScalar(required=False)
        slug = graphene.String(required=False)


class UpdateDocumentSummary(graphene.Mutation):
    """
    Mutation to update a document's markdown summary for a specific corpus, creating a new version in the process.
    Users can create/update summaries if:
    - No summary exists yet and they have permission on the corpus (public or their corpus)
    - A summary exists and they are the original author
    """

    class Arguments:
        document_id = graphene.ID(
            required=True, description="ID of the document to update"
        )
        corpus_id = graphene.ID(
            required=True, description="ID of the corpus this summary is for"
        )
        new_content = graphene.String(
            required=True, description="New markdown content for the document summary"
        )

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(DocumentType)
    version = graphene.Int(description="The new version number after update")

    @login_required
    def mutate(
        root, info, document_id, corpus_id, new_content
    ) -> "UpdateDocumentSummary":
        try:
            from opencontractserver.documents.models import DocumentSummaryRevision

            user = info.context.user
            not_found_msg = (
                "Document or corpus not found, or you do not have permission."
            )

            # Extract pks from graphene ids
            _, doc_pk = from_global_id(document_id)
            _, corpus_pk = from_global_id(corpus_id)

            # Use visible_to_user() to prevent object-existence enumeration
            try:
                document = Document.objects.visible_to_user(user).get(pk=doc_pk)
            except Document.DoesNotExist:
                return UpdateDocumentSummary(
                    ok=False, message=not_found_msg, obj=None, version=None
                )

            try:
                corpus = Corpus.objects.visible_to_user(user).get(pk=corpus_pk)
            except Corpus.DoesNotExist:
                return UpdateDocumentSummary(
                    ok=False, message=not_found_msg, obj=None, version=None
                )

            # Check if user has any existing summary for this document-corpus combination
            existing_summary = (
                DocumentSummaryRevision.objects.filter(
                    document_id=doc_pk, corpus_id=corpus_pk
                )
                .order_by("version")
                .first()
            )

            # Permission logic
            if existing_summary:
                # If summary exists, only the original author can update
                if existing_summary.author != user:
                    return UpdateDocumentSummary(
                        ok=False,
                        message=not_found_msg,
                        obj=None,
                        version=None,
                    )
            else:
                # If no summary exists, require corpus modify rights
                # (superuser, creator, or explicit guardian UPDATE).
                if not user_can_modify_corpus(user, corpus):
                    return UpdateDocumentSummary(
                        ok=False,
                        message=not_found_msg,
                        obj=None,
                        version=None,
                    )

            # Update the summary using the new method
            revision = document.update_summary(
                new_content=new_content, author=info.context.user, corpus=corpus
            )

            # If no change, revision will be None
            if revision is None:
                latest_version = (
                    DocumentSummaryRevision.objects.filter(
                        document_id=doc_pk, corpus_id=corpus_pk
                    ).aggregate(max_version=Max("version"))["max_version"]
                    or 0
                )

                return UpdateDocumentSummary(
                    ok=True,
                    message="No changes detected in summary content.",
                    obj=document,
                    version=latest_version,
                )

            return UpdateDocumentSummary(
                ok=True,
                message=f"Summary updated successfully. New version: {revision.version}",
                obj=document,
                version=revision.version,
            )

        except Exception as e:
            logger.error(f"Error updating document summary: {str(e)}")
            return UpdateDocumentSummary(
                ok=False,
                message="Error updating document summary.",
                obj=None,
                version=None,
            )


class DeleteDocument(DRFDeletion):
    class IOSettings:
        model = Document
        lookup_field = "id"

    class Arguments:
        id = graphene.String(required=True)


class DeleteMultipleDocuments(graphene.Mutation):
    class Arguments:
        document_ids_to_delete = graphene.List(
            graphene.String,
            required=True,
            description="List of ids of the documents to delete",
        )

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    def mutate(root, info, document_ids_to_delete) -> "DeleteMultipleDocuments":
        try:
            document_pks = list(
                map(
                    lambda label_id: from_global_id(label_id)[1], document_ids_to_delete
                )
            )
            documents = Document.objects.filter(
                pk__in=document_pks, creator=info.context.user
            )
            documents.delete()
            ok = True
            message = "Success"

        except Exception as e:
            ok = False
            message = f"Delete failed due to error: {e}"

        return DeleteMultipleDocuments(ok=ok, message=message)


class UploadDocumentsZip(graphene.Mutation):
    """
    Mutation for uploading multiple documents via a zip file.
    The zip is stored as a temporary file and processed asynchronously.
    Only files with allowed MIME types will be created as documents.
    """

    class Arguments:
        base64_file_string = graphene.String(
            required=True,
            description="Base64-encoded zip file containing documents to upload",
        )
        title_prefix = graphene.String(
            required=False,
            description="Optional prefix for document titles (will be combined with filename)",
        )
        description = graphene.String(
            required=False,
            description="Optional description to apply to all documents",
        )
        custom_meta = GenericScalar(
            required=False, description="Optional metadata to apply to all documents"
        )
        add_to_corpus_id = graphene.ID(
            required=False,
            description="If provided, successfully uploaded documents will be added to corpus with specified id",
        )
        make_public = graphene.Boolean(
            required=True,
            description="If True, documents are immediately public. Defaults to False.",
        )

    ok = graphene.Boolean()
    message = graphene.String()
    job_id = graphene.String(description="ID to track the processing job")

    @login_required
    @graphql_ratelimit(rate=RateLimits.IMPORT)
    def mutate(
        root,
        info,
        base64_file_string,
        make_public,
        title_prefix=None,
        description=None,
        custom_meta=None,
        add_to_corpus_id=None,
    ) -> "UploadDocumentsZip":
        user = info.context.user
        # Was going to user a user_passes_test decorator, but I wanted a custom error message
        # that could be easily reflected to user in the GUI.
        if user.is_usage_capped and not settings.USAGE_CAPPED_USER_CAN_IMPORT_CORPUS:
            raise PermissionError(
                "By default, usage-capped users cannot bulk upload documents. "
                "Please contact the admin to authorize your account."
            )

        try:
            logger.info("UploadDocumentsZip.mutate() - Received zip upload request...")

            # Store zip in a temporary file
            base64_img_bytes = base64_file_string.encode("utf-8")
            decoded_file_data = base64.decodebytes(base64_img_bytes)

            job_id = str(uuid.uuid4())

            # IDOR protection: bind this job_id to the requesting user so the
            # status resolver can refuse cross-user reads. Cache miss in the
            # status resolver fails closed.
            cache.set(
                f"{BULK_UPLOAD_OWNER_CACHE_PREFIX}{job_id}",
                info.context.user.id,
                BULK_UPLOAD_OWNER_CACHE_TTL_SECONDS,
            )

            with transaction.atomic():
                temporary_file = TemporaryFileHandle.objects.create()
                temporary_file.file = ContentFile(
                    decoded_file_data,
                    name=f"documents_zip_import_{job_id}.zip",
                )
                temporary_file.save()
                logger.info("UploadDocumentsZip.mutate() - temporary file created.")

                # Check if we need to link to a corpus
                corpus_id = None
                if add_to_corpus_id is not None:
                    # Unified error message prevents enumeration of inaccessible corpora
                    corpus_not_found_msg = (
                        "Corpus not found or you do not have permission to "
                        "add documents to it"
                    )
                    try:
                        corpus = Corpus.objects.visible_to_user(user).get(
                            id=from_global_id(add_to_corpus_id)[1]
                        )
                        # Check if user has permission on this corpus
                        if not user_has_permission_for_obj(
                            user, corpus, PermissionTypes.EDIT
                        ):
                            raise PermissionError(corpus_not_found_msg)
                        corpus_id = corpus.id
                    except Corpus.DoesNotExist:
                        return UploadDocumentsZip(
                            message=corpus_not_found_msg,
                            ok=False,
                            job_id=job_id,
                        )
                    except PermissionError:
                        return UploadDocumentsZip(
                            message=corpus_not_found_msg,
                            ok=False,
                            job_id=job_id,
                        )
                    except Exception as e:
                        logger.error(f"Error validating corpus: {e}")
                        return UploadDocumentsZip(
                            message=f"Error validating corpus: {e}",
                            ok=False,
                            job_id=job_id,
                        )

            # Launch async task to process the zip file
            if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
                chain(
                    process_documents_zip.s(
                        temporary_file.id,
                        user.id,
                        job_id,
                        title_prefix,
                        description,
                        custom_meta,
                        make_public,
                        corpus_id,
                    )
                ).apply_async()
            else:
                transaction.on_commit(
                    lambda: chain(
                        process_documents_zip.s(
                            temporary_file.id,
                            info.context.user.id,
                            job_id,
                            title_prefix,
                            description,
                            custom_meta,
                            make_public,
                            corpus_id,
                        )
                    ).apply_async()
                )
            logger.info("UploadDocumentsZip.mutate() - Async task launched...")

            ok = True
            message = f"Upload started. Job ID: {job_id}"

        except Exception as e:
            ok = False
            message = f"Could not start document upload job due to error: {e}"
            job_id = None
            logger.error(message)

        return UploadDocumentsZip(message=message, ok=ok, job_id=job_id)


class RetryDocumentProcessing(graphene.Mutation):
    """
    Retry processing for a failed document.

    This mutation allows users to manually trigger reprocessing of a document
    that failed during the parsing pipeline. It's useful when transient errors
    (like network timeouts or service unavailability) have been resolved.

    Requirements:
    - Document must be in FAILED processing state
    - User must have UPDATE permission on the document
    """

    class Arguments:
        document_id = graphene.String(
            required=True, description="ID of the failed document to retry processing"
        )

    ok = graphene.Boolean()
    message = graphene.String()
    document = graphene.Field(DocumentType)

    @login_required
    def mutate(root, info, document_id) -> "RetryDocumentProcessing":
        from opencontractserver.documents.models import DocumentProcessingStatus
        from opencontractserver.tasks.doc_tasks import retry_document_processing
        from opencontractserver.types.enums import PermissionTypes
        from opencontractserver.utils.permissioning import user_has_permission_for_obj

        try:
            # Decode global ID
            doc_pk = from_global_id(document_id)[1]

            # Fetch the document
            try:
                document = Document.objects.get(pk=doc_pk)
            except Document.DoesNotExist:
                return RetryDocumentProcessing(
                    ok=False, message="Document not found", document=None
                )

            # IDOR protection: Check user has access to this document
            if not document.is_public and document.creator != info.context.user:
                if not user_has_permission_for_obj(
                    info.context.user, document, PermissionTypes.READ
                ):
                    return RetryDocumentProcessing(
                        ok=False, message="Document not found", document=None
                    )

            # Check document is in failed state
            if document.processing_status != DocumentProcessingStatus.FAILED:
                return RetryDocumentProcessing(
                    ok=False,
                    message="Document is not in a failed state and cannot be retried",
                    document=None,
                )

            # Check user has UPDATE permission
            if (
                document.creator != info.context.user
                and not info.context.user.is_superuser
            ):
                if not user_has_permission_for_obj(
                    info.context.user, document, PermissionTypes.UPDATE
                ):
                    return RetryDocumentProcessing(
                        ok=False,
                        message="You don't have permission to retry processing for this document",
                        document=None,
                    )

            # Trigger the retry task
            retry_document_processing.delay(
                user_id=info.context.user.id, doc_id=document.id
            )

            return RetryDocumentProcessing(
                ok=True,
                message="Document reprocessing has been queued",
                document=document,
            )

        except Exception as e:
            return RetryDocumentProcessing(
                ok=False, message=f"Retry failed: {str(e)}", document=None
            )


class UploadAnnotatedDocument(graphene.Mutation):
    class Arguments:
        target_corpus_id = graphene.String(required=True)
        document_import_data = graphene.String(required=True)

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    def mutate(
        root, info, target_corpus_id, document_import_data
    ) -> "UploadAnnotatedDocument":

        try:
            ok = True
            message = "SUCCESS"
            received_json = json.loads(document_import_data)
            if not is_dict_instance_of_typed_dict(
                received_json, OpenContractsAnnotatedDocumentImportType
            ):
                raise GraphQLError("document_import_data is invalid...")

            import_document_to_corpus.s(
                target_corpus_id=target_corpus_id,
                user_id=info.context.user.id,
                document_import_data=received_json,
            ).apply_async()

        except Exception as e:
            ok = False
            message = f"UploadAnnotatedDocument() - could not start load job due to error: {e}"
            logger.error(message)

        return UploadAnnotatedDocument(message=message, ok=ok)


class UploadCorpusImportZip(graphene.Mutation):
    class Arguments:
        base_64_file_string = graphene.String(
            required=True,
            description="Base-64 encoded string for zip of corpus file you want to import",
        )

    ok = graphene.Boolean()
    message = graphene.String()
    corpus = graphene.Field(CorpusType)

    @login_required
    @graphql_ratelimit(rate=RateLimits.IMPORT)
    def mutate(root, info, base_64_file_string) -> "UploadCorpusImportZip":

        if (
            info.context.user.is_usage_capped
            and not settings.USAGE_CAPPED_USER_CAN_IMPORT_CORPUS
        ):
            raise PermissionError(
                "By default, new users import corpuses. Please contact the admin to "
                "authorize your account."
            )

        try:
            logger.info(
                "UploadCorpusImportZip.mutate() - Received corpus import base64 encoded..."
            )
            corpus_obj = Corpus.objects.create(
                title="New Import", creator=info.context.user, backend_lock=False
            )
            logger.info("UploadCorpusImportZip.mutate() - placeholder created...")

            set_permissions_for_obj_to_user(
                info.context.user, corpus_obj, [PermissionTypes.CRUD]
            )
            logger.info("UploadCorpusImportZip.mutate() - permissions assigned...")

            # Store our corpus in a temporary file handler which lets us rely on
            # django-wide selection of S3 or local storage in django container
            base64_img_bytes = base_64_file_string.encode("utf-8")
            decoded_file_data = base64.decodebytes(base64_img_bytes)

            with transaction.atomic():
                temporary_file = TemporaryFileHandle.objects.create()
                temporary_file.file = ContentFile(
                    decoded_file_data,
                    name=f"corpus_import_{uuid.uuid4()}.pdf",
                )
                temporary_file.save()
                logger.info("UploadCorpusImportZip.mutate() - temporary file created.")

            transaction.on_commit(
                lambda: chain(
                    import_corpus.s(
                        temporary_file.id, info.context.user.id, corpus_obj.id
                    )
                ).apply_async()
            )
            logger.info("UploadCorpusImportZip.mutate() - Async task launched...")

            ok = True
            message = "Started"
            logger.info("UploadCorpusImportZip() - Imported started")

        except Exception as e:
            ok = False
            message = (
                f"UploadCorpusImportZip() - could not start load job due to error: {e}"
            )
            corpus_obj = None
            logger.error(message)

        return UploadCorpusImportZip(message=message, ok=ok, corpus=corpus_obj)


class ImportZipToCorpus(graphene.Mutation):
    """
    Mutation for importing a zip file to a corpus with folder structure preserved.

    Unlike UploadDocumentsZip which discards folder structure, this mutation:
    - Creates corpus folders matching the zip's directory structure
    - Places documents in their corresponding folders
    - Validates zip security (path traversal, zip bombs, etc.)
    - Requires corpus EDIT permission

    The import is processed asynchronously. Use the returned job_id to track progress.
    """

    class Arguments:
        base64_file_string = graphene.String(
            required=True,
            description="Base64-encoded zip file containing documents to import",
        )
        corpus_id = graphene.ID(
            required=True,
            description="ID of the corpus to import documents into",
        )
        target_folder_id = graphene.ID(
            required=False,
            description=(
                "Optional folder ID within the corpus to place zip contents under. "
                "If not provided, zip contents are placed at corpus root."
            ),
        )
        title_prefix = graphene.String(
            required=False,
            description="Optional prefix for document titles (combined with filename)",
        )
        description = graphene.String(
            required=False,
            description="Optional description to apply to all documents",
        )
        custom_meta = GenericScalar(
            required=False,
            description="Optional metadata to apply to all documents",
        )
        make_public = graphene.Boolean(
            required=True,
            description="If True, documents are immediately public",
        )

    ok = graphene.Boolean()
    message = graphene.String()
    job_id = graphene.String(description="ID to track the import job")

    @login_required
    @graphql_ratelimit(rate=RateLimits.IMPORT)
    def mutate(
        root,
        info,
        base64_file_string,
        corpus_id,
        make_public,
        target_folder_id=None,
        title_prefix=None,
        description=None,
        custom_meta=None,
    ) -> "ImportZipToCorpus":
        from celery import chain

        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        user = info.context.user

        # Check if usage-capped users can import
        if user.is_usage_capped and not settings.USAGE_CAPPED_USER_CAN_IMPORT_CORPUS:
            raise PermissionError(
                "By default, usage-capped users cannot bulk import documents. "
                "Please contact the admin to authorize your account."
            )

        try:
            logger.info("ImportZipToCorpus.mutate() - Received zip import request...")

            # Validate and get corpus
            # Unified error message prevents enumeration of inaccessible corpora
            corpus_not_found_msg = (
                "Corpus not found or you do not have permission to add "
                "documents to it"
            )
            try:
                corpus = Corpus.objects.visible_to_user(user).get(
                    id=from_global_id(corpus_id)[1]
                )
            except Corpus.DoesNotExist:
                return ImportZipToCorpus(
                    ok=False,
                    message=corpus_not_found_msg,
                    job_id=None,
                )

            # Check permission on corpus
            if not user_has_permission_for_obj(user, corpus, PermissionTypes.EDIT):
                return ImportZipToCorpus(
                    ok=False,
                    message=corpus_not_found_msg,
                    job_id=None,
                )

            # Validate target folder if provided
            target_folder_pk = None
            if target_folder_id:
                try:
                    target_folder = CorpusFolder.objects.get(
                        id=from_global_id(target_folder_id)[1],
                        corpus=corpus,
                    )
                    target_folder_pk = target_folder.id
                except CorpusFolder.DoesNotExist:
                    return ImportZipToCorpus(
                        ok=False,
                        message="Target folder not found or does not belong to this corpus",
                        job_id=None,
                    )

            # Validate base64 string size before decoding to prevent memory exhaustion
            # Base64 encoding adds ~33% overhead, so max encoded size is ~1.4x decoded size
            max_encoded_size = int(ZIP_MAX_TOTAL_SIZE_BYTES * 1.4)
            if len(base64_file_string) > max_encoded_size:
                return ImportZipToCorpus(
                    ok=False,
                    message=f"File exceeds maximum allowed size of {ZIP_MAX_TOTAL_SIZE_BYTES // (1024 * 1024)}MB",
                    job_id=None,
                )

            # Decode and store the zip file
            base64_zip_bytes = base64_file_string.encode("utf-8")
            decoded_file_data = base64.decodebytes(base64_zip_bytes)

            job_id = str(uuid.uuid4())

            with transaction.atomic():
                temporary_file = TemporaryFileHandle.objects.create()
                temporary_file.file = ContentFile(
                    decoded_file_data,
                    name=f"zip_import_{job_id}.zip",
                )
                temporary_file.save()
                logger.info("ImportZipToCorpus.mutate() - Temporary file created")

            # Launch async task
            if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
                chain(
                    import_zip_with_folder_structure.s(
                        temporary_file.id,
                        user.id,
                        job_id,
                        corpus.id,
                        target_folder_pk,
                        title_prefix,
                        description,
                        custom_meta,
                        make_public,
                    )
                ).apply_async()
            else:
                transaction.on_commit(
                    lambda: chain(
                        import_zip_with_folder_structure.s(
                            temporary_file.id,
                            info.context.user.id,
                            job_id,
                            corpus.id,
                            target_folder_pk,
                            title_prefix,
                            description,
                            custom_meta,
                            make_public,
                        )
                    ).apply_async()
                )
            logger.info("ImportZipToCorpus.mutate() - Async task launched")

            return ImportZipToCorpus(
                ok=True,
                message=f"Import started. Job ID: {job_id}",
                job_id=job_id,
            )

        except Exception as e:
            logger.error(f"ImportZipToCorpus.mutate() - Error: {e}")
            return ImportZipToCorpus(
                ok=False,
                message=f"Could not start import job: {e}",
                job_id=None,
            )


class StartCorpusExport(graphene.Mutation):
    """
    Mutation entrypoint for starting a corpus export.
    Now refactored to optionally accept a list of Analysis IDs (analyses_ids)
    that should be included in the export. If analyses_ids are provided, then
    only annotations/labels from those analyses are included. Otherwise, all
    annotations/labels for the corpus are included.
    """

    class Arguments:
        corpus_id = graphene.String(
            required=True,
            description="Graphene id of the corpus you want to package for export",
        )
        export_format = graphene.Argument(graphene.Enum.from_enum(ExportType))
        post_processors = graphene.List(
            graphene.String,
            required=False,
            description="List of fully qualified Python paths to post-processor functions to run",
        )
        input_kwargs = GenericScalar(
            required=False,
            description="Additional keyword arguments to pass to post-processors",
        )
        analyses_ids = graphene.List(
            graphene.String,
            required=False,
            description="Optional list of Graphene IDs for analyses that should be included in the export",
        )
        annotation_filter_mode = graphene.Argument(
            graphene.Enum.from_enum(AnnotationFilterMode),
            required=False,
            default_value=AnnotationFilterMode.CORPUS_LABELSET_ONLY.value,
            description="How to filter annotations - from corpus label set only, plus analyses, or analyses only",
        )
        include_conversations = graphene.Boolean(
            required=False,
            default_value=False,
            description="Whether to include conversations and messages in the export (V2 format only)",
        )
        include_action_trail = graphene.Boolean(
            required=False,
            default_value=False,
            description="Whether to include corpus action execution trail in the export (V2 format only)",
        )

    ok = graphene.Boolean()
    message = graphene.String()
    export = graphene.Field(UserExportType)

    @login_required
    @graphql_ratelimit(rate=RateLimits.EXPORT)
    def mutate(
        root,
        info,
        corpus_id: str,
        export_format: str,
        post_processors: list[str] = None,
        input_kwargs: dict = None,
        analyses_ids: list[str] = None,
        annotation_filter_mode: str = AnnotationFilterMode.CORPUS_LABELSET_ONLY.value,
        include_conversations: bool = False,
        include_action_trail: bool = False,
    ) -> "StartCorpusExport":
        """
        Initiates async Celery export tasks. If analyses_ids are supplied,
        the export is filtered to annotations/labels from only those analyses.
        Otherwise, all annotations/labels on corpus are included.

        :param root: GraphQL's root object
        :param info: GraphQL's info, containing context
        :param corpus_id: Graphene string id for the corpus
        :param export_format: The type of export to create (OPEN_CONTRACTS, FUNSD, etc.)
        :param post_processors: Optional list of python paths for post-processing
        :param input_kwargs: Optional dictionary of extra info for post-processors
        :param analyses_ids: Optional list of GraphQL IDs for analyses to filter by
        :return: The StartCorpusExport GraphQL object
        """
        post_processors = post_processors or []
        input_kwargs = input_kwargs or {}

        # Usage checks, permission checks, etc
        if (
            info.context.user.is_usage_capped
            and not settings.USAGE_CAPPED_USER_CAN_EXPORT_CORPUS
        ):
            raise PermissionError(
                "By default, new users cannot create exports. Please contact the admin to "
                "authorize your account."
            )

        try:
            # Prepare a new UserExport row
            started = timezone.now()
            date_str = started.strftime("%m/%d/%Y, %H:%M:%S")
            corpus_pk = from_global_id(corpus_id)[1]

            # Verify corpus visibility and READ permission before creating export
            try:
                corpus = Corpus.objects.visible_to_user(info.context.user).get(
                    pk=corpus_pk
                )
            except Corpus.DoesNotExist:
                return StartCorpusExport(
                    ok=False, message="Corpus not found", export=None
                )

            if not user_has_permission_for_obj(
                info.context.user,
                corpus,
                PermissionTypes.READ,
                include_group_permissions=True,
            ):
                return StartCorpusExport(
                    ok=False, message="Corpus not found", export=None
                )

            export = UserExport.objects.create(
                creator=info.context.user,
                name=f"Export Corpus PK {corpus_pk} on {date_str}",
                started=started,
                format=export_format,
                backend_lock=True,
                post_processors=post_processors,
                input_kwargs=input_kwargs,
            )
            logger.info(f"Export created: {export}")

            set_permissions_for_obj_to_user(
                info.context.user, export, [PermissionTypes.CRUD]
            )

            # For chaining, we convert analyses_ids from GraphQL global IDs -> PKs (if any).
            analysis_pk_list: list[int] = []
            if analyses_ids is not None:
                for g_id in analyses_ids:
                    try:
                        _, pk_str = from_global_id(g_id)
                        analysis_pk_list.append(int(pk_str))
                    except Exception:  # If invalid, just skip for safety
                        pass

            # TODO(#816): refactor export path to use collect_corpus_objects
            # Collect doc_ids in the corpus via DocumentPath
            doc_ids = DocumentPath.objects.filter(
                corpus_id=corpus_pk, is_current=True, is_deleted=False
            ).values_list("document_id", flat=True)
            logger.info(f"Doc ids: {list(doc_ids)}")

            # Build the Celery chain: label lookups -> burn doc annotations -> package -> optional post-proc
            if export_format == ExportType.OPEN_CONTRACTS.value:
                chain(
                    build_label_lookups_task.si(
                        corpus_pk,
                        analysis_pk_list if analysis_pk_list else None,
                        annotation_filter_mode,
                    ),
                    chain(
                        chord(
                            group(
                                burn_doc_annotations.s(
                                    doc_id,
                                    corpus_pk,
                                    analysis_pk_list if analysis_pk_list else None,
                                    annotation_filter_mode,
                                )
                                for doc_id in doc_ids
                            ),
                            package_annotated_docs.s(
                                export.id,
                                corpus_pk,
                                analysis_pk_list if analysis_pk_list else None,
                                annotation_filter_mode,
                            ),
                        ),
                        on_demand_post_processors.si(
                            export.id,
                            corpus_pk,
                        ),
                    ),
                ).apply_async()

                ok = True
                message = "SUCCESS"

            elif export_format == ExportType.OPEN_CONTRACTS_V2.value:
                package_corpus_export_v2.delay(
                    export_id=export.id,
                    corpus_pk=int(corpus_pk),
                    include_conversations=include_conversations,
                    include_action_trail=include_action_trail,
                    analysis_pk_list=analysis_pk_list if analysis_pk_list else None,
                    annotation_filter_mode=annotation_filter_mode,
                )
                ok = True
                message = "SUCCESS"

            elif export_format == ExportType.FUNSD:
                chain(
                    chord(
                        group(
                            convert_doc_to_funsd.s(
                                info.context.user.id,
                                doc_id,
                                corpus_pk,
                                analysis_pk_list if analysis_pk_list else None,
                            )
                            for doc_id in doc_ids
                        ),
                        package_funsd_exports.s(
                            export.id,
                            corpus_pk,
                            analysis_pk_list if analysis_pk_list else None,
                        ),
                    ),
                    on_demand_post_processors.si(export.id, corpus_pk),
                ).apply_async()

                ok = True
                message = "SUCCESS"
            else:
                ok = False
                message = "Unknown Format"

            record_event(
                "export_started",
                {
                    "env": settings.MODE,
                    "user_id": info.context.user.id,
                    "export_format": export_format,
                },
            )

        except Exception as e:
            message = f"StartCorpusExport() - Unable to create export due to error: {e}"
            logger.error(message)
            ok = False
            export = None

        return StartCorpusExport(ok=ok, message=message, export=export)


class DeleteExport(DRFDeletion):
    class IOSettings:
        model = UserExport
        lookup_field = "id"

    class Arguments:
        id = graphene.String(required=True)


# DOCUMENT VERSIONING MUTATIONS ################################################


class RestoreDeletedDocument(graphene.Mutation):
    """
    Restore a soft-deleted document path within a corpus.

    Delegates to DocumentFolderService.restore_document() for:
    - Permission checking (corpus UPDATE permission)
    - Creating new DocumentPath with is_deleted=False
    """

    class Arguments:
        document_id = graphene.String(
            required=True, description="Global ID of the document to restore"
        )
        corpus_id = graphene.String(
            required=True, description="Global ID of the corpus"
        )

    ok = graphene.Boolean()
    message = graphene.String()
    document = graphene.Field(DocumentType)

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_MEDIUM)
    def mutate(root, info, document_id, corpus_id) -> "RestoreDeletedDocument":
        from opencontractserver.corpuses.folder_service import DocumentFolderService

        user = info.context.user
        not_found_msg = "Document or corpus not found, or you do not have permission."

        try:
            doc_pk = from_global_id(document_id)[1]
            corpus_pk = from_global_id(corpus_id)[1]

            # Use visible_to_user() to prevent object-existence enumeration
            try:
                document = Document.objects.visible_to_user(user).get(pk=doc_pk)
            except Document.DoesNotExist:
                return RestoreDeletedDocument(
                    ok=False, message=not_found_msg, document=None
                )

            try:
                corpus = Corpus.objects.visible_to_user(user).get(pk=corpus_pk)
            except Corpus.DoesNotExist:
                return RestoreDeletedDocument(
                    ok=False, message=not_found_msg, document=None
                )

            # Find the deleted path entry
            deleted_path = (
                DocumentPath.objects.filter(
                    document=document, corpus=corpus, is_deleted=True, is_current=True
                )
                .order_by("-created")
                .first()
            )

            if not deleted_path:
                return RestoreDeletedDocument(
                    ok=False,
                    message="Document is not currently in a deleted state in this corpus.",
                    document=None,
                )

            # Delegate to service - handles permission checks and restoration
            success, error = DocumentFolderService.restore_document(
                user=user,
                document_path=deleted_path,
            )

            if not success:
                return RestoreDeletedDocument(
                    ok=False,
                    message=error,
                    document=None,
                )

            return RestoreDeletedDocument(
                ok=True,
                message="Document restored successfully",
                document=document,
            )

        except Exception as e:
            logger.error(f"Failed to restore document: {str(e)}")
            return RestoreDeletedDocument(
                ok=False,
                message="Failed to restore document.",
                document=None,
            )


class PermanentlyDeleteDocument(graphene.Mutation):
    """
    Permanently delete a soft-deleted document from a corpus.

    This is IRREVERSIBLE and removes:
    - All DocumentPath history for the document in this corpus
    - User annotations (non-structural) on the document
    - Relationships involving those annotations
    - DocumentSummaryRevision records
    - The Document itself if no other corpus references it

    Requires DELETE permission on the corpus.
    """

    class Arguments:
        document_id = graphene.String(
            required=True, description="Global ID of the document to permanently delete"
        )
        corpus_id = graphene.String(
            required=True, description="Global ID of the corpus"
        )

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_MEDIUM)
    def mutate(root, info, document_id, corpus_id) -> "PermanentlyDeleteDocument":
        from opencontractserver.corpuses.folder_service import DocumentFolderService

        user = info.context.user
        not_found_msg = "Document or corpus not found, or you do not have permission."

        try:
            doc_pk = from_global_id(document_id)[1]
            corpus_pk = from_global_id(corpus_id)[1]

            # Use visible_to_user() to prevent object-existence enumeration
            try:
                document = Document.objects.visible_to_user(user).get(pk=doc_pk)
            except Document.DoesNotExist:
                return PermanentlyDeleteDocument(ok=False, message=not_found_msg)

            try:
                corpus = Corpus.objects.visible_to_user(user).get(pk=corpus_pk)
            except Corpus.DoesNotExist:
                return PermanentlyDeleteDocument(ok=False, message=not_found_msg)

            success, error = DocumentFolderService.permanently_delete_document(
                user=user,
                document=document,
                corpus=corpus,
            )

            if not success:
                return PermanentlyDeleteDocument(ok=False, message=error)

            return PermanentlyDeleteDocument(
                ok=True, message="Document permanently deleted"
            )

        except Exception as e:
            logger.error(f"Failed to permanently delete document: {str(e)}")
            return PermanentlyDeleteDocument(
                ok=False, message="Failed to permanently delete document."
            )


class EmptyTrash(graphene.Mutation):
    """
    Permanently delete ALL soft-deleted documents in a corpus (empty trash).

    This is IRREVERSIBLE and removes all documents currently in the corpus trash.

    Requires DELETE permission on the corpus.
    """

    class Arguments:
        corpus_id = graphene.String(
            required=True, description="Global ID of the corpus to empty trash for"
        )

    ok = graphene.Boolean()
    message = graphene.String()
    deleted_count = graphene.Int()

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_MEDIUM)
    def mutate(root, info, corpus_id) -> "EmptyTrash":
        from opencontractserver.corpuses.folder_service import DocumentFolderService

        user = info.context.user

        try:
            corpus_pk = from_global_id(corpus_id)[1]
            # visible_to_user guarantees the corpus exists AND is visible to the
            # caller; service layer enforces write/DELETE permission afterwards
            corpus = Corpus.objects.visible_to_user(user).get(pk=corpus_pk)

            deleted_count, error = DocumentFolderService.empty_trash(
                user=user,
                corpus=corpus,
            )

            if error:
                # Partial success case - some deleted but with errors
                return EmptyTrash(
                    ok=deleted_count > 0,
                    message=error,
                    deleted_count=deleted_count,
                )

            return EmptyTrash(
                ok=True,
                message=f"Successfully deleted {deleted_count} document(s) from trash",
                deleted_count=deleted_count,
            )

        except Corpus.DoesNotExist:
            return EmptyTrash(ok=False, message="Corpus not found", deleted_count=0)
        except Exception as e:
            logger.error(f"Failed to empty trash: {str(e)}")
            return EmptyTrash(
                ok=False, message=f"Failed to empty trash: {str(e)}", deleted_count=0
            )


class RestoreDocumentToVersion(graphene.Mutation):
    """
    Restore a document to a previous content version.
    Creates a new version that is a copy of the specified version.
    """

    class Arguments:
        document_id = graphene.String(
            required=True,
            description="Global ID of the document version to restore to",
        )
        corpus_id = graphene.String(
            required=True, description="Global ID of the corpus"
        )

    ok = graphene.Boolean()
    message = graphene.String()
    document = graphene.Field(DocumentType)
    new_version_number = graphene.Int()

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_MEDIUM)
    def mutate(root, info, document_id, corpus_id) -> "RestoreDocumentToVersion":
        user = info.context.user

        try:
            doc_pk = from_global_id(document_id)[1]
            corpus_pk = from_global_id(corpus_id)[1]

            # Unified error message prevents IDOR enumeration of document/corpus IDs
            not_found_msg = (
                "Document or corpus not found, or you do not have permission "
                "to access them"
            )

            try:
                old_version = Document.objects.visible_to_user(user).get(pk=doc_pk)
                corpus = Corpus.objects.visible_to_user(user).get(pk=corpus_pk)
            except (Document.DoesNotExist, Corpus.DoesNotExist):
                return RestoreDocumentToVersion(
                    ok=False,
                    message=not_found_msg,
                    document=None,
                    new_version_number=None,
                )

            # Check UPDATE permission on both document and corpus
            if not user_has_permission_for_obj(
                user,
                old_version,
                PermissionTypes.UPDATE,
                include_group_permissions=True,
            ):
                return RestoreDocumentToVersion(
                    ok=False,
                    message=not_found_msg,
                    document=None,
                    new_version_number=None,
                )

            if not user_has_permission_for_obj(
                user, corpus, PermissionTypes.UPDATE, include_group_permissions=True
            ):
                return RestoreDocumentToVersion(
                    ok=False,
                    message=not_found_msg,
                    document=None,
                    new_version_number=None,
                )

            # Find the current version in the same version tree
            current_version = Document.objects.filter(
                version_tree_id=old_version.version_tree_id, is_current=True
            ).first()

            if not current_version:
                return RestoreDocumentToVersion(
                    ok=False,
                    message="Cannot find current version of this document",
                    document=None,
                    new_version_number=None,
                )

            if old_version.id == current_version.id:
                return RestoreDocumentToVersion(
                    ok=False,
                    message="Cannot restore to current version",
                    document=None,
                    new_version_number=None,
                )

            # Find the current path in the corpus
            current_path = DocumentPath.objects.filter(
                document__version_tree_id=old_version.version_tree_id,
                corpus=corpus,
                is_current=True,
                is_deleted=False,
            ).first()

            if not current_path:
                return RestoreDocumentToVersion(
                    ok=False,
                    message="Document not found in this corpus",
                    document=None,
                    new_version_number=None,
                )

            # Create a new document version as a copy of the old version
            with transaction.atomic():
                # Mark old current as not current
                current_version.is_current = False
                current_version.save()

                # Create new document version
                new_document = Document.objects.create(
                    title=old_version.title,
                    description=old_version.description,
                    custom_meta=old_version.custom_meta,
                    pdf_file=old_version.pdf_file,
                    txt_extract_file=old_version.txt_extract_file,
                    pawls_parse_file=old_version.pawls_parse_file,
                    icon=old_version.icon,
                    page_count=old_version.page_count,
                    file_type=old_version.file_type,
                    pdf_file_hash=old_version.pdf_file_hash,
                    creator=user,
                    # Versioning fields
                    version_tree_id=old_version.version_tree_id,
                    is_current=True,
                    parent=current_version,  # Parent is the old current, not the restored version
                )

                # Copy permissions from old version
                set_permissions_for_obj_to_user(
                    user, new_document, [PermissionTypes.CRUD]
                )

                # Mark old path as not current FIRST to avoid unique constraint violation
                current_path.is_current = False
                current_path.save()

                # Create new path entry with incremented version number
                new_path = DocumentPath.objects.create(
                    document=new_document,
                    corpus=corpus,
                    folder=current_path.folder,
                    path=current_path.path,
                    version_number=current_path.version_number + 1,
                    is_current=True,
                    is_deleted=False,
                    parent=current_path,
                    creator=user,
                )

            logger.info(
                f"User {user.id} restored document to version {old_version.id} "
                f"in corpus {corpus_pk}, new version number: {new_path.version_number}"
            )

            return RestoreDocumentToVersion(
                ok=True,
                message="Document restored to version successfully",
                document=new_document,
                new_version_number=new_path.version_number,
            )

        except Exception as e:
            logger.error(f"Failed to restore document to version: {str(e)}")
            return RestoreDocumentToVersion(
                ok=False,
                message=f"Failed to restore document: {str(e)}",
                document=None,
                new_version_number=None,
            )
