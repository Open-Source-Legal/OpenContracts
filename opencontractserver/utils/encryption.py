"""
Fernet symmetric encryption helpers for storing sensitive configuration in the
database.

Used by both ``PipelineSettings`` (parser/embedder API keys) and
``LLMConfigSettings`` (LLM provider API keys). Encryption keys are derived from
Django's ``SECRET_KEY`` via PBKDF2-HMAC-SHA256 with a per-payload random salt;
ciphertext is stored as ``salt + fernet_token`` in a single ``BinaryField``.

⚠️  CRITICAL: SECRET_KEY rotation makes all stored secrets unrecoverable.
Export and re-encrypt before rotating ``SECRET_KEY`` in production.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings as django_settings

logger = logging.getLogger(__name__)

DEFAULT_SALT_LENGTH = 16
DEFAULT_ITERATIONS = 480_000
DEFAULT_MAX_PAYLOAD_BYTES = 10 * 1024  # 10 KiB


@dataclass(frozen=True)
class EncryptionPolicy:
    """Tunable per-call-site encryption parameters.

    ``setting_prefix`` lets each consumer (pipeline, llm_config, …) override
    iterations / salt length / max payload via Django settings without sharing
    a global namespace. Falls back to the defaults above when unset.
    """

    setting_prefix: str

    @property
    def salt_length(self) -> int:
        return getattr(
            django_settings,
            f"{self.setting_prefix}_ENCRYPTION_SALT_LENGTH",
            DEFAULT_SALT_LENGTH,
        )

    @property
    def iterations(self) -> int:
        return getattr(
            django_settings,
            f"{self.setting_prefix}_ENCRYPTION_ITERATIONS",
            DEFAULT_ITERATIONS,
        )

    @property
    def max_payload_bytes(self) -> int:
        return getattr(
            django_settings,
            f"{self.setting_prefix}_MAX_SECRET_SIZE_BYTES",
            DEFAULT_MAX_PAYLOAD_BYTES,
        )


def _derive_key(salt: bytes, iterations: int) -> bytes:
    """PBKDF2-HMAC-SHA256 → 32-byte urlsafe-b64-encoded key for Fernet."""
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        django_settings.SECRET_KEY.encode("utf-8"),
        salt,
        iterations,
        dklen=32,
    )
    return base64.urlsafe_b64encode(derived)


def encrypt_secrets(payload: dict, policy: EncryptionPolicy) -> bytes:
    """Encrypt a JSON-serialisable dict and return ``salt + ciphertext`` bytes.

    Raises ``ValueError`` when the serialized payload exceeds
    ``policy.max_payload_bytes``.
    """
    json_bytes = json.dumps(payload).encode("utf-8")
    if len(json_bytes) > policy.max_payload_bytes:
        raise ValueError(
            f"Secrets payload exceeds maximum size of {policy.max_payload_bytes} bytes"
        )

    salt = os.urandom(policy.salt_length)
    key = _derive_key(salt, policy.iterations)
    ciphertext = Fernet(key).encrypt(json_bytes)
    return salt + ciphertext


def decrypt_secrets(blob: bytes | memoryview | None, policy: EncryptionPolicy) -> dict:
    """Decrypt a ``salt + ciphertext`` blob produced by ``encrypt_secrets``.

    Returns ``{}`` when the blob is empty, malformed, or undecryptable (logged
    at error/critical level). Never raises — callers treat the absence of
    secrets as "not configured".
    """
    if not blob:
        return {}

    raw = bytes(blob)
    if len(raw) < policy.salt_length:
        logger.error(
            "encryption.decrypt_secrets: payload too short to contain salt "
            "(len=%d, salt_length=%d)",
            len(raw),
            policy.salt_length,
        )
        return {}

    salt = raw[: policy.salt_length]
    ciphertext = raw[policy.salt_length :]

    try:
        key = _derive_key(salt, policy.iterations)
        decrypted = Fernet(key).decrypt(ciphertext)
        return json.loads(decrypted.decode("utf-8"))
    except InvalidToken:
        logger.critical(
            "encryption.decrypt_secrets: InvalidToken — SECRET_KEY may have rotated; "
            "stored secrets are unrecoverable without the original SECRET_KEY."
        )
        return {}
    except json.JSONDecodeError as exc:
        logger.error("encryption.decrypt_secrets: invalid JSON after decrypt: %s", exc)
        return {}
    except Exception as exc:  # noqa: BLE001 — unexpected decryption failure
        logger.critical(
            "encryption.decrypt_secrets: unexpected error: %s. "
            "Payload may be corrupted or SECRET_KEY may have changed.",
            exc,
        )
        return {}
