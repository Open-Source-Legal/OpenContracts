"""Source-scoped writer for auto-derived authority key equivalences.

Ownership is partitioned by ``source``: the loader owns ``baseline``, humans own
``manual``, and the auto-derivation importers own ``uslm`` (USLM ``<sourceCredit>``
harvest) and ``popular_name`` (OLRC popular-name table import). This writer
enforces that partition — a writer NEVER overwrites a row owned by a *different*
source — so re-running an importer can't clobber a curator's manual fix or the
shipped baseline (and two importers can't fight over the same pair).

Shared by ``USCodeAuthoritySourceProvider`` (uslm) and the popular-name importer
(popular_name) so the ownership rule + key validation live in exactly one place.
"""

from __future__ import annotations

from django.db import transaction

from opencontractserver.annotations.models import AuthorityKeyEquivalence
from opencontractserver.enrichment.data import mappings as _mappings

# Outcome codes returned by :func:`upsert_equivalence`.
CREATED = "created"
UPDATED = "updated"
SKIPPED_INVALID = "skipped_invalid"
SKIPPED_OWNED = "skipped_owned"


def upsert_equivalence(
    *,
    from_key: str,
    to_key: str,
    source: str,
    confidence: float,
    note: str | None = None,
) -> str:
    """Idempotently upsert one equivalence under source-scoped ownership.

    Returns one of ``CREATED`` / ``UPDATED`` / ``SKIPPED_INVALID`` /
    ``SKIPPED_OWNED``:

    - ``SKIPPED_INVALID`` — a malformed canonical key or a self-equivalence
      (kept silent-failure-free: the caller tallies it, never crashes).
    - ``SKIPPED_OWNED`` — the pair already exists under a *different* source, so
      this writer leaves it untouched (ownership partition).
    """
    from_key = (from_key or "").strip()
    to_key = (to_key or "").strip()
    if (
        not _mappings.is_valid_canonical_key(from_key)
        or not _mappings.is_valid_canonical_key(to_key)
        or from_key == to_key
    ):
        return SKIPPED_INVALID

    # Atomic upsert under source-scoped ownership. A bare filter-then-create is
    # racy: two concurrent USLM fetches during a crawl could both read
    # ``existing=None``, both pass the ownership check, and the second
    # ``update_or_create`` would then flip ``source`` on the row the first just
    # created — clobbering ownership (the unique constraint only catches strict
    # duplicates, not source-ownership violations). ``select_for_update`` +
    # ``get_or_create`` inside ``transaction.atomic`` closes that window:
    # ``get_or_create`` resolves the insert race via the unique constraint, and
    # the row lock serialises the ownership decision against concurrent writers.
    with transaction.atomic():
        (
            obj,
            created,
        ) = AuthorityKeyEquivalence.objects.select_for_update().get_or_create(
            from_key=from_key,
            to_key=to_key,
            defaults={
                "source": source,
                "confidence": confidence,
                "note": (note or None),
            },
        )
        if created:
            return CREATED
        if obj.source != source:
            return SKIPPED_OWNED
        # Same source: refresh the stored values (YAML/importer is authoritative).
        AuthorityKeyEquivalence.objects.filter(pk=obj.pk).update(
            source=source,
            confidence=confidence,
            note=(note or None),
        )
        return UPDATED
