"""Framework-independent request validation and model concurrency controls."""

from __future__ import annotations

import hmac
import threading
from typing import Any, Callable


def api_key_is_valid(api_key: str | None, expected: str) -> bool:
    """Constant-time API key comparison to avoid timing side-channels.

    Compares UTF-8 bytes rather than the raw ``str`` values:
    ``hmac.compare_digest`` raises ``TypeError`` on non-ASCII ``str`` input,
    which would otherwise turn a malformed header into a 500 instead of a 401.
    """
    if api_key is None:
        return False
    return hmac.compare_digest(api_key.encode("utf-8"), expected.encode("utf-8"))


def non_empty_string_field(payload: object, field: str) -> str | None:
    """Return a non-blank JSON string field, or ``None`` when invalid."""
    if not isinstance(payload, dict):
        return None
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        return None
    return value


def all_non_empty_strings(values: list[object]) -> bool:
    """Return whether every list item is a non-blank string."""
    return all(isinstance(value, str) and bool(value.strip()) for value in values)


def public_fallback_reason(reason: str | None) -> str | None:
    """Map a raw backend exception to unauthenticated readiness metadata."""
    return "accelerator_initialization_failed" if reason else None


class SerializedModelOwner:
    """Serialize all modalities through one shared model instance.

    Only text requests are additionally coalesced by ``DynamicBatcher``
    (see ``main.py``); image requests are serialized here but never batched
    together. Images are rarer and heavier per-request, so the coalescing
    win is smaller -- this is a deliberate asymmetry, not an oversight.
    """

    def __init__(
        self,
        embed_texts: Callable[[list[str]], Any],
        embed_image: Callable[[str], Any],
        embed_images: Callable[[list[str]], Any],
    ) -> None:
        self._embed_texts = embed_texts
        self._embed_image = embed_image
        self._embed_images = embed_images
        self._lock = threading.Lock()

    def embed_texts(self, texts: list[str]) -> Any:
        with self._lock:
            return self._embed_texts(texts)

    def embed_image(self, image: str) -> Any:
        with self._lock:
            return self._embed_image(image)

    def embed_images(self, images: list[str]) -> Any:
        with self._lock:
            return self._embed_images(images)
