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

Grant-shape note: a *any-permission-row* match on the guardian tables
(rather than a ``read_*`` codename filter) is deliberately preserved from
the original inline implementations — holders of any explicit grant on the
source object clear the privacy gate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from django.db.models import QuerySet


def visible_analyses_for(user: Any) -> "QuerySet":
    """Analyses whose privacy-rooted annotations/relationships ``user`` may see.

    Returns a lazy queryset (safe to embed as a subquery via
    ``__in=...``): public analyses for anonymous users; public | own |
    user-granted | group-granted analyses for authenticated users.
    """
    from django.db.models import Q

    from opencontractserver.analyzer.models import (
        Analysis,
        AnalysisGroupObjectPermission,
        AnalysisUserObjectPermission,
    )

    if user is None or getattr(user, "is_anonymous", True):
        return Analysis.objects.filter(is_public=True)

    visible = Analysis.objects.filter(Q(is_public=True) | Q(creator=user))

    user_grant_ids = AnalysisUserObjectPermission.objects.filter(user=user).values_list(
        "content_object_id", flat=True
    )
    group_grant_ids = AnalysisGroupObjectPermission.objects.filter(
        group_id__in=user.groups.values_list("id", flat=True)
    ).values_list("content_object_id", flat=True)

    return (
        visible
        | Analysis.objects.filter(id__in=user_grant_ids)
        | Analysis.objects.filter(id__in=group_grant_ids)
    )


def visible_extracts_for(user: Any) -> "QuerySet":
    """Extracts whose privacy-rooted annotations/relationships ``user`` may see.

    Returns a lazy queryset (safe to embed as a subquery via
    ``__in=...``): nothing for anonymous users (extracts are never
    anonymous-visible); own | user-granted | group-granted extracts for
    authenticated users. ``is_public`` is intentionally absent — extract
    privacy has never keyed off the flag and no user-facing flow sets it.
    """
    from django.db.models import Q

    from opencontractserver.extracts.models import (
        Extract,
        ExtractGroupObjectPermission,
        ExtractUserObjectPermission,
    )

    if user is None or getattr(user, "is_anonymous", True):
        return Extract.objects.none()

    visible = Extract.objects.filter(Q(creator=user))

    user_grant_ids = ExtractUserObjectPermission.objects.filter(user=user).values_list(
        "content_object_id", flat=True
    )
    group_grant_ids = ExtractGroupObjectPermission.objects.filter(
        group_id__in=user.groups.values_list("id", flat=True)
    ).values_list("content_object_id", flat=True)

    return (
        visible
        | Extract.objects.filter(id__in=user_grant_ids)
        | Extract.objects.filter(id__in=group_grant_ids)
    )
