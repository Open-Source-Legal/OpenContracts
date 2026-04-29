from django.apps import AppConfig


class LLMsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "opencontractserver.llms"
    verbose_name = "LLMs"

    def ready(self) -> None:  # noqa: D401 — Django hook
        # Eagerly construct the provider registry so misconfigured providers
        # surface at boot rather than on first GraphQL request.
        from opencontractserver.llms.providers.registry import get_provider_registry

        get_provider_registry()
