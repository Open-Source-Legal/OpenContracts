"""Idempotent, source-scoped loader for the declarative authority-mappings baseline.

``opencontractserver/enrichment/data/authority_mappings.yaml`` is the single
source of truth for shipped (``source="baseline"``) authority key equivalences.
This loader upserts it into the DB and NEVER overwrites a ``source="manual"``
(runtime curator) row, so a re-load can't clobber an operator override.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from opencontractserver.annotations.models import AuthorityKeyEquivalence

DEFAULT_MAPPINGS_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "authority_mappings.yaml"
)

# canonical_key shape: "<prefix>:<section>" — lowercase-alnum/hyphen prefix.
_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9-]*:.+$")


class AuthorityMappingLoader:
    """Load the baseline authority mappings YAML into the database."""

    BASELINE = "baseline"
    MANUAL = "manual"

    @classmethod
    def load(cls, *, path: Path | str | None = None) -> dict:
        data = cls._read(path)
        equivalences = data.get("equivalences") or []

        created = updated = skipped_manual = 0
        seen: set[tuple[str, str]] = set()
        for entry in equivalences:
            try:
                from_key = str(entry["from_key"]).strip()
                to_key = str(entry["to_key"]).strip()
            except (KeyError, TypeError) as exc:
                raise ValueError(
                    f"authority_mappings entry missing from_key/to_key: {entry!r}"
                ) from exc
            cls._validate(from_key, to_key)
            pair = (from_key, to_key)
            if pair in seen:
                continue
            seen.add(pair)

            existing = AuthorityKeyEquivalence.objects.filter(
                from_key=from_key, to_key=to_key
            ).first()
            if existing is not None and existing.source == cls.MANUAL:
                skipped_manual += 1
                continue

            # YAML is authoritative for baseline rows: an omitted `note:` resets the
            # stored note. (Manual rows are never reached here — skipped above.)
            note = (entry.get("note") or "").strip()
            _, was_created = AuthorityKeyEquivalence.objects.update_or_create(
                from_key=from_key,
                to_key=to_key,
                defaults={
                    "source": cls.BASELINE,
                    "confidence": 1.0,
                    "note": note or None,
                },
            )
            created += int(was_created)
            updated += int(not was_created)

        # total = distinct validated pairs seen = created + updated + skipped_manual.
        return {
            "created": created,
            "updated": updated,
            "skipped_manual": skipped_manual,
            "total": len(seen),
        }

    @staticmethod
    def _read(path: Path | str | None) -> dict:
        p = Path(path) if path is not None else DEFAULT_MAPPINGS_PATH
        with open(p, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if not isinstance(data, dict):
            raise ValueError(f"authority_mappings YAML root must be a mapping: {p}")
        return data

    @classmethod
    def _validate(cls, from_key: str, to_key: str) -> None:
        for key in (from_key, to_key):
            if not _KEY_RE.match(key):
                raise ValueError(
                    f"Invalid canonical key {key!r}: expected '<prefix>:<section>'"
                )
