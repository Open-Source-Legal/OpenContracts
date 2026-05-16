import logging

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class UsersConfig(AppConfig):
    name: str = "opencontractserver.users"
    verbose_name = _("Users")

    def ready(self) -> None:
        import posthog
        from django.conf import settings

        # Initialize PostHog globally as per official Django integration
        if settings.TELEMETRY_ENABLED:
            posthog.api_key = settings.POSTHOG_API_KEY
            posthog.host = settings.POSTHOG_HOST
            posthog.disable_geoip = False

        try:
            import opencontractserver.users.signals  # noqa F401
        except ImportError:
            pass

        # Register system checks (Auth0 superuser-allowlist warning, etc.)
        from opencontractserver.users import checks  # noqa F401

        # Pre-warm the pipeline component registry at startup
        # This ensures the first GraphQL request is fast (~0ms instead of ~2s)
        self._warm_pipeline_registry()

    def _warm_pipeline_registry(self) -> None:
        """
        Pre-initialize the pipeline component registry.

        The registry discovers all parsers, embedders, thumbnailers, and
        post-processors by scanning modules. This is done once at startup
        to avoid the ~2s initialization delay on first GraphQL request.
        """
        try:
            from opencontractserver.pipeline.registry import get_registry

            registry = get_registry()
            logger.info(
                f"Pipeline registry warmed: {len(registry.parsers)} parsers, "
                f"{len(registry.embedders)} embedders, "
                f"{len(registry.thumbnailers)} thumbnailers, "
                f"{len(registry.post_processors)} post-processors"
            )
        except Exception as e:
            # Don't fail startup if registry warming fails
            logger.warning(f"Failed to warm pipeline registry: {e}")
