"""Idempotent, source-scoped loader for the declarative authority-mappings baseline.

``opencontractserver/enrichment/data/authority_mappings.yaml`` is the single
source of truth. This loader upserts it into the database:

- ``prefixes:``     → ``AuthorityNamespace`` registry rows (global, baseline)
- ``equivalences:`` → ``AuthorityKeyEquivalence`` rows tagged ``source="baseline"``

It NEVER overwrites a ``source="manual"`` equivalence (runtime curator override)
nor a corpus-linked ``AuthorityNamespace`` (``is_global=False``, bootstrap-owned),
so a re-load can't clobber operator/runtime state. Parsing + validation are
delegated to the pure ``enrichment.data.mappings`` reader (no Django models), so
the YAML grammar has exactly one definition shared with ``enrichment.constants``.
"""

from __future__ import annotations

from pathlib import Path

from opencontractserver.annotations.models import (
    AuthorityKeyEquivalence,
    AuthorityNamespace,
)
from opencontractserver.enrichment.data import mappings as _mappings


class AuthorityMappingLoader:
    """Load the declarative authority-mappings YAML into the database."""

    BASELINE = "baseline"
    MANUAL = "manual"

    @classmethod
    def load(cls, *, path: Path | str | None = None) -> dict:
        """Upsert equivalences as ``source="baseline"``; never clobber another source.

        Source-ownership partition (the loader owns only ``baseline``): any
        pre-existing row whose source is NOT ``baseline`` — a ``manual`` curator
        override or an importer-owned ``uslm`` / ``popular_name`` row — is left
        untouched and counted under ``skipped_owned``. Mirrors
        ``authority_equivalence_ingest.upsert_equivalence``'s symmetric guard so
        no writer ever overwrites a row another source owns.

        Returns ``{created, updated, skipped_owned, total}`` where ``total`` is
        the count of distinct validated ``(from_key, to_key)`` pairs in the file.
        Raises ``ValueError`` on a malformed/missing key (fail fast).
        """
        equivalences = _mappings.iter_equivalences(path)

        created = updated = skipped_owned = 0
        seen: set[tuple[str, str]] = set()
        for entry in equivalences:
            from_key = entry["from_key"]
            to_key = entry["to_key"]
            pair = (from_key, to_key)
            if pair in seen:
                continue
            seen.add(pair)

            existing = AuthorityKeyEquivalence.objects.filter(
                from_key=from_key, to_key=to_key
            ).first()
            if existing is not None and existing.source != cls.BASELINE:
                skipped_owned += 1
                continue

            # YAML is authoritative for baseline rows: an omitted `note:` resets
            # the stored note. (Non-baseline rows are never reached here.)
            _, was_created = AuthorityKeyEquivalence.objects.update_or_create(
                from_key=from_key,
                to_key=to_key,
                defaults={
                    "source": cls.BASELINE,
                    "confidence": 1.0,
                    "note": entry.get("note") or None,
                },
            )
            created += int(was_created)
            updated += int(not was_created)

        # total = distinct validated pairs seen = created + updated + skipped_owned.
        return {
            "created": created,
            "updated": updated,
            "skipped_owned": skipped_owned,
            "total": len(seen),
        }

    @classmethod
    def load_namespaces(cls, *, path: Path | str | None = None) -> dict:
        """Upsert global ``AuthorityNamespace`` registry rows from ``prefixes:``.

        Skips corpus-linked rows (``is_global=False``, bootstrap-owned) so a
        re-load never flips a corpus namespace to global. Returns
        ``{created, updated, skipped_corpus_linked, total}``.
        """
        prefixes = _mappings.iter_prefixes(path)

        created = updated = skipped_corpus_linked = 0
        for prefix, spec in prefixes.items():
            existing = AuthorityNamespace.objects.filter(prefix=prefix).first()
            if existing is not None and existing.authority_corpus_id:
                # A corpus-scoped namespace owns this prefix; never overwrite it
                # (it must stay is_global=False — see AuthorityNamespace.save()).
                skipped_corpus_linked += 1
                continue

            _, was_created = AuthorityNamespace.objects.update_or_create(
                prefix=prefix,
                defaults={
                    "display_name": spec["display_name"],
                    "jurisdiction": spec["jurisdiction"],
                    "authority_type": spec["authority_type"],
                    "aliases": sorted(set(spec["aliases"])),
                    "is_global": True,
                },
            )
            created += int(was_created)
            updated += int(not was_created)

        return {
            "created": created,
            "updated": updated,
            "skipped_corpus_linked": skipped_corpus_linked,
            "total": len(prefixes),
        }

    @classmethod
    def load_all(cls, *, path: Path | str | None = None) -> dict:
        """Upsert both namespaces and equivalences from the YAML.

        Returns ``{"namespaces": {...}, "equivalences": {...}}``. Namespaces are
        loaded first so an equivalence's prefix always has a registry row.
        """
        return {
            "namespaces": cls.load_namespaces(path=path),
            "equivalences": cls.load(path=path),
        }
