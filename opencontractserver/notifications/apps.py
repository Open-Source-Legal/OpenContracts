from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "opencontractserver.notifications"
    verbose_name = "Notifications"

    def ready(self):
        """
        Import signal handlers when the app is ready.
        """
        import opencontractserver.notifications.signals  # noqa: F401
