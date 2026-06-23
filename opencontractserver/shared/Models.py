import django
from django.conf import settings
from django.db import models

from opencontractserver.shared.Managers import BaseVisibilityManager
from opencontractserver.shared.user_can_mixin import InstanceUserCanMixin


class BaseOCModel(InstanceUserCanMixin, models.Model):
    """
    Base model for all OpenContracts models that has some properties it's nice to have on
    all models.

    ``user_can(user, permission)`` is provided by ``InstanceUserCanMixin``
    and routes through ``type(self)._default_manager.user_can``. The same
    mixin is also applied directly to ``Corpus`` / ``CorpusFolder`` (which
    extend ``TreeNode`` instead of ``BaseOCModel``) so every visibility-
    managed model exposes the same ergonomic surface.
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
