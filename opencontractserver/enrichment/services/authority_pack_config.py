"""Per-pack citation-taxonomy extensions: shape rules + abbreviation tables.

A jurisdiction's *citation vocabulary* — the prefix-family classification
(``classify_prefix``) and the Bluebook abbreviation tables the Tier-2a extractor
matches — ships as the engine's baseline in Python (``enrichment/constants.py``,
``enrichment/abbreviations.py``). A **pack** that adds a new jurisdiction can carry
its OWN additions *inside the pack*, declared in the pack's authority-mappings YAML
(the file ``pack.yaml`` points at via ``mappings:``) under two optional sections::

    shape_rules:                      # prefix-family → (jurisdiction, authority_type)
      - pattern: '^bo-ley-\\d+$'
        jurisdiction: bo
        authority_type: statute

    abbreviations:                    # Bluebook abbreviation → keyed authority
      state:
        "Ley N° {n} de Bolivia":      # matched literally by the Tier-2a grammar
          {prefix: bo-ley, jurisdiction: bo, authority_type: statute}
      municipal:
        ...

These are read from every *installed* pack (the same directories the pipeline
registry scans for providers -- see ``pipeline.registry.authority_pack_dirs``)
and merged with the Python baseline at runtime, so a pack's citation vocabulary
travels WITH the pack — copy the directory, get the classification. Installing the
pack is the decision; the baseline always wins a key collision (a pack extends, it
does not override the shipped engine vocab). Malformed entries are logged + skipped
so one bad pack cannot break extraction; ``load_authority_pack`` validates the
shape fail-fast.

Consumed lazily (``constants.classify_prefix`` for shape rules,
``grammars.GenericCitationExtractor`` for abbreviations) so importing this module —
which reaches the pipeline registry to enumerate packs — never cycles back through
the very-early ``enrichment.constants`` import.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path

import yaml

from opencontractserver.enrichment.constants import ALL_AUTHORITY_TYPES
from opencontractserver.pipeline.registry import authority_pack_dirs

logger = logging.getLogger(__name__)

# (compiled prefix pattern, jurisdiction | None, authority_type | None)
ShapeRule = tuple[re.Pattern, "str | None", "str | None"]
# abbreviation (as it appears in text) ->
# (prefix, jurisdiction, authority_type, requires_section_marker)
AbbrevEntry = tuple[str, str | None, str | None, bool]


def pack_origin_name(pack_dir: Path, manifest: dict) -> str:
    """A pack's identity string (its ``baseline_origin`` stamp / registry key):
    the manifest ``name:``, falling back to the pack directory's name. Shared by
    the mapping loader and ``load_authority_pack`` so the two can never derive
    different origins for the same pack."""
    return str((manifest or {}).get("name") or pack_dir.name)


def iter_pack_mapping_files(errors: list | None = None):
    """Yield ``(pack_dir, mappings_yaml_path, manifest)`` for every installed pack
    that declares a ``mappings:`` file that exists on disk.

    ``manifest`` is the parsed ``pack.yaml`` dict — yielded so callers that need
    manifest metadata (e.g. ``AuthorityMappingLoader.load_installed`` deriving the
    pack's baseline origin from ``name:``) don't re-read/re-parse the file.

    ``errors``: optional list to which ``(pack_dir, message)`` is appended for a
    pack that is broken rather than merely mappings-less — an unparsable
    ``pack.yaml``, or a declared ``mappings:`` file missing on disk (the classic
    typo) — so a reporting caller (``load_installed``) can surface the skip to
    the operator instead of it living only in the log. The runtime vocab scans
    omit it (log-and-skip is their whole contract). A manifest with no
    ``mappings:`` key is a content-only pack — skipped by design, never an
    error.
    """
    for pack_dir in authority_pack_dirs():
        manifest = pack_dir / "pack.yaml"
        if not manifest.is_file():
            continue
        try:
            data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            logger.warning("Could not parse %s: %s", manifest, exc)
            if errors is not None:
                errors.append((pack_dir, f"could not parse pack.yaml: {exc}"))
            continue
        rel = data.get("mappings")
        if not rel:
            continue
        path = pack_dir / rel
        if not path.is_file():
            # Declared but absent — a typo'd path would otherwise make the
            # pack's taxonomy silently never load (load_authority_pack raises
            # CommandError for this same condition).
            logger.warning(
                "Pack %s declares mappings %r but %s does not exist",
                pack_dir.name,
                rel,
                path,
            )
            if errors is not None:
                errors.append((pack_dir, f"declared mappings file not found: {path}"))
            continue
        yield pack_dir, path, data


def _load_yaml(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except yaml.YAMLError as exc:
        logger.warning("Could not parse pack mappings %s: %s", path, exc)
        return {}


def _valid_type(value) -> bool:
    return value is None or value in ALL_AUTHORITY_TYPES


def iter_shape_rules(data: dict, *, label: str = "shape_rules") -> list[dict]:
    """Validate a parsed ``shape_rules:`` list → ``[{pattern, jurisdiction?, authority_type?}]``.

    Raises ``ValueError`` on a malformed entry (uncompilable pattern / unknown
    authority_type) so ``load_authority_pack`` can fail fast; the runtime scan
    wraps this and downgrades a raise to log-and-skip.
    """
    raw = data.get("shape_rules")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"{label}: 'shape_rules' must be a list")
    out: list[dict] = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict) or not entry.get("pattern"):
            raise ValueError(f"{label}: shape_rules[{i}] needs a 'pattern'")
        pattern = str(entry["pattern"])
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"{label}: shape_rules[{i}] bad regex {pattern!r}: {exc}")
        atype = entry.get("authority_type")
        if not _valid_type(atype):
            raise ValueError(
                f"{label}: shape_rules[{i}] authority_type {atype!r} not in "
                f"ALL_AUTHORITY_TYPES"
            )
        out.append(
            {
                "pattern": pattern,
                "jurisdiction": entry.get("jurisdiction") or None,
                "authority_type": atype or None,
            }
        )
    return out


def iter_abbreviations(data: dict, *, label: str = "abbreviations") -> dict[str, dict]:
    """Validate a parsed ``abbreviations:`` mapping → ``{"state": {...}, "municipal": {...}}``.

    Each leaf is ``abbreviation -> {prefix, jurisdiction, authority_type,
    requires_section_marker?}``. ``requires_section_marker`` lets a pack keep a
    useful authority name while requiring ``§``, ``Section``, or ``Sec.`` before
    the locator. This avoids interpreting an edition year as a section without
    adding a one-off core grammar. Raises ``ValueError`` on a malformed entry;
    the runtime scan downgrades to skip.
    """
    raw = data.get("abbreviations")
    if raw is None:
        return {"state": {}, "municipal": {}}
    if not isinstance(raw, dict):
        raise ValueError(f"{label}: 'abbreviations' must be a mapping")
    out: dict[str, dict] = {"state": {}, "municipal": {}}
    for group in ("state", "municipal"):
        entries = raw.get(group) or {}
        if not isinstance(entries, dict):
            raise ValueError(f"{label}: abbreviations.{group} must be a mapping")
        for abbr, spec in entries.items():
            if not isinstance(spec, dict) or not spec.get("prefix"):
                raise ValueError(
                    f"{label}: abbreviations.{group}[{abbr!r}] needs 'prefix'"
                )
            atype = spec.get("authority_type")
            if not _valid_type(atype):
                raise ValueError(
                    f"{label}: abbreviations.{group}[{abbr!r}] authority_type "
                    f"{atype!r} not in ALL_AUTHORITY_TYPES"
                )
            requires_marker = spec.get("requires_section_marker", False)
            if type(requires_marker) is not bool:
                raise ValueError(
                    f"{label}: abbreviations.{group}[{abbr!r}] "
                    "'requires_section_marker' must be true or false"
                )
            out[group][str(abbr)] = {
                "prefix": str(spec["prefix"]),
                "jurisdiction": spec.get("jurisdiction") or None,
                "authority_type": atype or None,
                "requires_section_marker": requires_marker,
            }
    return out


def validate_pack_taxonomy_extensions(mappings_path: Path) -> None:
    """Fail-fast validation of a pack's ``shape_rules``/``abbreviations`` sections."""
    data = _load_yaml(Path(mappings_path))
    iter_shape_rules(data, label=str(mappings_path))
    iter_abbreviations(data, label=str(mappings_path))


@lru_cache(maxsize=1)
def pack_declared_shape_rules() -> tuple[ShapeRule, ...]:
    """Compiled shape rules contributed by every installed pack (cached)."""
    rules: list[ShapeRule] = []
    for pack_dir, mappings_path, _manifest in iter_pack_mapping_files():
        data = _load_yaml(mappings_path)
        try:
            parsed = iter_shape_rules(data, label=str(mappings_path))
        except ValueError as exc:
            logger.warning("Skipping shape_rules in pack %r: %s", pack_dir.name, exc)
            continue
        for r in parsed:
            rules.append(
                (re.compile(r["pattern"]), r["jurisdiction"], r["authority_type"])
            )
            logger.info(
                "Pack %r adds shape rule %s -> (%s, %s)",
                pack_dir.name,
                r["pattern"],
                r["jurisdiction"],
                r["authority_type"],
            )
    return tuple(rules)


@lru_cache(maxsize=1)
def pack_declared_abbreviations() -> (
    tuple[dict[str, AbbrevEntry], dict[str, AbbrevEntry]]
):
    """Merged ``(state, municipal)`` abbreviation tables from every installed pack.

    Returns dicts shaped like the Python baselines
    (``abbreviation -> (prefix, jurisdiction, authority_type)``) so the extractor
    can merge them with ``{**baseline, **pack}``.
    """
    state: dict[str, AbbrevEntry] = {}
    municipal: dict[str, AbbrevEntry] = {}
    for pack_dir, mappings_path, _manifest in iter_pack_mapping_files():
        data = _load_yaml(mappings_path)
        try:
            parsed = iter_abbreviations(data, label=str(mappings_path))
        except ValueError as exc:
            logger.warning("Skipping abbreviations in pack %r: %s", pack_dir.name, exc)
            continue
        for group, target in (("state", state), ("municipal", municipal)):
            for abbr, spec in parsed[group].items():
                target[abbr] = (
                    spec["prefix"],
                    spec["jurisdiction"],
                    spec["authority_type"],
                    spec["requires_section_marker"],
                )
    return state, municipal


def reset_pack_config_cache() -> None:
    """Clear the pack shape-rule / abbreviation caches (after changing packs)."""
    pack_declared_shape_rules.cache_clear()
    pack_declared_abbreviations.cache_clear()
