"""Service layer for the runtime authority-mappings CRUD surface.

Superuser-gated create / update / delete of ``AuthorityKeyEquivalence`` rows
(forced ``source="manual"``, capturing ``created_by`` + ``note``), plus the
read / stats queries the admin panel and GraphQL connection use.

Mirrors ``AuthorityFrontierService``: the mappings are global system data with
no per-object permissions, so every method is empty / denied for non-superusers
(same gate as ``RunAuthorityDiscoveryMutation``). Loader/importer-owned rows
(``baseline`` / ``popular_name`` / ``uslm``) are read-only here — only ``manual``
rows are editable/deletable, so a reseed can never fight a curator and a curator
can never silently shadow shipped data.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Count, Q, QuerySet

from opencontractserver.annotations.models import AuthorityKeyEquivalence
from opencontractserver.enrichment.data import mappings as _mappings
from opencontractserver.enrichment.services.authority_permissions import (
    DENIED,
    is_authority_admin,
)
from opencontractserver.shared.services.base import BaseService

# ``DENIED`` is the shared opaque denial (re-exported here for existing importers
# of ``authority_mapping_service.DENIED``).
MANUAL = "manual"


@dataclass
class MappingResult:
    """Outcome of a CRUD operation: ``ok`` + an ``error`` string or the ``obj``."""

    ok: bool
    error: str = ""
    obj: AuthorityKeyEquivalence | None = None


class AuthorityKeyEquivalenceService(BaseService):
    """Superuser CRUD + read for runtime authority key-equivalence overrides."""

    @staticmethod
    def is_superuser(user) -> bool:
        # Thin delegate to the single authority-admin gate (kept for the existing
        # internal callers below); widen the role in ``authority_permissions``.
        return is_authority_admin(user)

    @classmethod
    def visible(cls, user) -> QuerySet:
        """Superuser-only queryset (empty otherwise) — backs the GraphQL node gate."""
        if not cls.is_superuser(user):
            return AuthorityKeyEquivalence.objects.none()
        return AuthorityKeyEquivalence.objects.all()

    @classmethod
    def stats(cls, user, *, search: str | None = None) -> dict:
        """Per-``source`` row counts for the admin panel's summary chips.

        Honours ``search`` but NOT a source filter, so the chips always show the
        full source breakdown for the current search. Empty for non-superusers.
        Returns ``{"total_count": int, "by_source": [{"source", "count"}, ...]}``.
        """
        if not cls.is_superuser(user):
            return {"total_count": 0, "by_source": []}
        qs = AuthorityKeyEquivalence.objects.all()
        if search:
            qs = qs.filter(Q(from_key__icontains=search) | Q(to_key__icontains=search))
        by_source = [
            {"source": r["source"], "count": r["count"]}
            for r in qs.values("source").annotate(count=Count("id")).order_by("-count")
        ]
        return {
            "total_count": sum(r["count"] for r in by_source),
            "by_source": by_source,
        }

    @classmethod
    def create(
        cls, user, *, from_key: str, to_key: str, note: str | None = None
    ) -> MappingResult:
        if not cls.is_superuser(user):
            return MappingResult(False, DENIED)
        from_key = (from_key or "").strip()
        to_key = (to_key or "").strip()
        err = cls._validate_keys(from_key, to_key)
        if err:
            return MappingResult(False, err)
        if AuthorityKeyEquivalence.objects.filter(
            from_key=from_key, to_key=to_key
        ).exists():
            return MappingResult(
                False, f"A mapping {from_key} → {to_key} already exists."
            )
        obj = AuthorityKeyEquivalence.objects.create(
            from_key=from_key,
            to_key=to_key,
            source=MANUAL,
            confidence=1.0,
            note=((note or "").strip() or None),
            created_by=user,
        )
        cls.log_action("Created", obj, user, source=MANUAL)
        return MappingResult(True, obj=obj)

    @classmethod
    def update(
        cls,
        user,
        *,
        pk,
        from_key: str | None = None,
        to_key: str | None = None,
        note: str | None = None,
    ) -> MappingResult:
        if not cls.is_superuser(user):
            return MappingResult(False, DENIED)
        obj = AuthorityKeyEquivalence.objects.filter(pk=pk).first()
        if obj is None:
            return MappingResult(False, DENIED)
        if obj.source != MANUAL:
            return MappingResult(
                False,
                f"Only manual mappings are editable; '{obj.source}' rows are "
                "managed by the loader/importers.",
            )
        new_from = (from_key if from_key is not None else obj.from_key).strip()
        new_to = (to_key if to_key is not None else obj.to_key).strip()
        err = cls._validate_keys(new_from, new_to)
        if err:
            return MappingResult(False, err)
        if (new_from, new_to) != (obj.from_key, obj.to_key) and (
            AuthorityKeyEquivalence.objects.filter(from_key=new_from, to_key=new_to)
            .exclude(pk=pk)
            .exists()
        ):
            return MappingResult(
                False, f"A mapping {new_from} → {new_to} already exists."
            )
        obj.from_key = new_from
        obj.to_key = new_to
        if note is not None:
            obj.note = note.strip() or None
        obj.save(update_fields=["from_key", "to_key", "note", "modified"])
        cls.log_action("Updated", obj, user)
        return MappingResult(True, obj=obj)

    @classmethod
    def delete(cls, user, *, pk) -> MappingResult:
        if not cls.is_superuser(user):
            return MappingResult(False, DENIED)
        obj = AuthorityKeyEquivalence.objects.filter(pk=pk).first()
        if obj is None:
            return MappingResult(False, DENIED)
        if obj.source != MANUAL:
            return MappingResult(
                False,
                f"Only manual mappings can be deleted; '{obj.source}' rows are "
                "managed by the loader/importers.",
            )
        cls.log_action("Deleted", obj, user)
        obj.delete()
        return MappingResult(True)

    @staticmethod
    def _validate_keys(from_key: str, to_key: str) -> str:
        """Return an error string on a malformed pair, else ``""``."""
        for label, key in (("from_key", from_key), ("to_key", to_key)):
            if not _mappings.is_valid_canonical_key(key):
                return (
                    f"Invalid {label} {key!r}: expected '<prefix>:<section>' "
                    "(e.g. 'irc:401')."
                )
        if from_key == to_key:
            return "from_key and to_key must differ."
        return ""
