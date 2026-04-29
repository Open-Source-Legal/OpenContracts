"""Database models for LLM configuration.

This module is the database half of the "LLM configuration system" mirror of
``PipelineSettings`` / pipeline component registry:

* :class:`LLMConfigSettings` — singleton holding admin-managed provider
  credentials (Fernet-encrypted) plus a default-model reference.
* :class:`LLMModel` — admin-curated rows describing each *enabled* model under
  a registered provider. Columns reference these via FK.

Provider classes themselves are *code-defined* and live in
``opencontractserver.llms.providers``.
"""

from __future__ import annotations

from typing import Any, NoReturn

import django
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from opencontractserver.shared.fields import NullableJSONField


# --------------------------------------------------------------------------- #
# Singleton: LLMConfigSettings
# --------------------------------------------------------------------------- #


class LLMConfigSettings(django.db.models.Model):
    """Singleton (pk=1) for site-wide LLM provider configuration.

    Mirrors ``PipelineSettings`` exactly:

    * one row, enforced by ``CheckConstraint(pk=1)``;
    * ``encrypted_secrets`` BinaryField holds Fernet-encrypted credentials,
      keyed by provider key (``"openai"``, ``"anthropic"``, …);
    * ``provider_configs`` JSONField holds *non-secret* per-provider config
      (``base_url``, ``organization``, …) so the admin UI can read it back;
    * cached via Django's cache framework with a 5-minute TTL.

    SECRET_KEY rotation makes encrypted credentials unrecoverable. Export
    via ``LLMConfigSettings.get_instance().get_secrets()`` before rotating.
    """

    provider_configs = NullableJSONField(
        default=dict,
        blank=True,
        help_text=(
            "Non-secret per-provider configuration, keyed by provider key. "
            'e.g. {"openai": {"base_url": "https://...", "organization": "..."}}'
        ),
    )

    encrypted_secrets = django.db.models.BinaryField(
        blank=True,
        null=True,
        help_text="Fernet-encrypted JSON: {provider_key: {credential_field: value}}",
    )

    default_model = django.db.models.ForeignKey(
        "llms.LLMModel",
        null=True,
        blank=True,
        on_delete=django.db.models.SET_NULL,
        related_name="default_for_settings",
        help_text="Fallback model when a Column has no preferred_llm_model.",
    )

    modified = django.db.models.DateTimeField(auto_now=True, db_index=True)
    modified_by = django.db.models.ForeignKey(
        get_user_model(),
        on_delete=django.db.models.SET_NULL,
        null=True,
        blank=True,
        related_name="llm_config_settings_modifications",
    )

    CACHE_KEY = "llm_config_settings_singleton"
    _ENCRYPTION_SETTING_PREFIX = "LLM_CONFIG_SETTINGS"

    class Meta:
        verbose_name = "LLM Configuration Settings"
        verbose_name_plural = "LLM Configuration Settings"
        constraints = [
            django.db.models.CheckConstraint(
                condition=django.db.models.Q(pk=1),
                name="llm_config_settings_singleton_pk",
            ),
        ]

    def __str__(self) -> str:  # noqa: D401
        return "LLMConfigSettings (Singleton)"

    # ------------------------------------------------------------------ #
    # Singleton plumbing
    # ------------------------------------------------------------------ #

    @classmethod
    def _get_cache_ttl(cls) -> int:
        from django.conf import settings as django_settings

        return getattr(django_settings, "LLM_CONFIG_SETTINGS_CACHE_TTL_SECONDS", 300)

    @classmethod
    def _invalidate_cache(cls) -> None:
        from django.core.cache import cache

        cache.delete(cls.CACHE_KEY)

    def save(self, *args: Any, **kwargs: Any) -> None:
        from django.db import transaction

        if not self.pk and LLMConfigSettings.objects.exists():
            raise ValidationError(
                "LLMConfigSettings is a singleton. Use LLMConfigSettings.get_instance()."
            )
        super().save(*args, **kwargs)
        self._invalidate_cache()
        transaction.on_commit(lambda: self._invalidate_cache())

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:  # noqa: D401
        raise ValidationError("LLMConfigSettings singleton cannot be deleted.")

    @classmethod
    def get_instance(cls, use_cache: bool = True) -> "LLMConfigSettings":
        from django.core.cache import cache
        from django.db import transaction

        if use_cache:
            cached = cache.get(cls.CACHE_KEY)
            if cached is not None:
                return cached

        with transaction.atomic():
            instance, _created = cls.objects.select_related("default_model").get_or_create(
                pk=1,
                defaults={"provider_configs": {}},
            )

        if use_cache:
            cache.set(cls.CACHE_KEY, instance, cls._get_cache_ttl())

        return instance

    # ------------------------------------------------------------------ #
    # Encrypted credentials
    # ------------------------------------------------------------------ #

    @classmethod
    def _encryption_policy(cls):
        from opencontractserver.utils.encryption import EncryptionPolicy

        return EncryptionPolicy(setting_prefix=cls._ENCRYPTION_SETTING_PREFIX)

    def get_secrets(self) -> dict:
        """Return ``{provider_key: {field: value}}`` decrypted, or ``{}``."""
        from opencontractserver.utils.encryption import decrypt_secrets

        return decrypt_secrets(self.encrypted_secrets, self._encryption_policy())

    def set_secrets(self, secrets: dict) -> None:
        from opencontractserver.utils.encryption import encrypt_secrets

        self.encrypted_secrets = encrypt_secrets(secrets, self._encryption_policy())

    def get_provider_secrets(self, provider_key: str) -> dict:
        return self.get_secrets().get(provider_key, {})

    def update_provider_secrets(self, provider_key: str, values: dict) -> None:
        secrets = self.get_secrets()
        secrets.setdefault(provider_key, {}).update(values)
        self.set_secrets(secrets)

    def delete_provider_secrets(self, provider_key: str) -> None:
        secrets = self.get_secrets()
        if provider_key in secrets:
            del secrets[provider_key]
            self.set_secrets(secrets)

    # ------------------------------------------------------------------ #
    # Non-secret config helpers
    # ------------------------------------------------------------------ #

    def get_provider_config(self, provider_key: str) -> dict:
        return (self.provider_configs or {}).get(provider_key, {})

    def update_provider_config(self, provider_key: str, values: dict) -> None:
        configs = dict(self.provider_configs or {})
        configs.setdefault(provider_key, {}).update(values)
        self.provider_configs = configs

    def delete_provider_config(self, provider_key: str) -> None:
        configs = dict(self.provider_configs or {})
        if provider_key in configs:
            del configs[provider_key]
            self.provider_configs = configs

    def get_full_provider_credentials(self, provider_key: str) -> dict:
        """Merge non-secret config + decrypted secrets for a single provider.

        Used by the resolver to hand a ready-to-use dict to provider.build_*.
        """
        merged = dict(self.get_provider_config(provider_key))
        merged.update(self.get_provider_secrets(provider_key))
        return merged

    def is_provider_configured(self, provider_key: str) -> bool:
        """A provider is *configured* if it has at least one non-empty credential.

        Required-secret validation happens at write time in the GraphQL layer;
        this method is a cheap "should we surface this provider's models?"
        check used by resolvers.
        """
        from opencontractserver.llms.providers import get_provider

        defn = get_provider(provider_key)
        if defn is None:
            return False

        credentials = self.get_full_provider_credentials(provider_key)
        # Every required field must be present and non-empty.
        for field in defn.credential_schema:
            if field.required and not credentials.get(field.name):
                return False
        return True


# --------------------------------------------------------------------------- #
# Admin-curated rows: LLMModel
# --------------------------------------------------------------------------- #


class LLMModel(django.db.models.Model):
    """One row per registered model.

    Admins curate which models are *available* under each registered provider.
    Columns reference these rows by FK; the resolver checks both ``is_enabled``
    and the underlying provider's ``is_provider_configured`` state when
    deciding whether the model is currently usable.

    Not a ``BaseOCModel`` because:

    * there is no per-row sharing — admin-only writes;
    * we want a hard ``NOT NULL`` ``creator`` only via ``modified_by`` style
      audit — using a ``models.SET_NULL`` user FK keeps deletions safe.
    """

    provider_key = django.db.models.CharField(
        max_length=64,
        db_index=True,
        help_text="Stable provider key, validated against the LLMProviderRegistry.",
    )
    model_name = django.db.models.CharField(
        max_length=255,
        help_text="Provider's raw model identifier (e.g. 'gpt-4o-mini').",
    )
    display_name = django.db.models.CharField(
        max_length=255,
        help_text="Human label shown in the column editor.",
    )
    description = django.db.models.TextField(blank=True, default="")

    is_enabled = django.db.models.BooleanField(
        default=True,
        db_index=True,
        help_text="Disable to hide from column editors without deleting the row.",
    )
    supports_vision = django.db.models.BooleanField(default=False)
    supports_tools = django.db.models.BooleanField(default=True)
    supports_structured_output = django.db.models.BooleanField(default=True)

    max_context_tokens = django.db.models.PositiveIntegerField(null=True, blank=True)
    default_temperature = django.db.models.FloatField(default=0.3)

    extra_settings = NullableJSONField(
        default=dict,
        blank=True,
        help_text="Passthrough kwargs forwarded to pydantic-ai at invocation time.",
    )

    created = django.db.models.DateTimeField(auto_now_add=True)
    modified = django.db.models.DateTimeField(auto_now=True)
    created_by = django.db.models.ForeignKey(
        get_user_model(),
        on_delete=django.db.models.SET_NULL,
        null=True,
        blank=True,
        related_name="llm_models_created",
    )

    class Meta:
        verbose_name = "LLM Model"
        verbose_name_plural = "LLM Models"
        constraints = [
            django.db.models.UniqueConstraint(
                fields=["provider_key", "model_name"],
                name="llmmodel_unique_provider_model",
            ),
        ]
        ordering = ("provider_key", "display_name")

    def __str__(self) -> str:  # noqa: D401
        return f"{self.display_name} ({self.provider_key}:{self.model_name})"

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @property
    def provider_definition(self):
        """Resolve the registry entry, or ``None`` if the provider was removed."""
        from opencontractserver.llms.providers import get_provider

        return get_provider(self.provider_key)

    def pydantic_ai_string(self) -> str:
        """Return ``"<prefix>:<model_name>"`` for pydantic-ai consumption."""
        defn = self.provider_definition
        if defn is None or not defn.pydantic_ai_prefix:
            return self.model_name
        return f"{defn.pydantic_ai_prefix}:{self.model_name}"

    def is_available(self) -> bool:
        """True iff the model is enabled, the provider is registered, and
        the provider has the credentials it requires."""
        if not self.is_enabled:
            return False
        if self.provider_definition is None:
            return False
        return LLMConfigSettings.get_instance().is_provider_configured(self.provider_key)

    def clean(self) -> None:
        super().clean()
        if self.provider_definition is None:
            from opencontractserver.llms.providers import get_provider_registry

            available = ", ".join(d.key for d in get_provider_registry().providers)
            raise ValidationError(
                {
                    "provider_key": (
                        f"Unknown provider '{self.provider_key}'. Available: {available}"
                    )
                }
            )

    def save(self, *args: Any, **kwargs: Any) -> None:
        # Validate against registry on every save — keeps bad data out even if
        # the row is created via the ORM directly.
        self.full_clean(exclude=["created_by"])
        super().save(*args, **kwargs)
        # Default-model FK on settings caches the row, so invalidate.
        LLMConfigSettings._invalidate_cache()
