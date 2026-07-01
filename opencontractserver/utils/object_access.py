"""Generic helpers for reading attributes off values of unknown shape.

Several third-party parsing SDKs (e.g. LiteParse) return a mix of dataclass
instances and plain dicts across versions/entry points. Parser code that
needs to read the same field off either shape without a large if/else ladder
belongs here rather than being redefined per-parser.
"""

from typing import Any


def attr_or_key(obj: Any, name: str, default: Any = None) -> Any:
    """Read ``name`` from ``obj``, whether it's a dict or an attribute-bearing object.

    Useful for SDK types that may return either dataclass instances or plain
    dicts (version drift in a binding, or lightweight stand-ins used in unit
    tests), so callers don't need to special-case each shape.
    """
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)
