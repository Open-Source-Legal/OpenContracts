"""First-run bootstrap for the single-user desktop build.

Idempotent. Run once after ``migrate`` on the desktop profile
(``DJANGO_SETTINGS_MODULE=config.settings.desktop``); the ``oc-desktop``
launcher invokes it automatically on first boot. It:

1. Creates a single local superuser for the graphql_jwt / session login
   (Auth0 is off on desktop) from the ``OC_DESKTOP_PASSWORD`` env var; no
   secret is generated, printed, or written to disk.
2. Seeds the ``PipelineSettings`` singleton from the desktop Django settings —
   PDF → Warp-Ingest, embeddings → OpenAI-compatible endpoint — via
   ``migrate_pipeline_settings``. That row is written ONCE, so it must be seeded
   explicitly here rather than relying on later settings changes.
3. Ensures the ``nltk`` corpora Warp-Ingest imports at load time
   (``stopwords``, ``punkt``) are present for offline use.

See ``docs/deployment/desktop_packaging.md``.
"""

import logging
import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

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
        # Seed the (idempotent) user and nltk corpora regardless, then signal
        # failure via a non-zero exit if pipeline seeding did not fully succeed.
        # The launcher only writes the first-run marker on a clean exit, so a
        # transient failure here is retried automatically on the next launch
        # rather than permanently disabling Tier-1 embeddings/chat.
        self._seed_user(options["username"], options["email"])
        pipeline_ok = self._seed_pipeline_settings()
        if not options["skip_nltk"]:
            self._ensure_nltk_data()
        if not pipeline_ok:
            raise CommandError(
                "Pipeline settings did not fully seed; the desktop launcher will "
                "retry bootstrap on the next launch."
            )
        self.stdout.write(self.style.SUCCESS("Desktop bootstrap complete."))

    # ------------------------------------------------------------------ user
    def _seed_user(self, username: str, email: str) -> None:
        User = get_user_model()
        if User.objects.filter(username=username).exists():
            self.stdout.write(f"Local user '{username}' already exists; skipping.")
            return

        # The login password comes ONLY from the environment — never generated,
        # stored on disk, or printed (avoids clear-text secret handling). When
        # unset, the user is created with an unusable password and the operator
        # sets one explicitly; the launcher passes OC_DESKTOP_PASSWORD through.
        password = os.environ.get("OC_DESKTOP_PASSWORD") or None
        # create_superuser(password=None) already stores an unusable password
        # (set_password(None) -> set_unusable_password), so no explicit reset.
        User.objects.create_superuser(username=username, email=email, password=password)
        if password:
            self.stdout.write(
                self.style.SUCCESS(f"Created local superuser '{username}'.")
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"Created local superuser '{username}' with NO login "
                    "password. Set OC_DESKTOP_PASSWORD before first run, or run "
                    f"`python manage.py changepassword {username} "
                    "--settings=config.settings.desktop` to enable login."
                )
            )

    # -------------------------------------------------------- pipeline settings
    def _seed_pipeline_settings(self) -> bool:
        """Seed the PipelineSettings singleton at the offline components.

        Returns True on success, False if ``migrate_pipeline_settings`` failed
        (the caller turns a False into a non-zero exit so the launcher retries).
        """
        from opencontractserver.documents.models import PipelineSettings

        # get_instance() creates pk=1 seeded from the desktop Django settings
        # (PREFERRED_PARSERS/PREFERRED_EMBEDDERS/DEFAULT_EMBEDDER → Warp-Ingest /
        # OpenAIEmbedder) — so the parser/embedder SELECTION is seeded here.
        # migrate_pipeline_settings then fills component_settings + encrypted
        # secrets (e.g. OPENAI_API_KEY). A failure there only leaves those
        # unseeded — PDF parsing still works, only Tier-1 embeddings/chat degrade.
        PipelineSettings.get_instance()
        try:
            call_command("migrate_pipeline_settings")
            self.stdout.write(
                "Seeded pipeline components: PDF → Warp-Ingest, embeddings → "
                f"{getattr(settings, 'DEFAULT_EMBEDDER', '?')}."
            )
            return True
        except Exception as exc:
            logger.error("migrate_pipeline_settings failed: %s", exc, exc_info=True)
            self.stderr.write(
                self.style.WARNING(
                    "Pipeline SECRET/component settings did not seed "
                    f"({exc}). PDF parsing still works; embeddings/chat may be "
                    "disabled until the next launch retries bootstrap (or you "
                    "re-run `python manage.py migrate_pipeline_settings "
                    "--settings=config.settings.desktop`)."
                )
            )
            return False

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
