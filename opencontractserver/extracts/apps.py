from django.apps import AppConfig


class ExtractsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "opencontractserver.extracts"

    def ready(self) -> None:
        pass
