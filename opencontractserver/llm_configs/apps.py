from django.apps import AppConfig


class LLMConfigsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "opencontractserver.llm_configs"
    verbose_name = "LLM Configurations"

    def ready(self):
        pass
