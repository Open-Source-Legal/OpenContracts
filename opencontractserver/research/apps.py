from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ResearchConfig(AppConfig):
    default_auto_field: str = "django.db.models.BigAutoField"
    name: str = "opencontractserver.research"
    verbose_name = _("Research")
