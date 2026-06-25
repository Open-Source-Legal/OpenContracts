"""Pure reader for the declarative authority-mappings YAML.

Single source of truth:
``opencontractserver/enrichment/data/authority_mappings.yaml``. This module
ONLY parses + shape-validates that file and derives the in-memory lookup maps
the engine exposes. It imports **no Django models** on purpose, so
``enrichment.constants`` — imported very early and very widely — can derive its
prefix tables from here without a circular import.

DB upserts (``AuthorityNamespace`` / ``AuthorityKeyEquivalence``) live in
``enrichment.services.authority_mapping_loader.AuthorityMappingLoader``, which
reuses this module's parsing/validation. The runtime rewrite-rule evaluation
(:func:`apply_rewrite_rules`) also reads from here so the YAML stays the one
editable surface for prefixes, equivalences, and rewrite rules.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

DEFAULT_MAPPINGS_PATH = Path(__file__).resolve().parent / "authority_mappings.yaml"

# canonical_key shape: "<prefix>:<section>" — lowercase-alnum/hyphen prefix, then
# a non-empty section. Shared grammar for equivalence keys + CRUD validation.
_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9-]*:.+$")
# A bare prefix token (no section): lowercase-alnum/hyphen.
_PREFIX_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def is_valid_canonical_key(key: str | None) -> bool:
    """True iff *key* is a well-formed ``"<prefix>:<section>"`` canonical key."""
    return bool(_KEY_RE.match(key or ""))


def is_valid_prefix(prefix: str | None) -> bool:
    """True iff *prefix* is a well-formed bare authority prefix (no section)."""
    return bool(_PREFIX_RE.match(prefix or ""))


def load_mappings_file(path: Path | str | None = None) -> dict:
    """Parse the YAML file (or the shipped default) into a plain dict."""
    p = Path(path) if path is not None else DEFAULT_MAPPINGS_PATH
    with open(p, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"authority_mappings YAML root must be a mapping: {p}")
    return data


def _as_data(data_or_path: Any) -> dict:
    """Accept an already-parsed dict, a path, or ``None`` (the default file)."""
    if isinstance(data_or_path, dict):
        return data_or_path
    return load_mappings_file(data_or_path)


def iter_prefixes(data: Any = None) -> dict[str, dict]:
    """Return ``{prefix: {aliases, jurisdiction, authority_type, display_name}}``.

    Shape-validates each entry (well-formed prefix; display_name defaults to the
    prefix). Authority-type/jurisdiction *vocabulary* validation lives in the
    completeness test (it needs ``enrichment.constants``, which imports this
    module — keeping it here would be circular).
    """
    data = _as_data(data)
    raw = data.get("prefixes") or {}
    if not isinstance(raw, dict):
        raise ValueError("authority_mappings 'prefixes' must be a mapping")
    out: dict[str, dict] = {}
    for prefix, spec in raw.items():
        prefix = str(prefix).strip()
        if not is_valid_prefix(prefix):
            raise ValueError(f"Invalid authority prefix {prefix!r}")
        spec = spec or {}
        aliases = [
            str(a).strip().lower()
            for a in (spec.get("aliases") or [])
            if str(a).strip()
        ]
        out[prefix] = {
            "aliases": aliases,
            "jurisdiction": (spec.get("jurisdiction") or None),
            "authority_type": (spec.get("authority_type") or None),
            "display_name": str(spec.get("display_name") or prefix),
        }
    return out


def iter_equivalences(data: Any = None) -> list[dict]:
    """Return validated ``[{from_key, to_key, note?}]`` equivalence entries.

    Raises ``ValueError`` on a missing key or a malformed canonical key so a
    typo fails fast at load rather than silently mis-resolving.
    """
    data = _as_data(data)
    raw = data.get("equivalences") or []
    if not isinstance(raw, list):
        raise ValueError("authority_mappings 'equivalences' must be a list")
    out: list[dict] = []
    for entry in raw:
        try:
            from_key = str(entry["from_key"]).strip()
            to_key = str(entry["to_key"]).strip()
        except (KeyError, TypeError) as exc:
            raise ValueError(
                f"authority_mappings equivalence missing from_key/to_key: {entry!r}"
            ) from exc
        for key in (from_key, to_key):
            if not is_valid_canonical_key(key):
                raise ValueError(
                    f"Invalid canonical key {key!r}: expected '<prefix>:<section>'"
                )
        # A self-equivalence bridges a key to itself — a no-op that the DB
        # CheckConstraint and the atomic upsert both reject as SKIPPED_INVALID.
        # Reject it here too so the loader's tally can never silently drop a pair
        # it counted into ``total`` (the reader is the single fail-fast surface).
        if from_key == to_key:
            raise ValueError(
                f"authority_mappings equivalence is self-referential "
                f"(from_key == to_key == {from_key!r}); a key cannot bridge to itself"
            )
        out.append(
            {
                "from_key": from_key,
                "to_key": to_key,
                "note": (str(entry.get("note")).strip() if entry.get("note") else None),
            }
        )
    return out


def iter_rewrite_rules(data: Any = None) -> list[dict]:
    """Return validated ``[{pattern, replacement, note?}]`` rewrite-rule entries.

    Each ``pattern`` must compile as a regex; an invalid pattern fails fast.
    Rewrite rules are a sparing, reviewed fallback evaluated AFTER explicit
    per-key equivalences (see :func:`apply_rewrite_rules`).
    """
    data = _as_data(data)
    raw = data.get("rewrite_rules") or []
    if not isinstance(raw, list):
        raise ValueError("authority_mappings 'rewrite_rules' must be a list")
    out: list[dict] = []
    for entry in raw:
        try:
            pattern = str(entry["pattern"])
            replacement = str(entry["replacement"])
        except (KeyError, TypeError) as exc:
            raise ValueError(
                f"authority_mappings rewrite_rule missing pattern/replacement: "
                f"{entry!r}"
            ) from exc
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError(
                f"authority_mappings rewrite_rule pattern {pattern!r} is not a "
                f"valid regex: {exc}"
            ) from exc
        out.append(
            {
                "pattern": pattern,
                "replacement": replacement,
                "note": (str(entry.get("note")).strip() if entry.get("note") else None),
            }
        )
    return out


# --- Rewrite-rule evaluation -------------------------------------------------- #
# Compiled once per process from the shipped file (rules change rarely and the
# worker is long-lived). Tests pass explicit ``rules=`` to bypass the cache.


@lru_cache(maxsize=1)
def _default_compiled_rewrite_rules() -> tuple[tuple[Any, str], ...]:
    return tuple(
        (re.compile(r["pattern"]), r["replacement"])
        for r in iter_rewrite_rules(load_mappings_file())
    )


def apply_rewrite_rules(
    key: str,
    *,
    rules: list[dict] | None = None,
) -> list[str]:
    """Apply every matching rewrite rule to *key*, returning rewritten keys.

    The original *key* is never included in the result. Used as a FALLBACK in
    the two resolution seams (``_provider_for`` / ``find_authority_target``)
    after explicit per-key equivalences are exhausted — so an explicit row
    always wins over a mechanical rule. ``rules`` (the parsed
    ``iter_rewrite_rules`` shape) overrides the cached shipped rules; omit it in
    production.
    """
    if not key:
        return []
    if rules is None:
        compiled = _default_compiled_rewrite_rules()
    else:
        compiled = tuple((re.compile(r["pattern"]), r["replacement"]) for r in rules)

    out: list[str] = []
    seen: set[str] = {key}
    for pattern, replacement in compiled:
        if not pattern.search(key):
            continue
        rewritten = pattern.sub(replacement, key)
        if rewritten and rewritten not in seen:
            seen.add(rewritten)
            out.append(rewritten)
    return out


# --- Derived lookup maps consumed by ``enrichment.constants`` ----------------- #
# Built once from the shipped default file. ``enrichment.constants`` exposes
# these as ``AUTHORITY_PREFIX`` / ``PREFIX_CLASSIFICATION`` / ``PREFIX_DISPLAY_NAME``
# so the YAML is the single editable source and the legacy reader API is
# preserved unchanged.


@lru_cache(maxsize=1)
def _default_prefixes() -> dict[str, dict]:
    return iter_prefixes(load_mappings_file())


def authority_prefix_map() -> dict[str, str]:
    """``alias (lowercased) -> canonical prefix`` (legacy ``AUTHORITY_PREFIX``)."""
    out: dict[str, str] = {}
    for prefix, spec in _default_prefixes().items():
        for alias in spec["aliases"]:
            out[alias] = prefix
    return out


def prefix_classification() -> dict[str, tuple]:
    """``prefix -> (jurisdiction, authority_type)`` (legacy ``PREFIX_CLASSIFICATION``)."""
    return {
        p: (s["jurisdiction"], s["authority_type"])
        for p, s in _default_prefixes().items()
    }


def prefix_display_name() -> dict[str, str]:
    """``prefix -> display_name`` (legacy ``PREFIX_DISPLAY_NAME``)."""
    return {p: s["display_name"] for p, s in _default_prefixes().items()}
