"""
Reusable Fernet-encrypted secrets storage for Django singletons.

Extracted from ``PipelineSettings`` so the same encryption contract can be
shared by other admin-configurable singletons (e.g. ``LLMSettings``). The
encryption key is derived from Django's ``SECRET_KEY`` via PBKDF2-HMAC-SHA256
with a per-write random salt; ciphertext is laid out as ``salt || token``.

⚠️  SECRET_KEY rotation invalidates all stored secrets — see the warning
on the host model's docstring for the recovery procedure.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from typing import Any

import django.db.models
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings as django_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tuning knobs (can be overridden via Django settings)
# ---------------------------------------------------------------------------

DEFAULT_ENCRYPTION_SALT_LENGTH = 16
DEFAULT_ENCRYPTION_ITERATIONS = 480000  # OWASP 2023 recommendation for PBKDF2-SHA256
DEFAULT_MAX_SECRET_SIZE_BYTES = 10240  # 10 KB

# Setting names — mirrored from the original PipelineSettings constants so
# operator-facing tuning continues to work via the same env vars.
SETTING_SALT_LENGTH = "PIPELINE_SETTINGS_ENCRYPTION_SALT_LENGTH"
SETTING_ITERATIONS = "PIPELINE_SETTINGS_ENCRYPTION_ITERATIONS"
SETTING_MAX_SIZE = "PIPELINE_SETTINGS_MAX_SECRET_SIZE_BYTES"


class EncryptedSecretsMixin(django.db.models.Model):
    """
    Add an ``encrypted_secrets`` BinaryField + helper API to a Django model.

    Subclasses gain ``get_secrets`` / ``set_secrets`` / ``update_secrets`` /
    ``get_component_secrets`` / ``delete_component_secrets`` methods. Secret
    payloads are JSON dicts of the shape ``{namespace: {key: value}}`` where
    ``namespace`` is caller-defined (e.g. component class path, provider class
    path, ``"tool:web_search"``).

    The ``encrypted_secrets`` field stores ``salt || ciphertext`` so the
    per-write random salt travels with the ciphertext and can be used to
    re-derive the key on read.
    """

    encrypted_secrets = django.db.models.BinaryField(
        blank=True,
        null=True,
        help_text=(
            "Encrypted storage for sensitive configuration " "(API keys, credentials)"
        ),
    )

    class Meta:
        abstract = True

    # ------------------------------------------------------------------ #
    # Tuning helpers
    # ------------------------------------------------------------------ #

    @classmethod
    def _get_encryption_salt_length(cls) -> int:
        return getattr(
            django_settings, SETTING_SALT_LENGTH, DEFAULT_ENCRYPTION_SALT_LENGTH
        )

    @classmethod
    def _get_encryption_iterations(cls) -> int:
        return getattr(
            django_settings, SETTING_ITERATIONS, DEFAULT_ENCRYPTION_ITERATIONS
        )

    @classmethod
    def _get_max_secret_size(cls) -> int:
        return getattr(django_settings, SETTING_MAX_SIZE, DEFAULT_MAX_SECRET_SIZE_BYTES)

    # ------------------------------------------------------------------ #
    # Key derivation
    # ------------------------------------------------------------------ #

    @classmethod
    def _derive_key(cls, salt: bytes) -> bytes:
        key = hashlib.pbkdf2_hmac(
            "sha256",
            django_settings.SECRET_KEY.encode(),
            salt,
            cls._get_encryption_iterations(),
            dklen=32,
        )
        return base64.urlsafe_b64encode(key)

    # ------------------------------------------------------------------ #
    # Read / write
    # ------------------------------------------------------------------ #

    def get_secrets(self) -> dict[str, dict[str, Any]]:
        """Return the decrypted secrets dict, or ``{}`` on any failure."""
        if not self.encrypted_secrets:
            return {}

        try:
            raw_data = bytes(self.encrypted_secrets)

            salt_length = self._get_encryption_salt_length()
            if len(raw_data) < salt_length:
                logger.error(
                    "%s: encrypted_secrets too short to contain salt",
                    type(self).__name__,
                )
                return {}

            salt = raw_data[:salt_length]
            ciphertext = raw_data[salt_length:]

            key = self._derive_key(salt)
            fernet = Fernet(key)
            decrypted = fernet.decrypt(ciphertext)
            return json.loads(decrypted.decode("utf-8"))

        except InvalidToken:
            logger.critical(
                "%s: Failed to decrypt secrets — InvalidToken. SECRET_KEY may "
                "have changed; secrets are unrecoverable without the original "
                "key.",
                type(self).__name__,
            )
            return {}
        except json.JSONDecodeError as e:
            logger.error(
                "%s: Decrypted secrets contain invalid JSON: %s",
                type(self).__name__,
                e,
            )
            return {}
        except Exception as e:  # pragma: no cover — defensive
            logger.critical(
                "%s: Unexpected error decrypting secrets: %s",
                type(self).__name__,
                e,
            )
            return {}

    def set_secrets(self, secrets: dict[str, dict[str, Any]]) -> None:
        """Encrypt and store ``secrets`` (replaces any existing payload)."""
        json_bytes = json.dumps(secrets).encode("utf-8")

        max_size = self._get_max_secret_size()
        if len(json_bytes) > max_size:
            raise ValueError(
                f"Secrets payload exceeds maximum size of {max_size} bytes"
            )

        salt = os.urandom(self._get_encryption_salt_length())
        key = self._derive_key(salt)
        fernet = Fernet(key)
        ciphertext = fernet.encrypt(json_bytes)
        self.encrypted_secrets = salt + ciphertext

    # ------------------------------------------------------------------ #
    # Per-namespace helpers
    # ------------------------------------------------------------------ #

    def update_secrets(self, namespace: str, secret_values: dict[str, Any]) -> None:
        """Merge ``secret_values`` into the namespace bucket and re-encrypt."""
        secrets = self.get_secrets()
        if namespace not in secrets:
            secrets[namespace] = {}
        secrets[namespace].update(secret_values)
        self.set_secrets(secrets)

    def get_component_secrets(self, namespace: str) -> dict[str, Any]:
        """Return the secrets dict for ``namespace`` (empty if none)."""
        return self.get_secrets().get(namespace, {})

    def delete_component_secrets(self, namespace: str) -> None:
        """Remove the namespace bucket from the encrypted payload."""
        secrets = self.get_secrets()
        if namespace in secrets:
            del secrets[namespace]
            self.set_secrets(secrets)
