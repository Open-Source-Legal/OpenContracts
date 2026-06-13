"""Shared visibility builders for annotation/relationship privacy sources.

The ``created_by_analysis`` / ``created_by_extract`` privacy gates need
"which Analyses / Extracts can this user see" expressed as lazy querysets
that compile to SQL subqueries. Four call sites previously built these
inline (``AnnotationQuerySet.visible_to_user``,
``AnnotationService.get_document_annotations``,
``AnnotationService.get_corpus_annotations``, and
``RelationshipService.get_document_relationships``) and every one of them
omitted GROUP-level guardian grants — drifting from ``user_can``'s privacy
recursion, which honours group grants by default
(``include_group_permissions=True``). A user whose analysis READ came via a
group passed ``user_can`` but never saw the private annotations in list
queries (2026-06 permissioning audit; parity invariant pinned in
``opencontractserver/tests/permissioning/test_authorization_invariants.py``).

Anonymous semantics (agreed in the same audit):

- **analyses** — public analyses only.
- **extracts** — NONE. Extracts are never visible to anonymous users, at
  any layer (see ``ExtractManager`` and ``ExtractService``).

Grant-shape note: the gates match guardian rows carrying the ``read_*``
codename specifically — NOT any-permission rows. The original inline
implementations matched any grant, which was itself a parity drift:
``user_can``'s privacy recursion resolves READ through
``Analysis.objects.user_can`` / ``Extract.objects.user_can``, whose
guardian branch checks the read codename — so an ``update_analysis``-only
grantee cleared the old list gates while failing ``user_can(READ)``
(2026-06 audit follow-up; pinned by
``test_update_only_source_grant_does_not_unlock_lists``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db.models import Q

if TYPE_CHECKING:
    from django.db.models import QuerySet


def apply_source_privacy_gate(qs: QuerySet, user: Any) -> QuerySet:
    """Exclude non-structural rows whose ``created_by_*`` source ``user``
    cannot see — unless ``user`` is the ROW's own creator.

    The single home for the privacy-gate *exclusion* shape (the source
    subqueries live in the two builders below). Works on any queryset of a
    model carrying ``created_by_analysis`` / ``created_by_extract`` /
    ``structural`` / ``creator`` — i.e. ``Annotation`` and
    ``Relationship``. Structural rows always pass (privacy never hides
    structural data); anonymous semantics come from the builders (public
    analyses only, no extracts).

    Creator exemption (2026-06 audit, review round 17): the row's own
    creator passes the gate for AUTHENTICATED users, matching the
    ``Q(creator=user)`` disjunct in ``AnnotationQuerySet.visible_to_user``
    and the creator short-circuit in ``RelationshipManager.user_can`` /
    ``visible_to_user``. Without it the service listings were the odd
    surface out: a relationship's creator who lost source access kept
    READ on both manager surfaces yet vanished from the document view.
    Annotation filter/check parity for this same source-privacy exemption
    is pinned by
    ``test_annotation_creator_source_private_row_has_filter_check_parity``.
    The exemption is deliberately NOT built for anonymous users —
    ``Q(creator=<anonymous>)`` is not a valid lookup, and anonymous callers
    can never be a row's creator.

    NOTE: ``AnnotationQuerySet.visible_to_user`` composes the SAME
    semantics as a positive ``Q`` filter (structural | creator |
    no-source | source-visible) purely for single-WHERE composition with
    its doc/corpus EXISTS predicates — keep the two shapes in sync when
    changing either (pinned by
    ``test_gate_matches_queryset_visibility_for_non_creator``).
    """
    if user is not None and not getattr(user, "is_anonymous", True):
        creator_exempt = Q(creator=user)
    else:
        # Always-false predicate: anonymous callers get no exemption and
        # ``Q(creator=AnonymousUser())`` would not be a valid lookup. Primary
        # keys are non-null, so this excludes every row without relying on the
        # database-specific SQL Django emits for ``pk__in=[]``.
        creator_exempt = Q(pk__isnull=True)

    return qs.exclude(
        Q(created_by_analysis__isnull=False)
        & Q(structural=False)
        & ~creator_exempt
        & ~Q(created_by_analysis__in=visible_analyses_for(user))
    ).exclude(
        Q(created_by_extract__isnull=False)
        & Q(structural=False)
        & ~creator_exempt
        & ~Q(created_by_extract__in=visible_extracts_for(user))
    )


def visible_analyses_for(user: Any) -> QuerySet:
    """Analyses whose privacy-rooted annotations/relationships ``user`` may see.

    Returns a lazy queryset (safe to embed as a subquery via
    ``__in=...``): public analyses for anonymous users; public | own |
    user-granted | group-granted analyses for authenticated users.
    """
    from opencontractserver.analyzer.models import (
        Analysis,
        AnalysisGroupObjectPermission,
        AnalysisUserObjectPermission,
    )

    if user is None or getattr(user, "is_anonymous", True):
        return Analysis.objects.filter(is_public=True)

    user_grant_ids = AnalysisUserObjectPermission.objects.filter(
        user=user, permission__codename="read_analysis"
    ).values_list("content_object_id", flat=True)
    group_grant_ids = AnalysisGroupObjectPermission.objects.filter(
        group_id__in=user.groups.values_list("id", flat=True),
        permission__codename="read_analysis",
    ).values_list("content_object_id", flat=True)

    # Single filter with OR'd Q objects — one WHERE clause with two
    # uncorrelated id-subqueries. (Queryset ``|`` would OR-merge to the
    # same SQL here; the single-filter shape just reads more directly.)
    return Analysis.objects.filter(
        Q(is_public=True)
        | Q(creator=user)
        | Q(id__in=user_grant_ids)
        | Q(id__in=group_grant_ids)
    )


def visible_extracts_for(user: Any) -> QuerySet:
    """Extracts whose privacy-rooted annotations/relationships ``user`` may see.

    Returns a lazy queryset (safe to embed as a subquery via
    ``__in=...``): nothing for anonymous users (extracts are never
    anonymous-visible — ``ExtractManager`` denies them on both surfaces, so
    the flag is irrelevant on that branch); public | own | user-granted |
    group-granted extracts for authenticated users.

    ``is_public`` note: the original inline implementations omitted the
    flag for extracts (while including it for analyses). That was a latent
    filter/check parity violation, not a design choice — ``user_can``'s
    privacy recursion delegates to ``Extract.objects.user_can``, which
    grants READ on ``is_public`` rows for authenticated users, so an
    extract-rooted row on a public extract passed ``user_can(READ)`` while
    never appearing in lists. Including the flag here (authenticated branch
    only) restores parity and mirrors ``visible_analyses_for``. No
    user-facing flow currently sets ``Extract.is_public``, so this has no
    practical exposure today; pinned by
    ``test_public_extract_source_passes_both_surfaces``.

    Surface note: this gate is deliberately NOT corpus-gated. The
    extract-OBJECT listing (``ExtractService.get_visible_extracts``) is the
    hybrid surface — extract permission AND corpus READ — while this gate
    mirrors the manager-level ``Extract.objects.user_can`` that ``user_can``'s
    privacy recursion consults (no corpus AND). The row being unlocked still
    requires doc+corpus READ of ITS OWN corpus through the enclosing query,
    so corpus gating is not lost — it just applies to the row's corpus, not
    the source's.
    """
    from opencontractserver.extracts.models import (
        Extract,
        ExtractGroupObjectPermission,
        ExtractUserObjectPermission,
    )

    if user is None or getattr(user, "is_anonymous", True):
        return Extract.objects.none()

    user_grant_ids = ExtractUserObjectPermission.objects.filter(
        user=user, permission__codename="read_extract"
    ).values_list("content_object_id", flat=True)
    group_grant_ids = ExtractGroupObjectPermission.objects.filter(
        group_id__in=user.groups.values_list("id", flat=True),
        permission__codename="read_extract",
    ).values_list("content_object_id", flat=True)

    # Same single-filter shape as ``visible_analyses_for`` — one WHERE
    # clause with two uncorrelated id-subqueries.
    return Extract.objects.filter(
        Q(is_public=True)
        | Q(creator=user)
        | Q(id__in=user_grant_ids)
        | Q(id__in=group_grant_ids)
    )
