from django.contrib import admin
from django.contrib.auth import admin as auth_admin
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from opencontractserver.shared.admin import GuardedModelAdmin
from opencontractserver.users.forms import UserChangeForm, UserCreationForm
from opencontractserver.users.models import Assignment, UserExport, UserImport

User = get_user_model()


@admin.register(User)
class UserAdmin(auth_admin.UserAdmin):

    open_new_window = True

    form = UserChangeForm
    add_form = UserCreationForm

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (_("Personal info"), {"fields": ("name", "email")}),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "is_usage_capped",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "password1", "password2"),
            },
        ),
    )
    list_display = ["username", "name", "is_superuser"]
    search_fields = ["name"]


@admin.register(UserImport)
class ImportAdmin(GuardedModelAdmin):
    list_display = ["id", "name", "created", "started", "finished", "errors"]


@admin.register(UserExport)
class ExportAdmin(GuardedModelAdmin):
    list_display = ["id", "name", "created", "started", "finished", "errors"]


@admin.register(Assignment)
class AssignmentAdmin(GuardedModelAdmin):
    list_display = ["id", "document", "corpus", "assignor", "assignee"]
