from django.apps import AppConfig
from django.db.models.signals import post_save


class AnnotationsConfig(AppConfig):
    default_auto_field: str = "django.db.models.BigAutoField"
    name: str = "opencontractserver.analyzer"

    def ready(self) -> None:
        try:
            import opencontractserver.analyzer.signals  # noqa F401
            from opencontractserver.analyzer.models import GremlinEngine
            from opencontractserver.analyzer.signals import install_gremlin_on_creation

            post_save.connect(
                install_gremlin_on_creation,
                sender=GremlinEngine,
                dispatch_uid="install_gremlin_on_creation",
            )

        except ImportError:
            pass

        # Register system checks
        from opencontractserver.analyzer import checks  # noqa F401
