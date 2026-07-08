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
from config.graphql._util import coerce_enum, coerce_str, strip_unset
from config.graphql import enums

from config.graphql.serializers import AnnotationSerializer
from opencontractserver.annotations.models import Annotation
from opencontractserver.annotations.models import Note


@strawberry.type(name="AddAnnotation")
class AddAnnotation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    message: Optional[str] = strawberry.field(name="message", default=None)
    annotation: Optional[Annotated["AnnotationType", strawberry.lazy("config.graphql.annotation_types")]] = strawberry.field(name="annotation", default=None)


register_type("AddAnnotation", AddAnnotation, model=None)


@strawberry.type(name="AddUrlAnnotation", description='Create an annotation labelled ``OC_URL`` with a click-through URL.\n\nConvenience wrapper over ``AddAnnotation``: ensures the corpus has an\n``OC_URL`` label (creating it if absent) and stamps ``link_url`` on the\nresulting annotation so the frontend renders the highlighted text as a\nclickable hyperlink.')
class AddUrlAnnotation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    message: Optional[str] = strawberry.field(name="message", default=None)
    annotation: Optional[Annotated["AnnotationType", strawberry.lazy("config.graphql.annotation_types")]] = strawberry.field(name="annotation", default=None)


register_type("AddUrlAnnotation", AddUrlAnnotation, model=None)


@strawberry.type(name="AddCountryAnnotation", description='Create an annotation labelled ``OC_COUNTRY`` with offline-geocoded data.\n\nMirrors :class:`AddUrlAnnotation` but routes through the bundled\ngeocoding service (see :mod:`opencontractserver.utils.geocoding`).\n``country_hint`` is intentionally absent — the country lookup is\nself-disambiguating.')
class AddCountryAnnotation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    message: Optional[str] = strawberry.field(name="message", default=None)
    annotation: Optional[Annotated["AnnotationType", strawberry.lazy("config.graphql.annotation_types")]] = strawberry.field(name="annotation", default=None)
    geocoded: Optional[bool] = strawberry.field(name="geocoded", description='True if the offline geocoder resolved the span; False when the annotation was created but no map pin was generated.', default=None)


register_type("AddCountryAnnotation", AddCountryAnnotation, model=None)


@strawberry.type(name="AddStateAnnotation", description='Create an annotation labelled ``OC_STATE`` with offline-geocoded data.\n\n``country_hint`` narrows the candidate pool to a single country; today\nthe bundled state dataset is US-only, so the hint mostly exists as a\nforward-compatibility hook for when non-US first-level admin\ndivisions are added.')
class AddStateAnnotation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    message: Optional[str] = strawberry.field(name="message", default=None)
    annotation: Optional[Annotated["AnnotationType", strawberry.lazy("config.graphql.annotation_types")]] = strawberry.field(name="annotation", default=None)
    geocoded: Optional[bool] = strawberry.field(name="geocoded", description='True if the offline geocoder resolved the span; False when the annotation was created but no map pin was generated.', default=None)


register_type("AddStateAnnotation", AddStateAnnotation, model=None)


@strawberry.type(name="AddCityAnnotation", description='Create an annotation labelled ``OC_CITY`` with offline-geocoded data.\n\n``country_hint`` / ``state_hint`` resolve via the same indexes the\nmain lookup uses, so any recognised form ("France" / "FR" / "Texas"\n/ "TX") works. Hints narrow the candidate pool BEFORE the\nexact / alias / fuzzy chain runs, so a hinted ambiguous string\n(e.g. "Paris" + state_hint="TX") prefers the right row even when\nmultiple rows are exact name matches.')
class AddCityAnnotation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    message: Optional[str] = strawberry.field(name="message", default=None)
    annotation: Optional[Annotated["AnnotationType", strawberry.lazy("config.graphql.annotation_types")]] = strawberry.field(name="annotation", default=None)
    geocoded: Optional[bool] = strawberry.field(name="geocoded", description='True if the offline geocoder resolved the span; False when the annotation was created but no map pin was generated.', default=None)


register_type("AddCityAnnotation", AddCityAnnotation, model=None)


@strawberry.type(name="RemoveAnnotation")
class RemoveAnnotation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    message: Optional[str] = strawberry.field(name="message", default=None)


register_type("RemoveAnnotation", RemoveAnnotation, model=None)


@strawberry.type(name="UpdateAnnotation")
class UpdateAnnotation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    message: Optional[str] = strawberry.field(name="message", default=None)
    obj_id: Optional[strawberry.ID] = strawberry.field(name="objId", default=None)


register_type("UpdateAnnotation", UpdateAnnotation, model=None)


@strawberry.type(name="AddDocTypeAnnotation")
class AddDocTypeAnnotation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    message: Optional[str] = strawberry.field(name="message", default=None)
    annotation: Optional[Annotated["AnnotationType", strawberry.lazy("config.graphql.annotation_types")]] = strawberry.field(name="annotation", default=None)


register_type("AddDocTypeAnnotation", AddDocTypeAnnotation, model=None)


@strawberry.type(name="ApproveAnnotation")
class ApproveAnnotation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    user_feedback: Optional[Annotated["UserFeedbackType", strawberry.lazy("config.graphql.user_types")]] = strawberry.field(name="userFeedback", default=None)
    message: Optional[str] = strawberry.field(name="message", default=None)


register_type("ApproveAnnotation", ApproveAnnotation, model=None)


@strawberry.type(name="RejectAnnotation")
class RejectAnnotation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    user_feedback: Optional[Annotated["UserFeedbackType", strawberry.lazy("config.graphql.user_types")]] = strawberry.field(name="userFeedback", default=None)
    message: Optional[str] = strawberry.field(name="message", default=None)


register_type("RejectAnnotation", RejectAnnotation, model=None)


@strawberry.type(name="AddRelationship")
class AddRelationship:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    relationship: Optional[Annotated["RelationshipType", strawberry.lazy("config.graphql.annotation_types")]] = strawberry.field(name="relationship", default=None)
    message: Optional[str] = strawberry.field(name="message", default=None)


register_type("AddRelationship", AddRelationship, model=None)


@strawberry.type(name="RemoveRelationship")
class RemoveRelationship:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    message: Optional[str] = strawberry.field(name="message", default=None)


register_type("RemoveRelationship", RemoveRelationship, model=None)


@strawberry.type(name="RemoveRelationships")
class RemoveRelationships:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    message: Optional[str] = strawberry.field(name="message", default=None)


register_type("RemoveRelationships", RemoveRelationships, model=None)


@strawberry.type(name="UpdateRelationship", description='Update an existing relationship by adding or removing annotations\nfrom source or target sets.')
class UpdateRelationship:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    relationship: Optional[Annotated["RelationshipType", strawberry.lazy("config.graphql.annotation_types")]] = strawberry.field(name="relationship", default=None)
    message: Optional[str] = strawberry.field(name="message", default=None)


register_type("UpdateRelationship", UpdateRelationship, model=None)


@strawberry.type(name="UpdateRelations")
class UpdateRelations:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    message: Optional[str] = strawberry.field(name="message", default=None)


register_type("UpdateRelations", UpdateRelations, model=None)


@strawberry.type(name="UpdateNote", description="Mutation to update a note's content, creating a new version in the process.\nOnly the note creator can update their notes.")
class UpdateNote:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    message: Optional[str] = strawberry.field(name="message", default=None)
    obj: Optional[Annotated["NoteType", strawberry.lazy("config.graphql.annotation_types")]] = strawberry.field(name="obj", default=None)
    version: Optional[int] = strawberry.field(name="version", description='The new version number after update', default=None)


register_type("UpdateNote", UpdateNote, model=None)


@strawberry.type(name="DeleteNote", description='Mutation to delete a note. Only the creator can delete their notes.')
class DeleteNote:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    message: Optional[str] = strawberry.field(name="message", default=None)


register_type("DeleteNote", DeleteNote, model=None)


@strawberry.type(name="CreateNote", description='Mutation to create a new note for a document.')
class CreateNote:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    message: Optional[str] = strawberry.field(name="message", default=None)
    obj: Optional[Annotated["NoteType", strawberry.lazy("config.graphql.annotation_types")]] = strawberry.field(name="obj", default=None)


register_type("CreateNote", CreateNote, model=None)


def _mutate_AddAnnotation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:257

    Port of AddAnnotation.mutate
    """
    raise NotImplementedError("_mutate_AddAnnotation not yet ported — see manifest")


def m_add_annotation(info: strawberry.Info, annotation_label_id: Annotated[str, strawberry.argument(name="annotationLabelId", description='Id of the label that is applied via this annotation.')] = strawberry.UNSET, annotation_type: Annotated[enums.LabelType, strawberry.argument(name="annotationType")] = strawberry.UNSET, corpus_id: Annotated[str, strawberry.argument(name="corpusId", description='ID of the corpus this annotation is for.')] = strawberry.UNSET, document_id: Annotated[str, strawberry.argument(name="documentId", description='Id of the document this annotation is on.')] = strawberry.UNSET, json: Annotated[GenericScalar, strawberry.argument(name="json", description='New-style JSON for multipage annotations')] = strawberry.UNSET, link_url: Annotated[Optional[str], strawberry.argument(name="linkUrl", description='Optional URL opened on click. Restricted to http(s):// or site-relative paths; intended for OC_URL annotations.')] = strawberry.UNSET, long_description: Annotated[Optional[str], strawberry.argument(name="longDescription", description='Optional markdown description for this annotation.')] = strawberry.UNSET, page: Annotated[int, strawberry.argument(name="page", description='What page is this annotation on (0-indexed)')] = strawberry.UNSET, raw_text: Annotated[str, strawberry.argument(name="rawText", description='What is the raw text of the annotation?')] = strawberry.UNSET) -> Optional["AddAnnotation"]:
    kwargs = strip_unset({"annotation_label_id": annotation_label_id, "annotation_type": annotation_type, "corpus_id": corpus_id, "document_id": document_id, "json": json, "link_url": link_url, "long_description": long_description, "page": page, "raw_text": raw_text})
    return _mutate_AddAnnotation(AddAnnotation, None, info, **kwargs)


def _mutate_AddUrlAnnotation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:365

    Port of AddUrlAnnotation.mutate
    """
    raise NotImplementedError("_mutate_AddUrlAnnotation not yet ported — see manifest")


def m_add_url_annotation(info: strawberry.Info, annotation_type: Annotated[enums.LabelType, strawberry.argument(name="annotationType", description='Annotation type: TOKEN_LABEL for PDFs, SPAN_LABEL for text.')] = strawberry.UNSET, corpus_id: Annotated[str, strawberry.argument(name="corpusId", description='ID of the corpus this annotation is for.')] = strawberry.UNSET, document_id: Annotated[str, strawberry.argument(name="documentId", description='ID of the document this annotation is on.')] = strawberry.UNSET, json: Annotated[GenericScalar, strawberry.argument(name="json", description='New-style JSON for multipage annotations.')] = strawberry.UNSET, link_url: Annotated[str, strawberry.argument(name="linkUrl", description='The target URL to open on click.')] = strawberry.UNSET, page: Annotated[int, strawberry.argument(name="page", description='What page is this annotation on (0-indexed).')] = strawberry.UNSET, raw_text: Annotated[str, strawberry.argument(name="rawText", description='The raw text being linked.')] = strawberry.UNSET) -> Optional["AddUrlAnnotation"]:
    kwargs = strip_unset({"annotation_type": annotation_type, "corpus_id": corpus_id, "document_id": document_id, "json": json, "link_url": link_url, "page": page, "raw_text": raw_text})
    return _mutate_AddUrlAnnotation(AddUrlAnnotation, None, info, **kwargs)


def _mutate_AddCountryAnnotation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:632

    Port of AddCountryAnnotation.mutate
    """
    raise NotImplementedError("_mutate_AddCountryAnnotation not yet ported — see manifest")


def m_add_country_annotation(info: strawberry.Info, annotation_type: Annotated[enums.LabelType, strawberry.argument(name="annotationType", description='Annotation type: TOKEN_LABEL for PDFs, SPAN_LABEL for text.')] = strawberry.UNSET, corpus_id: Annotated[str, strawberry.argument(name="corpusId", description='ID of the corpus this annotation is for.')] = strawberry.UNSET, document_id: Annotated[str, strawberry.argument(name="documentId", description='ID of the document this annotation is on.')] = strawberry.UNSET, json: Annotated[GenericScalar, strawberry.argument(name="json", description='New-style JSON for multipage annotations.')] = strawberry.UNSET, page: Annotated[int, strawberry.argument(name="page", description='What page is this annotation on (0-indexed).')] = strawberry.UNSET, raw_text: Annotated[str, strawberry.argument(name="rawText", description="The raw text identifying the country (e.g. 'France', 'FR').")] = strawberry.UNSET) -> Optional["AddCountryAnnotation"]:
    kwargs = strip_unset({"annotation_type": annotation_type, "corpus_id": corpus_id, "document_id": document_id, "json": json, "page": page, "raw_text": raw_text})
    return _mutate_AddCountryAnnotation(AddCountryAnnotation, None, info, **kwargs)


def _mutate_AddStateAnnotation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:710

    Port of AddStateAnnotation.mutate
    """
    raise NotImplementedError("_mutate_AddStateAnnotation not yet ported — see manifest")


def m_add_state_annotation(info: strawberry.Info, annotation_type: Annotated[enums.LabelType, strawberry.argument(name="annotationType")] = strawberry.UNSET, corpus_id: Annotated[str, strawberry.argument(name="corpusId")] = strawberry.UNSET, country_hint: Annotated[Optional[str], strawberry.argument(name="countryHint", description='Optional country to disambiguate the state (default: United States, the only first-level admin set bundled today).')] = strawberry.UNSET, document_id: Annotated[str, strawberry.argument(name="documentId")] = strawberry.UNSET, json: Annotated[GenericScalar, strawberry.argument(name="json")] = strawberry.UNSET, page: Annotated[int, strawberry.argument(name="page")] = strawberry.UNSET, raw_text: Annotated[str, strawberry.argument(name="rawText", description="The raw text identifying the state (e.g. 'Texas', 'TX').")] = strawberry.UNSET) -> Optional["AddStateAnnotation"]:
    kwargs = strip_unset({"annotation_type": annotation_type, "corpus_id": corpus_id, "country_hint": country_hint, "document_id": document_id, "json": json, "page": page, "raw_text": raw_text})
    return _mutate_AddStateAnnotation(AddStateAnnotation, None, info, **kwargs)


def _mutate_AddCityAnnotation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:798

    Port of AddCityAnnotation.mutate
    """
    raise NotImplementedError("_mutate_AddCityAnnotation not yet ported — see manifest")


def m_add_city_annotation(info: strawberry.Info, annotation_type: Annotated[enums.LabelType, strawberry.argument(name="annotationType")] = strawberry.UNSET, corpus_id: Annotated[str, strawberry.argument(name="corpusId")] = strawberry.UNSET, country_hint: Annotated[Optional[str], strawberry.argument(name="countryHint", description='Optional country to narrow candidate cities.')] = strawberry.UNSET, document_id: Annotated[str, strawberry.argument(name="documentId")] = strawberry.UNSET, json: Annotated[GenericScalar, strawberry.argument(name="json")] = strawberry.UNSET, page: Annotated[int, strawberry.argument(name="page")] = strawberry.UNSET, raw_text: Annotated[str, strawberry.argument(name="rawText", description="The raw text identifying the city. Disambiguation hints are recommended for ambiguous names (e.g. 'Paris', 'Springfield').")] = strawberry.UNSET, state_hint: Annotated[Optional[str], strawberry.argument(name="stateHint", description='Optional state / first-level admin division (only applied when the country is the US in the bundled dataset).')] = strawberry.UNSET) -> Optional["AddCityAnnotation"]:
    kwargs = strip_unset({"annotation_type": annotation_type, "corpus_id": corpus_id, "country_hint": country_hint, "document_id": document_id, "json": json, "page": page, "raw_text": raw_text, "state_hint": state_hint})
    return _mutate_AddCityAnnotation(AddCityAnnotation, None, info, **kwargs)


def _mutate_RemoveAnnotation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:65

    Port of RemoveAnnotation.mutate
    """
    raise NotImplementedError("_mutate_RemoveAnnotation not yet ported — see manifest")


def m_remove_annotation(info: strawberry.Info, annotation_id: Annotated[str, strawberry.argument(name="annotationId", description='Id of the annotation that is to be deleted.')] = strawberry.UNSET) -> Optional["RemoveAnnotation"]:
    kwargs = strip_unset({"annotation_id": annotation_id})
    return _mutate_RemoveAnnotation(RemoveAnnotation, None, info, **kwargs)


def m_update_annotation(info: strawberry.Info, annotation_label: Annotated[Optional[str], strawberry.argument(name="annotationLabel")] = strawberry.UNSET, id: Annotated[str, strawberry.argument(name="id")] = strawberry.UNSET, json: Annotated[Optional[GenericScalar], strawberry.argument(name="json")] = strawberry.UNSET, link_url: Annotated[Optional[str], strawberry.argument(name="linkUrl", description='Optional click-through URL for OC_URL annotations. Pass an empty string to clear an existing URL. Restricted to http(s):// or site-relative paths.')] = strawberry.UNSET, long_description: Annotated[Optional[str], strawberry.argument(name="longDescription")] = strawberry.UNSET, page: Annotated[Optional[int], strawberry.argument(name="page")] = strawberry.UNSET, raw_text: Annotated[Optional[str], strawberry.argument(name="rawText")] = strawberry.UNSET) -> Optional["UpdateAnnotation"]:
    kwargs = strip_unset({"annotation_label": annotation_label, "id": id, "json": json, "link_url": link_url, "long_description": long_description, "page": page, "raw_text": raw_text})
    return drf_mutation(payload_cls=UpdateAnnotation, model=Annotation, serializer=AnnotationSerializer, type_name="AnnotationType", pk_fields=('annotation_label',), lookup_field="id", root=None, info=info, kwargs=kwargs)


def _mutate_AddDocTypeAnnotation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:856

    Port of AddDocTypeAnnotation.mutate
    """
    raise NotImplementedError("_mutate_AddDocTypeAnnotation not yet ported — see manifest")


def m_add_doc_type_annotation(info: strawberry.Info, annotation_label_id: Annotated[str, strawberry.argument(name="annotationLabelId", description='Id of the label that is applied via this annotation.')] = strawberry.UNSET, corpus_id: Annotated[str, strawberry.argument(name="corpusId", description='ID of the corpus this annotation is for.')] = strawberry.UNSET, document_id: Annotated[str, strawberry.argument(name="documentId", description='Id of the document this annotation is on.')] = strawberry.UNSET) -> Optional["AddDocTypeAnnotation"]:
    kwargs = strip_unset({"annotation_label_id": annotation_label_id, "corpus_id": corpus_id, "document_id": document_id})
    return _mutate_AddDocTypeAnnotation(AddDocTypeAnnotation, None, info, **kwargs)


def _mutate_RemoveAnnotation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:65

    Port of RemoveAnnotation.mutate
    """
    raise NotImplementedError("_mutate_RemoveAnnotation not yet ported — see manifest")


def m_remove_doc_type_annotation(info: strawberry.Info, annotation_id: Annotated[str, strawberry.argument(name="annotationId", description='Id of the annotation that is to be deleted.')] = strawberry.UNSET) -> Optional["RemoveAnnotation"]:
    kwargs = strip_unset({"annotation_id": annotation_id})
    return _mutate_RemoveAnnotation(RemoveAnnotation, None, info, **kwargs)


def _mutate_ApproveAnnotation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:141

    Port of ApproveAnnotation.mutate
    """
    raise NotImplementedError("_mutate_ApproveAnnotation not yet ported — see manifest")


def m_approve_annotation(info: strawberry.Info, annotation_id: Annotated[strawberry.ID, strawberry.argument(name="annotationId", description='ID of the annotation to approve')] = strawberry.UNSET, comment: Annotated[Optional[str], strawberry.argument(name="comment", description='Optional comment for the approval')] = strawberry.UNSET) -> Optional["ApproveAnnotation"]:
    kwargs = strip_unset({"annotation_id": annotation_id, "comment": comment})
    return _mutate_ApproveAnnotation(ApproveAnnotation, None, info, **kwargs)


def _mutate_RejectAnnotation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:112

    Port of RejectAnnotation.mutate
    """
    raise NotImplementedError("_mutate_RejectAnnotation not yet ported — see manifest")


def m_reject_annotation(info: strawberry.Info, annotation_id: Annotated[strawberry.ID, strawberry.argument(name="annotationId", description='ID of the annotation to reject')] = strawberry.UNSET, comment: Annotated[Optional[str], strawberry.argument(name="comment", description='Optional comment for the rejection')] = strawberry.UNSET) -> Optional["RejectAnnotation"]:
    kwargs = strip_unset({"annotation_id": annotation_id, "comment": comment})
    return _mutate_RejectAnnotation(RejectAnnotation, None, info, **kwargs)


def _mutate_AddRelationship(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:968

    Port of AddRelationship.mutate
    """
    raise NotImplementedError("_mutate_AddRelationship not yet ported — see manifest")


def m_add_relationship(info: strawberry.Info, corpus_id: Annotated[str, strawberry.argument(name="corpusId", description='ID of the corpus for this relationship.')] = strawberry.UNSET, document_id: Annotated[str, strawberry.argument(name="documentId", description='ID of the document for this relationship.')] = strawberry.UNSET, relationship_label_id: Annotated[str, strawberry.argument(name="relationshipLabelId", description='ID of the label for this relationship.')] = strawberry.UNSET, source_ids: Annotated[list[Optional[str]], strawberry.argument(name="sourceIds", description='List of ids of the tokens in the source annotation')] = strawberry.UNSET, target_ids: Annotated[list[Optional[str]], strawberry.argument(name="targetIds", description='List of ids of the target tokens in the label')] = strawberry.UNSET) -> Optional["AddRelationship"]:
    kwargs = strip_unset({"corpus_id": corpus_id, "document_id": document_id, "relationship_label_id": relationship_label_id, "source_ids": source_ids, "target_ids": target_ids})
    return _mutate_AddRelationship(AddRelationship, None, info, **kwargs)


def _mutate_RemoveRelationship(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:905

    Port of RemoveRelationship.mutate
    """
    raise NotImplementedError("_mutate_RemoveRelationship not yet ported — see manifest")


def m_remove_relationship(info: strawberry.Info, relationship_id: Annotated[str, strawberry.argument(name="relationshipId", description='Id of the relationship that is to be deleted.')] = strawberry.UNSET) -> Optional["RemoveRelationship"]:
    kwargs = strip_unset({"relationship_id": relationship_id})
    return _mutate_RemoveRelationship(RemoveRelationship, None, info, **kwargs)


def _mutate_RemoveRelationships(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:1096

    Port of RemoveRelationships.mutate
    """
    raise NotImplementedError("_mutate_RemoveRelationships not yet ported — see manifest")


def m_remove_relationships(info: strawberry.Info, relationship_ids: Annotated[Optional[list[Optional[str]]], strawberry.argument(name="relationshipIds")] = strawberry.UNSET) -> Optional["RemoveRelationships"]:
    kwargs = strip_unset({"relationship_ids": relationship_ids})
    return _mutate_RemoveRelationships(RemoveRelationships, None, info, **kwargs)


def _mutate_UpdateRelationship(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:1151

    Port of UpdateRelationship.mutate
    """
    raise NotImplementedError("_mutate_UpdateRelationship not yet ported — see manifest")


def m_update_relationship(info: strawberry.Info, add_source_ids: Annotated[Optional[list[Optional[str]]], strawberry.argument(name="addSourceIds", description='List of annotation IDs to add as sources')] = strawberry.UNSET, add_target_ids: Annotated[Optional[list[Optional[str]]], strawberry.argument(name="addTargetIds", description='List of annotation IDs to add as targets')] = strawberry.UNSET, relationship_id: Annotated[str, strawberry.argument(name="relationshipId", description='ID of the relationship to update')] = strawberry.UNSET, remove_source_ids: Annotated[Optional[list[Optional[str]]], strawberry.argument(name="removeSourceIds", description='List of annotation IDs to remove from sources')] = strawberry.UNSET, remove_target_ids: Annotated[Optional[list[Optional[str]]], strawberry.argument(name="removeTargetIds", description='List of annotation IDs to remove from targets')] = strawberry.UNSET) -> Optional["UpdateRelationship"]:
    kwargs = strip_unset({"add_source_ids": add_source_ids, "add_target_ids": add_target_ids, "relationship_id": relationship_id, "remove_source_ids": remove_source_ids, "remove_target_ids": remove_target_ids})
    return _mutate_UpdateRelationship(UpdateRelationship, None, info, **kwargs)


def _mutate_UpdateRelations(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:1289

    Port of UpdateRelations.mutate
    """
    raise NotImplementedError("_mutate_UpdateRelations not yet ported — see manifest")


def m_update_relationships(info: strawberry.Info, relationships: Annotated[Optional[list[Optional[Annotated["RelationInputType", strawberry.lazy("config.graphql.annotation_types")]]]], strawberry.argument(name="relationships")] = strawberry.UNSET) -> Optional["UpdateRelations"]:
    kwargs = strip_unset({"relationships": relationships})
    return _mutate_UpdateRelations(UpdateRelations, None, info, **kwargs)


def _mutate_UpdateNote(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:1355

    Port of UpdateNote.mutate
    """
    raise NotImplementedError("_mutate_UpdateNote not yet ported — see manifest")


def m_update_note(info: strawberry.Info, new_content: Annotated[str, strawberry.argument(name="newContent", description='New markdown content for the note')] = strawberry.UNSET, note_id: Annotated[strawberry.ID, strawberry.argument(name="noteId", description='ID of the note to update')] = strawberry.UNSET, title: Annotated[Optional[str], strawberry.argument(name="title", description='Optional new title for the note')] = strawberry.UNSET) -> Optional["UpdateNote"]:
    kwargs = strip_unset({"new_content": new_content, "note_id": note_id, "title": title})
    return _mutate_UpdateNote(UpdateNote, None, info, **kwargs)


def m_delete_note(info: strawberry.Info, id: Annotated[str, strawberry.argument(name="id")] = strawberry.UNSET) -> Optional["DeleteNote"]:
    kwargs = strip_unset({"id": id})
    return drf_deletion(payload_cls=DeleteNote, model=Note, lookup_field="id", root=None, info=info, kwargs=kwargs)


def _mutate_CreateNote(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:1458

    Port of CreateNote.mutate
    """
    raise NotImplementedError("_mutate_CreateNote not yet ported — see manifest")


def m_create_note(info: strawberry.Info, content: Annotated[str, strawberry.argument(name="content", description='Markdown content of the note')] = strawberry.UNSET, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId", description='Optional ID of the corpus this note is associated with')] = strawberry.UNSET, document_id: Annotated[strawberry.ID, strawberry.argument(name="documentId", description='ID of the document this note is for')] = strawberry.UNSET, parent_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="parentId", description='Optional ID of parent note for hierarchical notes')] = strawberry.UNSET, title: Annotated[str, strawberry.argument(name="title", description='Title of the note')] = strawberry.UNSET) -> Optional["CreateNote"]:
    kwargs = strip_unset({"content": content, "corpus_id": corpus_id, "document_id": document_id, "parent_id": parent_id, "title": title})
    return _mutate_CreateNote(CreateNote, None, info, **kwargs)



MUTATION_FIELDS = {
    "add_annotation": strawberry.field(resolver=m_add_annotation, name="addAnnotation"),
    "add_url_annotation": strawberry.field(resolver=m_add_url_annotation, name="addUrlAnnotation", description='Create an annotation labelled ``OC_URL`` with a click-through URL.\n\nConvenience wrapper over ``AddAnnotation``: ensures the corpus has an\n``OC_URL`` label (creating it if absent) and stamps ``link_url`` on the\nresulting annotation so the frontend renders the highlighted text as a\nclickable hyperlink.'),
    "add_country_annotation": strawberry.field(resolver=m_add_country_annotation, name="addCountryAnnotation", description='Create an annotation labelled ``OC_COUNTRY`` with offline-geocoded data.\n\nMirrors :class:`AddUrlAnnotation` but routes through the bundled\ngeocoding service (see :mod:`opencontractserver.utils.geocoding`).\n``country_hint`` is intentionally absent — the country lookup is\nself-disambiguating.'),
    "add_state_annotation": strawberry.field(resolver=m_add_state_annotation, name="addStateAnnotation", description='Create an annotation labelled ``OC_STATE`` with offline-geocoded data.\n\n``country_hint`` narrows the candidate pool to a single country; today\nthe bundled state dataset is US-only, so the hint mostly exists as a\nforward-compatibility hook for when non-US first-level admin\ndivisions are added.'),
    "add_city_annotation": strawberry.field(resolver=m_add_city_annotation, name="addCityAnnotation", description='Create an annotation labelled ``OC_CITY`` with offline-geocoded data.\n\n``country_hint`` / ``state_hint`` resolve via the same indexes the\nmain lookup uses, so any recognised form ("France" / "FR" / "Texas"\n/ "TX") works. Hints narrow the candidate pool BEFORE the\nexact / alias / fuzzy chain runs, so a hinted ambiguous string\n(e.g. "Paris" + state_hint="TX") prefers the right row even when\nmultiple rows are exact name matches.'),
    "remove_annotation": strawberry.field(resolver=m_remove_annotation, name="removeAnnotation"),
    "update_annotation": strawberry.field(resolver=m_update_annotation, name="updateAnnotation"),
    "add_doc_type_annotation": strawberry.field(resolver=m_add_doc_type_annotation, name="addDocTypeAnnotation"),
    "remove_doc_type_annotation": strawberry.field(resolver=m_remove_doc_type_annotation, name="removeDocTypeAnnotation"),
    "approve_annotation": strawberry.field(resolver=m_approve_annotation, name="approveAnnotation"),
    "reject_annotation": strawberry.field(resolver=m_reject_annotation, name="rejectAnnotation"),
    "add_relationship": strawberry.field(resolver=m_add_relationship, name="addRelationship"),
    "remove_relationship": strawberry.field(resolver=m_remove_relationship, name="removeRelationship"),
    "remove_relationships": strawberry.field(resolver=m_remove_relationships, name="removeRelationships"),
    "update_relationship": strawberry.field(resolver=m_update_relationship, name="updateRelationship", description='Update an existing relationship by adding or removing annotations\nfrom source or target sets.'),
    "update_relationships": strawberry.field(resolver=m_update_relationships, name="updateRelationships"),
    "update_note": strawberry.field(resolver=m_update_note, name="updateNote", description="Mutation to update a note's content, creating a new version in the process.\nOnly the note creator can update their notes."),
    "delete_note": strawberry.field(resolver=m_delete_note, name="deleteNote", description='Mutation to delete a note. Only the creator can delete their notes.'),
    "create_note": strawberry.field(resolver=m_create_note, name="createNote", description='Mutation to create a new note for a document.'),
}
