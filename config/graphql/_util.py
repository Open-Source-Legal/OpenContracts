"""Shared runtime helpers for generated strawberry modules."""

from enum import Enum
from typing import Any

import strawberry


def strip_unset(kwargs: dict) -> dict:
    """Drop UNSET args (graphene omitted absent kwargs) and unwrap enums."""
    out = {}
    for k, v in kwargs.items():
        if v is strawberry.UNSET:
            continue
        if isinstance(v, Enum):
            v = v.value
        out[k] = v
    return out


def coerce_str(value: Any):
    """graphene String coercion (str() on anything non-null)."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def coerce_enum(enum_cls, value: Any):
    if value is None or value == "":
        return None
    if isinstance(value, enum_cls):
        return value
    return enum_cls(value)
