"""
Notifications app for OpenContracts.

This app uses a deliberately simpler ownership model than other domain
apps: a :class:`~opencontractserver.notifications.models.Notification`
belongs to exactly one ``recipient`` (the user who should see it), and
that field alone determines visibility. No guardian rows are created,
and the app does **not** inherit
:class:`~config.graphql.permissioning.permission_annotator.mixins.AnnotatePermissionsForReadMixin`
or any other per-object permission machinery.

This divergence is intentional and described in ``CLAUDE.md`` under
"Permission System". Typing this package preserves that design in the
signatures — queryset helpers (``for_user``, ``mark_as_read``) are
scoped by ``recipient`` rather than a permission check. If you change
the visibility model, update both this docstring and ``CLAUDE.md``.
"""

default_app_config = "opencontractserver.notifications.apps.NotificationsConfig"
