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

import logging
from typing import Annotated

import strawberry
from django.contrib.auth import get_user_model
from graphql_relay import from_global_id

from config.graphql._util import strip_unset
from config.graphql.core.auth import PermissionDenied
from config.graphql.core.relay import (
    register_type,
)
from config.graphql.ratelimits import RateLimits, graphql_ratelimit
from opencontractserver.corpuses.models import (
    Corpus,
    CorpusFolder,
)
from opencontractserver.corpuses.services import (
    FolderCRUDService,
    FolderDocumentService,
)
from opencontractserver.documents.models import Document
from opencontractserver.shared.services.base import BaseService

User = get_user_model()
logger = logging.getLogger(__name__)


@strawberry.type(
    name="CreateCorpusFolderMutation",
    description="Create a new folder in a corpus.\n\nDelegates to FolderCRUDService.create_folder() for:\n- Permission checking (corpus UPDATE permission)\n- Validation (unique name, parent in same corpus)\n- Folder creation",
)
class CreateCorpusFolderMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    folder: None | (
        Annotated[CorpusFolderType, strawberry.lazy("config.graphql.corpus_types")]
    ) = strawberry.field(name="folder", default=None)


register_type("CreateCorpusFolderMutation", CreateCorpusFolderMutation, model=None)


@strawberry.type(
    name="UpdateCorpusFolderMutation",
    description="Update folder properties (name, description, color, icon, tags).\n\nDelegates to FolderCRUDService.update_folder() for:\n- Permission checking (corpus UPDATE permission)\n- Validation (unique name within parent)\n- Folder update",
)
class UpdateCorpusFolderMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    folder: None | (
        Annotated[CorpusFolderType, strawberry.lazy("config.graphql.corpus_types")]
    ) = strawberry.field(name="folder", default=None)


register_type("UpdateCorpusFolderMutation", UpdateCorpusFolderMutation, model=None)


@strawberry.type(
    name="MoveCorpusFolderMutation",
    description="Move a folder to a different parent (or to root if parent_id is null).\n\nDelegates to FolderCRUDService.move_folder() for:\n- Permission checking (corpus UPDATE permission)\n- Validation (no self-move, no move into descendants, same corpus)\n- Folder move",
)
class MoveCorpusFolderMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    folder: None | (
        Annotated[CorpusFolderType, strawberry.lazy("config.graphql.corpus_types")]
    ) = strawberry.field(name="folder", default=None)


register_type("MoveCorpusFolderMutation", MoveCorpusFolderMutation, model=None)


@strawberry.type(
    name="DeleteCorpusFolderMutation",
    description="Delete a folder and optionally its contents.\n\nDelegates to FolderCRUDService.delete_folder() for:\n- Permission checking (corpus DELETE permission)\n- Child folder handling (reparent or cascade)\n- Document folder assignment cleanup via DocumentPath",
)
class DeleteCorpusFolderMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("DeleteCorpusFolderMutation", DeleteCorpusFolderMutation, model=None)


@strawberry.type(
    name="MoveDocumentToFolderMutation",
    description="Move a document to a specific folder (or to corpus root if folder_id is null).\n\nDelegates to FolderDocumentService.move_document_to_folder() for:\n- Permission checking (corpus UPDATE permission)\n- Validation (document in corpus, folder in corpus)\n- DocumentPath folder assignment update",
)
class MoveDocumentToFolderMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    document: None | (
        Annotated[DocumentType, strawberry.lazy("config.graphql.document_types")]
    ) = strawberry.field(name="document", default=None)


register_type("MoveDocumentToFolderMutation", MoveDocumentToFolderMutation, model=None)


@strawberry.type(
    name="MoveDocumentsToFolderMutation",
    description="Move multiple documents to a specific folder in bulk.\n\nDelegates to FolderDocumentService.move_documents_to_folder() for:\n- Permission checking (corpus UPDATE permission)\n- Validation (all documents in corpus, folder in corpus)\n- Bulk DocumentPath folder assignment update",
)
class MoveDocumentsToFolderMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    moved_count: int | None = strawberry.field(
        name="movedCount",
        description="Number of documents successfully moved",
        default=None,
    )


register_type(
    "MoveDocumentsToFolderMutation", MoveDocumentsToFolderMutation, model=None
)


def _mutate_CreateCorpusFolderMutation(
    payload_cls,
    root,
    info,
    corpus_id,
    name,
    parent_id=None,
    description="",
    color="#05313d",
    icon="folder",
    tags=None,
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_folder_mutations.py:67

    Port of CreateCorpusFolderMutation.mutate
    """
    # @login_required (graphql_jwt) — inlined because mutate stubs take
    # ``payload_cls`` as their first positional argument, which does not
    # match core.auth's ``(root, info, ...)`` calling convention.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    # @graphql_ratelimit is applied to an inner ``mutate`` so the calling
    # convention (root, info, ...) and the rate-limit cache group ("mutate")
    # match the graphene original.
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(
        root,
        info,
        corpus_id,
        name,
        parent_id=None,
        description="",
        color="#05313d",
        icon="folder",
        tags=None,
    ):
        user = info.context.user

        try:
            corpus_pk = from_global_id(corpus_id)[1]
            corpus = BaseService.get_or_none(
                Corpus, corpus_pk, user, request=info.context
            )
            if corpus is None:
                raise Corpus.DoesNotExist

            # Get parent folder if provided (scoped to corpus)
            parent = None
            if parent_id:
                parent_pk = from_global_id(parent_id)[1]
                parent = CorpusFolder.objects.get(pk=parent_pk, corpus=corpus)

            # Delegate to service - handles permission checks, validation, creation
            folder, error = FolderCRUDService.create_folder(
                user=user,
                corpus=corpus,
                name=name,
                parent=parent,
                description=description,
                color=color,
                icon=icon,
                tags=tags,
                request=info.context,
            )

            if error:
                return payload_cls(
                    ok=False,
                    message=error,
                    folder=None,
                )

            return payload_cls(
                ok=True,
                message="Folder created successfully",
                folder=folder,
            )

        except (Corpus.DoesNotExist, CorpusFolder.DoesNotExist):
            return payload_cls(
                ok=False,
                message="Resource not found",
                folder=None,
            )
        except Exception as e:
            logger.exception("Error creating folder")
            return payload_cls(
                ok=False,
                message=f"Failed to create folder: {str(e)}",
                folder=None,
            )

    return mutate(
        root,
        info,
        corpus_id=corpus_id,
        name=name,
        parent_id=parent_id,
        description=description,
        color=color,
        icon=icon,
        tags=tags,
    )


def m_create_corpus_folder(
    info: strawberry.Info,
    color: Annotated[
        str | None,
        strawberry.argument(name="color", description="Folder color (hex code)"),
    ] = strawberry.UNSET,
    corpus_id: Annotated[
        strawberry.ID,
        strawberry.argument(
            name="corpusId", description="Corpus ID to create the folder in"
        ),
    ] = strawberry.UNSET,
    description: Annotated[
        str | None,
        strawberry.argument(name="description", description="Folder description"),
    ] = strawberry.UNSET,
    icon: Annotated[
        str | None,
        strawberry.argument(name="icon", description="Folder icon identifier"),
    ] = strawberry.UNSET,
    name: Annotated[
        str, strawberry.argument(name="name", description="Folder name")
    ] = strawberry.UNSET,
    parent_id: Annotated[
        strawberry.ID | None,
        strawberry.argument(
            name="parentId", description="Parent folder ID (omit for root-level folder)"
        ),
    ] = strawberry.UNSET,
    tags: Annotated[
        list[str | None] | None,
        strawberry.argument(name="tags", description="List of tags"),
    ] = strawberry.UNSET,
) -> CreateCorpusFolderMutation | None:
    kwargs = strip_unset(
        {
            "color": color,
            "corpus_id": corpus_id,
            "description": description,
            "icon": icon,
            "name": name,
            "parent_id": parent_id,
            "tags": tags,
        }
    )
    return _mutate_CreateCorpusFolderMutation(
        CreateCorpusFolderMutation, None, info, **kwargs
    )


def _mutate_UpdateCorpusFolderMutation(
    payload_cls,
    root,
    info,
    folder_id,
    name=None,
    description=None,
    color=None,
    icon=None,
    tags=None,
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_folder_mutations.py:158

    Port of UpdateCorpusFolderMutation.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_CreateCorpusFolderMutation.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    # @graphql_ratelimit on an inner ``mutate`` — see _mutate_CreateCorpusFolderMutation.
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(
        root,
        info,
        folder_id,
        name=None,
        description=None,
        color=None,
        icon=None,
        tags=None,
    ):
        user = info.context.user

        try:
            folder_pk = from_global_id(folder_id)[1]
            folder = CorpusFolder.objects.select_related("corpus").get(pk=folder_pk)
            # Verify user can see the parent corpus to prevent IDOR
            if (
                not BaseService.filter_visible(Corpus, user, request=info.context)
                .filter(pk=folder.corpus_id)
                .exists()
            ):
                raise CorpusFolder.DoesNotExist

            # Delegate to service - handles permission checks, validation, update
            success, error = FolderCRUDService.update_folder(
                user=user,
                folder=folder,
                name=name,
                description=description,
                color=color,
                icon=icon,
                tags=tags,
                request=info.context,
            )

            if not success:
                return payload_cls(
                    ok=False,
                    message=error,
                    folder=None,
                )

            # Refresh folder from DB to get updated values
            folder.refresh_from_db()

            return payload_cls(
                ok=True,
                message="Folder updated successfully",
                folder=folder,
            )

        except CorpusFolder.DoesNotExist:
            return payload_cls(
                ok=False,
                message="Folder not found",
                folder=None,
            )
        except Exception as e:
            logger.exception("Error updating folder")
            return payload_cls(
                ok=False,
                message=f"Failed to update folder: {str(e)}",
                folder=None,
            )

    return mutate(
        root,
        info,
        folder_id=folder_id,
        name=name,
        description=description,
        color=color,
        icon=icon,
        tags=tags,
    )


def m_update_corpus_folder(
    info: strawberry.Info,
    color: Annotated[
        str | None,
        strawberry.argument(name="color", description="New color (hex code)"),
    ] = strawberry.UNSET,
    description: Annotated[
        str | None,
        strawberry.argument(name="description", description="New description"),
    ] = strawberry.UNSET,
    folder_id: Annotated[
        strawberry.ID,
        strawberry.argument(name="folderId", description="Folder ID to update"),
    ] = strawberry.UNSET,
    icon: Annotated[
        str | None,
        strawberry.argument(name="icon", description="New icon identifier"),
    ] = strawberry.UNSET,
    name: Annotated[
        str | None, strawberry.argument(name="name", description="New folder name")
    ] = strawberry.UNSET,
    tags: Annotated[
        list[str | None] | None,
        strawberry.argument(name="tags", description="New list of tags"),
    ] = strawberry.UNSET,
) -> UpdateCorpusFolderMutation | None:
    kwargs = strip_unset(
        {
            "color": color,
            "description": description,
            "folder_id": folder_id,
            "icon": icon,
            "name": name,
            "tags": tags,
        }
    )
    return _mutate_UpdateCorpusFolderMutation(
        UpdateCorpusFolderMutation, None, info, **kwargs
    )


def _mutate_MoveCorpusFolderMutation(
    payload_cls, root, info, folder_id, new_parent_id=None
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_folder_mutations.py:246

    Port of MoveCorpusFolderMutation.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_CreateCorpusFolderMutation.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    # @graphql_ratelimit on an inner ``mutate`` — see _mutate_CreateCorpusFolderMutation.
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(root, info, folder_id, new_parent_id=None):
        user = info.context.user

        try:
            folder_pk = from_global_id(folder_id)[1]
            folder = CorpusFolder.objects.select_related("corpus").get(pk=folder_pk)
            # Verify user can see the parent corpus
            if (
                not BaseService.filter_visible(Corpus, user, request=info.context)
                .filter(pk=folder.corpus_id)
                .exists()
            ):
                raise CorpusFolder.DoesNotExist

            # Get new parent if provided (scoped to same corpus)
            new_parent = None
            if new_parent_id:
                new_parent_pk = from_global_id(new_parent_id)[1]
                new_parent = CorpusFolder.objects.get(
                    pk=new_parent_pk, corpus=folder.corpus
                )

            # Delegate to service - handles permission checks, validation, move
            success, error = FolderCRUDService.move_folder(
                user=user,
                folder=folder,
                new_parent=new_parent,
                request=info.context,
            )

            if not success:
                return payload_cls(
                    ok=False,
                    message=error,
                    folder=None,
                )

            # Refresh folder from DB to get updated parent
            folder.refresh_from_db()

            return payload_cls(
                ok=True,
                message="Folder moved successfully",
                folder=folder,
            )

        except CorpusFolder.DoesNotExist:
            return payload_cls(
                ok=False,
                message="Folder not found",
                folder=None,
            )
        except Exception as e:
            logger.exception("Error moving folder")
            return payload_cls(
                ok=False,
                message=f"Failed to move folder: {str(e)}",
                folder=None,
            )

    return mutate(root, info, folder_id=folder_id, new_parent_id=new_parent_id)


def m_move_corpus_folder(
    info: strawberry.Info,
    folder_id: Annotated[
        strawberry.ID,
        strawberry.argument(name="folderId", description="Folder ID to move"),
    ] = strawberry.UNSET,
    new_parent_id: Annotated[
        strawberry.ID | None,
        strawberry.argument(
            name="newParentId",
            description="New parent folder ID (null to move to root)",
        ),
    ] = strawberry.UNSET,
) -> MoveCorpusFolderMutation | None:
    kwargs = strip_unset({"folder_id": folder_id, "new_parent_id": new_parent_id})
    return _mutate_MoveCorpusFolderMutation(
        MoveCorpusFolderMutation, None, info, **kwargs
    )


def _mutate_DeleteCorpusFolderMutation(
    payload_cls, root, info, folder_id, delete_contents=False
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_folder_mutations.py:329

    Port of DeleteCorpusFolderMutation.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_CreateCorpusFolderMutation.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    # @graphql_ratelimit on an inner ``mutate`` — see _mutate_CreateCorpusFolderMutation.
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(root, info, folder_id, delete_contents=False):
        user = info.context.user

        try:
            folder_pk = from_global_id(folder_id)[1]
            folder = CorpusFolder.objects.select_related("corpus").get(pk=folder_pk)
            # Verify user can see the parent corpus
            if (
                not BaseService.filter_visible(Corpus, user, request=info.context)
                .filter(pk=folder.corpus_id)
                .exists()
            ):
                raise CorpusFolder.DoesNotExist

            # Delegate to service - handles permission checks, cleanup, deletion
            success, error = FolderCRUDService.delete_folder(
                user=user,
                folder=folder,
                move_children_to_parent=not delete_contents,
                request=info.context,
            )

            if not success:
                return payload_cls(
                    ok=False,
                    message=error,
                )

            return payload_cls(
                ok=True,
                message="Folder deleted successfully",
            )

        except CorpusFolder.DoesNotExist:
            return payload_cls(
                ok=False,
                message="Folder not found",
            )
        except Exception as e:
            logger.exception("Error deleting folder")
            return payload_cls(
                ok=False,
                message=f"Failed to delete folder: {str(e)}",
            )

    return mutate(root, info, folder_id=folder_id, delete_contents=delete_contents)


def m_delete_corpus_folder(
    info: strawberry.Info,
    delete_contents: Annotated[
        bool | None,
        strawberry.argument(
            name="deleteContents",
            description="If true, delete subfolders; if false, move to parent",
        ),
    ] = False,
    folder_id: Annotated[
        strawberry.ID,
        strawberry.argument(name="folderId", description="Folder ID to delete"),
    ] = strawberry.UNSET,
) -> DeleteCorpusFolderMutation | None:
    kwargs = strip_unset({"delete_contents": delete_contents, "folder_id": folder_id})
    return _mutate_DeleteCorpusFolderMutation(
        DeleteCorpusFolderMutation, None, info, **kwargs
    )


def _mutate_MoveDocumentToFolderMutation(
    payload_cls, root, info, document_id, corpus_id, folder_id=None
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_folder_mutations.py:402

    Port of MoveDocumentToFolderMutation.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_CreateCorpusFolderMutation.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    # @graphql_ratelimit on an inner ``mutate`` — see _mutate_CreateCorpusFolderMutation.
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(root, info, document_id, corpus_id, folder_id=None):
        user = info.context.user

        try:
            document_pk = from_global_id(document_id)[1]
            corpus_pk = from_global_id(corpus_id)[1]

            # Get objects with visibility filtering
            document = BaseService.get_or_none(
                Document, document_pk, user, request=info.context
            )
            if document is None:
                raise Document.DoesNotExist
            corpus = BaseService.get_or_none(
                Corpus, corpus_pk, user, request=info.context
            )
            if corpus is None:
                raise Corpus.DoesNotExist

            # Get folder if provided
            folder = None
            if folder_id:
                folder_pk = from_global_id(folder_id)[1]
                folder = CorpusFolder.objects.get(pk=folder_pk)

            # Delegate to service - handles permission checks, validation, dual-system update
            success, error = FolderDocumentService.move_document_to_folder(
                user=user,
                document=document,
                corpus=corpus,
                folder=folder,
                request=info.context,
            )

            if not success:
                return payload_cls(
                    ok=False,
                    message=error,
                    document=None,
                )

            return payload_cls(
                ok=True,
                message="Document moved successfully",
                document=document,
            )

        except Document.DoesNotExist:
            return payload_cls(
                ok=False,
                message="Document not found",
                document=None,
            )
        except Corpus.DoesNotExist:
            return payload_cls(
                ok=False,
                message="Corpus not found",
                document=None,
            )
        except CorpusFolder.DoesNotExist:
            return payload_cls(
                ok=False,
                message="Folder not found",
                document=None,
            )
        except Exception as e:
            logger.exception("Error moving document")
            return payload_cls(
                ok=False,
                message=f"Failed to move document: {str(e)}",
                document=None,
            )

    return mutate(
        root, info, document_id=document_id, corpus_id=corpus_id, folder_id=folder_id
    )


def m_move_document_to_folder(
    info: strawberry.Info,
    corpus_id: Annotated[
        strawberry.ID,
        strawberry.argument(
            name="corpusId", description="Corpus ID where the document is located"
        ),
    ] = strawberry.UNSET,
    document_id: Annotated[
        strawberry.ID,
        strawberry.argument(name="documentId", description="Document ID to move"),
    ] = strawberry.UNSET,
    folder_id: Annotated[
        strawberry.ID | None,
        strawberry.argument(
            name="folderId", description="Folder ID to move to (null for corpus root)"
        ),
    ] = strawberry.UNSET,
) -> MoveDocumentToFolderMutation | None:
    kwargs = strip_unset(
        {"corpus_id": corpus_id, "document_id": document_id, "folder_id": folder_id}
    )
    return _mutate_MoveDocumentToFolderMutation(
        MoveDocumentToFolderMutation, None, info, **kwargs
    )


def _mutate_MoveDocumentsToFolderMutation(
    payload_cls, root, info, document_ids, corpus_id, folder_id=None
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_folder_mutations.py:505

    Port of MoveDocumentsToFolderMutation.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_CreateCorpusFolderMutation.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    # @graphql_ratelimit on an inner ``mutate`` — see _mutate_CreateCorpusFolderMutation.
    @graphql_ratelimit(rate=RateLimits.WRITE_HEAVY)
    def mutate(root, info, document_ids, corpus_id, folder_id=None):
        user = info.context.user

        try:
            corpus_pk = from_global_id(corpus_id)[1]
            corpus = BaseService.get_or_none(
                Corpus, corpus_pk, user, request=info.context
            )
            if corpus is None:
                raise Corpus.DoesNotExist

            # Get folder if provided
            folder = None
            if folder_id:
                folder_pk = from_global_id(folder_id)[1]
                folder = CorpusFolder.objects.get(pk=folder_pk)

            # Convert document IDs from global IDs to integer PKs
            doc_pks = [int(from_global_id(doc_id)[1]) for doc_id in document_ids]

            # Delegate to service - handles permission checks, validation, bulk update
            moved_count, error = FolderDocumentService.move_documents_to_folder(
                user=user,
                document_ids=doc_pks,
                corpus=corpus,
                folder=folder,
                request=info.context,
            )

            if error:
                return payload_cls(
                    ok=False,
                    message=error,
                    moved_count=0,
                )

            return payload_cls(
                ok=True,
                message=f"Successfully moved {moved_count} document(s)",
                moved_count=moved_count,
            )

        except Corpus.DoesNotExist:
            return payload_cls(
                ok=False,
                message="Corpus not found",
                moved_count=0,
            )
        except CorpusFolder.DoesNotExist:
            return payload_cls(
                ok=False,
                message="Folder not found",
                moved_count=0,
            )
        except Exception as e:
            logger.exception("Error moving documents")
            return payload_cls(
                ok=False,
                message=f"Failed to move documents: {str(e)}",
                moved_count=0,
            )

    return mutate(
        root, info, document_ids=document_ids, corpus_id=corpus_id, folder_id=folder_id
    )


def m_move_documents_to_folder(
    info: strawberry.Info,
    corpus_id: Annotated[
        strawberry.ID,
        strawberry.argument(
            name="corpusId", description="Corpus ID where the documents are located"
        ),
    ] = strawberry.UNSET,
    document_ids: Annotated[
        list[strawberry.ID | None],
        strawberry.argument(
            name="documentIds", description="List of document IDs to move"
        ),
    ] = strawberry.UNSET,
    folder_id: Annotated[
        strawberry.ID | None,
        strawberry.argument(
            name="folderId", description="Folder ID to move to (null for corpus root)"
        ),
    ] = strawberry.UNSET,
) -> MoveDocumentsToFolderMutation | None:
    kwargs = strip_unset(
        {"corpus_id": corpus_id, "document_ids": document_ids, "folder_id": folder_id}
    )
    return _mutate_MoveDocumentsToFolderMutation(
        MoveDocumentsToFolderMutation, None, info, **kwargs
    )


MUTATION_FIELDS = {
    "create_corpus_folder": strawberry.field(
        resolver=m_create_corpus_folder,
        name="createCorpusFolder",
        description="Create a new folder in a corpus.\n\nDelegates to FolderCRUDService.create_folder() for:\n- Permission checking (corpus UPDATE permission)\n- Validation (unique name, parent in same corpus)\n- Folder creation",
    ),
    "update_corpus_folder": strawberry.field(
        resolver=m_update_corpus_folder,
        name="updateCorpusFolder",
        description="Update folder properties (name, description, color, icon, tags).\n\nDelegates to FolderCRUDService.update_folder() for:\n- Permission checking (corpus UPDATE permission)\n- Validation (unique name within parent)\n- Folder update",
    ),
    "move_corpus_folder": strawberry.field(
        resolver=m_move_corpus_folder,
        name="moveCorpusFolder",
        description="Move a folder to a different parent (or to root if parent_id is null).\n\nDelegates to FolderCRUDService.move_folder() for:\n- Permission checking (corpus UPDATE permission)\n- Validation (no self-move, no move into descendants, same corpus)\n- Folder move",
    ),
    "delete_corpus_folder": strawberry.field(
        resolver=m_delete_corpus_folder,
        name="deleteCorpusFolder",
        description="Delete a folder and optionally its contents.\n\nDelegates to FolderCRUDService.delete_folder() for:\n- Permission checking (corpus DELETE permission)\n- Child folder handling (reparent or cascade)\n- Document folder assignment cleanup via DocumentPath",
    ),
    "move_document_to_folder": strawberry.field(
        resolver=m_move_document_to_folder,
        name="moveDocumentToFolder",
        description="Move a document to a specific folder (or to corpus root if folder_id is null).\n\nDelegates to FolderDocumentService.move_document_to_folder() for:\n- Permission checking (corpus UPDATE permission)\n- Validation (document in corpus, folder in corpus)\n- DocumentPath folder assignment update",
    ),
    "move_documents_to_folder": strawberry.field(
        resolver=m_move_documents_to_folder,
        name="moveDocumentsToFolder",
        description="Move multiple documents to a specific folder in bulk.\n\nDelegates to FolderDocumentService.move_documents_to_folder() for:\n- Permission checking (corpus UPDATE permission)\n- Validation (all documents in corpus, folder in corpus)\n- Bulk DocumentPath folder assignment update",
    ),
}
