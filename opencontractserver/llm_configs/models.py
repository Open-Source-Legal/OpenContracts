"""
Admin-curated LLM provider/model configuration.

Two concepts:

* ``LLMSettings`` — singleton mirroring ``PipelineSettings``. Holds
  per-provider non-secret kwargs in ``provider_settings`` and per-provider
  API keys in the inherited ``encrypted_secrets`` field (namespaced by
  provider class path). Also points at the ``RegisteredLLM`` row used as
  the default for extracts when a Column has no preferred LLM.

* ``RegisteredLLM`` — admin-curated row representing one (provider, model)
  combination operators have approved for use. Rows are **never edited or
  deleted** once persisted; "edit" creates a new row with
  ``previous_version`` pointing at the prior row, forming an immutable
  lineage chain walkable via a recursive CTE on ``previous_version_id``.
  ``Column.preferred_llm`` and ``Datacell.executed_llm`` will use
  ``on_delete=PROTECT`` so historical references can never dangle.
"""

from __future__ import annotations

from typing import Any, NoReturn

import django.db.models
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from opencontractserver.shared.encrypted_secrets import EncryptedSecretsMixin
from opencontractserver.shared.fields import NullableJSONField
from opencontractserver.shared.Managers import BaseVisibilityManager
from opencontractserver.shared.Models import BaseOCModel

# ---------------------------------------------------------------------------
# RegisteredLLM
# ---------------------------------------------------------------------------


class RegisteredLLMManager(BaseVisibilityManager):
    """Manager exposing helpers for the immutable version-chain model."""

    def heads(self) -> django.db.models.QuerySet:
        """Return only rows that no other row points at via ``previous_version``.

        These are the "current" versions admins can pick. Use a NOT EXISTS
        subquery so the head set updates atomically as new versions are
        appended to a lineage chain.
        """
        sub = self.model.objects.filter(
            previous_version_id=django.db.models.OuterRef("pk")
        )
        return self.annotate(_has_next=django.db.models.Exists(sub)).filter(
            _has_next=False
        )

    def selectable(self) -> django.db.models.QuerySet:
        """Heads that operators are allowed to pick from in the UI.

        Filters out archived and disabled rows. Resolvability against the
        provider registry / encrypted secrets is enforced at runtime by
        the resolver (Phase 2), not at the DB layer.
        """
        return self.heads().filter(is_enabled=True, is_archived=False)


class RegisteredLLM(BaseOCModel):
    """One (provider, model) combination an admin has approved for use.

    Immutable after creation: any "edit" (display-name change, enabling/
    disabling, archiving, etc.) creates a new row with
    ``previous_version`` set to the prior one. ``Column.preferred_llm``
    and ``Datacell.executed_llm`` will use ``on_delete=PROTECT`` so the
    chain cannot be broken from the FK side either.

    Resolvability (whether this row can actually run an LLM call) is
    determined at runtime by combining: ``is_enabled``,
    ``not is_archived``, the provider class existing in the
    ``LLMProviderRegistry`` (Phase 2), and a non-empty ``api_key`` in
    ``LLMSettings.encrypted_secrets`` for the provider class path.
    """

    objects = RegisteredLLMManager()

    # ---- Identity --------------------------------------------------------

    provider_class_path = django.db.models.CharField(
        max_length=256,
        help_text=(
            "Full Python class path of the LLMProvider class "
            "(e.g. 'opencontractserver.llms.providers.anthropic.AnthropicProvider')."
        ),
    )
    model_id = django.db.models.CharField(
        max_length=128,
        help_text=(
            "Provider-native model identifier "
            "(e.g. 'gpt-4o-mini', 'claude-opus-4-7'). Combined with the "
            "provider's pydantic-ai prefix to form the model string passed "
            "to pydantic-ai (e.g. 'openai:gpt-4o-mini')."
        ),
    )
    display_name = django.db.models.CharField(
        max_length=256,
        help_text="Human-readable label shown in admin and column pickers.",
    )

    # ---- Lifecycle flags ------------------------------------------------

    is_enabled = django.db.models.BooleanField(
        default=True,
        help_text=(
            "If False, this version is greyed out in pickers but still "
            "referenceable for historical Datacells/Columns."
        ),
    )
    is_archived = django.db.models.BooleanField(
        default=False,
        help_text=(
            "If True, this version is hidden from pickers entirely. "
            "Historical references survive via PROTECT FKs."
        ),
    )

    # ---- Version chain --------------------------------------------------

    previous_version = django.db.models.ForeignKey(
        "self",
        on_delete=django.db.models.PROTECT,
        null=True,
        blank=True,
        related_name="next_version",
        help_text=(
            "Set to the prior row when this row is the result of an edit. "
            "Walk the chain backwards via a recursive CTE on "
            "previous_version_id to recover full version history. NULL on "
            "the original row of a lineage."
        ),
    )

    # ---- Capabilities (override registry / pydantic-ai introspection) ---

    context_window = django.db.models.IntegerField(
        null=True,
        blank=True,
        help_text=(
            "Override for context window size (tokens). When NULL, the "
            "resolver falls back to "
            "opencontractserver.llms.context_guardrails.MODEL_CONTEXT_WINDOWS."
        ),
    )
    supports_structured_output = django.db.models.BooleanField(
        default=True,
        help_text="Whether this model supports pydantic-ai structured output.",
    )
    supports_tools = django.db.models.BooleanField(
        default=True,
        help_text="Whether this model supports tool/function calling.",
    )
    max_output_tokens = django.db.models.IntegerField(
        null=True,
        blank=True,
        help_text="Optional max_tokens cap to apply on every call.",
    )
    temperature_default = django.db.models.FloatField(
        null=True,
        blank=True,
        help_text=(
            "Optional default temperature. NULL means callers/extractors "
            "use their own defaults (e.g. EXTRACT_DEFAULT_TEMPERATURE)."
        ),
    )

    # ---- Free-form notes -------------------------------------------------

    notes = django.db.models.TextField(
        blank=True,
        default="",
        help_text="Operator notes (e.g. cost tier, deployment region).",
    )

    class Meta:
        verbose_name = "Registered LLM"
        verbose_name_plural = "Registered LLMs"
        indexes = [
            django.db.models.Index(
                fields=["provider_class_path", "model_id"],
                name="reg_llm_provider_model_idx",
            ),
            django.db.models.Index(
                fields=["is_archived", "is_enabled"],
                name="reg_llm_lifecycle_idx",
            ),
        ]
        permissions = (
            ("permission_registeredllm", "permission registered llm"),
            ("create_registeredllm", "create registered llm"),
            ("read_registeredllm", "read registered llm"),
            ("update_registeredllm", "update registered llm"),
            ("remove_registeredllm", "delete registered llm"),
            ("comment_registeredllm", "comment registered llm"),
            ("publish_registeredllm", "publish registered llm"),
        )

    def __str__(self) -> str:
        return f"{self.display_name} ({self.provider_class_path}:{self.model_id})"

    # ------------------------------------------------------------------
    # Lifecycle helpers
    # ------------------------------------------------------------------

    def is_head(self) -> bool:
        """True iff no other row points at ``self`` via ``previous_version``."""
        return not type(self).objects.filter(previous_version_id=self.pk).exists()

    def is_resolvable(self, llm_settings: "LLMSettings | None" = None) -> bool:
        """True iff this row can actually run an LLM call right now.

        Combines lifecycle flags (``is_enabled``, ``is_archived``) with
        provider-registry membership and encrypted-secret presence.
        Implementation lives in :func:`opencontractserver.llms.resolution.is_resolvable`
        so the resolution logic stays in one place.
        """
        # Local import — keeps llm_configs.models importable without
        # pulling in the providers package eagerly.
        from opencontractserver.llms.resolution import is_resolvable as _is_resolvable

        return _is_resolvable(self, llm_settings=llm_settings)

    def unavailable_reason(
        self, llm_settings: "LLMSettings | None" = None
    ) -> "str | None":
        """Operator-facing explanation of why this row isn't resolvable
        (or ``None`` if it is). Used by the GraphQL type and the column
        picker tooltip.
        """
        from opencontractserver.llms.resolution import (
            unavailable_reason as _unavailable_reason,
        )

        return _unavailable_reason(self, llm_settings=llm_settings)


# ---------------------------------------------------------------------------
# LLMSettings (singleton)
# ---------------------------------------------------------------------------


class LLMSettings(EncryptedSecretsMixin):
    """Singleton holding global LLM configuration.

    Mirrors ``PipelineSettings``: pk is constrained to 1, the row is
    seeded by migration, deletion is forbidden, and reads are cached.
    Provider API keys live in the inherited ``encrypted_secrets`` field
    keyed by provider class path; non-secret per-provider kwargs live in
    ``provider_settings``.
    """

    # Non-secret per-provider settings, keyed by provider class path.
    # Example: {"…AnthropicProvider": {"base_url": "...", "max_retries": 3}}
    provider_settings = NullableJSONField(
        default=dict,
        blank=True,
        help_text="Mapping of provider class paths to non-secret configuration.",
    )

    # Default LLM used by extract tasks when a Column has no preferred_llm
    # set. PROTECT mirrors the FK contract on Column/Datacell — we never
    # delete RegisteredLLM rows, so PROTECT is purely defence in depth.
    default_extract_llm = django.db.models.ForeignKey(
        RegisteredLLM,
        on_delete=django.db.models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "Default LLM for extract tasks (used when a Column has no "
            "preferred_llm). NULL falls back to "
            "constants.extraction.DEFAULT_EXTRACT_MODEL."
        ),
    )

    # Audit fields
    modified = django.db.models.DateTimeField(auto_now=True, db_index=True)
    modified_by = django.db.models.ForeignKey(
        get_user_model(),
        on_delete=django.db.models.SET_NULL,
        null=True,
        blank=True,
        related_name="llm_settings_modifications",
        help_text="User who last modified these settings.",
    )

    CACHE_KEY = "llm_settings_singleton"

    class Meta:
        verbose_name = "LLM Settings"
        verbose_name_plural = "LLM Settings"
        constraints = [
            django.db.models.CheckConstraint(
                condition=django.db.models.Q(pk=1),
                name="llm_settings_singleton_pk",
            ),
        ]

    def __str__(self) -> str:
        return "LLMSettings (Singleton)"

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    @classmethod
    def _get_cache_ttl(cls) -> int:
        from django.conf import settings as django_settings

        return getattr(django_settings, "LLM_SETTINGS_CACHE_TTL_SECONDS", 300)

    @classmethod
    def _invalidate_cache(cls) -> None:
        from django.core.cache import cache

        cache.delete(cls.CACHE_KEY)

    # ------------------------------------------------------------------
    # Singleton machinery
    # ------------------------------------------------------------------

    def save(self, *args: Any, **kwargs: Any) -> None:
        from django.db import transaction

        if not self.pk and LLMSettings.objects.exists():
            raise ValidationError(
                "LLMSettings is a singleton. Use LLMSettings.get_instance() instead."
            )
        super().save(*args, **kwargs)
        # Eagerly invalidate cache for in-test consistency, then again on
        # commit so larger transactions don't leave a stale entry.
        self._invalidate_cache()
        transaction.on_commit(lambda: self._invalidate_cache())

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise ValidationError("LLMSettings singleton cannot be deleted.")

    @classmethod
    def get_instance(cls, use_cache: bool = True) -> LLMSettings:
        from django.core.cache import cache
        from django.db import transaction

        if use_cache:
            cached = cache.get(cls.CACHE_KEY)
            if cached is not None:
                return cached

        with transaction.atomic():
            instance, _ = cls.objects.select_related(
                "modified_by", "default_extract_llm"
            ).get_or_create(pk=1)

        if use_cache:
            cache.set(cls.CACHE_KEY, instance, cls._get_cache_ttl())

        return instance

    # ------------------------------------------------------------------
    # Provider settings + secrets API (mirrors PipelineSettings naming)
    # ------------------------------------------------------------------

    def get_provider_settings(self, provider_class_path: str) -> dict:
        """Return the non-secret settings dict for ``provider_class_path``."""
        if self.provider_settings and provider_class_path in self.provider_settings:
            return dict(self.provider_settings[provider_class_path])
        return {}

    def get_full_provider_settings(self, provider_class_path: str) -> dict:
        """Merged non-secret + decrypted-secret settings for a provider.

        Secrets take precedence on key collision so callers can rely on a
        single dict (``api_key``, ``base_url``, etc.).
        """
        merged = self.get_provider_settings(provider_class_path)
        merged.update(self.get_component_secrets(provider_class_path))
        return merged

    def has_valid_secrets(self, provider_class_path: str) -> bool:
        """True if the provider has a non-empty ``api_key`` configured.

        Used by the resolver (Phase 2) to decide whether a
        ``RegisteredLLM`` row is fully resolvable. Centralising the
        definition of "valid secrets" here avoids drift between the
        resolver and the admin UI.
        """
        api_key = self.get_component_secrets(provider_class_path).get("api_key")
        return bool(api_key) and isinstance(api_key, str) and api_key.strip() != ""
