"""Bootstrap an LLMSettings + RegisteredLLM configuration from Django settings.

Mirrors ``migrate_pipeline_settings`` for the LLM config system. Creates the
default ``RegisteredLLM`` row for ``constants.extraction.DEFAULT_EXTRACT_MODEL``
(ships as ``"openai:gpt-4o-mini"``), copies the matching API key out of
Django settings (``settings.OPENAI_API_KEY`` by default) into
``LLMSettings.encrypted_secrets``, and sets the new row as
``LLMSettings.default_extract_llm`` so the resolver picks it up.

Idempotent: re-running with no new flags is a no-op once a default is set.
``--force`` registers a new lineage version even if a default already exists
(useful for refreshing the api_key after a key rotation).

Usage::

    python manage.py seed_default_llm                       # bootstrap from env
    python manage.py seed_default_llm --dry-run             # preview only
    python manage.py seed_default_llm --api-key sk-...      # explicit key
    python manage.py seed_default_llm --model openai:gpt-4o # explicit model string
    python manage.py seed_default_llm --force               # rotate / refresh
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from django.conf import settings as django_settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from opencontractserver.constants.extraction import DEFAULT_EXTRACT_MODEL
from opencontractserver.llm_configs.models import LLMSettings, RegisteredLLM
from opencontractserver.llms.providers.registry import get_provider_registry

logger = logging.getLogger(__name__)

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Bootstrap LLMSettings + a default RegisteredLLM from Django "
        "settings (OPENAI_API_KEY + DEFAULT_EXTRACT_MODEL by default). "
        "Idempotent — safe to run on every deploy."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--model",
            type=str,
            default=DEFAULT_EXTRACT_MODEL,
            help=(
                f"pydantic-ai model identifier in '<prefix>:<model_id>' form "
                f"(default: {DEFAULT_EXTRACT_MODEL!r})."
            ),
        )
        parser.add_argument(
            "--api-key",
            type=str,
            default=None,
            help=(
                "API key to store under the resolved provider. Defaults to "
                "the provider's declared env_var (e.g. OPENAI_API_KEY)."
            ),
        )
        parser.add_argument(
            "--display-name",
            type=str,
            default=None,
            help="Display name for the seeded RegisteredLLM row.",
        )
        parser.add_argument(
            "--creator-username",
            type=str,
            default=None,
            help=(
                "Username to attribute the seeded RegisteredLLM to. Defaults "
                "to the first superuser; required if no superuser exists."
            ),
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help=(
                "Even if LLMSettings.default_extract_llm is already set, "
                "create a new lineage version with the supplied / refreshed "
                "values and point the default at it."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created / changed without writing to the DB.",
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _split_model_string(self, model: str) -> tuple[str, str]:
        """Split ``"<prefix>:<model_id>"`` into ``(prefix, model_id)``."""
        if ":" not in model:
            raise CommandError(
                f"--model {model!r} must be in '<prefix>:<model_id>' form "
                "(e.g. 'openai:gpt-4o-mini')."
            )
        prefix, model_id = model.split(":", 1)
        if not prefix or not model_id:
            raise CommandError(f"--model {model!r} has an empty prefix or model_id.")
        return prefix, model_id

    def _resolve_provider_for_prefix(self, prefix: str) -> tuple[type, str]:
        """Find the provider class whose ``pydantic_ai_prefix`` matches.

        Returns ``(provider_class, class_path)``. Raises CommandError when
        no registered provider claims the prefix.
        """
        registry = get_provider_registry()
        candidates = [cls for cls in registry.all() if cls.pydantic_ai_prefix == prefix]
        if not candidates:
            raise CommandError(
                f"No registered provider has pydantic_ai_prefix={prefix!r}. "
                f"Known prefixes: {sorted({c.pydantic_ai_prefix for c in registry.all()})}"
            )
        if len(candidates) > 1:
            # Ambiguous — surface so operator can extend the command with
            # an explicit --provider-class-path flag if needed.
            paths = [c.class_path() for c in candidates]
            raise CommandError(
                f"Multiple providers claim prefix {prefix!r}: {paths}. "
                "Disambiguate by registering only one or extend this command."
            )
        cls = candidates[0]
        return cls, cls.class_path()

    def _resolve_api_key(self, provider_cls: type, override: Optional[str]) -> str:
        """Pick the api_key to store: explicit --api-key wins; else env_var."""
        if override:
            return override
        # Walk the provider's Settings dataclass for the api_key env_var.
        from opencontractserver.pipeline.base.settings_schema import (
            get_settings_schema,
        )

        schema = get_settings_schema(provider_cls)
        api_key_info = schema.get("api_key", {})
        env_var = api_key_info.get("env_var")
        if not env_var:
            return ""
        return getattr(django_settings, env_var, "") or ""

    def _resolve_creator(self, override_username: Optional[str]) -> Any:
        if override_username:
            try:
                return User.objects.get(username=override_username)
            except User.DoesNotExist:
                raise CommandError(
                    f"--creator-username {override_username!r} does not match "
                    "any user."
                )
        creator = User.objects.filter(is_superuser=True).order_by("pk").first()
        if creator is None:
            raise CommandError(
                "No superuser exists to attribute the seeded RegisteredLLM "
                "to. Create one first or pass --creator-username."
            )
        return creator

    # ------------------------------------------------------------------ #
    # Entry point
    # ------------------------------------------------------------------ #

    def handle(self, *args: Any, **options: Any) -> None:
        model_string: str = options["model"]
        api_key_override: Optional[str] = options["api_key"]
        display_name_override: Optional[str] = options["display_name"]
        creator_username: Optional[str] = options["creator_username"]
        force: bool = options["force"]
        dry_run: bool = options["dry_run"]

        prefix, model_id = self._split_model_string(model_string)
        provider_cls, provider_class_path = self._resolve_provider_for_prefix(prefix)
        api_key = self._resolve_api_key(provider_cls, api_key_override)
        if not api_key:
            raise CommandError(
                f"No API key available for provider {provider_cls.__name__} "
                "(neither --api-key nor the env_var declared on Settings is set)."
            )
        display_name = (
            display_name_override
            or f"{provider_cls.title or provider_cls.__name__} {model_id}"
        )

        settings_instance = LLMSettings.get_instance(use_cache=False)
        existing_default: Optional[RegisteredLLM] = (
            settings_instance.default_extract_llm
        )

        if existing_default and not force:
            self.stdout.write(
                self.style.WARNING(
                    f"LLMSettings.default_extract_llm is already set to "
                    f"#{existing_default.pk} ({existing_default.display_name!r}). "
                    "Re-run with --force to register a new lineage version."
                )
            )
            return

        # When --force, the new row is the next version of the existing default
        # (preserves the immutable lineage). Otherwise, we may still find a
        # head row matching (provider, model) we can adopt as the default.
        previous_version: Optional[RegisteredLLM] = None
        adopted: Optional[RegisteredLLM] = None
        if force and existing_default is not None:
            previous_version = existing_default
        elif not existing_default:
            adopted = (
                RegisteredLLM.objects.selectable()
                .filter(provider_class_path=provider_class_path, model_id=model_id)
                .first()
            )

        creator = self._resolve_creator(creator_username)

        if dry_run:
            self.stdout.write("[dry-run] would:")
            self.stdout.write(
                f"  - store api_key for {provider_class_path} in LLMSettings.encrypted_secrets"
            )
            if adopted:
                self.stdout.write(
                    f"  - adopt existing RegisteredLLM #{adopted.pk} ({adopted.display_name!r}) as default"
                )
            else:
                self.stdout.write(
                    f"  - create RegisteredLLM(provider={provider_class_path}, "
                    f"model_id={model_id!r}, display_name={display_name!r}, "
                    f"previous_version={previous_version.pk if previous_version else None})"
                )
            self.stdout.write(
                "  - set LLMSettings.default_extract_llm to the row above"
            )
            return

        # 1. Persist the api_key under the provider class path.
        settings_instance.update_secrets(provider_class_path, {"api_key": api_key})

        # 2. Either adopt an existing matching row, or create a new one.
        if adopted is not None:
            row = adopted
            self.stdout.write(
                f"Adopting existing RegisteredLLM #{row.pk} ({row.display_name!r})."
            )
        else:
            row = RegisteredLLM.objects.create(
                provider_class_path=provider_class_path,
                model_id=model_id,
                display_name=display_name,
                previous_version=previous_version,
                creator=creator,
            )
            self.stdout.write(
                f"Created RegisteredLLM #{row.pk} ({row.display_name!r})."
            )

        # 3. Point LLMSettings at the row.
        settings_instance.default_extract_llm = row
        settings_instance.modified_by = creator
        settings_instance.save()

        self.stdout.write(
            self.style.SUCCESS(
                f"LLMSettings.default_extract_llm set to RegisteredLLM #{row.pk}. "
                f"Resolver will now hand out {prefix}:{model_id} for extracts."
            )
        )
