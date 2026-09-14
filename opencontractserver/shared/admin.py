"""Guardian's admin rules and forms, with the shared grant-write lifetime."""

from guardian.admin import (
    AdminGroupObjectPermissionsForm,
    AdminUserObjectPermissionsForm,
)
from guardian.admin import GuardedModelAdmin as GuardianModelAdmin
from guardian.forms import BaseObjectPermissionsForm

from opencontractserver.shared.grant_cache import permission_grant_change


class _ObjectPermissionsForm(BaseObjectPermissionsForm):
    def save_obj_perms(self):
        user_id = (
            self.user.pk if isinstance(self, AdminUserObjectPermissionsForm) else None
        )
        with permission_grant_change(
            self.obj, user_id, groups=isinstance(self, AdminGroupObjectPermissionsForm)
        ):
            super().save_obj_perms()


class _UserPermissionsForm(_ObjectPermissionsForm, AdminUserObjectPermissionsForm):
    pass


class _GroupPermissionsForm(_ObjectPermissionsForm, AdminGroupObjectPermissionsForm):
    pass


class GuardedModelAdmin(GuardianModelAdmin):
    """Keep Guardian admission, querysets, choices and widgets at their owner."""

    def get_obj_perms_manage_user_form(self, request):
        return _UserPermissionsForm

    def get_obj_perms_manage_group_form(self, request):
        return _GroupPermissionsForm
