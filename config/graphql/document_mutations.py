"""Generated strawberry GraphQL module (graphene migration).

Shape-generated from the graphene schema; stub functions marked PORT(...)
carry the ported business logic. See config/graphql_new/manifest.json.
"""

# mypy: disable-error-code="name-defined, valid-type, arg-type"
#   Code-generation artifacts of the strawberry schema bindings that
#   mypy's static pass cannot resolve, NOT real typing defects:
#     name-defined / valid-type — ``Annotated["XType", strawberry.lazy(...)]``
#       forward-reference strings + the runtime-generated ``*Connection``
#       types (``make_connection_types``).
#     arg-type — resolvers construct result types with ``to_global_id()``
#       (``str``) for ``strawberry.ID`` fields and return Django MODEL
#       instances where the field annotation names the strawberry type
#       (the graphene-django resolver contract). Both are correct at
#       runtime. Hand-written config/graphql/core/* stays fully checked.
# flake8: noqa: E501, F821 — generated strawberry schema module.
# E501: long GraphQL field/argument ``description=`` strings and the
# single-line generated resolver signatures (black cannot split string
# literals). F821: ``Annotated["XType", strawberry.lazy(...)]`` /
# ``cast("QuerySet", ...)`` forward-reference STRINGS that pyflakes
# resolves as names — the whole point of strawberry.lazy is to avoid the
# import (which would then be F401). Both are code-generation artifacts,
# not defects; hand-written modules (config/graphql/core/*, security.py,
# testing.py, filters.py, …) stay fully linted.

from __future__ import annotations

import base64
import json
import logging
from typing import Annotated

import strawberry
from celery import chain, chord, group
from django.conf import settings
from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone
from graphql import GraphQLError
from graphql_relay import from_global_id

from config.graphql import enums
from config.graphql._util import strip_unset
from config.graphql.core.auth import login_required
from config.graphql.core.mutations import drf_deletion, drf_mutation
from config.graphql.core.relay import (
    register_type,
)
from config.graphql.core.scalars import GenericScalar
from config.graphql.document_types import INGESTION_SOURCE_GLOBAL_ID_TYPE
from config.graphql.ratelimits import (
    RateLimits,
    get_user_tier_rate,
    graphql_ratelimit,
    graphql_ratelimit_dynamic,
)
from config.graphql.serializers import DocumentSerializer
from config.telemetry import record_event
from opencontractserver.corpuses.models import Corpus
from opencontractserver.document_imports.services import (
    check_usage_cap,
    import_document_for_user,
    import_documents_zip_for_user,
)
from opencontractserver.documents.models import Document, DocumentPath, IngestionSource
from opencontractserver.extracts.models import Extract
from opencontractserver.shared.services.base import BaseService
from opencontractserver.tasks import (
    build_label_lookups_task,
    burn_doc_annotations,
    import_document_to_corpus,
    package_annotated_docs,
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
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

logger = logging.getLogger(__name__)


@strawberry.type(name="UploadDocument")
class UploadDocument:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    document: None | (
        Annotated[DocumentType, strawberry.lazy("config.graphql.document_types")]
    ) = strawberry.field(name="document", default=None)


register_type("UploadDocument", UploadDocument, model=None)


@strawberry.type(name="UpdateDocument")
class UpdateDocument:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj_id: strawberry.ID | None = strawberry.field(name="objId", default=None)


register_type("UpdateDocument", UpdateDocument, model=None)


@strawberry.type(
    name="UpdateDocumentSummary",
    description="Mutation to update a document's markdown summary for a specific corpus, creating a new version in the process.\nUsers can create/update summaries if:\n- No summary exists yet and they have permission on the corpus (public or their corpus)\n- A summary exists and they are the original author",
)
class UpdateDocumentSummary:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[DocumentType, strawberry.lazy("config.graphql.document_types")]
    ) = strawberry.field(name="obj", default=None)
    version: int | None = strawberry.field(
        name="version", description="The new version number after update", default=None
    )


register_type("UpdateDocumentSummary", UpdateDocumentSummary, model=None)


@strawberry.type(name="DeleteDocument")
class DeleteDocument:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("DeleteDocument", DeleteDocument, model=None)


@strawberry.type(name="DeleteMultipleDocuments")
class DeleteMultipleDocuments:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("DeleteMultipleDocuments", DeleteMultipleDocuments, model=None)


@strawberry.type(
    name="UploadDocumentsZip",
    description="Mutation for uploading multiple documents via a zip file.\nThe zip is stored as a temporary file and processed asynchronously.\nOnly files with allowed MIME types will be created as documents.",
)
class UploadDocumentsZip:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    job_id: str | None = strawberry.field(
        name="jobId", description="ID to track the processing job", default=None
    )


register_type("UploadDocumentsZip", UploadDocumentsZip, model=None)


@strawberry.type(
    name="RetryDocumentProcessing",
    description="Retry processing for a failed document.\n\nThis mutation allows users to manually trigger reprocessing of a document\nthat failed during the parsing pipeline. It's useful when transient errors\n(like network timeouts or service unavailability) have been resolved.\n\nRequirements:\n- Document must be in FAILED processing state\n- User must have UPDATE permission on the document",
)
class RetryDocumentProcessing:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    document: None | (
        Annotated[DocumentType, strawberry.lazy("config.graphql.document_types")]
    ) = strawberry.field(name="document", default=None)


register_type("RetryDocumentProcessing", RetryDocumentProcessing, model=None)


@strawberry.type(
    name="RestoreDeletedDocument",
    description="Restore a soft-deleted document path within a corpus.\n\nDelegates to DocumentLifecycleService.restore_document() for:\n- Permission checking (corpus UPDATE permission)\n- Creating new DocumentPath with is_deleted=False",
)
class RestoreDeletedDocument:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    document: None | (
        Annotated[DocumentType, strawberry.lazy("config.graphql.document_types")]
    ) = strawberry.field(name="document", default=None)


register_type("RestoreDeletedDocument", RestoreDeletedDocument, model=None)


@strawberry.type(
    name="RestoreDocumentToVersion",
    description="Restore a document to a previous content version.\nCreates a new version that is a copy of the specified version.",
)
class RestoreDocumentToVersion:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    document: None | (
        Annotated[DocumentType, strawberry.lazy("config.graphql.document_types")]
    ) = strawberry.field(name="document", default=None)
    new_version_number: int | None = strawberry.field(
        name="newVersionNumber", default=None
    )


register_type("RestoreDocumentToVersion", RestoreDocumentToVersion, model=None)


@strawberry.type(
    name="PermanentlyDeleteDocument",
    description="Permanently delete a soft-deleted document from a corpus.\n\nThis is IRREVERSIBLE and removes:\n- All DocumentPath history for the document in this corpus\n- User annotations (non-structural) on the document\n- Relationships involving those annotations\n- DocumentSummaryRevision records\n- The Document itself if no other corpus references it\n\nRequires DELETE permission on the corpus.",
)
class PermanentlyDeleteDocument:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("PermanentlyDeleteDocument", PermanentlyDeleteDocument, model=None)


@strawberry.type(
    name="EmptyTrash",
    description="Permanently delete ALL soft-deleted documents in a corpus (empty trash).\n\nThis is IRREVERSIBLE and removes all documents currently in the corpus trash.\n\nRequires DELETE permission on the corpus.",
)
class EmptyTrash:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    deleted_count: int | None = strawberry.field(name="deletedCount", default=None)


register_type("EmptyTrash", EmptyTrash, model=None)


@strawberry.type(
    name="EmptyCorpus",
    description='Move EVERY document in a corpus to Trash and remove ALL of its folders.\n\nThis is the "empty everything" action. Documents are soft-deleted (they\nremain in the trash and are restorable until the trash is emptied); the\nfolder tree is removed. Nothing is permanently deleted here — callers can\nfollow up with ``emptyTrash`` to purge.\n\nRequires DELETE permission on the corpus.',
)
class EmptyCorpus:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    trashed_count: int | None = strawberry.field(name="trashedCount", default=None)


register_type("EmptyCorpus", EmptyCorpus, model=None)


@strawberry.type(name="UploadAnnotatedDocument")
class UploadAnnotatedDocument:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("UploadAnnotatedDocument", UploadAnnotatedDocument, model=None)


@strawberry.type(
    name="StartCorpusExport",
    description="Mutation entrypoint for starting a corpus export.\nNow refactored to optionally accept a list of Analysis IDs (analyses_ids)\nthat should be included in the export. If analyses_ids are provided, then\nonly annotations/labels from those analyses are included. Otherwise, all\nannotations/labels for the corpus are included.",
)
class StartCorpusExport:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    export: None | (
        Annotated[UserExportType, strawberry.lazy("config.graphql.user_types")]
    ) = strawberry.field(name="export", default=None)


register_type("StartCorpusExport", StartCorpusExport, model=None)


@strawberry.type(name="DeleteExport")
class DeleteExport:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("DeleteExport", DeleteExport, model=None)


def _mutate_UploadDocument(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:119

    Port of UploadDocument.mutate
    """

    # Decorators are applied to an inner function because mutate stubs take
    # ``payload_cls`` as their first positional argument, which does not match
    # the ``(root, info, ...)`` calling convention the decorators expect.
    # Naming it ``mutate`` keeps the rate-limit cache group identical to
    # graphene (``group`` defaults to the decorated function's __name__).
    @login_required
    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("WRITE_HEAVY"))
    def mutate(
        root,
        info,
        base64_file_string,
        filename,
        title,
        description,
        make_public,
        custom_meta=None,
        add_to_corpus_id=None,
        add_to_extract_id=None,
        add_to_folder_id=None,
        slug=None,
        ingestion_source_id=None,
        external_id=None,
        ingestion_metadata=None,
    ) -> UploadDocument:
        if add_to_corpus_id is not None and add_to_extract_id is not None:
            return UploadDocument(
                message="Cannot simultaneously add document to both corpus and extract",
                ok=False,
                document=None,
            )

        user = info.context.user

        # Run the usage-cap check before any transport-specific resolution
        # so a capped user with an invalid ingestion_source_id still sees
        # the cap error (not a misleading "Ingestion source not found").
        # The shared service re-checks it for transports (e.g. REST) that
        # have nothing to resolve up front; the redundant call here is
        # cheap and keeps the cap error precedence on the GraphQL path.
        check_usage_cap(user)

        # Resolve ingestion source up front (GraphQL-only feature) so we
        # can hand a fully-built lineage dict to the shared service.
        lineage_kwargs: dict = {}
        if ingestion_source_id is not None:
            try:
                type_name, source_pk = from_global_id(ingestion_source_id)
                if type_name != INGESTION_SOURCE_GLOBAL_ID_TYPE:
                    raise IngestionSource.DoesNotExist
                ingestion_source = IngestionSource.objects.get(
                    pk=source_pk, creator=user
                )
                lineage_kwargs["ingestion_source"] = ingestion_source
            except (IngestionSource.DoesNotExist, ValueError, TypeError):
                return UploadDocument(
                    message="Ingestion source not found", ok=False, document=None
                )
        if external_id is not None:
            lineage_kwargs["external_id"] = external_id
        if ingestion_metadata is not None:
            lineage_kwargs["ingestion_metadata"] = ingestion_metadata

        try:
            file_bytes = base64.b64decode(base64_file_string)
        except Exception as e:
            return UploadDocument(
                message=f"Error on upload: {e}", ok=False, document=None
            )

        try:
            result = import_document_for_user(
                user=user,
                file_bytes=file_bytes,
                filename=filename,
                title=title,
                description=description,
                custom_meta=custom_meta,
                make_public=make_public,
                add_to_corpus_id=add_to_corpus_id,
                add_to_folder_id=add_to_folder_id,
                slug=slug,
                lineage_kwargs=lineage_kwargs,
            )
        except PermissionError:
            # Surface usage-cap as an exception, matching legacy contract
            raise

        if result.error or result.document is None:
            return UploadDocument(
                message=result.error or "Upload failed", ok=False, document=None
            )

        document = result.document
        message = "Success"

        # Handle linking to extract (mutually exclusive with corpus). This
        # is GraphQL-only; the REST endpoint does not expose extract linking.
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

        return UploadDocument(message=message, ok=True, document=document)

    return mutate(root, info, **kwargs)


def m_upload_document(
    info: strawberry.Info,
    add_to_corpus_id: Annotated[
        strawberry.ID | None,
        strawberry.argument(
            name="addToCorpusId",
            description="If provided, successfully uploaded document will be uploaded to corpus with specified id",
        ),
    ] = strawberry.UNSET,
    add_to_extract_id: Annotated[
        strawberry.ID | None,
        strawberry.argument(
            name="addToExtractId",
            description="If provided, successfully uploaded document will be added to extract with specified id",
        ),
    ] = strawberry.UNSET,
    add_to_folder_id: Annotated[
        strawberry.ID | None,
        strawberry.argument(
            name="addToFolderId",
            description="If provided along with add_to_corpus_id, the document will be assigned to this folder within the corpus",
        ),
    ] = strawberry.UNSET,
    base64_file_string: Annotated[
        str,
        strawberry.argument(
            name="base64FileString",
            description="Base64-encoded file string for the file.",
        ),
    ] = strawberry.UNSET,
    custom_meta: Annotated[
        GenericScalar | None, strawberry.argument(name="customMeta")
    ] = strawberry.UNSET,
    description: Annotated[
        str,
        strawberry.argument(
            name="description", description="Description of the document."
        ),
    ] = strawberry.UNSET,
    external_id: Annotated[
        str | None,
        strawberry.argument(
            name="externalId",
            description="Identifier in the external system (e.g. 'alpha:contract-123')",
        ),
    ] = strawberry.UNSET,
    filename: Annotated[
        str,
        strawberry.argument(name="filename", description="Filename of the document."),
    ] = strawberry.UNSET,
    ingestion_metadata: Annotated[
        GenericScalar | None,
        strawberry.argument(
            name="ingestionMetadata",
            description="Arbitrary source-specific metadata (URL, crawl job ID, etc.)",
        ),
    ] = strawberry.UNSET,
    ingestion_source_id: Annotated[
        strawberry.ID | None,
        strawberry.argument(
            name="ingestionSourceId",
            description="Global ID of the IngestionSource that produced this document",
        ),
    ] = strawberry.UNSET,
    make_public: Annotated[
        bool,
        strawberry.argument(
            name="makePublic",
            description="If True, document is immediately public. Defaults to False.",
        ),
    ] = strawberry.UNSET,
    slug: Annotated[str | None, strawberry.argument(name="slug")] = strawberry.UNSET,
    title: Annotated[
        str, strawberry.argument(name="title", description="Title of the document.")
    ] = strawberry.UNSET,
) -> UploadDocument | None:
    kwargs = strip_unset(
        {
            "add_to_corpus_id": add_to_corpus_id,
            "add_to_extract_id": add_to_extract_id,
            "add_to_folder_id": add_to_folder_id,
            "base64_file_string": base64_file_string,
            "custom_meta": custom_meta,
            "description": description,
            "external_id": external_id,
            "filename": filename,
            "ingestion_metadata": ingestion_metadata,
            "ingestion_source_id": ingestion_source_id,
            "make_public": make_public,
            "slug": slug,
            "title": title,
        }
    )
    return _mutate_UploadDocument(UploadDocument, None, info, **kwargs)


def m_update_document(
    info: strawberry.Info,
    custom_meta: Annotated[
        GenericScalar | None, strawberry.argument(name="customMeta")
    ] = strawberry.UNSET,
    description: Annotated[
        str | None, strawberry.argument(name="description")
    ] = strawberry.UNSET,
    id: Annotated[str, strawberry.argument(name="id")] = strawberry.UNSET,
    pdf_file: Annotated[
        str | None, strawberry.argument(name="pdfFile")
    ] = strawberry.UNSET,
    slug: Annotated[str | None, strawberry.argument(name="slug")] = strawberry.UNSET,
    title: Annotated[str | None, strawberry.argument(name="title")] = strawberry.UNSET,
) -> UpdateDocument | None:
    kwargs = strip_unset(
        {
            "custom_meta": custom_meta,
            "description": description,
            "id": id,
            "pdf_file": pdf_file,
            "slug": slug,
            "title": title,
        }
    )
    return drf_mutation(
        payload_cls=UpdateDocument,
        model=Document,
        serializer=DocumentSerializer,
        type_name="DocumentType",
        pk_fields=(),
        lookup_field="id",
        root=None,
        info=info,
        kwargs=kwargs,
    )


def _mutate_UpdateDocumentSummary(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:266

    Port of UpdateDocumentSummary.mutate
    """

    # Decorator applied to an inner function — see _mutate_UploadDocument.
    @login_required
    def mutate(
        root, info, document_id, corpus_id, new_content
    ) -> UpdateDocumentSummary:
        try:
            from opencontractserver.documents.models import DocumentSummaryRevision

            user = info.context.user
            not_found_msg = (
                "Document or corpus not found, or you do not have permission."
            )

            # Extract pks from graphene ids
            _, doc_pk = from_global_id(document_id)
            _, corpus_pk = from_global_id(corpus_id)

            # IDOR-safe fetch via the service layer.
            document = BaseService.get_or_none(
                Document, doc_pk, user, request=info.context
            )
            if document is None:
                return UpdateDocumentSummary(
                    ok=False, message=not_found_msg, obj=None, version=None
                )

            corpus = BaseService.get_or_none(
                Corpus, corpus_pk, user, request=info.context
            )
            if corpus is None:
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
                if BaseService.require_permission(
                    corpus, user, PermissionTypes.UPDATE, request=info.context
                ):
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

    return mutate(root, info, **kwargs)


def m_update_document_summary(
    info: strawberry.Info,
    corpus_id: Annotated[
        strawberry.ID,
        strawberry.argument(
            name="corpusId", description="ID of the corpus this summary is for"
        ),
    ] = strawberry.UNSET,
    document_id: Annotated[
        strawberry.ID,
        strawberry.argument(
            name="documentId", description="ID of the document to update"
        ),
    ] = strawberry.UNSET,
    new_content: Annotated[
        str,
        strawberry.argument(
            name="newContent",
            description="New markdown content for the document summary",
        ),
    ] = strawberry.UNSET,
) -> UpdateDocumentSummary | None:
    kwargs = strip_unset(
        {"corpus_id": corpus_id, "document_id": document_id, "new_content": new_content}
    )
    return _mutate_UpdateDocumentSummary(UpdateDocumentSummary, None, info, **kwargs)


def m_delete_document(
    info: strawberry.Info,
    id: Annotated[str, strawberry.argument(name="id")] = strawberry.UNSET,
) -> DeleteDocument | None:
    kwargs = strip_unset({"id": id})
    return drf_deletion(
        payload_cls=DeleteDocument,
        model=Document,
        lookup_field="id",
        root=None,
        info=info,
        kwargs=kwargs,
    )


def _mutate_DeleteMultipleDocuments(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:389

    Port of DeleteMultipleDocuments.mutate
    """

    # Decorator applied to an inner function — see _mutate_UploadDocument.
    @login_required
    def mutate(root, info, document_ids_to_delete) -> DeleteMultipleDocuments:
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

    return mutate(root, info, **kwargs)


def m_delete_multiple_documents(
    info: strawberry.Info,
    document_ids_to_delete: Annotated[
        list[str | None],
        strawberry.argument(
            name="documentIdsToDelete",
            description="List of ids of the documents to delete",
        ),
    ] = strawberry.UNSET,
) -> DeleteMultipleDocuments | None:
    kwargs = strip_unset({"document_ids_to_delete": document_ids_to_delete})
    return _mutate_DeleteMultipleDocuments(
        DeleteMultipleDocuments, None, info, **kwargs
    )


def _mutate_UploadDocumentsZip(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:447

    Port of UploadDocumentsZip.mutate
    """

    # Decorators applied to an inner function — see _mutate_UploadDocument.
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
    ) -> UploadDocumentsZip:
        user = info.context.user
        logger.info("UploadDocumentsZip.mutate() - Received zip upload request...")

        try:
            decoded_file_data = base64.decodebytes(base64_file_string.encode("utf-8"))
        except Exception as e:
            return UploadDocumentsZip(
                message=f"Could not decode base64 zip: {e}", ok=False, job_id=None
            )

        result = import_documents_zip_for_user(
            user=user,
            zip_source=decoded_file_data,
            title_prefix=title_prefix,
            description=description,
            custom_meta=custom_meta,
            make_public=make_public,
            add_to_corpus_id=add_to_corpus_id,
        )

        if result.error or result.job_id is None:
            return UploadDocumentsZip(
                message=result.error or "Upload failed",
                ok=False,
                job_id=result.job_id,
            )

        return UploadDocumentsZip(
            message=f"Upload started. Job ID: {result.job_id}",
            ok=True,
            job_id=result.job_id,
        )

    return mutate(root, info, **kwargs)


def m_upload_documents_zip(
    info: strawberry.Info,
    add_to_corpus_id: Annotated[
        strawberry.ID | None,
        strawberry.argument(
            name="addToCorpusId",
            description="If provided, successfully uploaded documents will be added to corpus with specified id",
        ),
    ] = strawberry.UNSET,
    base64_file_string: Annotated[
        str,
        strawberry.argument(
            name="base64FileString",
            description="Base64-encoded zip file containing documents to upload",
        ),
    ] = strawberry.UNSET,
    custom_meta: Annotated[
        GenericScalar | None,
        strawberry.argument(
            name="customMeta", description="Optional metadata to apply to all documents"
        ),
    ] = strawberry.UNSET,
    description: Annotated[
        str | None,
        strawberry.argument(
            name="description",
            description="Optional description to apply to all documents",
        ),
    ] = strawberry.UNSET,
    make_public: Annotated[
        bool,
        strawberry.argument(
            name="makePublic",
            description="If True, documents are immediately public. Defaults to False.",
        ),
    ] = strawberry.UNSET,
    title_prefix: Annotated[
        str | None,
        strawberry.argument(
            name="titlePrefix",
            description="Optional prefix for document titles (will be combined with filename)",
        ),
    ] = strawberry.UNSET,
) -> UploadDocumentsZip | None:
    kwargs = strip_unset(
        {
            "add_to_corpus_id": add_to_corpus_id,
            "base64_file_string": base64_file_string,
            "custom_meta": custom_meta,
            "description": description,
            "make_public": make_public,
            "title_prefix": title_prefix,
        }
    )
    return _mutate_UploadDocumentsZip(UploadDocumentsZip, None, info, **kwargs)


def _mutate_RetryDocumentProcessing(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:515

    Port of RetryDocumentProcessing.mutate
    """

    # Decorator applied to an inner function — see _mutate_UploadDocument.
    @login_required
    def mutate(root, info, document_id) -> RetryDocumentProcessing:
        from opencontractserver.documents.models import DocumentProcessingStatus
        from opencontractserver.tasks.doc_tasks import retry_document_processing
        from opencontractserver.types.enums import PermissionTypes
        from opencontractserver.utils.permissioning import get_for_user_or_none

        try:
            # Decode global ID
            doc_pk = from_global_id(document_id)[1]

            # Fetch the document with IDOR protection — get_for_user_or_none
            # collapses 'document doesn't exist' and 'caller can't READ it'
            # into the same None return so the response can't be used to
            # enumerate document existence.
            document = get_for_user_or_none(Document, doc_pk, info.context.user)
            if document is None:
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

            # Check user has UPDATE permission (the service-layer helper
            # delegates to the manager which handles creator/superuser
            # short-circuits internally).
            if BaseService.require_permission(
                document,
                info.context.user,
                PermissionTypes.UPDATE,
                request=info.context,
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

    return mutate(root, info, **kwargs)


def m_retry_document_processing(
    info: strawberry.Info,
    document_id: Annotated[
        str,
        strawberry.argument(
            name="documentId",
            description="ID of the failed document to retry processing",
        ),
    ] = strawberry.UNSET,
) -> RetryDocumentProcessing | None:
    kwargs = strip_unset({"document_id": document_id})
    return _mutate_RetryDocumentProcessing(
        RetryDocumentProcessing, None, info, **kwargs
    )


def _mutate_RestoreDeletedDocument(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:884

    Port of RestoreDeletedDocument.mutate
    """

    # Decorators applied to an inner function — see _mutate_UploadDocument.
    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_MEDIUM)
    def mutate(root, info, document_id, corpus_id) -> RestoreDeletedDocument:
        from opencontractserver.corpuses.services import DocumentLifecycleService

        user = info.context.user
        not_found_msg = "Document or corpus not found, or you do not have permission."

        try:
            doc_pk = from_global_id(document_id)[1]
            corpus_pk = from_global_id(corpus_id)[1]

            # IDOR-safe fetch via the service layer.
            document = BaseService.get_or_none(
                Document, doc_pk, user, request=info.context
            )
            if document is None:
                return RestoreDeletedDocument(
                    ok=False, message=not_found_msg, document=None
                )

            corpus = BaseService.get_or_none(
                Corpus, corpus_pk, user, request=info.context
            )
            if corpus is None:
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
            success, error = DocumentLifecycleService.restore_document(
                user=user,
                document_path=deleted_path,
                request=info.context,
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

    return mutate(root, info, **kwargs)


def m_restore_deleted_document(
    info: strawberry.Info,
    corpus_id: Annotated[
        str, strawberry.argument(name="corpusId", description="Global ID of the corpus")
    ] = strawberry.UNSET,
    document_id: Annotated[
        str,
        strawberry.argument(
            name="documentId", description="Global ID of the document to restore"
        ),
    ] = strawberry.UNSET,
) -> RestoreDeletedDocument | None:
    kwargs = strip_unset({"corpus_id": corpus_id, "document_id": document_id})
    return _mutate_RestoreDeletedDocument(RestoreDeletedDocument, None, info, **kwargs)


def _mutate_RestoreDocumentToVersion(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:1185

    Port of RestoreDocumentToVersion.mutate
    """

    # Decorators applied to an inner function — see _mutate_UploadDocument.
    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_MEDIUM)
    def mutate(root, info, document_id, corpus_id) -> RestoreDocumentToVersion:
        user = info.context.user

        try:
            doc_pk = from_global_id(document_id)[1]
            corpus_pk = from_global_id(corpus_id)[1]

            # Unified error message prevents IDOR enumeration of document/corpus IDs
            not_found_msg = (
                "Document or corpus not found, or you do not have permission "
                "to access them"
            )

            old_version = BaseService.get_or_none(
                Document, doc_pk, user, request=info.context
            )
            corpus = BaseService.get_or_none(
                Corpus, corpus_pk, user, request=info.context
            )
            if old_version is None or corpus is None:
                return RestoreDocumentToVersion(
                    ok=False,
                    message=not_found_msg,
                    document=None,
                    new_version_number=None,
                )

            # Check UPDATE permission on both document and corpus.
            if BaseService.require_permission(
                old_version, user, PermissionTypes.UPDATE, request=info.context
            ):
                return RestoreDocumentToVersion(
                    ok=False,
                    message=not_found_msg,
                    document=None,
                    new_version_number=None,
                )

            if BaseService.require_permission(
                corpus, user, PermissionTypes.UPDATE, request=info.context
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
                    user,
                    new_document,
                    [PermissionTypes.CRUD],
                    request=info.context,
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

    return mutate(root, info, **kwargs)


def m_restore_document_to_version(
    info: strawberry.Info,
    corpus_id: Annotated[
        str, strawberry.argument(name="corpusId", description="Global ID of the corpus")
    ] = strawberry.UNSET,
    document_id: Annotated[
        str,
        strawberry.argument(
            name="documentId",
            description="Global ID of the document version to restore to",
        ),
    ] = strawberry.UNSET,
) -> RestoreDocumentToVersion | None:
    kwargs = strip_unset({"corpus_id": corpus_id, "document_id": document_id})
    return _mutate_RestoreDocumentToVersion(
        RestoreDocumentToVersion, None, info, **kwargs
    )


def _mutate_PermanentlyDeleteDocument(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:983

    Port of PermanentlyDeleteDocument.mutate
    """

    # Decorators applied to an inner function — see _mutate_UploadDocument.
    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_MEDIUM)
    def mutate(root, info, document_id, corpus_id) -> PermanentlyDeleteDocument:
        from opencontractserver.corpuses.services import DocumentLifecycleService

        user = info.context.user
        not_found_msg = "Document or corpus not found, or you do not have permission."

        try:
            doc_pk = from_global_id(document_id)[1]
            corpus_pk = from_global_id(corpus_id)[1]

            # IDOR-safe fetch via the service layer.
            document = BaseService.get_or_none(
                Document, doc_pk, user, request=info.context
            )
            if document is None:
                return PermanentlyDeleteDocument(ok=False, message=not_found_msg)

            corpus = BaseService.get_or_none(
                Corpus, corpus_pk, user, request=info.context
            )
            if corpus is None:
                return PermanentlyDeleteDocument(ok=False, message=not_found_msg)

            success, error = DocumentLifecycleService.permanently_delete_document(
                user=user,
                document=document,
                corpus=corpus,
                request=info.context,
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

    return mutate(root, info, **kwargs)


def m_permanently_delete_document(
    info: strawberry.Info,
    corpus_id: Annotated[
        str, strawberry.argument(name="corpusId", description="Global ID of the corpus")
    ] = strawberry.UNSET,
    document_id: Annotated[
        str,
        strawberry.argument(
            name="documentId",
            description="Global ID of the document to permanently delete",
        ),
    ] = strawberry.UNSET,
) -> PermanentlyDeleteDocument | None:
    kwargs = strip_unset({"corpus_id": corpus_id, "document_id": document_id})
    return _mutate_PermanentlyDeleteDocument(
        PermanentlyDeleteDocument, None, info, **kwargs
    )


def _mutate_EmptyTrash(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:1047

    Port of EmptyTrash.mutate
    """

    # Decorators applied to an inner function — see _mutate_UploadDocument.
    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_MEDIUM)
    def mutate(root, info, corpus_id) -> EmptyTrash:
        from opencontractserver.corpuses.services import DocumentLifecycleService

        user = info.context.user

        try:
            corpus_pk = from_global_id(corpus_id)[1]
            # Service-layer fetch guarantees the corpus exists AND is visible
            # to the caller; the lifecycle service enforces write/DELETE
            # permission afterwards.
            corpus = BaseService.get_or_none(
                Corpus, corpus_pk, user, request=info.context
            )
            if corpus is None:
                raise Corpus.DoesNotExist

            deleted_count, error = DocumentLifecycleService.empty_trash(
                user=user,
                corpus=corpus,
                request=info.context,
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

    return mutate(root, info, **kwargs)


def m_empty_trash(
    info: strawberry.Info,
    corpus_id: Annotated[
        str,
        strawberry.argument(
            name="corpusId", description="Global ID of the corpus to empty trash for"
        ),
    ] = strawberry.UNSET,
) -> EmptyTrash | None:
    kwargs = strip_unset({"corpus_id": corpus_id})
    return _mutate_EmptyTrash(EmptyTrash, None, info, **kwargs)


def _mutate_EmptyCorpus(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:1115

    Port of EmptyCorpus.mutate
    """

    # Decorators applied to an inner function — see _mutate_UploadDocument.
    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_MEDIUM)
    def mutate(root, info, corpus_id) -> EmptyCorpus:
        from opencontractserver.corpuses.services import DocumentLifecycleService

        user = info.context.user

        try:
            corpus_pk = from_global_id(corpus_id)[1]
            # Service-layer fetch guarantees the corpus exists AND is visible
            # to the caller; the lifecycle service enforces DELETE permission.
            corpus = BaseService.get_or_none(
                Corpus, corpus_pk, user, request=info.context
            )
            if corpus is None:
                raise Corpus.DoesNotExist

            trashed_count, error = DocumentLifecycleService.empty_corpus(
                user=user,
                corpus=corpus,
                request=info.context,
            )

            if error:
                return EmptyCorpus(
                    ok=False,
                    message=error,
                    trashed_count=trashed_count,
                )

            return EmptyCorpus(
                ok=True,
                message=(
                    f"Moved {trashed_count} document(s) to trash and removed all "
                    "folders"
                ),
                trashed_count=trashed_count,
            )

        except Corpus.DoesNotExist:
            return EmptyCorpus(ok=False, message="Corpus not found", trashed_count=0)
        except Exception as e:
            # Keep the full detail (table/constraint names, paths) in the log, but
            # return a generic message so internal specifics never reach the client.
            logger.error("Failed to empty corpus %s: %s", corpus_id, e, exc_info=True)
            return EmptyCorpus(
                ok=False, message="Failed to empty corpus.", trashed_count=0
            )

    return mutate(root, info, **kwargs)


def m_empty_corpus(
    info: strawberry.Info,
    corpus_id: Annotated[
        str,
        strawberry.argument(
            name="corpusId", description="Global ID of the corpus to empty"
        ),
    ] = strawberry.UNSET,
) -> EmptyCorpus | None:
    kwargs = strip_unset({"corpus_id": corpus_id})
    return _mutate_EmptyCorpus(EmptyCorpus, None, info, **kwargs)


def _mutate_UploadAnnotatedDocument(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:584

    Port of UploadAnnotatedDocument.mutate
    """

    # Decorator applied to an inner function — see _mutate_UploadDocument.
    @login_required
    def mutate(
        root, info, target_corpus_id, document_import_data
    ) -> UploadAnnotatedDocument:

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

    return mutate(root, info, **kwargs)


def m_import_annotated_doc_to_corpus(
    info: strawberry.Info,
    document_import_data: Annotated[
        str, strawberry.argument(name="documentImportData")
    ] = strawberry.UNSET,
    target_corpus_id: Annotated[
        str, strawberry.argument(name="targetCorpusId")
    ] = strawberry.UNSET,
) -> UploadAnnotatedDocument | None:
    kwargs = strip_unset(
        {
            "document_import_data": document_import_data,
            "target_corpus_id": target_corpus_id,
        }
    )
    return _mutate_UploadAnnotatedDocument(
        UploadAnnotatedDocument, None, info, **kwargs
    )


def _mutate_StartCorpusExport(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:662

    Port of StartCorpusExport.mutate
    """

    # Decorators applied to an inner function — see _mutate_UploadDocument.
    @login_required
    @graphql_ratelimit(rate=RateLimits.EXPORT)
    def mutate(
        root,
        info,
        corpus_id: str,
        export_format: str,
        post_processors: list[str] | None = None,
        input_kwargs: dict | None = None,
        analyses_ids: list[str] | None = None,
        annotation_filter_mode: str = AnnotationFilterMode.CORPUS_LABELSET_ONLY.value,
        include_conversations: bool = False,
        include_action_trail: bool = False,
    ) -> StartCorpusExport:
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

            # Verify corpus visibility and READ permission before creating export.
            corpus = BaseService.get_or_none(
                Corpus, corpus_pk, info.context.user, request=info.context
            )
            if corpus is None or BaseService.require_permission(
                corpus,
                info.context.user,
                PermissionTypes.READ,
                request=info.context,
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
                info.context.user,
                export,
                [PermissionTypes.CRUD],
                request=info.context,
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

    return mutate(root, info, **kwargs)


def m_export_corpus(
    info: strawberry.Info,
    analyses_ids: Annotated[
        list[str | None] | None,
        strawberry.argument(
            name="analysesIds",
            description="Optional list of Graphene IDs for analyses that should be included in the export",
        ),
    ] = strawberry.UNSET,
    annotation_filter_mode: Annotated[
        enums.AnnotationFilterMode | None,
        strawberry.argument(
            name="annotationFilterMode",
            description="How to filter annotations - from corpus label set only, plus analyses, or analyses only",
        ),
    ] = enums.AnnotationFilterMode.CORPUS_LABELSET_ONLY,
    corpus_id: Annotated[
        str,
        strawberry.argument(
            name="corpusId",
            description="Graphene id of the corpus you want to package for export",
        ),
    ] = strawberry.UNSET,
    export_format: Annotated[
        enums.ExportType | None, strawberry.argument(name="exportFormat")
    ] = strawberry.UNSET,
    include_action_trail: Annotated[
        bool | None,
        strawberry.argument(
            name="includeActionTrail",
            description="Whether to include corpus action execution trail in the export (V2 format only)",
        ),
    ] = False,
    include_conversations: Annotated[
        bool | None,
        strawberry.argument(
            name="includeConversations",
            description="Whether to include conversations and messages in the export (V2 format only)",
        ),
    ] = False,
    input_kwargs: Annotated[
        GenericScalar | None,
        strawberry.argument(
            name="inputKwargs",
            description="Additional keyword arguments to pass to post-processors",
        ),
    ] = strawberry.UNSET,
    post_processors: Annotated[
        list[str | None] | None,
        strawberry.argument(
            name="postProcessors",
            description="List of fully qualified Python paths to post-processor functions to run",
        ),
    ] = strawberry.UNSET,
) -> StartCorpusExport | None:
    kwargs = strip_unset(
        {
            "analyses_ids": analyses_ids,
            "annotation_filter_mode": annotation_filter_mode,
            "corpus_id": corpus_id,
            "export_format": export_format,
            "include_action_trail": include_action_trail,
            "include_conversations": include_conversations,
            "input_kwargs": input_kwargs,
            "post_processors": post_processors,
        }
    )
    return _mutate_StartCorpusExport(StartCorpusExport, None, info, **kwargs)


def m_delete_export(
    info: strawberry.Info,
    id: Annotated[str, strawberry.argument(name="id")] = strawberry.UNSET,
) -> DeleteExport | None:
    kwargs = strip_unset({"id": id})
    return drf_deletion(
        payload_cls=DeleteExport,
        model=UserExport,
        lookup_field="id",
        root=None,
        info=info,
        kwargs=kwargs,
    )


MUTATION_FIELDS = {
    "upload_document": strawberry.field(
        resolver=m_upload_document, name="uploadDocument"
    ),
    "update_document": strawberry.field(
        resolver=m_update_document, name="updateDocument"
    ),
    "update_document_summary": strawberry.field(
        resolver=m_update_document_summary,
        name="updateDocumentSummary",
        description="Mutation to update a document's markdown summary for a specific corpus, creating a new version in the process.\nUsers can create/update summaries if:\n- No summary exists yet and they have permission on the corpus (public or their corpus)\n- A summary exists and they are the original author",
    ),
    "delete_document": strawberry.field(
        resolver=m_delete_document, name="deleteDocument"
    ),
    "delete_multiple_documents": strawberry.field(
        resolver=m_delete_multiple_documents, name="deleteMultipleDocuments"
    ),
    "upload_documents_zip": strawberry.field(
        resolver=m_upload_documents_zip,
        name="uploadDocumentsZip",
        description="Mutation for uploading multiple documents via a zip file.\nThe zip is stored as a temporary file and processed asynchronously.\nOnly files with allowed MIME types will be created as documents.",
    ),
    "retry_document_processing": strawberry.field(
        resolver=m_retry_document_processing,
        name="retryDocumentProcessing",
        description="Retry processing for a failed document.\n\nThis mutation allows users to manually trigger reprocessing of a document\nthat failed during the parsing pipeline. It's useful when transient errors\n(like network timeouts or service unavailability) have been resolved.\n\nRequirements:\n- Document must be in FAILED processing state\n- User must have UPDATE permission on the document",
    ),
    "restore_deleted_document": strawberry.field(
        resolver=m_restore_deleted_document,
        name="restoreDeletedDocument",
        description="Restore a soft-deleted document path within a corpus.\n\nDelegates to DocumentLifecycleService.restore_document() for:\n- Permission checking (corpus UPDATE permission)\n- Creating new DocumentPath with is_deleted=False",
    ),
    "restore_document_to_version": strawberry.field(
        resolver=m_restore_document_to_version,
        name="restoreDocumentToVersion",
        description="Restore a document to a previous content version.\nCreates a new version that is a copy of the specified version.",
    ),
    "permanently_delete_document": strawberry.field(
        resolver=m_permanently_delete_document,
        name="permanentlyDeleteDocument",
        description="Permanently delete a soft-deleted document from a corpus.\n\nThis is IRREVERSIBLE and removes:\n- All DocumentPath history for the document in this corpus\n- User annotations (non-structural) on the document\n- Relationships involving those annotations\n- DocumentSummaryRevision records\n- The Document itself if no other corpus references it\n\nRequires DELETE permission on the corpus.",
    ),
    "empty_trash": strawberry.field(
        resolver=m_empty_trash,
        name="emptyTrash",
        description="Permanently delete ALL soft-deleted documents in a corpus (empty trash).\n\nThis is IRREVERSIBLE and removes all documents currently in the corpus trash.\n\nRequires DELETE permission on the corpus.",
    ),
    "empty_corpus": strawberry.field(
        resolver=m_empty_corpus,
        name="emptyCorpus",
        description='Move EVERY document in a corpus to Trash and remove ALL of its folders.\n\nThis is the "empty everything" action. Documents are soft-deleted (they\nremain in the trash and are restorable until the trash is emptied); the\nfolder tree is removed. Nothing is permanently deleted here — callers can\nfollow up with ``emptyTrash`` to purge.\n\nRequires DELETE permission on the corpus.',
    ),
    "import_annotated_doc_to_corpus": strawberry.field(
        resolver=m_import_annotated_doc_to_corpus, name="importAnnotatedDocToCorpus"
    ),
    "export_corpus": strawberry.field(
        resolver=m_export_corpus,
        name="exportCorpus",
        description="Mutation entrypoint for starting a corpus export.\nNow refactored to optionally accept a list of Analysis IDs (analyses_ids)\nthat should be included in the export. If analyses_ids are provided, then\nonly annotations/labels from those analyses are included. Otherwise, all\nannotations/labels for the corpus are included.",
    ),
    "delete_export": strawberry.field(resolver=m_delete_export, name="deleteExport"),
}
