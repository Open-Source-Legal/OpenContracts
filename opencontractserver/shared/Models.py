import django
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import models

from opencontractserver.shared.Managers import PermissionManager
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import user_has_permission_for_obj


class BaseOCModel(models.Model):

    """
    Base model for all OpenContracts models that has some properties it's nice to have on
    all models.
    """

    # this makes the queryset function readable_by_user() available which will filter properly on permissioning system.
    objects = PermissionManager()

    class Meta:
        abstract = True

    # Processing fields
    # user_lock should be set when long-running process is activated for a given model by a user
    # and unset when process is done.
    user_lock = django.db.models.ForeignKey(
        get_user_model(),
        on_delete=django.db.models.SET_NULL,
        null=True,
        blank=True,
        related_name="locked_%(class)s_objects",
        db_index=True,
    )
    # This should be set to true if a long-running job is set on a model (e.g. change permissions or delete)
    backend_lock = django.db.models.BooleanField(default=False)

    # Sharing
    is_public = django.db.models.BooleanField(default=False)
    creator = django.db.models.ForeignKey(
        get_user_model(),
        on_delete=django.db.models.CASCADE,
        null=False,
        blank=False,
        db_index=True,
    )

    # Timing variables
    created = django.db.models.DateTimeField(auto_now_add=True, blank=False, null=False)
    modified = django.db.models.DateTimeField(auto_now=True, blank=False, null=False)

    def save_as(self, user, *args, **kwargs) -> None:
        """
        Save this instance only if the given user has the appropriate permission.

        For new objects, check the CREATE permission.
        For existing objects, check the UPDATE (or EDIT) permission.
        Raises PermissionDenied if the user does not have the required permission.
        """
        if self.pk is not None:
            # Existing object requires update permission.
            if not user_has_permission_for_obj(user, self, PermissionTypes.UPDATE):
                raise PermissionDenied(
                    "User does not have update permission for this object."
                )
        else:
            # New object requires create permission.
            if not user_has_permission_for_obj(user, self, PermissionTypes.CREATE):
                raise PermissionDenied(
                    "User does not have create permission for this object."
                )
        # If permissions check passes, delegate to the standard save.
        super().save(*args, **kwargs)

    def delete_as(self, user, *args, **kwargs) -> None:
        """
        Delete this instance only if the given user has the DELETE permission.
        Raises PermissionDenied if the user does not have the required permission.
        """
        if not user_has_permission_for_obj(user, self, PermissionTypes.DELETE):
            raise PermissionDenied(
                "User does not have delete permission for this object."
            )
        # If permission check passes, delegate to the standard delete.
        super().delete(*args, **kwargs)
