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

from config.graphql.annotation_serializers import AnnotationLabelSerializer
from config.graphql.serializers import LabelsetSerializer
from opencontractserver.annotations.models import AnnotationLabel
from opencontractserver.annotations.models import LabelSet


@strawberry.type(name="CreateLabelset")
class CreateLabelset:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["LabelSetType", strawberry.lazy("config.graphql_new.annotation_types")]] = strawberry.field(name="obj")


register_type("CreateLabelset", CreateLabelset, model=None)


@strawberry.type(name="UpdateLabelset")
class UpdateLabelset:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    @strawberry.field(name="objId")
    def obj_id(self, info: strawberry.Info) -> Optional[strawberry.ID]:
        return coerce_str(getattr(self, "obj_id", None))


register_type("UpdateLabelset", UpdateLabelset, model=None)


@strawberry.type(name="DeleteLabelset")
class DeleteLabelset:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))


register_type("DeleteLabelset", DeleteLabelset, model=None)


@strawberry.type(name="CreateLabelMutation")
class CreateLabelMutation:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    @strawberry.field(name="objId")
    def obj_id(self, info: strawberry.Info) -> Optional[strawberry.ID]:
        return coerce_str(getattr(self, "obj_id", None))


register_type("CreateLabelMutation", CreateLabelMutation, model=None)


@strawberry.type(name="UpdateLabelMutation")
class UpdateLabelMutation:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    @strawberry.field(name="objId")
    def obj_id(self, info: strawberry.Info) -> Optional[strawberry.ID]:
        return coerce_str(getattr(self, "obj_id", None))


register_type("UpdateLabelMutation", UpdateLabelMutation, model=None)


@strawberry.type(name="DeleteLabelMutation")
class DeleteLabelMutation:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))


register_type("DeleteLabelMutation", DeleteLabelMutation, model=None)


@strawberry.type(name="DeleteMultipleLabelMutation")
class DeleteMultipleLabelMutation:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))


register_type("DeleteMultipleLabelMutation", DeleteMultipleLabelMutation, model=None)


@strawberry.type(name="CreateLabelForLabelsetMutation")
class CreateLabelForLabelsetMutation:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["AnnotationLabelType", strawberry.lazy("config.graphql_new.annotation_types")]] = strawberry.field(name="obj")
    @strawberry.field(name="objId")
    def obj_id(self, info: strawberry.Info) -> Optional[strawberry.ID]:
        return coerce_str(getattr(self, "obj_id", None))


register_type("CreateLabelForLabelsetMutation", CreateLabelForLabelsetMutation, model=None)


@strawberry.type(name="RemoveLabelsFromLabelsetMutation")
class RemoveLabelsFromLabelsetMutation:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))


register_type("RemoveLabelsFromLabelsetMutation", RemoveLabelsFromLabelsetMutation, model=None)


def _mutate_CreateLabelset(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:49

    Port of CreateLabelset.mutate
    """
    raise NotImplementedError("_mutate_CreateLabelset not yet ported — see manifest")


def m_create_labelset(info: strawberry.Info, base64_icon_string: Annotated[Optional[str], strawberry.argument(name="base64IconString", description='Base64-encoded file string for the Labelset icon (optional).')] = strawberry.UNSET, description: Annotated[Optional[str], strawberry.argument(name="description", description='Description of the Labelset.')] = strawberry.UNSET, filename: Annotated[Optional[str], strawberry.argument(name="filename", description='Filename of the document.')] = strawberry.UNSET, title: Annotated[str, strawberry.argument(name="title", description='Title of the Labelset.')] = strawberry.UNSET) -> Optional["CreateLabelset"]:
    kwargs = strip_unset({"base64_icon_string": base64_icon_string, "description": description, "filename": filename, "title": title})
    return _mutate_CreateLabelset(CreateLabelset, None, info, **kwargs)


def m_update_labelset(info: strawberry.Info, description: Annotated[Optional[str], strawberry.argument(name="description", description='Description of the Labelset.')] = strawberry.UNSET, icon: Annotated[Optional[str], strawberry.argument(name="icon", description='Base64-encoded file string for the Labelset icon (optional).')] = strawberry.UNSET, id: Annotated[str, strawberry.argument(name="id")] = strawberry.UNSET, title: Annotated[str, strawberry.argument(name="title", description='Title of the Labelset.')] = strawberry.UNSET) -> Optional["UpdateLabelset"]:
    kwargs = strip_unset({"description": description, "icon": icon, "id": id, "title": title})
    return drf_mutation(payload_cls=UpdateLabelset, model=LabelSet, serializer=LabelsetSerializer, type_name="LabelSetType", pk_fields=(), lookup_field="id", root=None, info=info, kwargs=kwargs)


def m_delete_labelset(info: strawberry.Info, id: Annotated[str, strawberry.argument(name="id")] = strawberry.UNSET) -> Optional["DeleteLabelset"]:
    kwargs = strip_unset({"id": id})
    return drf_deletion(payload_cls=DeleteLabelset, model=LabelSet, lookup_field="id", root=None, info=info, kwargs=kwargs)


def m_create_annotation_label(info: strawberry.Info, color: Annotated[Optional[str], strawberry.argument(name="color")] = strawberry.UNSET, description: Annotated[Optional[str], strawberry.argument(name="description")] = strawberry.UNSET, icon: Annotated[Optional[str], strawberry.argument(name="icon")] = strawberry.UNSET, text: Annotated[Optional[str], strawberry.argument(name="text")] = strawberry.UNSET, type: Annotated[Optional[str], strawberry.argument(name="type")] = strawberry.UNSET) -> Optional["CreateLabelMutation"]:
    kwargs = strip_unset({"color": color, "description": description, "icon": icon, "text": text, "type": type})
    return drf_mutation(payload_cls=CreateLabelMutation, model=AnnotationLabel, serializer=AnnotationLabelSerializer, type_name="AnnotationLabelType", pk_fields=(), lookup_field="id", root=None, info=info, kwargs=kwargs)


def m_update_annotation_label(info: strawberry.Info, color: Annotated[Optional[str], strawberry.argument(name="color")] = strawberry.UNSET, description: Annotated[Optional[str], strawberry.argument(name="description")] = strawberry.UNSET, icon: Annotated[Optional[str], strawberry.argument(name="icon")] = strawberry.UNSET, id: Annotated[str, strawberry.argument(name="id")] = strawberry.UNSET, label_type: Annotated[Optional[str], strawberry.argument(name="labelType")] = strawberry.UNSET, text: Annotated[Optional[str], strawberry.argument(name="text")] = strawberry.UNSET) -> Optional["UpdateLabelMutation"]:
    kwargs = strip_unset({"color": color, "description": description, "icon": icon, "id": id, "label_type": label_type, "text": text})
    return drf_mutation(payload_cls=UpdateLabelMutation, model=AnnotationLabel, serializer=AnnotationLabelSerializer, type_name="AnnotationLabelType", pk_fields=(), lookup_field="id", root=None, info=info, kwargs=kwargs)


def m_delete_annotation_label(info: strawberry.Info, id: Annotated[str, strawberry.argument(name="id")] = strawberry.UNSET) -> Optional["DeleteLabelMutation"]:
    kwargs = strip_unset({"id": id})
    return drf_deletion(payload_cls=DeleteLabelMutation, model=AnnotationLabel, lookup_field="id", root=None, info=info, kwargs=kwargs)


def _mutate_DeleteMultipleLabelMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:169

    Port of DeleteMultipleLabelMutation.mutate
    """
    raise NotImplementedError("_mutate_DeleteMultipleLabelMutation not yet ported — see manifest")


def m_delete_multiple_annotation_labels(info: strawberry.Info, annotation_label_ids_to_delete: Annotated[list[Optional[str]], strawberry.argument(name="annotationLabelIdsToDelete", description='List of ids of the labels to delete')] = strawberry.UNSET) -> Optional["DeleteMultipleLabelMutation"]:
    kwargs = strip_unset({"annotation_label_ids_to_delete": annotation_label_ids_to_delete})
    return _mutate_DeleteMultipleLabelMutation(DeleteMultipleLabelMutation, None, info, **kwargs)


def _mutate_CreateLabelForLabelsetMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:235

    Port of CreateLabelForLabelsetMutation.mutate
    """
    raise NotImplementedError("_mutate_CreateLabelForLabelsetMutation not yet ported — see manifest")


def m_create_annotation_label_for_labelset(info: strawberry.Info, color: Annotated[Optional[str], strawberry.argument(name="color")] = strawberry.UNSET, description: Annotated[Optional[str], strawberry.argument(name="description")] = strawberry.UNSET, icon: Annotated[Optional[str], strawberry.argument(name="icon")] = strawberry.UNSET, label_type: Annotated[Optional[str], strawberry.argument(name="labelType")] = strawberry.UNSET, labelset_id: Annotated[str, strawberry.argument(name="labelsetId", description='Id of the label that is to be updated.')] = strawberry.UNSET, text: Annotated[Optional[str], strawberry.argument(name="text")] = strawberry.UNSET) -> Optional["CreateLabelForLabelsetMutation"]:
    kwargs = strip_unset({"color": color, "description": description, "icon": icon, "label_type": label_type, "labelset_id": labelset_id, "text": text})
    return _mutate_CreateLabelForLabelsetMutation(CreateLabelForLabelsetMutation, None, info, **kwargs)


def _mutate_RemoveLabelsFromLabelsetMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:369

    Port of RemoveLabelsFromLabelsetMutation.mutate
    """
    raise NotImplementedError("_mutate_RemoveLabelsFromLabelsetMutation not yet ported — see manifest")


def m_remove_annotation_labels_from_labelset(info: strawberry.Info, label_ids: Annotated[list[Optional[str]], strawberry.argument(name="labelIds", description='List of Ids of the labels to be deleted.')] = strawberry.UNSET, labelset_id: Annotated[str, strawberry.argument(name="labelsetId")] = 'Id of the labelset to delete the labels from') -> Optional["RemoveLabelsFromLabelsetMutation"]:
    kwargs = strip_unset({"label_ids": label_ids, "labelset_id": labelset_id})
    return _mutate_RemoveLabelsFromLabelsetMutation(RemoveLabelsFromLabelsetMutation, None, info, **kwargs)



MUTATION_FIELDS = {
    "create_labelset": strawberry.field(resolver=m_create_labelset, name="createLabelset"),
    "update_labelset": strawberry.field(resolver=m_update_labelset, name="updateLabelset"),
    "delete_labelset": strawberry.field(resolver=m_delete_labelset, name="deleteLabelset"),
    "create_annotation_label": strawberry.field(resolver=m_create_annotation_label, name="createAnnotationLabel"),
    "update_annotation_label": strawberry.field(resolver=m_update_annotation_label, name="updateAnnotationLabel"),
    "delete_annotation_label": strawberry.field(resolver=m_delete_annotation_label, name="deleteAnnotationLabel"),
    "delete_multiple_annotation_labels": strawberry.field(resolver=m_delete_multiple_annotation_labels, name="deleteMultipleAnnotationLabels"),
    "create_annotation_label_for_labelset": strawberry.field(resolver=m_create_annotation_label_for_labelset, name="createAnnotationLabelForLabelset"),
    "remove_annotation_labels_from_labelset": strawberry.field(resolver=m_remove_annotation_labels_from_labelset, name="removeAnnotationLabelsFromLabelset"),
}
