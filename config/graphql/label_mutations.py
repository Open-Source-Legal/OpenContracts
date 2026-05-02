"""
GraphQL mutations for label and labelset operations.
"""

import base64
import logging

import graphene
from django.conf import settings
from django.core.files.base import ContentFile
from graphql_jwt.decorators import login_required
from graphql_relay import from_global_id, to_global_id

from config.graphql.annotation_serializers import AnnotationLabelSerializer
from config.graphql.base import DRFDeletion, DRFMutation
from config.graphql.graphene_types import AnnotationLabelType, LabelSetType
from config.graphql.ratelimits import RateLimits, graphql_ratelimit
from config.graphql.serializers import LabelsetSerializer
from config.graphql.validation_utils import validate_color
from opencontractserver.annotations.models import AnnotationLabel, LabelSet
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import (
    set_permissions_for_obj_to_user,
    user_has_permission_for_obj,
)

logger = logging.getLogger(__name__)


class CreateLabelset(graphene.Mutation):
    class Arguments:
        base64_icon_string = graphene.String(
            required=False,
            description="Base64-encoded file string for the Labelset icon (optional).",
        )
        filename = graphene.String(
            required=False, description="Filename of the document."
        )
        title = graphene.String(required=True, description="Title of the Labelset.")
        description = graphene.String(
            required=False, description="Description of the Labelset."
        )

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(LabelSetType)

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_MEDIUM)
    def mutate(
        root, info, title, description, filename=None, base64_icon_string=None
    ) -> "CreateLabelset":
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
            obj = LabelSet(
                creator=user, title=title, description=description, icon=icon
            )
            obj.save()

            # Assign permissions for user to obj so it can be retrieved
            set_permissions_for_obj_to_user(user, obj, [PermissionTypes.CRUD])

            ok = True
            message = "Success"

        except Exception as e:
            message = f"Error creating labelset: {e}"

        return CreateLabelset(message=message, ok=ok, obj=obj)


class UpdateLabelset(DRFMutation):
    class IOSettings:
        lookup_field = "id"
        serializer = LabelsetSerializer
        model = LabelSet
        graphene_model = LabelSetType

    class Arguments:
        id = graphene.String(required=True)
        icon = graphene.String(
            required=False,
            description="Base64-encoded file string for the Labelset icon (optional).",
        )
        title = graphene.String(required=True, description="Title of the Labelset.")
        description = graphene.String(
            required=False, description="Description of the Labelset."
        )


class DeleteLabelset(DRFDeletion):
    class IOSettings:
        model = LabelSet
        lookup_field = "id"

    class Arguments:
        id = graphene.String(required=True)


class CreateLabelMutation(DRFMutation):
    class IOSettings:
        pk_fields = []
        serializer = AnnotationLabelSerializer
        model = AnnotationLabel
        graphene_model = AnnotationLabelType

    class Arguments:
        text = graphene.String(required=False)
        description = graphene.String(required=False)
        color = graphene.String(required=False)
        icon = graphene.String(required=False)
        type = graphene.String(required=False)


class UpdateLabelMutation(DRFMutation):
    class IOSettings:
        pk_fields = []
        serializer = AnnotationLabelSerializer
        lookup_field = "id"
        model = AnnotationLabel
        graphene_model = AnnotationLabelType

    class Arguments:
        id = graphene.String(required=True)
        text = graphene.String(required=False)
        description = graphene.String(required=False)
        color = graphene.String(required=False)
        icon = graphene.String(required=False)
        label_type = graphene.String(required=False)


class DeleteLabelMutation(DRFDeletion):
    class IOSettings:
        model = AnnotationLabel
        lookup_field = "id"

    class Arguments:
        id = graphene.String(required=True)


class DeleteMultipleLabelMutation(graphene.Mutation):
    class Arguments:
        annotation_label_ids_to_delete = graphene.List(
            graphene.String,
            required=True,
            description="List of ids of the labels to delete",
        )

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    def mutate(
        root, info, annotation_label_ids_to_delete
    ) -> "DeleteMultipleLabelMutation":
        user = info.context.user
        try:
            label_pks = list(
                map(
                    lambda label_id: from_global_id(label_id)[1],
                    annotation_label_ids_to_delete,
                )
            )
            for label_pk in label_pks:
                try:
                    label = AnnotationLabel.objects.get(pk=label_pk)
                    # AnnotationLabel uses creator-based permissions (no guardian tables)
                    # Only the creator or superuser can delete labels
                    # read_only labels cannot be deleted (built-in system labels)
                    if label.read_only:
                        return DeleteMultipleLabelMutation(
                            ok=False, message="Cannot delete read-only labels"
                        )
                    if not user.is_superuser and label.creator_id != user.id:
                        # Use consistent error message for IDOR protection
                        return DeleteMultipleLabelMutation(
                            ok=False, message="Label not found"
                        )
                    label.delete()
                except AnnotationLabel.DoesNotExist:
                    return DeleteMultipleLabelMutation(
                        ok=False, message="Label not found"
                    )
            ok = True
            message = "Success"

        except Exception as e:
            ok = False
            message = f"Delete failed due to error: {e}"

        return DeleteMultipleLabelMutation(ok=ok, message=message)


class CreateLabelForLabelsetMutation(graphene.Mutation):
    class Arguments:
        labelset_id = graphene.String(
            required=True, description="Id of the label that is to be updated."
        )
        text = graphene.String(required=False)
        description = graphene.String(required=False)
        color = graphene.String(required=False)
        icon = graphene.String(required=False)
        label_type = graphene.String(required=False)

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(AnnotationLabelType)
    obj_id = graphene.ID()

    @login_required
    def mutate(
        root,
        info,
        labelset_id,
        text=None,
        description=None,
        color=None,
        icon=None,
        label_type=None,
    ) -> "CreateLabelForLabelsetMutation":

        ok = False
        obj = None
        obj_id = None

        try:
            # Permission check runs before validation so a non-owner cannot
            # distinguish "reached validation" from "denied" via different
            # error messages (IDOR mitigation — see
            # docs/permissioning/consolidated_permissioning_guide.md).
            labelset = LabelSet.objects.get(pk=from_global_id(labelset_id)[1])
            if not user_has_permission_for_obj(
                info.context.user,
                labelset,
                PermissionTypes.UPDATE,
                include_group_permissions=True,
            ):
                raise LabelSet.DoesNotExist()

            # Reject blank text explicitly: Django's ``blank=False`` is
            # form-only and ``objects.create()`` would silently apply the
            # "Text Label" model default.
            if not (text and text.strip()):
                return CreateLabelForLabelsetMutation(
                    obj=None,
                    obj_id=None,
                    message="Label text is required and cannot be blank.",
                    ok=False,
                )

            if color == "":
                color = None
            is_valid_color, color_error = validate_color(color)
            if not is_valid_color:
                return CreateLabelForLabelsetMutation(
                    obj=None, obj_id=None, message=color_error, ok=False
                )

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
            obj = AnnotationLabel.objects.create(
                creator=info.context.user, **create_kwargs
            )
            obj_id = to_global_id("AnnotationLabelType", obj.id)
            logger.debug("CreateLabelForLabelsetMutation - mutate / Created label", obj)

            set_permissions_for_obj_to_user(
                info.context.user, obj, [PermissionTypes.CRUD]
            )
            logger.debug(
                "CreateLabelForLabelsetMutation - permissioned for creating user"
            )

            labelset.annotation_labels.add(obj)
            ok = True
            message = "SUCCESS"
            logger.debug("Done")

        except LabelSet.DoesNotExist:
            # Auth rejection or genuine 404 — warn without stack trace.
            logger.warning(
                "CreateLabelForLabelsetMutation: labelset not found or "
                "permission denied (labelset_id=%s)",
                labelset_id,
            )
            message = (
                "Failed to create label for labelset due to error: "
                "LabelSet matching query does not exist."
            )
        except Exception as e:
            logger.exception("CreateLabelForLabelsetMutation failed")
            message = f"Failed to create label for labelset due to error: {e}"

        return CreateLabelForLabelsetMutation(
            obj=obj, obj_id=obj_id, message=message, ok=ok
        )


class RemoveLabelsFromLabelsetMutation(graphene.Mutation):
    class Arguments:
        label_ids = graphene.List(
            graphene.String,
            required=True,
            description="List of Ids of the labels to be deleted.",
        )
        labelset_id = graphene.String(
            "Id of the labelset to delete the labels from", required=True
        )

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    def mutate(
        root, info, label_ids, labelset_id
    ) -> "RemoveLabelsFromLabelsetMutation":

        ok = False

        try:
            user = info.context.user
            label_pks = list(
                map(lambda graphene_id: from_global_id(graphene_id)[1], label_ids)
            )
            labelset = LabelSet.objects.get(pk=from_global_id(labelset_id)[1])
            if not user_has_permission_for_obj(
                user,
                labelset,
                PermissionTypes.UPDATE,
                include_group_permissions=True,
            ):
                raise LabelSet.DoesNotExist()
            labelset.annotation_labels.remove(*label_pks)
            ok = True
            message = "Success"

        except LabelSet.DoesNotExist:
            # Auth rejection or genuine 404 — warn without stack trace.
            logger.warning(
                "RemoveLabelsFromLabelsetMutation: labelset not found or "
                "permission denied (labelset_id=%s)",
                labelset_id,
            )
            message = (
                "Error removing label(s) from labelset: "
                "LabelSet matching query does not exist."
            )
        except Exception as e:
            logger.exception("RemoveLabelsFromLabelsetMutation failed")
            message = f"Error removing label(s) from labelset: {e}"

        return RemoveLabelsFromLabelsetMutation(message=message, ok=ok)
