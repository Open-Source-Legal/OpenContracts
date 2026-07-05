"""First-run bootstrap for the single-user desktop build.

Idempotent. Run once after ``migrate`` on the desktop profile
(``DJANGO_SETTINGS_MODULE=config.settings.desktop``); the ``oc-desktop``
launcher invokes it automatically on first boot. It:

1. Creates a single local superuser for the graphql_jwt / session login
   (Auth0 is off on desktop), persisting the generated password under the
   app-data dir.
2. Seeds the ``PipelineSettings`` singleton from the desktop Django settings —
   PDF → Warp-Ingest, embeddings → OpenAI-compatible endpoint — via
   ``migrate_pipeline_settings``. That row is written ONCE, so it must be seeded
   explicitly here rather than relying on later settings changes.
3. Ensures the ``nltk`` corpora Warp-Ingest imports at load time
   (``stopwords``, ``punkt``) are present for offline use.

See ``docs/deployment/desktop_packaging.md``.
"""

import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils.crypto import get_random_string

from opencontractserver.desktop import paths

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "First-run bootstrap for the single-user desktop build (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            default="desktop",
            help="Username for the local superuser (default: 'desktop').",
        )
        parser.add_argument(
            "--email",
            default="desktop@localhost",
            help="Email for the local superuser.",
        )
        parser.add_argument(
            "--skip-nltk",
            action="store_true",
            help="Do not attempt to download nltk corpora.",
        )

    def handle(self, *args, **options):
        self._seed_user(options["username"], options["email"])
        self._seed_pipeline_settings()
        if not options["skip_nltk"]:
            self._ensure_nltk_data()
        self.stdout.write(self.style.SUCCESS("Desktop bootstrap complete."))

    # ------------------------------------------------------------------ user
    def _seed_user(self, username: str, email: str) -> None:
        User = get_user_model()
        if User.objects.filter(username=username).exists():
            self.stdout.write(f"Local user '{username}' already exists; skipping.")
            return

        creds_file = paths.app_data_dir() / "credentials.txt"
        password = get_random_string(20)
        User.objects.create_superuser(username=username, email=email, password=password)
        try:
            creds_file.parent.mkdir(parents=True, exist_ok=True)
            creds_file.write_text(
                f"username: {username}\npassword: {password}\n", encoding="utf-8"
            )
            import os

            os.chmod(creds_file, 0o600)
            where = f" (saved to {creds_file})"
        except OSError:
            where = ""
        self.stdout.write(
            self.style.SUCCESS(
                f"Created local superuser '{username}'{where}. " f"Password: {password}"
            )
        )

    # -------------------------------------------------------- pipeline settings
    def _seed_pipeline_settings(self) -> None:
        """Seed the PipelineSettings singleton at the offline components."""
        from opencontractserver.documents.models import PipelineSettings

        # get_instance() creates pk=1 seeded from the desktop Django settings
        # (PREFERRED_PARSERS/PREFERRED_EMBEDDERS/DEFAULT_EMBEDDER → Warp-Ingest /
        # OpenAIEmbedder). migrate_pipeline_settings then fills component_settings
        # and encrypted secrets (e.g. OPENAI_API_KEY) from settings/env.
        PipelineSettings.get_instance()
        try:
            call_command("migrate_pipeline_settings")
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("migrate_pipeline_settings failed: %s", exc)
        self.stdout.write(
            "Seeded pipeline components: PDF → Warp-Ingest, embeddings → "
            f"{getattr(settings, 'DEFAULT_EMBEDDER', '?')}."
        )

    # ------------------------------------------------------------------ nltk
    def _ensure_nltk_data(self) -> None:
        try:
            import nltk
        except ImportError:
            self.stdout.write("nltk not installed; skipping corpus download.")
            return

        nltk_dir = paths.subdir("nltk_data", create=True)
        if str(nltk_dir) not in nltk.data.path:
            nltk.data.path.insert(0, str(nltk_dir))
        for resource in ("stopwords", "punkt", "punkt_tab"):
            try:
                nltk.download(resource, download_dir=str(nltk_dir), quiet=True)
            except Exception as exc:  # pragma: no cover - network dependent
                logger.warning("Could not download nltk '%s': %s", resource, exc)
        self.stdout.write(f"nltk corpora ready under {nltk_dir}.")
