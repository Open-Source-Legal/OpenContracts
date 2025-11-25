from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AgentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "opencontractserver.agents"
    verbose_name = _("Agents")
