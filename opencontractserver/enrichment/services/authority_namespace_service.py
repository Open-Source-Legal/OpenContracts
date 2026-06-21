"""Service layer for the runtime AuthorityNamespace management surface.

``AuthorityNamespace`` is the registry of bodies of law (one row per
``canonical_key`` prefix, e.g. ``usc-15`` / ``dgcl``) whose ``aliases`` drive
Tier-1 citation extraction. Until now it had no runtime management surface at
all — editable only by hand-editing ``authority_mappings.yaml`` + re-running the
loader, or by seed migrations. This service is its missing peer to
``AuthorityKeyEquivalenceService``: superuser-gated create / update / delete /
alias-edit plus the read / stats / detail queries the Authority Console uses.

Two invariants make runtime editing safe:

- Rows created/edited here are stamped ``source="manual"``; the loader
  (``AuthorityMappingLoader.load_namespaces``) skips ``manual`` rows, so a
  re-load never clobbers a curator's edits (mirrors the equivalence partition).
- ``AuthorityNamespace.save()`` enforces the ``is_global`` ⊕ ``authority_corpus``
  mutual exclusion; ``create`` / ``update`` surface its ``ValidationError`` as a
  clean operation error rather than a 500.

The cross-model ``detail`` projection joins everything about one body of law by
STRING KEY (there are no FKs between the authority models): equivalences and
references are matched on the ``"<prefix>:"`` key prefix — colon-anchored so
``usc-1`` never swallows ``usc-15`` — and frontier rows on ``authority=prefix``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import Count, Q, QuerySet

from opencontractserver.annotations.models import (
    AuthorityFrontier,
    AuthorityKeyEquivalence,
    AuthorityNamespace,
    CorpusReference,
)
from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.data import mappings as _mappings
from opencontractserver.enrichment.services.authority_permissions import (
    DENIED,
    is_authority_admin,
)
from opencontractserver.shared.services.base import BaseService

MANUAL = "manual"

# How many joined rows the detail projection returns per section (the registry
# is small, but a heavily-cited authority can have many references/frontier
# rows — cap so one body of law never returns an unbounded payload).
DETAIL_EQUIVALENCE_CAP = 250
DETAIL_FRONTIER_CAP = 250
DETAIL_REFERENCE_SAMPLE_CAP = 50


@dataclass
class NamespaceResult:
    """Outcome of a CRUD operation: ``ok`` + an ``error`` string or the ``obj``."""

    ok: bool
    error: str = ""
    obj: AuthorityNamespace | None = None


@dataclass
class AuthorityDetail:
    """The string-joined projection of everything about one body of law."""

    namespace: AuthorityNamespace
    equivalences_out: list[AuthorityKeyEquivalence] = field(default_factory=list)
    equivalences_in: list[AuthorityKeyEquivalence] = field(default_factory=list)
    frontier_rows: list[AuthorityFrontier] = field(default_factory=list)
    frontier_state_counts: list[dict] = field(default_factory=list)
    reference_total: int = 0
    reference_status_counts: list[dict] = field(default_factory=list)
    reference_sample: list[CorpusReference] = field(default_factory=list)
    effective_provider: str | None = None


class AuthorityNamespaceService(BaseService):
    """Superuser CRUD + read for the AuthorityNamespace registry."""

    # ----- gating / read ------------------------------------------------ #

    @classmethod
    def visible(cls, user) -> QuerySet:
        """Superuser-only queryset (empty otherwise) — backs the node gate."""
        if not is_authority_admin(user):
            return AuthorityNamespace.objects.none()
        return AuthorityNamespace.objects.all()

    @classmethod
    def stats(cls, user, *, search: str | None = None) -> dict:
        """Faceted row counts for the registry panel's summary chips.

        Honours ``search`` but NOT the facet selects, so the chips always show
        the full breakdown for the current search (mirrors
        ``AuthorityKeyEquivalenceService.stats``). Empty for non-admins. Returns
        ``{total_count, by_jurisdiction, by_authority_type, by_scope}``.
        """
        if not is_authority_admin(user):
            return {
                "total_count": 0,
                "by_jurisdiction": [],
                "by_authority_type": [],
                "by_scope": [],
            }
        qs = AuthorityNamespace.objects.all()
        if search:
            qs = cls._apply_search(qs, search)

        def _facet(field_name: str) -> list[dict]:
            # Generic {value, count} shape so one GraphQL facet type serves all
            # three breakdowns. A null jurisdiction/authority_type collapses to ""
            # so the chip has a stable, comparable key.
            return [
                {"value": r[field_name] or "", "count": r["count"]}
                for r in qs.values(field_name)
                .annotate(count=Count("id"))
                .order_by("-count")
            ]

        by_scope = [
            {"value": ("global" if r["is_global"] else "corpus"), "count": r["count"]}
            for r in qs.values("is_global")
            .annotate(count=Count("id"))
            .order_by("-count")
        ]
        return {
            "total_count": qs.count(),
            "by_jurisdiction": _facet("jurisdiction"),
            "by_authority_type": _facet("authority_type"),
            "by_scope": by_scope,
        }

    @classmethod
    def detail(cls, user, prefix: str) -> AuthorityDetail | None:
        """Assemble the cross-model projection for one body of law (string joins).

        ``None`` for non-admins or an unknown prefix (opaque — no existence
        oracle). All joins are colon-anchored on ``"<prefix>:"`` /
        ``authority=prefix`` so ``usc-1`` never matches ``usc-15``.
        """
        if not is_authority_admin(user):
            return None
        ns = AuthorityNamespace.objects.filter(prefix=prefix).first()
        if ns is None:
            return None

        key_prefix = f"{prefix}:"
        eq_out = list(
            AuthorityKeyEquivalence.objects.filter(from_key__startswith=key_prefix)
            .select_related("created_by")
            .order_by("from_key", "to_key")[:DETAIL_EQUIVALENCE_CAP]
        )
        eq_in = list(
            AuthorityKeyEquivalence.objects.filter(to_key__startswith=key_prefix)
            .select_related("created_by")
            .order_by("to_key", "from_key")[:DETAIL_EQUIVALENCE_CAP]
        )

        frontier_qs = AuthorityFrontier.objects.filter(authority=prefix)
        frontier_rows = list(
            frontier_qs.select_related("ingested_document").order_by(
                "-mention_count", "discovery_state"
            )[:DETAIL_FRONTIER_CAP]
        )
        frontier_state_counts = [
            {"state": r["discovery_state"], "count": r["count"]}
            for r in frontier_qs.values("discovery_state")
            .annotate(count=Count("id"))
            .order_by("-count")
        ]

        ref_qs = CorpusReference.objects.filter(canonical_key__startswith=key_prefix)
        reference_status_counts = [
            {"status": r["resolution_status"], "count": r["count"]}
            for r in ref_qs.values("resolution_status")
            .annotate(count=Count("id"))
            .order_by("-count")
        ]
        reference_total = sum(r["count"] for r in reference_status_counts)
        reference_sample = list(
            ref_qs.select_related(
                "corpus", "target_document", "created_by_analysis"
            ).order_by("-modified")[:DETAIL_REFERENCE_SAMPLE_CAP]
        )

        return AuthorityDetail(
            namespace=ns,
            equivalences_out=eq_out,
            equivalences_in=eq_in,
            frontier_rows=frontier_rows,
            frontier_state_counts=frontier_state_counts,
            reference_total=reference_total,
            reference_status_counts=reference_status_counts,
            reference_sample=reference_sample,
            effective_provider=cls._effective_provider(prefix),
        )

    # ----- write -------------------------------------------------------- #

    @classmethod
    def create(
        cls,
        user,
        *,
        prefix: str,
        display_name: str,
        jurisdiction: str | None = None,
        authority_type: str | None = None,
        aliases: list[str] | None = None,
        is_global: bool = True,
        authority_corpus_id: int | None = None,
        provider: str | None = None,
        source_root_url: str | None = None,
        license: str | None = None,
    ) -> NamespaceResult:
        if not is_authority_admin(user):
            return NamespaceResult(False, DENIED)
        prefix = (prefix or "").strip()
        display_name = (display_name or "").strip()
        err = cls._validate(
            prefix=prefix,
            display_name=display_name,
            jurisdiction=jurisdiction,
            authority_type=authority_type,
        )
        if err:
            return NamespaceResult(False, err)
        if AuthorityNamespace.objects.filter(prefix=prefix).exists():
            return NamespaceResult(
                False, f"An authority with prefix '{prefix}' already exists."
            )
        ns = AuthorityNamespace(
            prefix=prefix,
            display_name=display_name,
            jurisdiction=cls._clean(jurisdiction),
            authority_type=cls._clean(authority_type),
            aliases=cls._normalize_aliases(aliases),
            is_global=bool(is_global) and not authority_corpus_id,
            authority_corpus_id=authority_corpus_id,
            provider=cls._clean(provider),
            source_root_url=cls._clean(source_root_url),
            license=cls._clean(license),
            source=MANUAL,
            created_by=user,
        )
        try:
            ns.save()
        except (ValidationError, IntegrityError) as exc:
            return NamespaceResult(False, cls._error_text(exc))
        cls.log_action("Created", ns, user, source=MANUAL)
        return NamespaceResult(True, obj=ns)

    @classmethod
    def update(cls, user, *, pk, **partial: Any) -> NamespaceResult:
        """Edit a namespace. Stamps ``source="manual"`` so the loader leaves it
        alone thereafter (a curator override wins over the shipped baseline)."""
        if not is_authority_admin(user):
            return NamespaceResult(False, DENIED)
        ns = AuthorityNamespace.objects.filter(pk=pk).first()
        if ns is None:
            return NamespaceResult(False, DENIED)

        # Only mutate the fields the caller actually supplied (None == "leave").
        if "display_name" in partial and partial["display_name"] is not None:
            ns.display_name = partial["display_name"].strip()
        if "jurisdiction" in partial:
            ns.jurisdiction = cls._clean(partial["jurisdiction"])
        if "authority_type" in partial:
            ns.authority_type = cls._clean(partial["authority_type"])
        if "aliases" in partial and partial["aliases"] is not None:
            ns.aliases = cls._normalize_aliases(partial["aliases"])
        if "provider" in partial:
            ns.provider = cls._clean(partial["provider"])
        if "source_root_url" in partial:
            ns.source_root_url = cls._clean(partial["source_root_url"])
        if "license" in partial:
            ns.license = cls._clean(partial["license"])
        if "authority_corpus_id" in partial:
            ns.authority_corpus_id = partial["authority_corpus_id"]
        if "is_global" in partial and partial["is_global"] is not None:
            ns.is_global = bool(partial["is_global"])
        # A corpus link forces non-global (mirrors create); save() also enforces.
        if ns.authority_corpus_id:
            ns.is_global = False

        err = cls._validate(
            prefix=ns.prefix,
            display_name=ns.display_name,
            jurisdiction=ns.jurisdiction,
            authority_type=ns.authority_type,
        )
        if err:
            return NamespaceResult(False, err)

        ns.source = MANUAL
        if ns.created_by_id is None:
            ns.created_by = user
        try:
            ns.save()
        except (ValidationError, IntegrityError) as exc:
            return NamespaceResult(False, cls._error_text(exc))
        cls.log_action("Updated", ns, user)
        return NamespaceResult(True, obj=ns)

    @classmethod
    def set_aliases(cls, user, *, pk, aliases: list[str]) -> NamespaceResult:
        """The ONE alias writer (lowercase + de-dupe + sort)."""
        return cls.update(user, pk=pk, aliases=aliases)

    @classmethod
    def delete(cls, user, *, pk) -> NamespaceResult:
        """Delete a namespace, guarding against orphaning dependent rows.

        Refuse if the prefix still has equivalences / frontier rows / references
        pointing at it (deleting the namespace would strip the taxonomy that
        drives extraction and leave those rows dangling). The error carries the
        counts so the operator knows what to clear first.
        """
        if not is_authority_admin(user):
            return NamespaceResult(False, DENIED)
        ns = AuthorityNamespace.objects.filter(pk=pk).first()
        if ns is None:
            return NamespaceResult(False, DENIED)
        blockers = cls._dependency_counts(ns.prefix)
        if blockers:
            detail = ", ".join(f"{n} {label}" for label, n in blockers.items())
            return NamespaceResult(
                False,
                f"Cannot delete '{ns.prefix}': it still has {detail}. "
                "Reassign or clear those first.",
            )
        cls.log_action("Deleted", ns, user)
        ns.delete()
        return NamespaceResult(True)

    # ----- helpers ------------------------------------------------------ #

    @staticmethod
    def _clean(value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @staticmethod
    def _apply_search(qs: QuerySet, search: str) -> QuerySet:
        # aliases is a JSON list; icontains over the serialized text is a cheap,
        # index-free substring match good enough for the small registry table.
        return qs.filter(
            Q(prefix__icontains=search)
            | Q(display_name__icontains=search)
            | Q(aliases__icontains=search)
        )

    @staticmethod
    def _normalize_aliases(aliases: list[str] | None) -> list[str]:
        if not aliases:
            return []
        return sorted({a.strip().lower() for a in aliases if a and a.strip()})

    @staticmethod
    def _validate(
        *,
        prefix: str,
        display_name: str,
        jurisdiction: str | None,
        authority_type: str | None,
    ) -> str:
        if not _mappings.is_valid_prefix(prefix):
            return (
                f"Invalid prefix {prefix!r}: expected a lowercase canonical-key "
                "prefix (e.g. 'usc-15', 'dgcl')."
            )
        if not display_name:
            return "display_name is required."
        if authority_type and authority_type.strip():
            if authority_type.strip() not in C.ALL_AUTHORITY_TYPES:
                allowed = ", ".join(C.ALL_AUTHORITY_TYPES)
                return (
                    f"Invalid authority_type {authority_type!r}: expected one of "
                    f"{allowed}."
                )
        return ""

    @staticmethod
    def _dependency_counts(prefix: str) -> dict[str, int]:
        key_prefix = f"{prefix}:"
        counts = {
            "equivalence(s)": (
                AuthorityKeyEquivalence.objects.filter(
                    Q(from_key__startswith=key_prefix)
                    | Q(to_key__startswith=key_prefix)
                ).count()
            ),
            "frontier row(s)": AuthorityFrontier.objects.filter(
                authority=prefix
            ).count(),
            "reference(s)": CorpusReference.objects.filter(
                canonical_key__startswith=key_prefix
            ).count(),
        }
        return {label: n for label, n in counts.items() if n}

    @staticmethod
    def _effective_provider(prefix: str) -> str | None:
        """Registry class-name that would actually handle this body of law.

        Reuses the canonical provider-selection path (the same one the frontier's
        ``predicted_provider`` uses) on a representative section key, so the
        console can contrast it with the namespace's *advisory* ``provider``
        column. Best-effort: returns ``None`` if no provider can handle it.
        """
        try:
            from opencontractserver.enrichment.services.authority_discovery_service import (  # noqa: E501
                AuthorityDiscoveryService,
            )

            return AuthorityDiscoveryService._provider_for(f"{prefix}:1")[0]
        except Exception:  # noqa: BLE001 — advisory display, never fail the detail
            return None

    @staticmethod
    def _error_text(exc: Exception) -> str:
        messages = getattr(exc, "messages", None)
        if messages:
            return " ".join(messages)
        return str(exc)
