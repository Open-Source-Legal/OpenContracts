"""
GraphQL mutations for the corpus folder system.

This module implements folder management functionality including:
- Creating, updating, moving, and deleting folders
- Moving documents to/from folders
- Bulk document operations
"""

import logging

import graphene
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from graphql_jwt.decorators import login_required
from graphql_relay import from_global_id

from config.graphql.graphene_types import CorpusFolderType, DocumentType
from config.graphql.ratelimits import RateLimits, graphql_ratelimit
from opencontractserver.corpuses.models import (
    Corpus,
    CorpusDocumentFolder,
    CorpusFolder,
)
from opencontractserver.documents.models import Document
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import user_has_permission_for_obj

User = get_user_model()
logger = logging.getLogger(__name__)


class CreateCorpusFolderMutation(graphene.Mutation):
    """Create a new folder in a corpus."""

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
    ):
        user = info.context.user

        try:
            corpus_pk = from_global_id(corpus_id)[1]

            # Check corpus permissions - user must have UPDATE permission or be creator
            # Note: is_public grants READ-ONLY access, not write access
            corpus = Corpus.objects.get(pk=corpus_pk)
            if not (
                corpus.creator == user
                or user_has_permission_for_obj(
                    user, corpus, PermissionTypes.UPDATE, include_group_permissions=True
                )
            ):
                return CreateCorpusFolderMutation(
                    ok=False,
                    message="You do not have permission to create folders in this corpus",
                    folder=None,
                )

            # Validate and get parent folder if provided
            parent = None
            if parent_id:
                parent_pk = from_global_id(parent_id)[1]
                parent = CorpusFolder.objects.get(pk=parent_pk)

                # Verify parent is in the same corpus
                if parent.corpus_id != corpus.id:
                    return CreateCorpusFolderMutation(
                        ok=False,
                        message="Parent folder must be in the same corpus",
                        folder=None,
                    )

            # Create folder
            folder = CorpusFolder(
                name=name,
                corpus=corpus,
                parent=parent,
                description=description,
                color=color,
                icon=icon,
                tags=tags or [],
                creator=user,
            )

            # This will trigger validation (clean) and save
            folder.save()

            return CreateCorpusFolderMutation(
                ok=True,
                message="Folder created successfully",
                folder=folder,
            )

        except Corpus.DoesNotExist:
            return CreateCorpusFolderMutation(
                ok=False,
                message="Corpus not found",
                folder=None,
            )
        except CorpusFolder.DoesNotExist:
            return CreateCorpusFolderMutation(
                ok=False,
                message="Parent folder not found",
                folder=None,
            )
        except IntegrityError as e:
            # This typically means duplicate folder name under same parent
            if "unique constraint" in str(e).lower():
                return CreateCorpusFolderMutation(
                    ok=False,
                    message=f"A folder named '{name}' already exists in this location",
                    folder=None,
                )
            logger.exception("Integrity error creating folder")
            return CreateCorpusFolderMutation(
                ok=False,
                message=f"Database error creating folder: {str(e)}",
                folder=None,
            )
        except ValidationError as e:
            return CreateCorpusFolderMutation(
                ok=False,
                message=f"Validation error: {str(e)}",
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
    """Update folder properties (name, description, color, icon, tags)."""

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
    ):
        user = info.context.user

        try:
            folder_pk = from_global_id(folder_id)[1]
            folder = CorpusFolder.objects.get(pk=folder_pk)

            # Check permission - user must have UPDATE permission or be creator
            # Note: is_public grants READ-ONLY access, not write access
            if not (
                folder.corpus.creator == user
                or user_has_permission_for_obj(
                    user,
                    folder.corpus,
                    PermissionTypes.UPDATE,
                    include_group_permissions=True,
                )
            ):
                return UpdateCorpusFolderMutation(
                    ok=False,
                    message="You do not have permission to update folders in this corpus",
                    folder=None,
                )

            # Update provided fields
            if name is not None:
                folder.name = name
            if description is not None:
                folder.description = description
            if color is not None:
                folder.color = color
            if icon is not None:
                folder.icon = icon
            if tags is not None:
                folder.tags = tags

            # Save with validation
            folder.save()

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
        except IntegrityError as e:
            if "unique constraint" in str(e).lower():
                return UpdateCorpusFolderMutation(
                    ok=False,
                    message=f"A folder named '{name}' already exists in this location",
                    folder=None,
                )
            logger.exception("Integrity error updating folder")
            return UpdateCorpusFolderMutation(
                ok=False,
                message=f"Database error updating folder: {str(e)}",
                folder=None,
            )
        except ValidationError as e:
            return UpdateCorpusFolderMutation(
                ok=False,
                message=f"Validation error: {str(e)}",
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
    """Move a folder to a different parent (or to root if parent_id is null)."""

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
    def mutate(root, info, folder_id, new_parent_id=None):
        user = info.context.user

        try:
            folder_pk = from_global_id(folder_id)[1]
            folder = CorpusFolder.objects.get(pk=folder_pk)

            # Check permission - user must have UPDATE permission or be creator
            # Note: is_public grants READ-ONLY access, not write access
            if not (
                folder.corpus.creator == user
                or user_has_permission_for_obj(
                    user,
                    folder.corpus,
                    PermissionTypes.UPDATE,
                    include_group_permissions=True,
                )
            ):
                return MoveCorpusFolderMutation(
                    ok=False,
                    message="You do not have permission to move folders in this corpus",
                    folder=None,
                )

            # Get new parent if provided
            new_parent = None
            if new_parent_id:
                new_parent_pk = from_global_id(new_parent_id)[1]
                new_parent = CorpusFolder.objects.get(pk=new_parent_pk)

                # Verify new parent is in the same corpus
                if new_parent.corpus_id != folder.corpus_id:
                    return MoveCorpusFolderMutation(
                        ok=False,
                        message="Cannot move folder to a different corpus",
                        folder=None,
                    )

                # Prevent moving a folder into itself or its descendants
                if new_parent == folder or new_parent in folder.descendants():
                    return MoveCorpusFolderMutation(
                        ok=False,
                        message="Cannot move folder into itself or its descendants",
                        folder=None,
                    )

            # Move folder
            folder.parent = new_parent
            folder.save()

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
        except IntegrityError as e:
            if "unique constraint" in str(e).lower():
                return MoveCorpusFolderMutation(
                    ok=False,
                    message="A folder with this name already exists at the destination",
                    folder=None,
                )
            logger.exception("Integrity error moving folder")
            return MoveCorpusFolderMutation(
                ok=False,
                message=f"Database error moving folder: {str(e)}",
                folder=None,
            )
        except ValidationError as e:
            return MoveCorpusFolderMutation(
                ok=False,
                message=f"Validation error: {str(e)}",
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
    """Delete a folder and optionally its contents."""

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
    def mutate(root, info, folder_id, delete_contents=False):
        user = info.context.user

        try:
            folder_pk = from_global_id(folder_id)[1]
            folder = CorpusFolder.objects.get(pk=folder_pk)

            # Check permission - user must have DELETE permission or be creator
            if not (
                folder.corpus.creator == user
                or user_has_permission_for_obj(user, folder.corpus, "delete")
            ):
                return DeleteCorpusFolderMutation(
                    ok=False,
                    message="You do not have permission to delete folders in this corpus",
                )

            with transaction.atomic():
                if not delete_contents:
                    # Move child folders to this folder's parent
                    children = folder.children.all()
                    for child in children:
                        child.parent = folder.parent
                        child.save()

                    # Move documents to corpus root (delete their folder assignments)
                    CorpusDocumentFolder.objects.filter(
                        folder=folder, corpus=folder.corpus
                    ).delete()

                # Delete the folder (CASCADE will handle subfolders if delete_contents=True)
                folder.delete()

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
    """Move a document to a specific folder (or to corpus root if folder_id is null)."""

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
    def mutate(root, info, document_id, corpus_id, folder_id=None):
        user = info.context.user

        try:
            document_pk = from_global_id(document_id)[1]
            corpus_pk = from_global_id(corpus_id)[1]

            # Get and check objects
            document = Document.objects.get(pk=document_pk)
            corpus = Corpus.objects.get(pk=corpus_pk)

            # Check permissions - user must have UPDATE permission or be creator
            # Note: is_public grants READ-ONLY access, not write access
            if not (
                corpus.creator == user
                or user_has_permission_for_obj(
                    user, corpus, PermissionTypes.UPDATE, include_group_permissions=True
                )
            ):
                return MoveDocumentToFolderMutation(
                    ok=False,
                    message="You do not have permission to organize documents in this corpus",
                    document=None,
                )

            # Verify document is in corpus (using DocumentPath source of truth)
            if not corpus.get_documents().filter(pk=document.pk).exists():
                return MoveDocumentToFolderMutation(
                    ok=False,
                    message="Document is not in this corpus",
                    document=None,
                )

            # Get folder if provided
            folder = None
            if folder_id:
                folder_pk = from_global_id(folder_id)[1]
                folder = CorpusFolder.objects.get(pk=folder_pk)

                # Verify folder is in the same corpus
                if folder.corpus_id != corpus.id:
                    return MoveDocumentToFolderMutation(
                        ok=False,
                        message="Folder must be in the same corpus as the document",
                        document=None,
                    )

            # Update or create document folder assignment
            with transaction.atomic():
                # Delete existing assignment for this corpus
                CorpusDocumentFolder.objects.filter(
                    document=document, corpus=corpus
                ).delete()

                # Create new assignment if folder specified
                # (if folder is None, document goes to root)
                if folder is not None:
                    CorpusDocumentFolder.objects.create(
                        document=document,
                        corpus=corpus,
                        folder=folder,
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
    """Move multiple documents to a specific folder in bulk."""

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
    def mutate(root, info, document_ids, corpus_id, folder_id=None):
        user = info.context.user

        try:
            corpus_pk = from_global_id(corpus_id)[1]
            corpus = Corpus.objects.get(pk=corpus_pk)

            # Check permissions - user must have UPDATE permission or be creator
            # Note: is_public grants READ-ONLY access, not write access
            if not (
                corpus.creator == user
                or user_has_permission_for_obj(
                    user, corpus, PermissionTypes.UPDATE, include_group_permissions=True
                )
            ):
                return MoveDocumentsToFolderMutation(
                    ok=False,
                    message="You do not have permission to organize documents in this corpus",
                    moved_count=0,
                )

            # Get folder if provided
            folder = None
            if folder_id:
                folder_pk = from_global_id(folder_id)[1]
                folder = CorpusFolder.objects.get(pk=folder_pk)

                # Verify folder is in the same corpus
                if folder.corpus_id != corpus.id:
                    return MoveDocumentsToFolderMutation(
                        ok=False,
                        message="Folder must be in the same corpus",
                        moved_count=0,
                    )

            # Convert document IDs
            doc_pks = [from_global_id(doc_id)[1] for doc_id in document_ids]

            # Verify all documents are in corpus (using DocumentPath source of truth)
            corpus_doc_ids = set(corpus.get_documents().values_list("id", flat=True))
            invalid_docs = [pk for pk in doc_pks if int(pk) not in corpus_doc_ids]
            if invalid_docs:
                return MoveDocumentsToFolderMutation(
                    ok=False,
                    message=f"Some documents are not in this corpus: {invalid_docs}",
                    moved_count=0,
                )

            # Bulk move documents
            with transaction.atomic():
                # Delete existing assignments
                CorpusDocumentFolder.objects.filter(
                    document_id__in=doc_pks, corpus=corpus
                ).delete()

                # Create new assignments if folder specified
                if folder is not None:
                    assignments = [
                        CorpusDocumentFolder(
                            document_id=doc_pk,
                            corpus=corpus,
                            folder=folder,
                        )
                        for doc_pk in doc_pks
                    ]
                    CorpusDocumentFolder.objects.bulk_create(assignments)

            return MoveDocumentsToFolderMutation(
                ok=True,
                message=f"Successfully moved {len(doc_pks)} document(s)",
                moved_count=len(doc_pks),
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
