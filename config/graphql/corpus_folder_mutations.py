"""
GraphQL mutations for the corpus folder system.

This module implements folder management functionality including:
- Creating, updating, moving, and deleting folders
- Moving documents to/from folders
- Bulk document operations

All mutations delegate to the segmented corpus services
(``FolderCRUDService`` / ``FolderDocumentService``) for business logic,
permission checks, and consistency via DocumentPath.
"""

import logging

import graphene
from django.contrib.auth import get_user_model
from graphql_jwt.decorators import login_required
from graphql_relay import from_global_id

from config.graphql.graphene_types import CorpusFolderType, DocumentType
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


class CreateCorpusFolderMutation(graphene.Mutation):
    """Create a new folder in a corpus.

    Delegates to FolderCRUDService.create_folder() for:
    - Permission checking (corpus UPDATE permission)
    - Validation (unique name, parent in same corpus)
    - Folder creation
    """

    class Arguments:
        corpus_id = graphene.ID(
            required=True, description="Corpus ID to create the folder in"
        )
        name = graphene.String(required=True, description="Folder name")
        parent_id = graphene.ID(
            required=False,
            description="Parent folder ID (omit for root-level folder)",
        )
        description = graphene.String(required=False, description="Folder description")
        color = graphene.String(required=False, description="Folder color (hex code)")
        icon = graphene.String(required=False, description="Folder icon identifier")
        tags = graphene.List(graphene.String, description="List of tags")

    ok = graphene.Boolean()
    message = graphene.String()
    folder = graphene.Field(CorpusFolderType)

    @login_required
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
    ) -> "CreateCorpusFolderMutation":
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
                return CreateCorpusFolderMutation(
                    ok=False,
                    message=error,
                    folder=None,
                )

            return CreateCorpusFolderMutation(
                ok=True,
                message="Folder created successfully",
                folder=folder,
            )

        except (Corpus.DoesNotExist, CorpusFolder.DoesNotExist):
            return CreateCorpusFolderMutation(
                ok=False,
                message="Resource not found",
                folder=None,
            )
        except Exception as e:
            logger.exception("Error creating folder")
            return CreateCorpusFolderMutation(
                ok=False,
                message=f"Failed to create folder: {str(e)}",
                folder=None,
            )


class UpdateCorpusFolderMutation(graphene.Mutation):
    """Update folder properties (name, description, color, icon, tags).

    Delegates to FolderCRUDService.update_folder() for:
    - Permission checking (corpus UPDATE permission)
    - Validation (unique name within parent)
    - Folder update
    """

    class Arguments:
        folder_id = graphene.ID(required=True, description="Folder ID to update")
        name = graphene.String(required=False, description="New folder name")
        description = graphene.String(required=False, description="New description")
        color = graphene.String(required=False, description="New color (hex code)")
        icon = graphene.String(required=False, description="New icon identifier")
        tags = graphene.List(graphene.String, description="New list of tags")

    ok = graphene.Boolean()
    message = graphene.String()
    folder = graphene.Field(CorpusFolderType)

    @login_required
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
    ) -> "UpdateCorpusFolderMutation":
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
                return UpdateCorpusFolderMutation(
                    ok=False,
                    message=error,
                    folder=None,
                )

            # Refresh folder from DB to get updated values
            folder.refresh_from_db()

            return UpdateCorpusFolderMutation(
                ok=True,
                message="Folder updated successfully",
                folder=folder,
            )

        except CorpusFolder.DoesNotExist:
            return UpdateCorpusFolderMutation(
                ok=False,
                message="Folder not found",
                folder=None,
            )
        except Exception as e:
            logger.exception("Error updating folder")
            return UpdateCorpusFolderMutation(
                ok=False,
                message=f"Failed to update folder: {str(e)}",
                folder=None,
            )


class MoveCorpusFolderMutation(graphene.Mutation):
    """Move a folder to a different parent (or to root if parent_id is null).

    Delegates to FolderCRUDService.move_folder() for:
    - Permission checking (corpus UPDATE permission)
    - Validation (no self-move, no move into descendants, same corpus)
    - Folder move
    """

    class Arguments:
        folder_id = graphene.ID(required=True, description="Folder ID to move")
        new_parent_id = graphene.ID(
            required=False,
            description="New parent folder ID (null to move to root)",
        )

    ok = graphene.Boolean()
    message = graphene.String()
    folder = graphene.Field(CorpusFolderType)

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(root, info, folder_id, new_parent_id=None) -> "MoveCorpusFolderMutation":
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
                return MoveCorpusFolderMutation(
                    ok=False,
                    message=error,
                    folder=None,
                )

            # Refresh folder from DB to get updated parent
            folder.refresh_from_db()

            return MoveCorpusFolderMutation(
                ok=True,
                message="Folder moved successfully",
                folder=folder,
            )

        except CorpusFolder.DoesNotExist:
            return MoveCorpusFolderMutation(
                ok=False,
                message="Folder not found",
                folder=None,
            )
        except Exception as e:
            logger.exception("Error moving folder")
            return MoveCorpusFolderMutation(
                ok=False,
                message=f"Failed to move folder: {str(e)}",
                folder=None,
            )


class DeleteCorpusFolderMutation(graphene.Mutation):
    """Delete a folder and optionally its contents.

    Delegates to FolderCRUDService.delete_folder() for:
    - Permission checking (corpus DELETE permission)
    - Child folder handling (reparent or cascade)
    - Document folder assignment cleanup via DocumentPath
    """

    class Arguments:
        folder_id = graphene.ID(required=True, description="Folder ID to delete")
        delete_contents = graphene.Boolean(
            required=False,
            default_value=False,
            description="If true, delete subfolders; if false, move to parent",
        )

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(
        root, info, folder_id, delete_contents=False
    ) -> "DeleteCorpusFolderMutation":
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
                return DeleteCorpusFolderMutation(
                    ok=False,
                    message=error,
                )

            return DeleteCorpusFolderMutation(
                ok=True,
                message="Folder deleted successfully",
            )

        except CorpusFolder.DoesNotExist:
            return DeleteCorpusFolderMutation(
                ok=False,
                message="Folder not found",
            )
        except Exception as e:
            logger.exception("Error deleting folder")
            return DeleteCorpusFolderMutation(
                ok=False,
                message=f"Failed to delete folder: {str(e)}",
            )


class MoveDocumentToFolderMutation(graphene.Mutation):
    """Move a document to a specific folder (or to corpus root if folder_id is null).

    Delegates to FolderDocumentService.move_document_to_folder() for:
    - Permission checking (corpus UPDATE permission)
    - Validation (document in corpus, folder in corpus)
    - DocumentPath folder assignment update
    """

    class Arguments:
        document_id = graphene.ID(required=True, description="Document ID to move")
        corpus_id = graphene.ID(
            required=True, description="Corpus ID where the document is located"
        )
        folder_id = graphene.ID(
            required=False,
            description="Folder ID to move to (null for corpus root)",
        )

    ok = graphene.Boolean()
    message = graphene.String()
    document = graphene.Field(DocumentType)

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(
        root, info, document_id, corpus_id, folder_id=None
    ) -> "MoveDocumentToFolderMutation":
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
                return MoveDocumentToFolderMutation(
                    ok=False,
                    message=error,
                    document=None,
                )

            return MoveDocumentToFolderMutation(
                ok=True,
                message="Document moved successfully",
                document=document,
            )

        except Document.DoesNotExist:
            return MoveDocumentToFolderMutation(
                ok=False,
                message="Document not found",
                document=None,
            )
        except Corpus.DoesNotExist:
            return MoveDocumentToFolderMutation(
                ok=False,
                message="Corpus not found",
                document=None,
            )
        except CorpusFolder.DoesNotExist:
            return MoveDocumentToFolderMutation(
                ok=False,
                message="Folder not found",
                document=None,
            )
        except Exception as e:
            logger.exception("Error moving document")
            return MoveDocumentToFolderMutation(
                ok=False,
                message=f"Failed to move document: {str(e)}",
                document=None,
            )


class MoveDocumentsToFolderMutation(graphene.Mutation):
    """Move multiple documents to a specific folder in bulk.

    Delegates to FolderDocumentService.move_documents_to_folder() for:
    - Permission checking (corpus UPDATE permission)
    - Validation (all documents in corpus, folder in corpus)
    - Bulk DocumentPath folder assignment update
    """

    class Arguments:
        document_ids = graphene.List(
            graphene.ID, required=True, description="List of document IDs to move"
        )
        corpus_id = graphene.ID(
            required=True, description="Corpus ID where the documents are located"
        )
        folder_id = graphene.ID(
            required=False,
            description="Folder ID to move to (null for corpus root)",
        )

    ok = graphene.Boolean()
    message = graphene.String()
    moved_count = graphene.Int(description="Number of documents successfully moved")

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_HEAVY)
    def mutate(
        root, info, document_ids, corpus_id, folder_id=None
    ) -> "MoveDocumentsToFolderMutation":
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
                return MoveDocumentsToFolderMutation(
                    ok=False,
                    message=error,
                    moved_count=0,
                )

            return MoveDocumentsToFolderMutation(
                ok=True,
                message=f"Successfully moved {moved_count} document(s)",
                moved_count=moved_count,
            )

        except Corpus.DoesNotExist:
            return MoveDocumentsToFolderMutation(
                ok=False,
                message="Corpus not found",
                moved_count=0,
            )
        except CorpusFolder.DoesNotExist:
            return MoveDocumentsToFolderMutation(
                ok=False,
                message="Folder not found",
                moved_count=0,
            )
        except Exception as e:
            logger.exception("Error moving documents")
            return MoveDocumentsToFolderMutation(
                ok=False,
                message=f"Failed to move documents: {str(e)}",
                moved_count=0,
            )
