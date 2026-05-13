import django
from django.conf import settings
from django.db import models

from opencontractserver.shared.Managers import BaseVisibilityManager


class BaseOCModel(models.Model):
    """
    Base model for all OpenContracts models that has some properties it's nice to have on
    all models.
    """

    # All BaseOCModel subclasses get BaseVisibilityManager by default, providing
    # the visible_to_user() method for consistent permission filtering
    objects = BaseVisibilityManager()

    class Meta:
        abstract = True

    # Processing fields
    # user_lock should be set when long-running process is activated for a given model by a user
    # and unset when process is done.
    user_lock = django.db.models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=django.db.models.SET_NULL,
        null=True,
        blank=True,
        related_name="locked_%(class)s_objects",
        db_index=True,
    )
    # This should be set to true if a long-running job is set on a model (e.g. change permissions or delete)
    backend_lock = django.db.models.BooleanField(default=False, db_index=True)

    # Sharing
    is_public = django.db.models.BooleanField(default=False)
    creator = django.db.models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=django.db.models.CASCADE,
        null=False,
        blank=False,
        db_index=True,
    )

    # Timing variables
    created = django.db.models.DateTimeField(auto_now_add=True, blank=False, null=False)
    modified = django.db.models.DateTimeField(auto_now=True, blank=False, null=False)

    def user_can(
        self, user, permission, *, include_group_permissions: bool = True
    ) -> bool:
        """Ergonomic single-object authorization check.

        Equivalent to ``type(self)._default_manager.user_can(user, self,
        permission)``. The Manager (or QuerySet) is the source of truth for
        per-model overrides; this method is just a thin delegate so callers
        can write ``obj.user_can(user, perm)`` instead.
        """
        return type(self)._default_manager.user_can(
            user,
            self,
            permission,
            include_group_permissions=include_group_permissions,
        )
