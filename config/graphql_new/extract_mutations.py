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

from opencontractserver.extracts.models import Extract


@strawberry.type(name="CreateFieldset")
class CreateFieldset:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["FieldsetType", strawberry.lazy("config.graphql_new.extract_types")]] = strawberry.field(name="obj")


register_type("CreateFieldset", CreateFieldset, model=None)


@strawberry.type(name="UpdateFieldset", description='Rename / re-describe a fieldset the caller may UPDATE.')
class UpdateFieldset:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["FieldsetType", strawberry.lazy("config.graphql_new.extract_types")]] = strawberry.field(name="obj")


register_type("UpdateFieldset", UpdateFieldset, model=None)


@strawberry.type(name="CreateColumn")
class CreateColumn:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["ColumnType", strawberry.lazy("config.graphql_new.extract_types")]] = strawberry.field(name="obj")


register_type("CreateColumn", CreateColumn, model=None)


@strawberry.type(name="UpdateColumnMutation")
class UpdateColumnMutation:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    @strawberry.field(name="objId")
    def obj_id(self, info: strawberry.Info) -> Optional[strawberry.ID]:
        return coerce_str(getattr(self, "obj_id", None))
    obj: Optional[Annotated["ColumnType", strawberry.lazy("config.graphql_new.extract_types")]] = strawberry.field(name="obj")


register_type("UpdateColumnMutation", UpdateColumnMutation, model=None)


@strawberry.type(name="DeleteColumn")
class DeleteColumn:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    @strawberry.field(name="deletedId")
    def deleted_id(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "deleted_id", None))


register_type("DeleteColumn", DeleteColumn, model=None)


@strawberry.type(name="CreateExtract", description='Create a new extract. If fieldset_id is provided, attach existing fieldset.\nOtherwise, a new fieldset is created. If no name is provided, fieldset name has\nform "[Extract name] Fieldset"')
class CreateExtract:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="msg")
    def msg(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "msg", None))
    obj: Optional[Annotated["ExtractType", strawberry.lazy("config.graphql_new.extract_types")]] = strawberry.field(name="obj")


register_type("CreateExtract", CreateExtract, model=None)


@strawberry.type(name="CreateExtractIteration", description='Fork an existing Extract into a new iteration along a single axis.\n\nThree axes are supported, mirroring the three eval workflows:\n  * ``MODEL`` — same fieldset + same documents, new model_config.\n  * ``DOCUMENT_VERSIONS`` — same fieldset + same model_config, but each\n    document is replaced by the current row in its version tree.\n  * ``FIELDSET`` — clone the fieldset (with optional per-column\n    overrides), keep documents + model_config.\n\nThe new extract has ``parent_extract`` set to the source so the UI can\nwalk the iteration series. If ``auto_start`` is true the standard\n``run_extract`` task is queued exactly as ``StartExtract`` would.')
class CreateExtractIteration:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["ExtractType", strawberry.lazy("config.graphql_new.extract_types")]] = strawberry.field(name="obj")


register_type("CreateExtractIteration", CreateExtractIteration, model=None)


@strawberry.type(name="StartExtract")
class StartExtract:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["ExtractType", strawberry.lazy("config.graphql_new.extract_types")]] = strawberry.field(name="obj")


register_type("StartExtract", StartExtract, model=None)


@strawberry.type(name="DeleteExtract")
class DeleteExtract:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))


register_type("DeleteExtract", DeleteExtract, model=None)


@strawberry.type(name="UpdateExtractMutation", description='Mutation to update an existing Extract object.\n\nSupports updating the name (title), corpus, fieldset, and error fields.\nEnsures proper permission checks are applied.')
class UpdateExtractMutation:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["ExtractType", strawberry.lazy("config.graphql_new.extract_types")]] = strawberry.field(name="obj")


register_type("UpdateExtractMutation", UpdateExtractMutation, model=None)


@strawberry.type(name="AddDocumentsToExtract")
class AddDocumentsToExtract:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    @strawberry.field(name="objId")
    def obj_id(self, info: strawberry.Info) -> Optional[strawberry.ID]:
        return coerce_str(getattr(self, "obj_id", None))
    @strawberry.field(name="objs")
    def objs(self, info: strawberry.Info) -> Optional[list[Optional[Annotated["DocumentType", strawberry.lazy("config.graphql_new.document_types")]]]]:
        return resolve_django_list(self, info, getattr(self, "objs"), "DocumentType")


register_type("AddDocumentsToExtract", AddDocumentsToExtract, model=None)


@strawberry.type(name="RemoveDocumentsFromExtract")
class RemoveDocumentsFromExtract:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    @strawberry.field(name="idsRemoved")
    def ids_removed(self, info: strawberry.Info) -> Optional[list[Optional[str]]]:
        return coerce_str(getattr(self, "ids_removed", None))


register_type("RemoveDocumentsFromExtract", RemoveDocumentsFromExtract, model=None)


@strawberry.type(name="ApproveDatacell")
class ApproveDatacell:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["DatacellType", strawberry.lazy("config.graphql_new.extract_types")]] = strawberry.field(name="obj")


register_type("ApproveDatacell", ApproveDatacell, model=None)


@strawberry.type(name="RejectDatacell")
class RejectDatacell:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["DatacellType", strawberry.lazy("config.graphql_new.extract_types")]] = strawberry.field(name="obj")


register_type("RejectDatacell", RejectDatacell, model=None)


@strawberry.type(name="EditDatacell")
class EditDatacell:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["DatacellType", strawberry.lazy("config.graphql_new.extract_types")]] = strawberry.field(name="obj")


register_type("EditDatacell", EditDatacell, model=None)


@strawberry.type(name="StartDocumentExtract")
class StartDocumentExtract:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["ExtractType", strawberry.lazy("config.graphql_new.extract_types")]] = strawberry.field(name="obj")


register_type("StartDocumentExtract", StartDocumentExtract, model=None)


@strawberry.type(name="CreateMetadataColumn", description='Create a metadata column for a corpus.')
class CreateMetadataColumn:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["ColumnType", strawberry.lazy("config.graphql_new.extract_types")]] = strawberry.field(name="obj")


register_type("CreateMetadataColumn", CreateMetadataColumn, model=None)


@strawberry.type(name="UpdateMetadataColumn", description='Update a metadata column.')
class UpdateMetadataColumn:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["ColumnType", strawberry.lazy("config.graphql_new.extract_types")]] = strawberry.field(name="obj")


register_type("UpdateMetadataColumn", UpdateMetadataColumn, model=None)


@strawberry.type(name="DeleteMetadataColumn", description='Delete a manual-entry metadata column definition (values cascade).')
class DeleteMetadataColumn:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))


register_type("DeleteMetadataColumn", DeleteMetadataColumn, model=None)


@strawberry.type(name="SetMetadataValue", description='Set a metadata value for a document.\n\nPermission model:\n- Requires Corpus UPDATE permission + Document READ permission\n- Metadata is a corpus-level feature, so corpus permission controls editing\n- Uses MetadataService for consistent permission checking')
class SetMetadataValue:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["DatacellType", strawberry.lazy("config.graphql_new.extract_types")]] = strawberry.field(name="obj")


register_type("SetMetadataValue", SetMetadataValue, model=None)


@strawberry.type(name="DeleteMetadataValue", description='Delete a metadata value for a document.\n\nPermission model:\n- Requires Corpus DELETE permission + Document READ permission\n- Metadata is a corpus-level feature, so corpus permission controls deletion\n- Uses MetadataService for consistent permission checking')
class DeleteMetadataValue:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))


register_type("DeleteMetadataValue", DeleteMetadataValue, model=None)


def _mutate_CreateFieldset(payload_cls, root, info, **kwargs):
    """PORT: config.graphql.extract_mutations.CreateFieldset.mutate

    Port of CreateFieldset.mutate
    """
    raise NotImplementedError("_mutate_CreateFieldset not yet ported — see manifest")


def m_create_fieldset(info: strawberry.Info, description: Annotated[str, strawberry.argument(name="description")] = strawberry.UNSET, name: Annotated[str, strawberry.argument(name="name")] = strawberry.UNSET) -> Optional["CreateFieldset"]:
    kwargs = strip_unset({"description": description, "name": name})
    return _mutate_CreateFieldset(CreateFieldset, None, info, **kwargs)


def _mutate_UpdateFieldset(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:656

    Port of UpdateFieldset.mutate
    """
    raise NotImplementedError("_mutate_UpdateFieldset not yet ported — see manifest")


def m_update_fieldset(info: strawberry.Info, description: Annotated[Optional[str], strawberry.argument(name="description")] = strawberry.UNSET, id: Annotated[strawberry.ID, strawberry.argument(name="id")] = strawberry.UNSET, name: Annotated[Optional[str], strawberry.argument(name="name")] = strawberry.UNSET) -> Optional["UpdateFieldset"]:
    kwargs = strip_unset({"description": description, "id": id, "name": name})
    return _mutate_UpdateFieldset(UpdateFieldset, None, info, **kwargs)


def _mutate_CreateColumn(payload_cls, root, info, **kwargs):
    """PORT: config.graphql.extract_mutations.CreateColumn.mutate

    Port of CreateColumn.mutate
    """
    raise NotImplementedError("_mutate_CreateColumn not yet ported — see manifest")


def m_create_column(info: strawberry.Info, extract_is_list: Annotated[Optional[bool], strawberry.argument(name="extractIsList")] = strawberry.UNSET, fieldset_id: Annotated[strawberry.ID, strawberry.argument(name="fieldsetId")] = strawberry.UNSET, instructions: Annotated[Optional[str], strawberry.argument(name="instructions")] = strawberry.UNSET, limit_to_label: Annotated[Optional[str], strawberry.argument(name="limitToLabel")] = strawberry.UNSET, match_text: Annotated[Optional[str], strawberry.argument(name="matchText")] = strawberry.UNSET, must_contain_text: Annotated[Optional[str], strawberry.argument(name="mustContainText")] = strawberry.UNSET, name: Annotated[str, strawberry.argument(name="name")] = strawberry.UNSET, output_type: Annotated[str, strawberry.argument(name="outputType")] = strawberry.UNSET, query: Annotated[Optional[str], strawberry.argument(name="query")] = strawberry.UNSET, task_name: Annotated[Optional[str], strawberry.argument(name="taskName")] = strawberry.UNSET) -> Optional["CreateColumn"]:
    kwargs = strip_unset({"extract_is_list": extract_is_list, "fieldset_id": fieldset_id, "instructions": instructions, "limit_to_label": limit_to_label, "match_text": match_text, "must_contain_text": must_contain_text, "name": name, "output_type": output_type, "query": query, "task_name": task_name})
    return _mutate_CreateColumn(CreateColumn, None, info, **kwargs)


def _mutate_UpdateColumnMutation(payload_cls, root, info, **kwargs):
    """PORT: config.graphql.extract_mutations.UpdateColumnMutation.mutate

    Port of UpdateColumnMutation.mutate
    """
    raise NotImplementedError("_mutate_UpdateColumnMutation not yet ported — see manifest")


def m_update_column(info: strawberry.Info, extract_is_list: Annotated[Optional[bool], strawberry.argument(name="extractIsList")] = strawberry.UNSET, fieldset_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="fieldsetId")] = strawberry.UNSET, id: Annotated[strawberry.ID, strawberry.argument(name="id")] = strawberry.UNSET, instructions: Annotated[Optional[str], strawberry.argument(name="instructions")] = strawberry.UNSET, limit_to_label: Annotated[Optional[str], strawberry.argument(name="limitToLabel")] = strawberry.UNSET, match_text: Annotated[Optional[str], strawberry.argument(name="matchText")] = strawberry.UNSET, must_contain_text: Annotated[Optional[str], strawberry.argument(name="mustContainText")] = strawberry.UNSET, name: Annotated[Optional[str], strawberry.argument(name="name")] = strawberry.UNSET, output_type: Annotated[Optional[str], strawberry.argument(name="outputType")] = strawberry.UNSET, query: Annotated[Optional[str], strawberry.argument(name="query")] = strawberry.UNSET, task_name: Annotated[Optional[str], strawberry.argument(name="taskName")] = strawberry.UNSET) -> Optional["UpdateColumnMutation"]:
    kwargs = strip_unset({"extract_is_list": extract_is_list, "fieldset_id": fieldset_id, "id": id, "instructions": instructions, "limit_to_label": limit_to_label, "match_text": match_text, "must_contain_text": must_contain_text, "name": name, "output_type": output_type, "query": query, "task_name": task_name})
    return _mutate_UpdateColumnMutation(UpdateColumnMutation, None, info, **kwargs)


def _mutate_DeleteColumn(payload_cls, root, info, **kwargs):
    """PORT: config.graphql.extract_mutations.DeleteColumn.mutate

    Port of DeleteColumn.mutate
    """
    raise NotImplementedError("_mutate_DeleteColumn not yet ported — see manifest")


def m_delete_column(info: strawberry.Info, id: Annotated[strawberry.ID, strawberry.argument(name="id")] = strawberry.UNSET) -> Optional["DeleteColumn"]:
    kwargs = strip_unset({"id": id})
    return _mutate_DeleteColumn(DeleteColumn, None, info, **kwargs)


def _mutate_CreateExtract(payload_cls, root, info, **kwargs):
    """PORT: config.graphql.extract_mutations.CreateExtract.mutate

    Port of CreateExtract.mutate
    """
    raise NotImplementedError("_mutate_CreateExtract not yet ported — see manifest")


def m_create_extract(info: strawberry.Info, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId")] = strawberry.UNSET, fieldset_description: Annotated[Optional[str], strawberry.argument(name="fieldsetDescription")] = strawberry.UNSET, fieldset_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="fieldsetId")] = strawberry.UNSET, fieldset_name: Annotated[Optional[str], strawberry.argument(name="fieldsetName")] = strawberry.UNSET, name: Annotated[str, strawberry.argument(name="name")] = strawberry.UNSET) -> Optional["CreateExtract"]:
    kwargs = strip_unset({"corpus_id": corpus_id, "fieldset_description": fieldset_description, "fieldset_id": fieldset_id, "fieldset_name": fieldset_name, "name": name})
    return _mutate_CreateExtract(CreateExtract, None, info, **kwargs)


def _mutate_CreateExtractIteration(payload_cls, root, info, **kwargs):
    """PORT: config.graphql.extract_mutations.CreateExtractIteration.mutate

    Port of CreateExtractIteration.mutate
    """
    raise NotImplementedError("_mutate_CreateExtractIteration not yet ported — see manifest")


def m_create_extract_iteration(info: strawberry.Info, auto_start: Annotated[Optional[bool], strawberry.argument(name="autoStart", description='If true, queue run_extract for the new iteration.')] = strawberry.UNSET, axis: Annotated[str, strawberry.argument(name="axis", description='One of MODEL | DOCUMENT_VERSIONS | FIELDSET')] = strawberry.UNSET, column_overrides: Annotated[Optional[GenericScalar], strawberry.argument(name="columnOverrides", description="FIELDSET-axis only: { '<column global id>': { 'query': '...', 'instructions': '...', ... } }.")] = strawberry.UNSET, model_config: Annotated[Optional[GenericScalar], strawberry.argument(name="modelConfig", description="Run-time model config to capture on the new iteration. If omitted, parent's config is reused.")] = strawberry.UNSET, name: Annotated[Optional[str], strawberry.argument(name="name", description="Optional name for the new iteration; defaults to '<source name> (iteration N)'.")] = strawberry.UNSET, source_extract_id: Annotated[strawberry.ID, strawberry.argument(name="sourceExtractId")] = strawberry.UNSET) -> Optional["CreateExtractIteration"]:
    kwargs = strip_unset({"auto_start": auto_start, "axis": axis, "column_overrides": column_overrides, "model_config": model_config, "name": name, "source_extract_id": source_extract_id})
    return _mutate_CreateExtractIteration(CreateExtractIteration, None, info, **kwargs)


def _mutate_StartExtract(payload_cls, root, info, **kwargs):
    """PORT: config.graphql.extract_mutations.StartExtract.mutate

    Port of StartExtract.mutate
    """
    raise NotImplementedError("_mutate_StartExtract not yet ported — see manifest")


def m_start_extract(info: strawberry.Info, extract_id: Annotated[strawberry.ID, strawberry.argument(name="extractId")] = strawberry.UNSET) -> Optional["StartExtract"]:
    kwargs = strip_unset({"extract_id": extract_id})
    return _mutate_StartExtract(StartExtract, None, info, **kwargs)


def m_delete_extract(info: strawberry.Info, id: Annotated[str, strawberry.argument(name="id")] = strawberry.UNSET) -> Optional["DeleteExtract"]:
    kwargs = strip_unset({"id": id})
    return drf_deletion(payload_cls=DeleteExtract, model=Extract, lookup_field="id", root=None, info=info, kwargs=kwargs)


def _mutate_UpdateExtractMutation(payload_cls, root, info, **kwargs):
    """PORT: config.graphql.extract_mutations.UpdateExtractMutation.mutate

    Port of UpdateExtractMutation.mutate
    """
    raise NotImplementedError("_mutate_UpdateExtractMutation not yet ported — see manifest")


def m_update_extract(info: strawberry.Info, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId", description='ID of the Corpus to associate with the Extract.')] = strawberry.UNSET, error: Annotated[Optional[str], strawberry.argument(name="error", description='Error message to update on the Extract.')] = strawberry.UNSET, fieldset_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="fieldsetId", description='ID of the Fieldset to associate with the Extract.')] = strawberry.UNSET, id: Annotated[strawberry.ID, strawberry.argument(name="id", description='ID of the Extract to update.')] = strawberry.UNSET, title: Annotated[Optional[str], strawberry.argument(name="title", description='New title for the Extract.')] = strawberry.UNSET) -> Optional["UpdateExtractMutation"]:
    kwargs = strip_unset({"corpus_id": corpus_id, "error": error, "fieldset_id": fieldset_id, "id": id, "title": title})
    return _mutate_UpdateExtractMutation(UpdateExtractMutation, None, info, **kwargs)


def _mutate_AddDocumentsToExtract(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:1121

    Port of AddDocumentsToExtract.mutate
    """
    raise NotImplementedError("_mutate_AddDocumentsToExtract not yet ported — see manifest")


def m_add_docs_to_extract(info: strawberry.Info, document_ids: Annotated[list[Optional[strawberry.ID]], strawberry.argument(name="documentIds", description='List of ids of the documents to add to extract.')] = strawberry.UNSET, extract_id: Annotated[strawberry.ID, strawberry.argument(name="extractId", description='Id of corpus to add docs to.')] = strawberry.UNSET) -> Optional["AddDocumentsToExtract"]:
    kwargs = strip_unset({"document_ids": document_ids, "extract_id": extract_id})
    return _mutate_AddDocumentsToExtract(AddDocumentsToExtract, None, info, **kwargs)


def _mutate_RemoveDocumentsFromExtract(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:1175

    Port of RemoveDocumentsFromExtract.mutate
    """
    raise NotImplementedError("_mutate_RemoveDocumentsFromExtract not yet ported — see manifest")


def m_remove_docs_from_extract(info: strawberry.Info, document_ids_to_remove: Annotated[list[Optional[strawberry.ID]], strawberry.argument(name="documentIdsToRemove", description='List of ids of the docs to remove from extract.')] = strawberry.UNSET, extract_id: Annotated[strawberry.ID, strawberry.argument(name="extractId", description='ID of extract to remove documents from.')] = strawberry.UNSET) -> Optional["RemoveDocumentsFromExtract"]:
    kwargs = strip_unset({"document_ids_to_remove": document_ids_to_remove, "extract_id": extract_id})
    return _mutate_RemoveDocumentsFromExtract(RemoveDocumentsFromExtract, None, info, **kwargs)


def _mutate_ApproveDatacell(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:87

    Port of ApproveDatacell.mutate
    """
    raise NotImplementedError("_mutate_ApproveDatacell not yet ported — see manifest")


def m_approve_datacell(info: strawberry.Info, datacell_id: Annotated[str, strawberry.argument(name="datacellId")] = strawberry.UNSET) -> Optional["ApproveDatacell"]:
    kwargs = strip_unset({"datacell_id": datacell_id})
    return _mutate_ApproveDatacell(ApproveDatacell, None, info, **kwargs)


def _mutate_RejectDatacell(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:125

    Port of RejectDatacell.mutate
    """
    raise NotImplementedError("_mutate_RejectDatacell not yet ported — see manifest")


def m_reject_datacell(info: strawberry.Info, datacell_id: Annotated[str, strawberry.argument(name="datacellId")] = strawberry.UNSET) -> Optional["RejectDatacell"]:
    kwargs = strip_unset({"datacell_id": datacell_id})
    return _mutate_RejectDatacell(RejectDatacell, None, info, **kwargs)


def _mutate_EditDatacell(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:162

    Port of EditDatacell.mutate
    """
    raise NotImplementedError("_mutate_EditDatacell not yet ported — see manifest")


def m_edit_datacell(info: strawberry.Info, datacell_id: Annotated[str, strawberry.argument(name="datacellId")] = strawberry.UNSET, edited_data: Annotated[GenericScalar, strawberry.argument(name="editedData")] = strawberry.UNSET) -> Optional["EditDatacell"]:
    kwargs = strip_unset({"datacell_id": datacell_id, "edited_data": edited_data})
    return _mutate_EditDatacell(EditDatacell, None, info, **kwargs)


def _mutate_StartDocumentExtract(payload_cls, root, info, **kwargs):
    """PORT: config.graphql.extract_mutations.StartDocumentExtract.mutate

    Port of StartDocumentExtract.mutate
    """
    raise NotImplementedError("_mutate_StartDocumentExtract not yet ported — see manifest")


def m_start_extract_for_doc(info: strawberry.Info, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId")] = strawberry.UNSET, document_id: Annotated[strawberry.ID, strawberry.argument(name="documentId")] = strawberry.UNSET, fieldset_id: Annotated[strawberry.ID, strawberry.argument(name="fieldsetId")] = strawberry.UNSET) -> Optional["StartDocumentExtract"]:
    kwargs = strip_unset({"corpus_id": corpus_id, "document_id": document_id, "fieldset_id": fieldset_id})
    return _mutate_StartDocumentExtract(StartDocumentExtract, None, info, **kwargs)


def _mutate_CreateMetadataColumn(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:206

    Port of CreateMetadataColumn.mutate
    """
    raise NotImplementedError("_mutate_CreateMetadataColumn not yet ported — see manifest")


def m_create_metadata_column(info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId", description='ID of the corpus')] = strawberry.UNSET, data_type: Annotated[str, strawberry.argument(name="dataType", description='Data type of the field')] = strawberry.UNSET, default_value: Annotated[Optional[GenericScalar], strawberry.argument(name="defaultValue", description='Default value')] = strawberry.UNSET, display_order: Annotated[Optional[int], strawberry.argument(name="displayOrder", description='Display order')] = strawberry.UNSET, help_text: Annotated[Optional[str], strawberry.argument(name="helpText", description='Help text for the field')] = strawberry.UNSET, name: Annotated[str, strawberry.argument(name="name", description='Name of the metadata field')] = strawberry.UNSET, validation_config: Annotated[Optional[GenericScalar], strawberry.argument(name="validationConfig", description='Validation configuration')] = strawberry.UNSET) -> Optional["CreateMetadataColumn"]:
    kwargs = strip_unset({"corpus_id": corpus_id, "data_type": data_type, "default_value": default_value, "display_order": display_order, "help_text": help_text, "name": name, "validation_config": validation_config})
    return _mutate_CreateMetadataColumn(CreateMetadataColumn, None, info, **kwargs)


def _mutate_UpdateMetadataColumn(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:336

    Port of UpdateMetadataColumn.mutate
    """
    raise NotImplementedError("_mutate_UpdateMetadataColumn not yet ported — see manifest")


def m_update_metadata_column(info: strawberry.Info, column_id: Annotated[strawberry.ID, strawberry.argument(name="columnId")] = strawberry.UNSET, default_value: Annotated[Optional[GenericScalar], strawberry.argument(name="defaultValue")] = strawberry.UNSET, display_order: Annotated[Optional[int], strawberry.argument(name="displayOrder")] = strawberry.UNSET, help_text: Annotated[Optional[str], strawberry.argument(name="helpText")] = strawberry.UNSET, name: Annotated[Optional[str], strawberry.argument(name="name")] = strawberry.UNSET, validation_config: Annotated[Optional[GenericScalar], strawberry.argument(name="validationConfig")] = strawberry.UNSET) -> Optional["UpdateMetadataColumn"]:
    kwargs = strip_unset({"column_id": column_id, "default_value": default_value, "display_order": display_order, "help_text": help_text, "name": name, "validation_config": validation_config})
    return _mutate_UpdateMetadataColumn(UpdateMetadataColumn, None, info, **kwargs)


def _mutate_DeleteMetadataColumn(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:409

    Port of DeleteMetadataColumn.mutate
    """
    raise NotImplementedError("_mutate_DeleteMetadataColumn not yet ported — see manifest")


def m_delete_metadata_column(info: strawberry.Info, column_id: Annotated[strawberry.ID, strawberry.argument(name="columnId")] = strawberry.UNSET) -> Optional["DeleteMetadataColumn"]:
    kwargs = strip_unset({"column_id": column_id})
    return _mutate_DeleteMetadataColumn(DeleteMetadataColumn, None, info, **kwargs)


def _mutate_SetMetadataValue(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:477

    Port of SetMetadataValue.mutate
    """
    raise NotImplementedError("_mutate_SetMetadataValue not yet ported — see manifest")


def m_set_metadata_value(info: strawberry.Info, column_id: Annotated[strawberry.ID, strawberry.argument(name="columnId")] = strawberry.UNSET, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId")] = strawberry.UNSET, document_id: Annotated[strawberry.ID, strawberry.argument(name="documentId")] = strawberry.UNSET, value: Annotated[GenericScalar, strawberry.argument(name="value")] = strawberry.UNSET) -> Optional["SetMetadataValue"]:
    kwargs = strip_unset({"column_id": column_id, "corpus_id": corpus_id, "document_id": document_id, "value": value})
    return _mutate_SetMetadataValue(SetMetadataValue, None, info, **kwargs)


def _mutate_DeleteMetadataValue(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:562

    Port of DeleteMetadataValue.mutate
    """
    raise NotImplementedError("_mutate_DeleteMetadataValue not yet ported — see manifest")


def m_delete_metadata_value(info: strawberry.Info, column_id: Annotated[strawberry.ID, strawberry.argument(name="columnId")] = strawberry.UNSET, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId")] = strawberry.UNSET, document_id: Annotated[strawberry.ID, strawberry.argument(name="documentId")] = strawberry.UNSET) -> Optional["DeleteMetadataValue"]:
    kwargs = strip_unset({"column_id": column_id, "corpus_id": corpus_id, "document_id": document_id})
    return _mutate_DeleteMetadataValue(DeleteMetadataValue, None, info, **kwargs)



MUTATION_FIELDS = {
    "create_fieldset": strawberry.field(resolver=m_create_fieldset, name="createFieldset"),
    "update_fieldset": strawberry.field(resolver=m_update_fieldset, name="updateFieldset", description='Rename / re-describe a fieldset the caller may UPDATE.'),
    "create_column": strawberry.field(resolver=m_create_column, name="createColumn"),
    "update_column": strawberry.field(resolver=m_update_column, name="updateColumn"),
    "delete_column": strawberry.field(resolver=m_delete_column, name="deleteColumn"),
    "create_extract": strawberry.field(resolver=m_create_extract, name="createExtract", description='Create a new extract. If fieldset_id is provided, attach existing fieldset.\nOtherwise, a new fieldset is created. If no name is provided, fieldset name has\nform "[Extract name] Fieldset"'),
    "create_extract_iteration": strawberry.field(resolver=m_create_extract_iteration, name="createExtractIteration", description='Fork an existing Extract into a new iteration along a single axis.\n\nThree axes are supported, mirroring the three eval workflows:\n  * ``MODEL`` — same fieldset + same documents, new model_config.\n  * ``DOCUMENT_VERSIONS`` — same fieldset + same model_config, but each\n    document is replaced by the current row in its version tree.\n  * ``FIELDSET`` — clone the fieldset (with optional per-column\n    overrides), keep documents + model_config.\n\nThe new extract has ``parent_extract`` set to the source so the UI can\nwalk the iteration series. If ``auto_start`` is true the standard\n``run_extract`` task is queued exactly as ``StartExtract`` would.'),
    "start_extract": strawberry.field(resolver=m_start_extract, name="startExtract"),
    "delete_extract": strawberry.field(resolver=m_delete_extract, name="deleteExtract"),
    "update_extract": strawberry.field(resolver=m_update_extract, name="updateExtract", description='Mutation to update an existing Extract object.\n\nSupports updating the name (title), corpus, fieldset, and error fields.\nEnsures proper permission checks are applied.'),
    "add_docs_to_extract": strawberry.field(resolver=m_add_docs_to_extract, name="addDocsToExtract"),
    "remove_docs_from_extract": strawberry.field(resolver=m_remove_docs_from_extract, name="removeDocsFromExtract"),
    "approve_datacell": strawberry.field(resolver=m_approve_datacell, name="approveDatacell"),
    "reject_datacell": strawberry.field(resolver=m_reject_datacell, name="rejectDatacell"),
    "edit_datacell": strawberry.field(resolver=m_edit_datacell, name="editDatacell"),
    "start_extract_for_doc": strawberry.field(resolver=m_start_extract_for_doc, name="startExtractForDoc"),
    "create_metadata_column": strawberry.field(resolver=m_create_metadata_column, name="createMetadataColumn", description='Create a metadata column for a corpus.'),
    "update_metadata_column": strawberry.field(resolver=m_update_metadata_column, name="updateMetadataColumn", description='Update a metadata column.'),
    "delete_metadata_column": strawberry.field(resolver=m_delete_metadata_column, name="deleteMetadataColumn", description='Delete a manual-entry metadata column definition (values cascade).'),
    "set_metadata_value": strawberry.field(resolver=m_set_metadata_value, name="setMetadataValue", description='Set a metadata value for a document.\n\nPermission model:\n- Requires Corpus UPDATE permission + Document READ permission\n- Metadata is a corpus-level feature, so corpus permission controls editing\n- Uses MetadataService for consistent permission checking'),
    "delete_metadata_value": strawberry.field(resolver=m_delete_metadata_value, name="deleteMetadataValue", description='Delete a metadata value for a document.\n\nPermission model:\n- Requires Corpus DELETE permission + Document READ permission\n- Metadata is a corpus-level feature, so corpus permission controls deletion\n- Uses MetadataService for consistent permission checking'),
}
