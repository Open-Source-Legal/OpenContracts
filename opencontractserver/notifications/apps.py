from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field: str = "django.db.models.BigAutoField"
    name: str = "opencontractserver.notifications"
    verbose_name: str = "Notifications"

    def ready(self) -> None:
        """
        Import signal handlers when the app is ready.

        Django's app registry calls this once per process after every app
        is loaded. Importing the signals module as a side-effect wires the
        :func:`@receiver <django.dispatch.receiver>`-decorated handlers
        into ``post_save`` signals for :class:`ChatMessage`,
        :class:`UserBadge`, and :class:`ModerationAction`. If this import
        is skipped, notifications silently stop being created — so this
        method MUST stay wired up across refactors.
        """
        import opencontractserver.notifications.signals  # noqa: F401
