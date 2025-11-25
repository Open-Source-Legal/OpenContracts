from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ConversationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "opencontractserver.conversations"
    verbose_name = _("Conversations")

    def ready(self):
        """Import signal handlers when the app is ready."""
        import opencontractserver.conversations.signals  # noqa: F401
