"""
Management command: mint a corpus-scoped worker-upload token from the CLI.

This is the one-command server-side setup step for the remote-ingest worker
(``scripts/remote_ingest``). It creates (or reuses) a worker service account and
issues a ``CorpusAccessToken`` bound to a single corpus, then prints the plaintext
token — which is shown only ONCE (the row stores only its SHA-256 hash).

Example::

    python manage.py mint_worker_token --corpus 7 --worker-name fortworth-rig

All authorisation and lifecycle logic is delegated to the worker-upload services
(``WorkerAccountService`` / ``CorpusAccessTokenService``); the command only
resolves an acting superuser and projects the result to stdout.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any, cast

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from opencontractserver.worker_uploads.models import WorkerAccount
from opencontractserver.worker_uploads.services import (
    CorpusAccessTokenService,
    WorkerAccountService,
)

if TYPE_CHECKING:
    from opencontractserver.worker_uploads.models import CorpusAccessToken

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Mint a corpus-scoped worker-upload token (for scripts/remote_ingest). "
        "Creates or reuses a worker account and prints the one-time token."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--corpus",
            type=int,
            required=True,
            help="Raw integer PK of the corpus to bind the token to.",
        )
        parser.add_argument(
            "--worker-name",
            type=str,
            required=True,
            help="Name of the worker service account (created if it doesn't exist).",
        )
        parser.add_argument(
            "--description",
            type=str,
            default="",
            help="Optional description for a newly-created worker account.",
        )
        parser.add_argument(
            "--rate-limit",
            type=int,
            default=0,
            help="Uploads-per-minute cap for the token (0 = unlimited).",
        )
        parser.add_argument(
            "--allow-authority-sections",
            action="store_true",
            help=(
                "Grant the token the authority-section push capability "
                "(bootstrap into the bound corpus + relink sweep). Off by "
                "default — larger blast radius than document upload."
            ),
        )
        parser.add_argument(
            "--expires-days",
            type=int,
            default=None,
            help="Token lifetime in days (default: never expires).",
        )
        parser.add_argument(
            "--as-user",
            type=str,
            default=None,
            help=(
                "Username of the superuser to act as. Defaults to the first "
                "active superuser found."
            ),
        )

    def handle(self, *args: Any, **options: Any) -> None:
        acting_user = self._resolve_superuser(options.get("as_user"))

        worker_name = options["worker_name"]
        existing = WorkerAccount.objects.filter(name=worker_name).first()
        if existing is None:
            create_result = WorkerAccountService.create_worker_account(
                acting_user,
                name=worker_name,
                description=options.get("description", ""),
            )
            if not create_result.ok:
                raise CommandError(
                    f"Could not create worker account: {create_result.error}"
                )
            # ``ok`` invariant: success carries a non-None value (cast narrows
            # for mypy without relying on assert, which -O strips).
            account = cast(WorkerAccount, create_result.value)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Created worker account '{account.name}' (id={account.id})."
                )
            )
        elif not existing.is_active:
            raise CommandError(
                f"Worker account '{worker_name}' exists but is deactivated. "
                f"Reactivate it before minting tokens."
            )
        else:
            account = existing
            self.stdout.write(
                f"Reusing existing worker account '{account.name}' (id={account.id})."
            )

        expires_at = None
        if options.get("expires_days") is not None:
            expires_at = timezone.now() + timedelta(days=options["expires_days"])

        token_result = CorpusAccessTokenService.create_token(
            acting_user,
            worker_account_id=account.id,
            corpus_id=options["corpus"],
            expires_at=expires_at,
            rate_limit_per_minute=options.get("rate_limit", 0),
            can_push_authority_sections=options.get("allow_authority_sections", False),
        )
        if not token_result.ok:
            raise CommandError(f"Could not mint token: {token_result.error}")

        token, plaintext_key = cast("tuple[CorpusAccessToken, str]", token_result.value)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 70))
        self.stdout.write(
            self.style.SUCCESS("Worker token minted (shown ONCE — copy it now):")
        )
        self.stdout.write(self.style.SUCCESS("=" * 70))
        self.stdout.write(f"  OC_WORKER_TOKEN={plaintext_key}")
        self.stdout.write(f"  OC_CORPUS_ID={token.corpus_id}")
        self.stdout.write("")
        self.stdout.write("Use it on the remote worker host, e.g.:")
        self.stdout.write(
            f"  export OC_WORKER_TOKEN={plaintext_key}\n"
            f"  export OC_CORPUS_ID={token.corpus_id}\n"
            f"  export OC_TARGET_URL=https://<your-opencontracts-host>"
        )
        self.stdout.write(self.style.SUCCESS("=" * 70))

    def _resolve_superuser(self, username: str | None) -> Any:
        if username:
            try:
                named = User.objects.get(username=username)
            except User.DoesNotExist:
                raise CommandError(f"User '{username}' not found.")
            if not named.is_superuser:
                raise CommandError(f"User '{username}' is not a superuser.")
            return named

        user = (
            User.objects.filter(is_superuser=True, is_active=True)
            .order_by("id")
            .first()
        )
        if user is None:
            raise CommandError(
                "No active superuser found. Create one with "
                "`python manage.py createsuperuser` or pass --as-user."
            )
        return user
