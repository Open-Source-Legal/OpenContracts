"""Runtime configuration resolution."""

from __future__ import annotations

import os

from .constants import DEFAULT_MODEL, MODEL_ENV_VAR


def resolve_model_name(explicit: str | None = None) -> str:
    """Model id precedence: explicit arg > ``OC_EXTRACT_MODEL`` env > default."""
    return explicit or os.environ.get(MODEL_ENV_VAR) or DEFAULT_MODEL
