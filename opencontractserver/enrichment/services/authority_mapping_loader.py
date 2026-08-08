"""Idempotent, source-scoped loader for the declarative authority-mappings baseline.

``opencontractserver/enrichment/data/authority_mappings.yaml`` is the single
source of truth for the CORE baseline; each installed authority pack may carry
its own mappings YAML (the file its ``pack.yaml`` points at via ``mappings:``).
This loader upserts either into the database:

- ``prefixes:``     → ``AuthorityNamespace`` registry rows (global, baseline)
- ``equivalences:`` → ``AuthorityKeyEquivalence`` rows tagged ``source="baseline"``

It NEVER overwrites a ``source="manual"`` equivalence (runtime curator override)
nor a corpus-linked ``AuthorityNamespace`` (``is_global=False``, bootstrap-owned),
so a re-load can't clobber operator/runtime state. Baseline namespace rows are
additionally stamped with a writer ``baseline_origin`` (``"core"`` or the pack's
manifest name) so two baseline writers on the same prefix cannot silently
last-write-wins each other either — the first writer owns the prefix and a
foreign origin is skipped with a warning (issue #2057). Parsing + validation are
delegated to the pure ``enrichment.data.mappings`` reader (no Django models), so
the YAML grammar has exactly one definition shared with ``enrichment.constants``.
"""

from __future__ import annotations

import logging
from pathlib import Path

from django.db import transaction

from opencontractserver.annotations.models import AuthorityNamespace
from opencontractserver.enrichment.constants import BASELINE_ORIGIN_CORE
from opencontractserver.enrichment.data import mappings as _mappings
from opencontractserver.enrichment.services.authority_equivalence_ingest import (
    CREATED,
    SKIPPED_OWNED,
    UPDATED,
    upsert_equivalence,
)

logger = logging.getLogger(__name__)


class AuthorityMappingLoader:
    """Load a declarative authority-mappings YAML into the database."""

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

        Unlike namespaces, equivalence rows carry no per-writer origin: the
        ``(from_key, to_key)`` pair IS the row's content, so two baseline
        writers declaring the same pair assert the same fact (only the optional
        ``note`` can differ, and the last load's note wins — cosmetic, not a
        clobber). Distinct pairs never touch each other.

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
    def load_namespaces(
        cls, *, path: Path | str | None = None, origin: str | None = None
    ) -> dict:
        """Upsert global ``AuthorityNamespace`` registry rows from ``prefixes:``.

        ``origin`` identifies the baseline WRITER — ``BASELINE_ORIGIN_CORE``
        (``"core"``) for the shipped default YAML (the default when ``path`` is
        omitted), or the pack's manifest ``name`` when loading a pack's mappings.

        Source-ownership partition (the loader owns only ``baseline``, and each
        baseline writer owns only its own prefixes): a pre-existing row is left
        untouched when ANY of

        - it is corpus-linked (``is_global=False``, bootstrap-owned) — a re-load
          must never flip a corpus namespace to global (see
          ``AuthorityNamespace.save()``), OR
        - it is ``source="manual"`` — a curator created/edited it through the
          admin console; clobbering it on the next loader run would silently
          discard the operator's edits, OR
        - it is a baseline row stamped with a DIFFERENT ``baseline_origin`` —
          another baseline writer (the core YAML vs. a pack, or two packs)
          already owns the prefix. First writer wins; the collision is logged
          and counted under ``skipped_foreign_baseline`` so two packs (or a
          pack and the core baseline) can never silently clobber each other
          (issue #2057). A legacy baseline row with a null origin is adopted —
          updated and stamped with this run's origin.

        Returns ``{created, updated, skipped_corpus_linked, skipped_manual,
        skipped_foreign_baseline, total}``.
        """
        if origin is None and path is None:
            origin = BASELINE_ORIGIN_CORE
        prefixes = _mappings.iter_prefixes(path)

        created = updated = 0
        skipped_corpus_linked = skipped_manual = skipped_foreign_baseline = 0
        for prefix, spec in prefixes.items():
            # NOTE: read-then-decide-then-write without select_for_update. Two
            # CONCURRENT loader runs with different origins racing on a
            # brand-new prefix could both see "absent" and the second write
            # would win without hitting the ownership guard. Accepted: namespace
            # loads are operator-run management commands / migrations, not
            # concurrent runtime writers (unlike equivalences, whose
            # ``upsert_equivalence`` IS invoked from concurrent ingest tasks and
            # therefore locks). Revisit if namespace loading ever moves into a
            # task fan-out.
            existing = AuthorityNamespace.objects.filter(prefix=prefix).first()
            if existing is not None and existing.authority_corpus_id:
                # A corpus-scoped namespace owns this prefix; never overwrite it.
                skipped_corpus_linked += 1
                continue
            if existing is not None and existing.source == cls.MANUAL:
                # A curator owns this prefix via the admin console; never clobber.
                skipped_manual += 1
                continue
            if (
                existing is not None
                and existing.baseline_origin
                and existing.baseline_origin != origin
            ):
                # Another baseline writer owns this prefix; never clobber. (An
                # unattributed run — origin=None with an explicit path — can
                # never steal an owned prefix either.)
                skipped_foreign_baseline += 1
                logger.warning(
                    "Baseline collision on authority prefix %r: owned by origin "
                    "%r, skipping the load from origin %r (first writer wins; "
                    "resolve by removing the prefix from one YAML, or curate the "
                    "row through the console to make it manual-owned).",
                    prefix,
                    existing.baseline_origin,
                    origin,
                )
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
                    "baseline_origin": origin,
                },
            )
            created += int(was_created)
            updated += int(not was_created)

        return {
            "created": created,
            "updated": updated,
            "skipped_corpus_linked": skipped_corpus_linked,
            "skipped_manual": skipped_manual,
            "skipped_foreign_baseline": skipped_foreign_baseline,
            "total": len(prefixes),
        }

    @classmethod
    def load_all(
        cls, *, path: Path | str | None = None, origin: str | None = None
    ) -> dict:
        """Upsert both namespaces and equivalences from one YAML, atomically.

        Returns ``{"namespaces": {...}, "equivalences": {...}}``. Namespaces are
        loaded first so an equivalence's prefix always has a registry row.
        ``origin`` is threaded to :meth:`load_namespaces` (equivalence rows carry
        no per-writer origin — see :meth:`load`).

        The two steps run in ONE transaction: without it, a YAML with valid
        ``prefixes:`` but a malformed ``equivalences:`` entry would durably
        commit the namespace rows and then raise — leaving a half-loaded file
        that ``load_installed`` / ``load_authority_pack`` would report as
        "errored / nothing loaded". An error must mean nothing took effect.
        """
        with transaction.atomic():
            return {
                "namespaces": cls.load_namespaces(path=path, origin=origin),
                "equivalences": cls.load(path=path),
            }

    @classmethod
    def load_installed(cls) -> dict[str, dict]:
        """Merge-load the core baseline YAML plus every installed pack's mappings.

        One idempotent call converges the whole installed taxonomy: the shipped
        ``authority_mappings.yaml`` first (origin ``"core"``), then each
        installed pack's mappings YAML (in-tree ``authority_packs/`` +
        sideloaded, in ``authority_pack_dirs()`` discovery order)
        stamped with the pack's manifest ``name`` (falling back to its directory
        name). Core loading first means that on a same-prefix collision the
        shipped engine baseline wins and the pack's claim is skipped + warned —
        the same "the baseline always wins" merge rule
        ``authority_pack_config`` applies to shape rules / abbreviations.

        Returns ``{origin: load_all()-summary}`` in load order.

        Deliberate asymmetry: only PACK loads get per-origin fault isolation.
        The initial core load raises on failure — a broken shipped
        ``authority_mappings.yaml`` is a build defect (its own test suite and
        the plain ``load_authority_mappings`` path fail on it), not an
        installed-pack problem to route around.
        """
        # Lazy import: authority_pack_config reaches the pipeline registry to
        # enumerate packs; consuming it lazily (like constants.classify_prefix
        # does) keeps this module import-light for the migration/seed path.
        from opencontractserver.enrichment.services.authority_pack_config import (
            iter_pack_mapping_files,
            pack_origin_name,
        )

        results: dict[str, dict] = {BASELINE_ORIGIN_CORE: cls.load_all()}
        pack_errors: list = []
        for pack_dir, mappings_path, manifest in iter_pack_mapping_files(
            errors=pack_errors
        ):
            origin = pack_origin_name(pack_dir, manifest)
            if origin.lower() == BASELINE_ORIGIN_CORE:
                # A pack literally named "core" would impersonate the shipped
                # baseline and bypass the collision guard — refuse it, and put
                # the refusal in the report so the operator sees it in the
                # command output, same as every other per-pack failure.
                # load_authority_pack raises CommandError for the same
                # condition.
                logger.warning(
                    "Skipping authority pack at %s: pack name %r is reserved "
                    "for the shipped core baseline.",
                    pack_dir,
                    origin,
                )
                _report_pack_error(
                    results,
                    pack_dir,
                    f"pack name {origin!r} is reserved for the shipped "
                    "core baseline; rename the pack",
                )
                continue
            if any(origin.lower() == seen.lower() for seen in results):
                # Case-insensitive, matching the reserved-name check. Two
                # installed pack dirs declaring the SAME manifest name are, by
                # declaration, the same pack (e.g. an in-tree copy + an
                # sideloaded copy): they co-own their prefixes, the
                # load stays idempotent, and the later summary replaces the
                # earlier one in the report. A case-DIFFERENT name ("Bolivia"
                # vs "bolivia") loads as a distinct origin — the collision
                # guard keeps the two from clobbering each other — but is
                # almost certainly an authoring typo, so flag it either way.
                logger.warning(
                    "Duplicate authority pack name %r (dir %s); pack names "
                    "must be unique (case-insensitively) across installed "
                    "packs.",
                    origin,
                    pack_dir,
                )
            try:
                results[origin] = cls.load_all(path=mappings_path, origin=origin)
            except Exception as exc:
                # Per-pack fault isolation, mirroring the registry's in-pack
                # provider import: one broken pack must not abort the converge
                # run for every other installed pack. Deliberately broad — a
                # schema ValueError, a yaml.YAMLError parse failure (NOT a
                # ValueError subclass), an unreadable file, or a DB-level
                # DataError (e.g. an over-length name/prefix) all mean the same
                # thing here: this pack didn't load (load_all's transaction
                # rolled its writes back), report it and continue. (A DIRECT
                # ``load_all(path=...)`` on the same file still raises — the
                # fail-fast path ``load_authority_pack`` relies on.)
                logger.error(
                    "Skipping authority pack %r mappings (%s): %s: %s",
                    origin,
                    mappings_path,
                    type(exc).__name__,
                    exc,
                )
                results[origin] = {"error": f"{type(exc).__name__}: {exc}"}
        # A pack the iterator classified as broken (unparsable pack.yaml, or a
        # declared mappings file missing on disk) never reaches the loop above;
        # surface it in the report instead of leaving it log-only.
        for pack_dir, message in pack_errors:
            _report_pack_error(results, pack_dir, message)
        return results


def _report_pack_error(results: dict, pack_dir: Path, message: str) -> None:
    """Record a per-pack failure in ``load_installed``'s report without ever
    displacing (or being hidden behind) another entry: keyed by the pack's
    directory name, falling back to its full path when that key is already
    taken (e.g. a directory literally named "core" — the reserved origin keys
    the real core summary)."""
    key = pack_dir.name if pack_dir.name not in results else str(pack_dir)
    results.setdefault(key, {"error": message})
