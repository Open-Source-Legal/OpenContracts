"""
Subtree group materialisation for structural annotations.

After a parser has imported structural annotations and any explicit
relationships, this utility walks the hierarchy tree formed by:

  (a) ``Annotation.parent`` self-FK edges, and
  (b) parent-style structural ``Relationship`` rows (label
      ``OC_PARENT_CHILD_LABEL_NAME``),

and materialises one ``Relationship`` row per non-leaf node whose
``source_annotations`` is the ancestor and ``target_annotations`` is the
ancestor's full transitive descendant set. This lets retrieval surface
the larger "block" of an annotation hit with a single join instead of a
recursive CTE per result.

Notes
-----
* Operates on structural annotations attached to the document. The rows
  created here are themselves structural and are picked up by
  ``BaseParser._create_structural_annotation_set`` and migrated onto the
  document's ``StructuralAnnotationSet`` automatically on first parse.
* Idempotent: prior ``OC_SUBTREE_GROUP`` rows for the document are
  deleted before fresh rows are created — regardless of whether they
  live under ``document`` (first parse) or under the document's
  ``StructuralAnnotationSet`` (re-parse), so re-parses converge.
* Re-parses: when a document already has a ``StructuralAnnotationSet``,
  ``BaseParser._create_structural_annotation_set`` returns early without
  re-running the migration. To avoid orphaned ``document``-scoped rows
  in that scenario, freshly created subtree-group ``Relationship`` rows
  are migrated to the existing structural set here, in step 7.
* Guardrails: subtrees larger than ``SUBTREE_GROUP_MAX_DESCENDANTS`` are
  skipped; the walker prunes branches deeper than
  ``SUBTREE_GROUP_MAX_DEPTH`` and detects cycles defensively.
* The built-in ``OC_SUBTREE_GROUP`` label is system-wide (resolved by
  ``(text, label_type, analyzer)`` ignoring creator) to avoid silently
  proliferating per-user duplicates across multi-user installations.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import TYPE_CHECKING

from django.db import IntegrityError, transaction
from django.db.models import Q

from opencontractserver.annotations.models import (
    RELATIONSHIP_LABEL,
    Annotation,
    AnnotationLabel,
    Relationship,
)
from opencontractserver.constants.annotations import (
    OC_PARENT_CHILD_LABEL_NAME,
    OC_SUBTREE_GROUP_LABEL_NAME,
    SUBTREE_GROUP_MAX_DEPTH,
    SUBTREE_GROUP_MAX_DESCENDANTS,
    SUBTREE_GROUP_PRUNED_SAMPLE_CAP,
)

if TYPE_CHECKING:
    from opencontractserver.documents.models import Document

logger = logging.getLogger(__name__)


def build_subtree_groups_for_document(
    document: Document,
    user_id: int,
    *,
    max_descendants: int = SUBTREE_GROUP_MAX_DESCENDANTS,
    max_depth: int = SUBTREE_GROUP_MAX_DEPTH,
) -> int:
    """Materialise OC_SUBTREE_GROUP relationships for a document.

    Args:
        document: Document whose structural annotations should be grouped.
        user_id: ID of the user credited as the creator of the resulting rows.
        max_descendants: Skip groups whose descendant set exceeds this size.
        max_depth: Prune branches deeper than this; defends against cycles
            or pathological trees.

    Returns:
        Number of OC_SUBTREE_GROUP relationships created on this run.
    """
    # ------------------------------------------------------------------ #
    # 1. Pull every structural annotation on the document, regardless of
    #    whether it is still scoped to ``document`` (first parse) or has
    #    already been migrated to a ``StructuralAnnotationSet`` (re-parse).
    # ------------------------------------------------------------------ #
    structural_set_id = document.structural_annotation_set_id
    # Cover both first-parse (rows still scoped to ``document``) and re-parse
    # (rows already migrated to the document's ``StructuralAnnotationSet``,
    # at which point ``annot.document`` is set to ``None`` by the parser —
    # see ``BaseParser._create_structural_annotation_set``). Built as a single
    # ``Q``-OR rather than ``qs1 | qs2`` so the WHERE clause is explicit and
    # matches the idempotency-delete pattern below. ``document=`` is
    # intentionally NOT duplicated onto the structural_set branch: migrated
    # rows have ``document=None`` and would never match.
    annotation_filter = Q(
        document=document, structural=True, structural_set__isnull=True
    )
    if structural_set_id is not None:
        annotation_filter |= Q(structural=True, structural_set_id=structural_set_id)
    annotation_qs = Annotation.objects.filter(annotation_filter)

    parent_pairs = list(annotation_qs.values_list("id", "parent_id"))
    if not parent_pairs:
        return 0

    structural_pks: set[int] = {pk for pk, _ in parent_pairs}
    parent_map: dict[int, int | None] = dict(parent_pairs)

    # ------------------------------------------------------------------ #
    # 2. Build the unified parent -> children adjacency.
    # ------------------------------------------------------------------ #
    children: dict[int, list[int]] = defaultdict(list)
    seen_edges: set[tuple[int, int]] = set()

    for child_id, parent_id in parent_map.items():
        if parent_id is None or parent_id not in structural_pks:
            continue
        edge = (parent_id, child_id)
        if edge in seen_edges:
            continue
        seen_edges.add(edge)
        children[parent_id].append(child_id)

    # Future-proofing: also consume any parent-style structural
    # Relationship rows already on the document or its structural set.
    # Currently no parser emits these, but analyzers may, and the cost
    # is negligible. Same ``Q``-OR rationale (and same reason ``document=``
    # is omitted on the structural_set branch — migrated rows have
    # ``rel.document=None``) as the annotation queryset above.
    rels_filter = Q(
        document=document,
        structural=True,
        structural_set__isnull=True,
        relationship_label__text=OC_PARENT_CHILD_LABEL_NAME,
    )
    if structural_set_id is not None:
        rels_filter |= Q(
            structural=True,
            structural_set_id=structural_set_id,
            relationship_label__text=OC_PARENT_CHILD_LABEL_NAME,
        )
    rels_qs = Relationship.objects.filter(rels_filter).prefetch_related(
        "source_annotations", "target_annotations"
    )
    for rel in rels_qs:
        source_ids = [a.id for a in rel.source_annotations.all()]
        target_ids = [a.id for a in rel.target_annotations.all()]
        for src in source_ids:
            if src not in structural_pks:
                continue
            for tgt in target_ids:
                if tgt not in structural_pks or tgt == src:
                    continue
                edge = (src, tgt)
                if edge in seen_edges:
                    continue
                seen_edges.add(edge)
                children[src].append(tgt)

    # Sort so row-creation order is deterministic across runs (``structural_pks``
    # is a ``set``); friendlier for audits and snapshot tests, no functional
    # impact since rows are keyed by source annotation. Note: an empty
    # ``non_leaves`` set is not an early-return — we still need to clean up
    # any prior generation of subtree groups (handled by the idempotency
    # delete in step 6) so re-parses that strip non-leaf structure don't
    # leak stale rows.
    non_leaves = sorted(pk for pk in structural_pks if pk in children)

    # ------------------------------------------------------------------ #
    # 3. Post-order DFS with cycle detection and depth cap.
    # ------------------------------------------------------------------ #
    # Sort so traversal order is deterministic across runs (``structural_pks``
    # is a ``set``); mirrors the ``non_leaves`` sort above for the same
    # audit/snapshot-test reason. No functional impact — every root is walked.
    roots = sorted(
        pk
        for pk in structural_pks
        if parent_map.get(pk) is None or parent_map[pk] not in structural_pks
    )
    post_order: list[int] = []
    visited: set[int] = set()
    on_stack: set[int] = set()
    pruned_examples: list[int] = []

    for root in roots:
        # Each frame is (node, child_iter_index, depth_at_node).
        stack: list[list[int]] = [[root, 0, 0]]
        while stack:
            frame = stack[-1]
            node, idx, depth = frame
            if idx == 0:
                if node in on_stack:
                    logger.warning(
                        "Cycle detected at annotation %s on document %s; "
                        "skipping branch",
                        node,
                        document.pk,
                    )
                    stack.pop()
                    continue
                if node in visited:
                    stack.pop()
                    continue
                on_stack.add(node)
            kids = children.get(node, [])
            if idx < len(kids):
                child = kids[idx]
                frame[1] = idx + 1
                if depth + 1 > max_depth:
                    if len(pruned_examples) < SUBTREE_GROUP_PRUNED_SAMPLE_CAP:
                        pruned_examples.append(child)
                    continue
                stack.append([child, 0, depth + 1])
            else:
                on_stack.discard(node)
                visited.add(node)
                post_order.append(node)
                stack.pop()

    if pruned_examples:
        logger.warning(
            "Subtree walker hit max_depth=%s on document %s; deeper branches "
            "were pruned (sample pruned descendants: %s)",
            max_depth,
            document.pk,
            pruned_examples,
        )

    # ------------------------------------------------------------------ #
    # 4. Bottom-up transitive closure (memoised by post-order).
    #
    # Only fold in children the walker actually visited — pruned-for-depth
    # and cycle-skipped nodes never enter ``descendants``, so they (and
    # their subtrees) are excluded from materialised groups. The
    # ``discard(node)`` guard ensures a node is never recorded as its own
    # descendant under any pathological adjacency.
    # ------------------------------------------------------------------ #
    descendants: dict[int, set[int]] = {}
    for node in post_order:
        acc: set[int] = set()
        for child in children.get(node, []):
            if child not in descendants:
                continue
            acc.add(child)
            acc.update(descendants[child])
        acc.discard(node)
        descendants[node] = acc

    # ------------------------------------------------------------------ #
    # 5. Resolve / create the built-in OC_SUBTREE_GROUP label.
    #
    # Resolved BEFORE the delete in step 6 so the idempotency query can
    # filter by ``relationship_label_id`` (indexed FK) instead of JOIN'ing
    # to ``AnnotationLabel`` on ``relationship_label__text``.
    #
    # ``AnnotationLabel.UniqueConstraint`` keys on ``(analyzer, text,
    # creator, label_type)``. Using ``get_or_create`` with
    # ``creator_id=user_id`` in the lookup would silently fork a
    # per-user copy of this system-wide built-in label in multi-user
    # installations. Filter first (ignoring creator), then on miss try
    # to create. If two concurrent first-time parses race, the loser's
    # ``create()`` raises ``IntegrityError`` from the unique constraint;
    # we recover by re-reading the now-existing row instead of failing
    # the parse.
    # ------------------------------------------------------------------ #
    label = (
        AnnotationLabel.objects.filter(
            text=OC_SUBTREE_GROUP_LABEL_NAME,
            label_type=RELATIONSHIP_LABEL,
            analyzer=None,
        )
        .order_by("id")
        .first()
    )
    if label is None:
        try:
            label = AnnotationLabel.objects.create(
                text=OC_SUBTREE_GROUP_LABEL_NAME,
                label_type=RELATIONSHIP_LABEL,
                creator_id=user_id,
                analyzer=None,
                description="Materialised subtree of structural annotations",
                color="gray",
                icon="sitemap",
                read_only=True,
            )
        except IntegrityError:
            label = (
                AnnotationLabel.objects.filter(
                    text=OC_SUBTREE_GROUP_LABEL_NAME,
                    label_type=RELATIONSHIP_LABEL,
                    analyzer=None,
                )
                .order_by("id")
                .first()
            )
            if label is None:
                # Constraint fired but the row is still not visible — re-raise.
                raise

    # ------------------------------------------------------------------ #
    # 6. Atomic idempotency: drop any prior OC_SUBTREE_GROUP rows for this
    #    document and write the fresh generation in a single transaction.
    #    Without the atomic wrapper, a failure mid-create would leave the
    #    document with the deletion already committed and no replacement
    #    rows. Cover BOTH scoping cases: rows still on ``document`` (first
    #    parse) and rows already migrated onto the document's
    #    ``StructuralAnnotationSet`` (re-parse).
    #
    #    Per-row ``Relationship.objects.create()`` (rather than
    #    ``bulk_create``) is intentional: ``Relationship.save()`` is
    #    overridden (see ``Relationship.save`` in
    #    ``opencontractserver/annotations/models.py``) to call
    #    ``self.clean()``, which enforces the document-XOR-structural_set
    #    constraint. Django's default ``Model.save()`` does NOT call
    #    ``clean()``, so ``bulk_create`` would silently bypass it. The row
    #    count is bounded by the number of non-leaf structural annotations
    #    and is small relative to the total annotation count.
    #
    #    Scope: on a first parse the structural set has not been created
    #    yet, so new rows are scoped to ``document``; the parser then
    #    migrates them to the set in ``_create_structural_annotation_set``.
    #    On a re-parse the structural set already exists, so we attach
    #    straight to it — otherwise the early-return in that method would
    #    leave us with orphaned ``document``-scoped rows.
    # ------------------------------------------------------------------ #
    created = 0
    with transaction.atomic():
        # Idempotency delete: drop prior OC_SUBTREE_GROUP rows for this
        # document regardless of scope. Single ``Q``-OR rather than
        # ``qs1 | qs2`` so ``.delete()`` runs against an explicit WHERE
        # clause (the prior union form relied on Django queryset combining
        # for delete semantics). ``document=`` is again intentionally
        # omitted on the structural_set branch — migrated rows have
        # ``document=None``.
        delete_filter = Q(
            document=document,
            structural=True,
            structural_set__isnull=True,
            relationship_label_id=label.pk,
        )
        if structural_set_id is not None:
            delete_filter |= Q(
                structural=True,
                structural_set_id=structural_set_id,
                relationship_label_id=label.pk,
            )
        Relationship.objects.filter(delete_filter).delete()

        for node in non_leaves:
            descs = descendants.get(node)
            if not descs:
                continue
            if len(descs) > max_descendants:
                logger.warning(
                    "Skipping OC_SUBTREE_GROUP for annotation %s on document "
                    "%s: %s descendants exceeds cap %s",
                    node,
                    document.pk,
                    len(descs),
                    max_descendants,
                )
                continue
            if structural_set_id is not None:
                rel = Relationship.objects.create(
                    relationship_label=label,
                    structural_set_id=structural_set_id,
                    creator_id=user_id,
                    structural=True,
                )
            else:
                rel = Relationship.objects.create(
                    relationship_label=label,
                    document=document,
                    creator_id=user_id,
                    structural=True,
                )
            rel.source_annotations.add(node)
            rel.target_annotations.set(descs)
            created += 1

    logger.info(
        "Materialised %s OC_SUBTREE_GROUP relationships for document %s",
        created,
        document.pk,
    )
    return created
