"""Generated strawberry GraphQL module (graphene migration).

Shape-generated from the graphene schema; stub functions marked PORT(...)
carry the ported business logic. See config/graphql_new/manifest.json.
"""
from __future__ import annotations

import datetime
import decimal
import uuid
from typing import Annotated, Any, Optional

import strawberry

from config.graphql.core import permissions as core_permissions
from config.graphql.core.filtering import filterset_factory, setup_filterset
from config.graphql.core.mutations import drf_deletion, drf_mutation
from config.graphql.core.relay import (
    Node,
    get_node_from_global_id,
    make_connection_types,
    register_type,
    resolve_django_connection,
    resolve_django_list,
)
from config.graphql.core.scalars import BigInt, GenericScalar, JSONString
from config.graphql_new._util import coerce_enum, coerce_str, strip_unset
from config.graphql_new import enums




@strawberry.type(name="CreateCorpusFolderMutation", description='Create a new folder in a corpus.\n\nDelegates to FolderCRUDService.create_folder() for:\n- Permission checking (corpus UPDATE permission)\n- Validation (unique name, parent in same corpus)\n- Folder creation')
class CreateCorpusFolderMutation:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    folder: Optional[Annotated["CorpusFolderType", strawberry.lazy("config.graphql_new.corpus_types")]] = strawberry.field(name="folder")


register_type("CreateCorpusFolderMutation", CreateCorpusFolderMutation, model=None)


@strawberry.type(name="UpdateCorpusFolderMutation", description='Update folder properties (name, description, color, icon, tags).\n\nDelegates to FolderCRUDService.update_folder() for:\n- Permission checking (corpus UPDATE permission)\n- Validation (unique name within parent)\n- Folder update')
class UpdateCorpusFolderMutation:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    folder: Optional[Annotated["CorpusFolderType", strawberry.lazy("config.graphql_new.corpus_types")]] = strawberry.field(name="folder")


register_type("UpdateCorpusFolderMutation", UpdateCorpusFolderMutation, model=None)


@strawberry.type(name="MoveCorpusFolderMutation", description='Move a folder to a different parent (or to root if parent_id is null).\n\nDelegates to FolderCRUDService.move_folder() for:\n- Permission checking (corpus UPDATE permission)\n- Validation (no self-move, no move into descendants, same corpus)\n- Folder move')
class MoveCorpusFolderMutation:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    folder: Optional[Annotated["CorpusFolderType", strawberry.lazy("config.graphql_new.corpus_types")]] = strawberry.field(name="folder")


register_type("MoveCorpusFolderMutation", MoveCorpusFolderMutation, model=None)


@strawberry.type(name="DeleteCorpusFolderMutation", description='Delete a folder and optionally its contents.\n\nDelegates to FolderCRUDService.delete_folder() for:\n- Permission checking (corpus DELETE permission)\n- Child folder handling (reparent or cascade)\n- Document folder assignment cleanup via DocumentPath')
class DeleteCorpusFolderMutation:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))


register_type("DeleteCorpusFolderMutation", DeleteCorpusFolderMutation, model=None)


@strawberry.type(name="MoveDocumentToFolderMutation", description='Move a document to a specific folder (or to corpus root if folder_id is null).\n\nDelegates to FolderDocumentService.move_document_to_folder() for:\n- Permission checking (corpus UPDATE permission)\n- Validation (document in corpus, folder in corpus)\n- DocumentPath folder assignment update')
class MoveDocumentToFolderMutation:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    document: Optional[Annotated["DocumentType", strawberry.lazy("config.graphql_new.document_types")]] = strawberry.field(name="document")


register_type("MoveDocumentToFolderMutation", MoveDocumentToFolderMutation, model=None)


@strawberry.type(name="MoveDocumentsToFolderMutation", description='Move multiple documents to a specific folder in bulk.\n\nDelegates to FolderDocumentService.move_documents_to_folder() for:\n- Permission checking (corpus UPDATE permission)\n- Validation (all documents in corpus, folder in corpus)\n- Bulk DocumentPath folder assignment update')
class MoveDocumentsToFolderMutation:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    moved_count: Optional[int] = strawberry.field(name="movedCount", description='Number of documents successfully moved')


register_type("MoveDocumentsToFolderMutation", MoveDocumentsToFolderMutation, model=None)


def _mutate_CreateCorpusFolderMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:65

    Port of CreateCorpusFolderMutation.mutate
    """
    raise NotImplementedError("_mutate_CreateCorpusFolderMutation not yet ported — see manifest")


def m_create_corpus_folder(info: strawberry.Info, color: Annotated[Optional[str], strawberry.argument(name="color", description='Folder color (hex code)')] = strawberry.UNSET, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId", description='Corpus ID to create the folder in')] = strawberry.UNSET, description: Annotated[Optional[str], strawberry.argument(name="description", description='Folder description')] = strawberry.UNSET, icon: Annotated[Optional[str], strawberry.argument(name="icon", description='Folder icon identifier')] = strawberry.UNSET, name: Annotated[str, strawberry.argument(name="name", description='Folder name')] = strawberry.UNSET, parent_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="parentId", description='Parent folder ID (omit for root-level folder)')] = strawberry.UNSET, tags: Annotated[Optional[list[Optional[str]]], strawberry.argument(name="tags", description='List of tags')] = strawberry.UNSET) -> Optional["CreateCorpusFolderMutation"]:
    kwargs = strip_unset({"color": color, "corpus_id": corpus_id, "description": description, "icon": icon, "name": name, "parent_id": parent_id, "tags": tags})
    return _mutate_CreateCorpusFolderMutation(CreateCorpusFolderMutation, None, info, **kwargs)


def _mutate_UpdateCorpusFolderMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:156

    Port of UpdateCorpusFolderMutation.mutate
    """
    raise NotImplementedError("_mutate_UpdateCorpusFolderMutation not yet ported — see manifest")


def m_update_corpus_folder(info: strawberry.Info, color: Annotated[Optional[str], strawberry.argument(name="color", description='New color (hex code)')] = strawberry.UNSET, description: Annotated[Optional[str], strawberry.argument(name="description", description='New description')] = strawberry.UNSET, folder_id: Annotated[strawberry.ID, strawberry.argument(name="folderId", description='Folder ID to update')] = strawberry.UNSET, icon: Annotated[Optional[str], strawberry.argument(name="icon", description='New icon identifier')] = strawberry.UNSET, name: Annotated[Optional[str], strawberry.argument(name="name", description='New folder name')] = strawberry.UNSET, tags: Annotated[Optional[list[Optional[str]]], strawberry.argument(name="tags", description='New list of tags')] = strawberry.UNSET) -> Optional["UpdateCorpusFolderMutation"]:
    kwargs = strip_unset({"color": color, "description": description, "folder_id": folder_id, "icon": icon, "name": name, "tags": tags})
    return _mutate_UpdateCorpusFolderMutation(UpdateCorpusFolderMutation, None, info, **kwargs)


def _mutate_MoveCorpusFolderMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:244

    Port of MoveCorpusFolderMutation.mutate
    """
    raise NotImplementedError("_mutate_MoveCorpusFolderMutation not yet ported — see manifest")


def m_move_corpus_folder(info: strawberry.Info, folder_id: Annotated[strawberry.ID, strawberry.argument(name="folderId", description='Folder ID to move')] = strawberry.UNSET, new_parent_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="newParentId", description='New parent folder ID (null to move to root)')] = strawberry.UNSET) -> Optional["MoveCorpusFolderMutation"]:
    kwargs = strip_unset({"folder_id": folder_id, "new_parent_id": new_parent_id})
    return _mutate_MoveCorpusFolderMutation(MoveCorpusFolderMutation, None, info, **kwargs)


def _mutate_DeleteCorpusFolderMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:327

    Port of DeleteCorpusFolderMutation.mutate
    """
    raise NotImplementedError("_mutate_DeleteCorpusFolderMutation not yet ported — see manifest")


def m_delete_corpus_folder(info: strawberry.Info, delete_contents: Annotated[Optional[bool], strawberry.argument(name="deleteContents", description='If true, delete subfolders; if false, move to parent')] = False, folder_id: Annotated[strawberry.ID, strawberry.argument(name="folderId", description='Folder ID to delete')] = strawberry.UNSET) -> Optional["DeleteCorpusFolderMutation"]:
    kwargs = strip_unset({"delete_contents": delete_contents, "folder_id": folder_id})
    return _mutate_DeleteCorpusFolderMutation(DeleteCorpusFolderMutation, None, info, **kwargs)


def _mutate_MoveDocumentToFolderMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:400

    Port of MoveDocumentToFolderMutation.mutate
    """
    raise NotImplementedError("_mutate_MoveDocumentToFolderMutation not yet ported — see manifest")


def m_move_document_to_folder(info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId", description='Corpus ID where the document is located')] = strawberry.UNSET, document_id: Annotated[strawberry.ID, strawberry.argument(name="documentId", description='Document ID to move')] = strawberry.UNSET, folder_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="folderId", description='Folder ID to move to (null for corpus root)')] = strawberry.UNSET) -> Optional["MoveDocumentToFolderMutation"]:
    kwargs = strip_unset({"corpus_id": corpus_id, "document_id": document_id, "folder_id": folder_id})
    return _mutate_MoveDocumentToFolderMutation(MoveDocumentToFolderMutation, None, info, **kwargs)


def _mutate_MoveDocumentsToFolderMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:503

    Port of MoveDocumentsToFolderMutation.mutate
    """
    raise NotImplementedError("_mutate_MoveDocumentsToFolderMutation not yet ported — see manifest")


def m_move_documents_to_folder(info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId", description='Corpus ID where the documents are located')] = strawberry.UNSET, document_ids: Annotated[list[Optional[strawberry.ID]], strawberry.argument(name="documentIds", description='List of document IDs to move')] = strawberry.UNSET, folder_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="folderId", description='Folder ID to move to (null for corpus root)')] = strawberry.UNSET) -> Optional["MoveDocumentsToFolderMutation"]:
    kwargs = strip_unset({"corpus_id": corpus_id, "document_ids": document_ids, "folder_id": folder_id})
    return _mutate_MoveDocumentsToFolderMutation(MoveDocumentsToFolderMutation, None, info, **kwargs)



MUTATION_FIELDS = {
    "create_corpus_folder": strawberry.field(resolver=m_create_corpus_folder, name="createCorpusFolder", description='Create a new folder in a corpus.\n\nDelegates to FolderCRUDService.create_folder() for:\n- Permission checking (corpus UPDATE permission)\n- Validation (unique name, parent in same corpus)\n- Folder creation'),
    "update_corpus_folder": strawberry.field(resolver=m_update_corpus_folder, name="updateCorpusFolder", description='Update folder properties (name, description, color, icon, tags).\n\nDelegates to FolderCRUDService.update_folder() for:\n- Permission checking (corpus UPDATE permission)\n- Validation (unique name within parent)\n- Folder update'),
    "move_corpus_folder": strawberry.field(resolver=m_move_corpus_folder, name="moveCorpusFolder", description='Move a folder to a different parent (or to root if parent_id is null).\n\nDelegates to FolderCRUDService.move_folder() for:\n- Permission checking (corpus UPDATE permission)\n- Validation (no self-move, no move into descendants, same corpus)\n- Folder move'),
    "delete_corpus_folder": strawberry.field(resolver=m_delete_corpus_folder, name="deleteCorpusFolder", description='Delete a folder and optionally its contents.\n\nDelegates to FolderCRUDService.delete_folder() for:\n- Permission checking (corpus DELETE permission)\n- Child folder handling (reparent or cascade)\n- Document folder assignment cleanup via DocumentPath'),
    "move_document_to_folder": strawberry.field(resolver=m_move_document_to_folder, name="moveDocumentToFolder", description='Move a document to a specific folder (or to corpus root if folder_id is null).\n\nDelegates to FolderDocumentService.move_document_to_folder() for:\n- Permission checking (corpus UPDATE permission)\n- Validation (document in corpus, folder in corpus)\n- DocumentPath folder assignment update'),
    "move_documents_to_folder": strawberry.field(resolver=m_move_documents_to_folder, name="moveDocumentsToFolder", description='Move multiple documents to a specific folder in bulk.\n\nDelegates to FolderDocumentService.move_documents_to_folder() for:\n- Permission checking (corpus UPDATE permission)\n- Validation (all documents in corpus, folder in corpus)\n- Bulk DocumentPath folder assignment update'),
}
