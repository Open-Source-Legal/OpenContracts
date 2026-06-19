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

    existing = AuthorityKeyEquivalence.objects.filter(
        from_key=from_key, to_key=to_key
    ).first()
    if existing is not None and existing.source != source:
        return SKIPPED_OWNED

    _, created = AuthorityKeyEquivalence.objects.update_or_create(
        from_key=from_key,
        to_key=to_key,
        defaults={
            "source": source,
            "confidence": confidence,
            "note": (note or None),
        },
    )
    return CREATED if created else UPDATED
