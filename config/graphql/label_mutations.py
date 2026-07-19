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
import logging
from typing import Annotated

import strawberry
from django.conf import settings
from django.core.files.base import ContentFile
from graphql_relay import from_global_id, to_global_id

from config.graphql._util import strip_unset
from config.graphql.annotation_serializers import AnnotationLabelSerializer
from config.graphql.core.auth import PermissionDenied
from config.graphql.core.mutations import drf_deletion, drf_mutation
from config.graphql.core.relay import (
    register_type,
)
from config.graphql.ratelimits import RateLimits, graphql_ratelimit
from config.graphql.serializers import LabelsetSerializer
from config.graphql.validation_utils import validate_color
from opencontractserver.annotations.models import AnnotationLabel, LabelSet
from opencontractserver.shared.services.base import BaseService
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import (
    get_for_user_or_none,
    set_permissions_for_obj_to_user,
)

logger = logging.getLogger(__name__)


@graphql_ratelimit(rate=RateLimits.WRITE_MEDIUM, group="mutate")
def _write_medium_rate_gate(root, info, **kwargs):
    """Rate-limit gate with the ``(root, info)`` shape core decorators expect.

    graphene applied ``@graphql_ratelimit(rate=RateLimits.WRITE_MEDIUM)``
    directly to the ``mutate`` classmethod; the strawberry mutate stubs take
    ``payload_cls`` first, so the decorator is hoisted onto this no-op and
    invoked at the top of the rate-limited stub. ``group="mutate"`` preserves
    the shared graphene bucket.
    """
    return None


@strawberry.type(name="CreateLabelset")
class CreateLabelset:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[LabelSetType, strawberry.lazy("config.graphql.annotation_types")]
    ) = strawberry.field(name="obj", default=None)


register_type("CreateLabelset", CreateLabelset, model=None)


@strawberry.type(name="UpdateLabelset")
class UpdateLabelset:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj_id: strawberry.ID | None = strawberry.field(name="objId", default=None)


register_type("UpdateLabelset", UpdateLabelset, model=None)


@strawberry.type(name="DeleteLabelset")
class DeleteLabelset:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("DeleteLabelset", DeleteLabelset, model=None)


@strawberry.type(name="CreateLabelMutation")
class CreateLabelMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj_id: strawberry.ID | None = strawberry.field(name="objId", default=None)


register_type("CreateLabelMutation", CreateLabelMutation, model=None)


@strawberry.type(name="UpdateLabelMutation")
class UpdateLabelMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj_id: strawberry.ID | None = strawberry.field(name="objId", default=None)


register_type("UpdateLabelMutation", UpdateLabelMutation, model=None)


@strawberry.type(name="DeleteLabelMutation")
class DeleteLabelMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("DeleteLabelMutation", DeleteLabelMutation, model=None)


@strawberry.type(name="DeleteMultipleLabelMutation")
class DeleteMultipleLabelMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("DeleteMultipleLabelMutation", DeleteMultipleLabelMutation, model=None)


@strawberry.type(name="CreateLabelForLabelsetMutation")
class CreateLabelForLabelsetMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[
            AnnotationLabelType, strawberry.lazy("config.graphql.annotation_types")
        ]
    ) = strawberry.field(name="obj", default=None)
    obj_id: strawberry.ID | None = strawberry.field(name="objId", default=None)


register_type(
    "CreateLabelForLabelsetMutation", CreateLabelForLabelsetMutation, model=None
)


@strawberry.type(name="RemoveLabelsFromLabelsetMutation")
class RemoveLabelsFromLabelsetMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type(
    "RemoveLabelsFromLabelsetMutation", RemoveLabelsFromLabelsetMutation, model=None
)


def _mutate_CreateLabelset(
    payload_cls, root, info, title, description, filename=None, base64_icon_string=None
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/label_mutations.py:51

    Port of CreateLabelset.mutate
    """
    # @login_required + @graphql_ratelimit(WRITE_MEDIUM) — inlined because the
    # mutate stub takes ``payload_cls`` first, breaking the ``(root, info)``
    # calling convention the core decorators expect.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()
    _write_medium_rate_gate(root, info)

    if base64_icon_string is None:
        base64_icon_string = settings.DEFAULT_IMAGE

    ok = False
    obj = None

    try:
        user = info.context.user
        icon = ContentFile(
            base64.b64decode(
                base64_icon_string.split(",")[1]
                if "," in base64_icon_string[:32]
                else base64_icon_string
            ),
            name=filename if filename is not None else "icon.png",
        )
        obj = LabelSet(creator=user, title=title, description=description, icon=icon)
        obj.save()

        # Assign permissions for user to obj so it can be retrieved
        set_permissions_for_obj_to_user(
            user, obj, [PermissionTypes.CRUD], is_new=True, request=info.context
        )

        ok = True
        message = "Success"

    except Exception as e:
        message = f"Error creating labelset: {e}"

    return payload_cls(message=message, ok=ok, obj=obj)


def m_create_labelset(
    info: strawberry.Info,
    base64_icon_string: Annotated[
        str | None,
        strawberry.argument(
            name="base64IconString",
            description="Base64-encoded file string for the Labelset icon (optional).",
        ),
    ] = strawberry.UNSET,
    description: Annotated[
        str | None,
        strawberry.argument(
            name="description", description="Description of the Labelset."
        ),
    ] = strawberry.UNSET,
    filename: Annotated[
        str | None,
        strawberry.argument(name="filename", description="Filename of the document."),
    ] = strawberry.UNSET,
    title: Annotated[
        str, strawberry.argument(name="title", description="Title of the Labelset.")
    ] = strawberry.UNSET,
) -> CreateLabelset | None:
    kwargs = strip_unset(
        {
            "base64_icon_string": base64_icon_string,
            "description": description,
            "filename": filename,
            "title": title,
        }
    )
    return _mutate_CreateLabelset(CreateLabelset, None, info, **kwargs)


def m_update_labelset(
    info: strawberry.Info,
    description: Annotated[
        str | None,
        strawberry.argument(
            name="description", description="Description of the Labelset."
        ),
    ] = strawberry.UNSET,
    icon: Annotated[
        str | None,
        strawberry.argument(
            name="icon",
            description="Base64-encoded file string for the Labelset icon (optional).",
        ),
    ] = strawberry.UNSET,
    id: Annotated[str, strawberry.argument(name="id")] = strawberry.UNSET,
    title: Annotated[
        str, strawberry.argument(name="title", description="Title of the Labelset.")
    ] = strawberry.UNSET,
) -> UpdateLabelset | None:
    kwargs = strip_unset(
        {"description": description, "icon": icon, "id": id, "title": title}
    )
    return drf_mutation(
        payload_cls=UpdateLabelset,
        model=LabelSet,
        serializer=LabelsetSerializer,
        type_name="LabelSetType",
        pk_fields=(),
        lookup_field="id",
        root=None,
        info=info,
        kwargs=kwargs,
    )


def m_delete_labelset(
    info: strawberry.Info,
    id: Annotated[str, strawberry.argument(name="id")] = strawberry.UNSET,
) -> DeleteLabelset | None:
    kwargs = strip_unset({"id": id})
    return drf_deletion(
        payload_cls=DeleteLabelset,
        model=LabelSet,
        lookup_field="id",
        root=None,
        info=info,
        kwargs=kwargs,
    )


def m_create_annotation_label(
    info: strawberry.Info,
    color: Annotated[str | None, strawberry.argument(name="color")] = strawberry.UNSET,
    description: Annotated[
        str | None, strawberry.argument(name="description")
    ] = strawberry.UNSET,
    icon: Annotated[str | None, strawberry.argument(name="icon")] = strawberry.UNSET,
    text: Annotated[str | None, strawberry.argument(name="text")] = strawberry.UNSET,
    type: Annotated[str | None, strawberry.argument(name="type")] = strawberry.UNSET,
) -> CreateLabelMutation | None:
    kwargs = strip_unset(
        {
            "color": color,
            "description": description,
            "icon": icon,
            "text": text,
            "type": type,
        }
    )
    return drf_mutation(
        payload_cls=CreateLabelMutation,
        model=AnnotationLabel,
        serializer=AnnotationLabelSerializer,
        type_name="AnnotationLabelType",
        pk_fields=(),
        lookup_field="id",
        root=None,
        info=info,
        kwargs=kwargs,
    )


def m_update_annotation_label(
    info: strawberry.Info,
    color: Annotated[str | None, strawberry.argument(name="color")] = strawberry.UNSET,
    description: Annotated[
        str | None, strawberry.argument(name="description")
    ] = strawberry.UNSET,
    icon: Annotated[str | None, strawberry.argument(name="icon")] = strawberry.UNSET,
    id: Annotated[str, strawberry.argument(name="id")] = strawberry.UNSET,
    label_type: Annotated[
        str | None, strawberry.argument(name="labelType")
    ] = strawberry.UNSET,
    text: Annotated[str | None, strawberry.argument(name="text")] = strawberry.UNSET,
) -> UpdateLabelMutation | None:
    kwargs = strip_unset(
        {
            "color": color,
            "description": description,
            "icon": icon,
            "id": id,
            "label_type": label_type,
            "text": text,
        }
    )
    return drf_mutation(
        payload_cls=UpdateLabelMutation,
        model=AnnotationLabel,
        serializer=AnnotationLabelSerializer,
        type_name="AnnotationLabelType",
        pk_fields=(),
        lookup_field="id",
        root=None,
        info=info,
        kwargs=kwargs,
    )


def m_delete_annotation_label(
    info: strawberry.Info,
    id: Annotated[str, strawberry.argument(name="id")] = strawberry.UNSET,
) -> DeleteLabelMutation | None:
    kwargs = strip_unset({"id": id})
    return drf_deletion(
        payload_cls=DeleteLabelMutation,
        model=AnnotationLabel,
        lookup_field="id",
        root=None,
        info=info,
        kwargs=kwargs,
    )


def _mutate_DeleteMultipleLabelMutation(
    payload_cls, root, info, annotation_label_ids_to_delete
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/label_mutations.py:170

    Port of DeleteMultipleLabelMutation.mutate
    """
    # @login_required — inlined (mutate stub takes ``payload_cls`` first).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()
    user = info.context.user
    try:
        label_pks = list(
            map(
                lambda label_id: from_global_id(label_id)[1],
                annotation_label_ids_to_delete,
            )
        )
        for label_pk in label_pks:
            # IDOR protection: collapse "label doesn't exist", "hidden
            # from caller", and "caller can READ but is not the creator"
            # into the same response. AnnotationLabel uses creator-based
            # permissions (no guardian tables); the service-layer
            # IDOR-safe lookup enforces creator/public (superusers are
            # computed like a normal user — scoped admin access, 2026-05).
            label = get_for_user_or_none(AnnotationLabel, label_pk, user)
            if label is None:
                return payload_cls(ok=False, message="Label not found")
            # Run the creator gate BEFORE the ``read_only`` check so a
            # non-creator who happens to be able to READ a public
            # built-in label gets the unified "Label not found" response
            # — surfacing "Cannot delete read-only labels" would reveal
            # the label's existence + read-only flag to anyone with a
            # guessable pk.
            if label.creator_id != user.id:
                return payload_cls(ok=False, message="Label not found")
            # read_only labels cannot be deleted (built-in system labels)
            if label.read_only:
                return payload_cls(ok=False, message="Cannot delete read-only labels")
            label.delete()
        ok = True
        message = "Success"

    except Exception as e:
        ok = False
        message = f"Delete failed due to error: {e}"

    return payload_cls(ok=ok, message=message)


def m_delete_multiple_annotation_labels(
    info: strawberry.Info,
    annotation_label_ids_to_delete: Annotated[
        list[str | None],
        strawberry.argument(
            name="annotationLabelIdsToDelete",
            description="List of ids of the labels to delete",
        ),
    ] = strawberry.UNSET,
) -> DeleteMultipleLabelMutation | None:
    kwargs = strip_unset(
        {"annotation_label_ids_to_delete": annotation_label_ids_to_delete}
    )
    return _mutate_DeleteMultipleLabelMutation(
        DeleteMultipleLabelMutation, None, info, **kwargs
    )


def _mutate_CreateLabelForLabelsetMutation(
    payload_cls,
    root,
    info,
    labelset_id,
    text=None,
    description=None,
    color=None,
    icon=None,
    label_type=None,
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/label_mutations.py:236

    Port of CreateLabelForLabelsetMutation.mutate
    """
    # @login_required — inlined (mutate stub takes ``payload_cls`` first).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()
    ok = False
    obj = None
    obj_id = None

    # Unified IDOR-safe message: missing pk, malformed pk, no READ, and
    # no UPDATE all collapse to a single response so the caller cannot
    # enumerate which labelsets exist.
    not_found_msg = (
        "Failed to create label for labelset due to error: "
        "LabelSet matching query does not exist."
    )

    try:
        labelset_pk = from_global_id(labelset_id)[1]
    except Exception:
        logger.warning(
            "CreateLabelForLabelsetMutation: malformed labelset_id=%s",
            labelset_id,
        )
        return payload_cls(obj=None, obj_id=None, message=not_found_msg, ok=False)

    # Permission check runs before validation so a non-owner cannot
    # distinguish "reached validation" from "denied" via different
    # error messages (IDOR mitigation — see
    # docs/permissioning/consolidated_permissioning_guide.md).
    # Phase D rule (#1658): READ is a precondition for UPDATE — the
    # IDOR-safe lookup helper enforces it; the explicit UPDATE check
    # below layers the write permission on top via the service layer.
    labelset = get_for_user_or_none(LabelSet, labelset_pk, info.context.user)
    if labelset is None or BaseService.require_permission(
        labelset, info.context.user, PermissionTypes.UPDATE, request=info.context
    ):
        logger.warning(
            "CreateLabelForLabelsetMutation: labelset not found or "
            "permission denied (labelset_id=%s)",
            labelset_id,
        )
        return payload_cls(obj=None, obj_id=None, message=not_found_msg, ok=False)

    try:
        # Reject blank text explicitly: Django's ``blank=False`` is
        # form-only and ``objects.create()`` would silently apply the
        # "Text Label" model default.
        if not (text and text.strip()):
            return payload_cls(
                obj=None,
                obj_id=None,
                message="Label text is required and cannot be blank.",
                ok=False,
            )

        if color == "":
            color = None
        is_valid_color, color_error = validate_color(color)
        if not is_valid_color:
            return payload_cls(obj=None, obj_id=None, message=color_error, ok=False)

        logger.debug("CreateLabelForLabelsetMutation - mutate / Labelset", labelset)
        # Drop None/"" so model field defaults apply rather than
        # writing blank values at the DB level.
        create_kwargs = {
            k: v
            for k, v in {
                "text": text,
                "description": description,
                "color": color,
                "icon": icon,
                "label_type": label_type,
            }.items()
            if v is not None and v != ""
        }
        obj = AnnotationLabel.objects.create(creator=info.context.user, **create_kwargs)
        obj_id = to_global_id("AnnotationLabelType", obj.id)
        logger.debug("CreateLabelForLabelsetMutation - mutate / Created label", obj)

        set_permissions_for_obj_to_user(
            info.context.user,
            obj,
            [PermissionTypes.CRUD],
            is_new=True,
            request=info.context,
        )
        logger.debug("CreateLabelForLabelsetMutation - permissioned for creating user")

        labelset.annotation_labels.add(obj)
        ok = True
        message = "SUCCESS"
        logger.debug("Done")

    except Exception as e:
        logger.exception("CreateLabelForLabelsetMutation failed")
        message = f"Failed to create label for labelset due to error: {e}"

    return payload_cls(obj=obj, obj_id=obj_id, message=message, ok=ok)


def m_create_annotation_label_for_labelset(
    info: strawberry.Info,
    color: Annotated[str | None, strawberry.argument(name="color")] = strawberry.UNSET,
    description: Annotated[
        str | None, strawberry.argument(name="description")
    ] = strawberry.UNSET,
    icon: Annotated[str | None, strawberry.argument(name="icon")] = strawberry.UNSET,
    label_type: Annotated[
        str | None, strawberry.argument(name="labelType")
    ] = strawberry.UNSET,
    labelset_id: Annotated[
        str,
        strawberry.argument(
            name="labelsetId", description="Id of the label that is to be updated."
        ),
    ] = strawberry.UNSET,
    text: Annotated[str | None, strawberry.argument(name="text")] = strawberry.UNSET,
) -> CreateLabelForLabelsetMutation | None:
    kwargs = strip_unset(
        {
            "color": color,
            "description": description,
            "icon": icon,
            "label_type": label_type,
            "labelset_id": labelset_id,
            "text": text,
        }
    )
    return _mutate_CreateLabelForLabelsetMutation(
        CreateLabelForLabelsetMutation, None, info, **kwargs
    )


def _mutate_RemoveLabelsFromLabelsetMutation(
    payload_cls, root, info, label_ids, labelset_id
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/label_mutations.py:370

    Port of RemoveLabelsFromLabelsetMutation.mutate
    """
    # @login_required — inlined (mutate stub takes ``payload_cls`` first).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()
    ok = False

    # Unified IDOR-safe message — see CreateLabelForLabelsetMutation.
    not_found_msg = (
        "Error removing label(s) from labelset: "
        "LabelSet matching query does not exist."
    )

    try:
        labelset_pk = from_global_id(labelset_id)[1]
        label_pks = [int(from_global_id(gid)[1]) for gid in label_ids]
    except Exception:
        logger.warning(
            "RemoveLabelsFromLabelsetMutation: malformed id "
            "(labelset_id=%s, label_ids=%r)",
            labelset_id,
            label_ids,
        )
        return payload_cls(message=not_found_msg, ok=False)

    user = info.context.user
    # Phase D rule (#1658): READ is a precondition for UPDATE.
    labelset = get_for_user_or_none(LabelSet, labelset_pk, user)
    if labelset is None or BaseService.require_permission(
        labelset, user, PermissionTypes.UPDATE, request=info.context
    ):
        logger.warning(
            "RemoveLabelsFromLabelsetMutation: labelset not found or "
            "permission denied (labelset_id=%s)",
            labelset_id,
        )
        return payload_cls(message=not_found_msg, ok=False)

    try:
        labelset.annotation_labels.remove(*label_pks)
        ok = True
        message = "Success"
    except Exception as e:
        logger.exception("RemoveLabelsFromLabelsetMutation failed")
        message = f"Error removing label(s) from labelset: {e}"

    return payload_cls(message=message, ok=ok)


def m_remove_annotation_labels_from_labelset(
    info: strawberry.Info,
    label_ids: Annotated[
        list[str | None],
        strawberry.argument(
            name="labelIds", description="List of Ids of the labels to be deleted."
        ),
    ] = strawberry.UNSET,
    labelset_id: Annotated[
        str, strawberry.argument(name="labelsetId")
    ] = "Id of the labelset to delete the labels from",
) -> RemoveLabelsFromLabelsetMutation | None:
    kwargs = strip_unset({"label_ids": label_ids, "labelset_id": labelset_id})
    return _mutate_RemoveLabelsFromLabelsetMutation(
        RemoveLabelsFromLabelsetMutation, None, info, **kwargs
    )


MUTATION_FIELDS = {
    "create_labelset": strawberry.field(
        resolver=m_create_labelset, name="createLabelset"
    ),
    "update_labelset": strawberry.field(
        resolver=m_update_labelset, name="updateLabelset"
    ),
    "delete_labelset": strawberry.field(
        resolver=m_delete_labelset, name="deleteLabelset"
    ),
    "create_annotation_label": strawberry.field(
        resolver=m_create_annotation_label, name="createAnnotationLabel"
    ),
    "update_annotation_label": strawberry.field(
        resolver=m_update_annotation_label, name="updateAnnotationLabel"
    ),
    "delete_annotation_label": strawberry.field(
        resolver=m_delete_annotation_label, name="deleteAnnotationLabel"
    ),
    "delete_multiple_annotation_labels": strawberry.field(
        resolver=m_delete_multiple_annotation_labels,
        name="deleteMultipleAnnotationLabels",
    ),
    "create_annotation_label_for_labelset": strawberry.field(
        resolver=m_create_annotation_label_for_labelset,
        name="createAnnotationLabelForLabelset",
    ),
    "remove_annotation_labels_from_labelset": strawberry.field(
        resolver=m_remove_annotation_labels_from_labelset,
        name="removeAnnotationLabelsFromLabelset",
    ),
}
