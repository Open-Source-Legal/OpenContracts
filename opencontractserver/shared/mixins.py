from typing import Any

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied

from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import user_has_permission_for_obj

User = get_user_model()


class PermissionedOperationsMixin:
    """
    Mixin that provides permission-checked mutation operations.
    Use save_as(user) or delete_as(user) instead of save() or delete().
    """

    def save_as(self, user: User, *args: Any, **kwargs: Any) -> None:
        if self.pk is not None:
            if not user_has_permission_for_obj(user, self, PermissionTypes.UPDATE):
                raise PermissionDenied(
                    "User does not have update permission for this object."
                )
        else:
            if not user_has_permission_for_obj(user, self, PermissionTypes.CREATE):
                raise PermissionDenied(
                    "User does not have create permission for this object."
                )
        super().save(*args, **kwargs)

    def delete_as(self, user: User, *args: Any, **kwargs: Any) -> None:
        if not user_has_permission_for_obj(user, self, PermissionTypes.DELETE):
            raise PermissionDenied(
                "User does not have delete permission for this object."
            )
        super().delete(*args, **kwargs)
