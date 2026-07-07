"""First-run bootstrap for the single-user desktop build.

Idempotent. Run once after ``migrate`` on the desktop profile
(``DJANGO_SETTINGS_MODULE=config.settings.desktop``); the ``oc-desktop``
launcher invokes it automatically on first boot. It:

1. Creates a single local superuser for the graphql_jwt / session login
   (Auth0 is off on desktop). The password comes from the
   ``OC_DESKTOP_PASSWORD`` env var when set, otherwise from an interactive
   prompt on the attached terminal (the common end-user path); no secret is
   generated, printed, or written to disk. A user left over from an earlier
   run *without* a usable password gets one on the next run, so a failed or
   password-less first boot is self-healing.
2. Seeds the ``PipelineSettings`` singleton from the desktop Django settings —
   PDF → Warp-Ingest, embeddings → OpenAI-compatible endpoint — via
   ``migrate_pipeline_settings``. That row is written ONCE, so it must be seeded
   explicitly here rather than relying on later settings changes.
3. Ensures the ``nltk`` corpora Warp-Ingest imports at load time
   (``stopwords``, ``punkt``) are present for offline use.

See ``docs/deployment/desktop_packaging.md``.
"""

import getpass
import logging
import os
import sys

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from opencontractserver.desktop import paths

logger = logging.getLogger(__name__)

# Django's AUTH_PASSWORD_VALIDATORS are form/serializer-level and are never
# invoked here (`create_superuser`/`set_password` bypass them), so enforce a
# floor ourselves — this account is a superuser.
MIN_PASSWORD_LENGTH = 8


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
    def _resolve_password(self, username: str) -> str | None:
        """The login password: ``OC_DESKTOP_PASSWORD`` wins, else prompt.

        Prompting on the attached terminal is the default end-user path — no
        env-var knowledge required. Returns None when the env var is unset and
        no interactive terminal is available (CI, a windowed shell); the
        password is never generated, stored on disk, or printed.
        """
        password = os.environ.get("OC_DESKTOP_PASSWORD")
        if password:
            return password
        if not sys.stdin.isatty():
            return None
        self.stdout.write(
            "\nChoose a password for your local OpenContracts login "
            f"(you will sign in as user '{username}')."
        )
        while True:
            # Ctrl+D / a closed stdin mid-prompt must not crash first-run
            # bootstrap — fall back to the no-password path (self-heals on the
            # next interactive launch).
            try:
                password = getpass.getpass(
                    f"  Password (min {MIN_PASSWORD_LENGTH} characters): "
                )
                if len(password) < MIN_PASSWORD_LENGTH:
                    self.stdout.write(
                        f"  Too short — use at least {MIN_PASSWORD_LENGTH} characters."
                    )
                    continue
                if password != getpass.getpass("  Repeat password: "):
                    self.stdout.write("  Passwords did not match — try again.")
                    continue
            except EOFError:
                return None
            return password

    def _no_password_warning(self, username: str) -> str:
        return (
            f"Local superuser '{username}' has NO login password. Set "
            "OC_DESKTOP_PASSWORD (or run from an interactive terminal) on the "
            f"next launch, or run `python manage.py changepassword {username} "
            "--settings=config.settings.desktop` to enable login."
        )

    def _seed_user(self, username: str, email: str) -> None:
        User = get_user_model()
        existing = User.objects.filter(username=username).first()
        if existing is not None:
            if existing.has_usable_password():
                self.stdout.write(f"Local user '{username}' already exists; skipping.")
                return
            # Self-heal a password-less account from an earlier run (e.g. a
            # first boot with no env var and no terminal).
            password = self._resolve_password(username)
            if password:
                existing.set_password(password)
                existing.save(update_fields=["password"])
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Set a login password for local user '{username}'."
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(self._no_password_warning(username))
                )
            return

        password = self._resolve_password(username)
        # create_superuser(password=None) already stores an unusable password
        # (set_password(None) -> set_unusable_password), so no explicit reset.
        User.objects.create_superuser(username=username, email=email, password=password)
        if password:
            self.stdout.write(
                self.style.SUCCESS(f"Created local superuser '{username}'.")
            )
        else:
            self.stdout.write(self.style.WARNING(self._no_password_warning(username)))

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

        # Progress line: this download can take a minute on slow connections
        # and previously ran silently, which read as a hang.
        self.stdout.write("Downloading language data for the PDF parser …")
        nltk_dir = paths.subdir("nltk_data", create=True)
        if str(nltk_dir) not in nltk.data.path:
            nltk.data.path.insert(0, str(nltk_dir))
        for resource in ("stopwords", "punkt", "punkt_tab"):
            try:
                nltk.download(resource, download_dir=str(nltk_dir), quiet=True)
            except Exception as exc:  # pragma: no cover - network dependent
                logger.warning("Could not download nltk '%s': %s", resource, exc)
        self.stdout.write(f"nltk corpora ready under {nltk_dir}.")
