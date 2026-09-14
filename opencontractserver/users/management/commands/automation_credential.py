"""Server-operator interface; secrets are printed only on mint/rotate."""

import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from rest_framework.exceptions import APIException

from opencontractserver.users.models import AutomationCredential
from opencontractserver.users.services import automation_credentials as credentials


class Command(BaseCommand):
    help = "Mint, inspect, rotate or revoke scoped automation credentials."

    def add_arguments(self, parser):
        commands = parser.add_subparsers(dest="operation", required=True)
        mint = commands.add_parser("mint")
        mint.add_argument("--user", required=True, help="Existing principal username")
        mint.add_argument("--name", required=True)
        mint.add_argument(
            "--scope",
            action="append",
            required=True,
            choices=[scope.value for scope in credentials.Scope],
        )
        corpuses = mint.add_mutually_exclusive_group(required=True)
        corpuses.add_argument("--corpus", action="append", type=int)
        corpuses.add_argument("--all-corpuses", action="store_true")
        mint.add_argument("--expires-days", type=int, default=30)
        for operation in ("inspect", "rotate", "revoke"):
            commands.add_parser(operation).add_argument("id")

    def handle(self, *args, **options):
        token = None
        try:
            operation = options["operation"]
            if operation == "mint":
                user = get_user_model().objects.get(username=options["user"])
                credential, token = credentials.mint(
                    user=user,
                    name=options["name"],
                    scopes=options["scope"],
                    corpus_ids=None if options["all_corpuses"] else options["corpus"],
                    expires_at=timezone.now() + timedelta(days=options["expires_days"]),
                )
            elif operation == "rotate":
                credential, token = credentials.rotate(options["id"])
            elif operation == "revoke":
                credential = credentials.revoke(options["id"])
            else:
                credential = AutomationCredential.objects.get(pk=options["id"])
        except (
            ValueError,
            ValidationError,
            APIException,
            AutomationCredential.DoesNotExist,
            get_user_model().DoesNotExist,
        ) as exc:
            raise CommandError("Invalid credential operation or arguments.") from exc
        result = credentials.metadata(credential)
        if token is not None:
            result["token"] = token
        self.stdout.write(json.dumps(result, default=str))
