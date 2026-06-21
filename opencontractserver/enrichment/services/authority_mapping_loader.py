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

from opencontractserver.annotations.models import AuthorityNamespace
from opencontractserver.enrichment.data import mappings as _mappings
from opencontractserver.enrichment.services.authority_equivalence_ingest import (
    CREATED,
    SKIPPED_OWNED,
    UPDATED,
    upsert_equivalence,
)


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

            # Delegate to the shared atomic upsert so the source-ownership guard
            # and the row write happen under one ``select_for_update`` lock — a
            # bare filter-then-create here is racy under concurrent loader calls
            # (same hazard the ingest writer guards). YAML is authoritative for
            # baseline rows: an omitted ``note:`` resets the stored note.
            outcome = upsert_equivalence(
                from_key=from_key,
                to_key=to_key,
                source=cls.BASELINE,
                confidence=1.0,
                note=entry.get("note") or None,
            )
            if outcome == CREATED:
                created += 1
            elif outcome == UPDATED:
                updated += 1
            elif outcome == SKIPPED_OWNED:
                skipped_owned += 1
            # SKIPPED_INVALID cannot occur: ``iter_equivalences`` already
            # fail-fast-validated every key's format above, and the baseline
            # never self-references.

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

        Source-ownership partition (the loader owns only ``baseline``): a
        pre-existing row is left untouched when EITHER

        - it is corpus-linked (``is_global=False``, bootstrap-owned) — a re-load
          must never flip a corpus namespace to global (see
          ``AuthorityNamespace.save()``), OR
        - it is ``source="manual"`` — a curator created/edited it through the
          admin console; clobbering it on the next loader run would silently
          discard the operator's edits.

        Mirrors the equivalence loader's ``skipped_owned`` guard exactly.
        Returns ``{created, updated, skipped_corpus_linked, skipped_manual,
        total}``.
        """
        prefixes = _mappings.iter_prefixes(path)

        created = updated = skipped_corpus_linked = skipped_manual = 0
        for prefix, spec in prefixes.items():
            existing = AuthorityNamespace.objects.filter(prefix=prefix).first()
            if existing is not None and existing.authority_corpus_id:
                # A corpus-scoped namespace owns this prefix; never overwrite it.
                skipped_corpus_linked += 1
                continue
            if existing is not None and existing.source == cls.MANUAL:
                # A curator owns this prefix via the admin console; never clobber.
                skipped_manual += 1
                continue

            _, was_created = AuthorityNamespace.objects.update_or_create(
                prefix=prefix,
                defaults={
                    "display_name": spec["display_name"],
                    "jurisdiction": spec["jurisdiction"],
                    "authority_type": spec["authority_type"],
                    "aliases": sorted(set(spec["aliases"])),
                    "is_global": True,
                    "source": cls.BASELINE,
                },
            )
            created += int(was_created)
            updated += int(not was_created)

        return {
            "created": created,
            "updated": updated,
            "skipped_corpus_linked": skipped_corpus_linked,
            "skipped_manual": skipped_manual,
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
