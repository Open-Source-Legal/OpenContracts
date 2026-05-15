"""Tests for opencontractserver.utils.subtree_groups.

Covers the four behaviours described in the plan:

1. One ``OC_SUBTREE_GROUP`` row is materialised per non-leaf structural
   annotation with the full transitive descendant set as targets.
2. Subtree-group rows produced before ``_create_structural_annotation_set``
   are migrated to the document's ``StructuralAnnotationSet`` by the
   existing parser flow.
3. Oversized subtrees are skipped, smaller ones are still materialised.
4. Cycles and deeper-than-cap branches are handled defensively.
"""

from __future__ import annotations

import logging
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.annotations.models import (
    RELATIONSHIP_LABEL,
    Annotation,
    AnnotationLabel,
    Relationship,
    StructuralAnnotationSet,
)
from opencontractserver.constants.annotations import (
    OC_PARENT_CHILD_LABEL_NAME,
    OC_SUBTREE_GROUP_LABEL_NAME,
    SUBTREE_GROUP_MAX_DEPTH,
)
from opencontractserver.documents.models import Document
from opencontractserver.pipeline.base.parser import BaseParser
from opencontractserver.utils.subtree_groups import (
    build_subtree_groups_for_document,
)

logger = logging.getLogger(__name__)
User = get_user_model()


class _ShimParser(BaseParser):
    """Minimal BaseParser stand-in for tests that only exercise
    ``_create_structural_annotation_set`` — the abstract
    ``_parse_document_impl`` is satisfied with a no-op."""

    title = "shim-parser"

    def _parse_document_impl(self, *args, **kwargs):
        return None


class SubtreeGroupMaterializationTestCase(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="grover", password="pw")
        self.document = Document.objects.create(title="Tree doc", creator=self.user)
        self.label = AnnotationLabel.objects.create(
            text="Structural", creator=self.user
        )
        # Tree:
        #
        #          N
        #        / | \
        #       A  B  C
        #      / \
        #     x   y
        #
        self.N = self._make_annot(raw_text="N")
        self.A = self._make_annot(raw_text="A", parent=self.N)
        self.B = self._make_annot(raw_text="B", parent=self.N)
        self.C = self._make_annot(raw_text="C", parent=self.N)
        self.x = self._make_annot(raw_text="x", parent=self.A)
        self.y = self._make_annot(raw_text="y", parent=self.A)

    def _make_annot(
        self, *, raw_text: str, parent: Annotation | None = None
    ) -> Annotation:
        return Annotation.objects.create(
            document=self.document,
            annotation_label=self.label,
            raw_text=raw_text,
            structural=True,
            creator=self.user,
            parent=parent,
        )

    def _subtree_groups(self) -> list[Relationship]:
        return list(
            Relationship.objects.filter(
                document=self.document,
                relationship_label__text=OC_SUBTREE_GROUP_LABEL_NAME,
            )
        )

    def test_subtree_groups_created_for_each_non_leaf(self) -> None:
        created = build_subtree_groups_for_document(self.document, self.user.id)
        self.assertEqual(created, 2)

        groups = self._subtree_groups()
        self.assertEqual(len(groups), 2)

        by_source: dict[int, set[int]] = {}
        for rel in groups:
            sources = list(rel.source_annotations.values_list("id", flat=True))
            self.assertEqual(len(sources), 1)
            self.assertTrue(rel.structural)
            self.assertIsNone(rel.structural_set_id)
            self.assertEqual(rel.document_id, self.document.id)
            by_source[sources[0]] = set(
                rel.target_annotations.values_list("id", flat=True)
            )

        self.assertEqual(
            by_source[self.N.id],
            {self.A.id, self.B.id, self.C.id, self.x.id, self.y.id},
        )
        self.assertEqual(by_source[self.A.id], {self.x.id, self.y.id})
        # Leaves get no group.
        for leaf in (self.B, self.C, self.x, self.y):
            self.assertNotIn(leaf.id, by_source)

    def test_re_run_is_idempotent(self) -> None:
        first = build_subtree_groups_for_document(self.document, self.user.id)
        second = build_subtree_groups_for_document(self.document, self.user.id)
        self.assertEqual(first, second)
        # Still only the two expected rows (the prior run was deleted).
        self.assertEqual(len(self._subtree_groups()), 2)

    def test_subtree_groups_migrate_to_structural_set(self) -> None:
        """Running through BaseParser.save_parsed_data attaches groups to the set."""
        parser = _ShimParser()

        # Materialise groups first (as save_parsed_data would).
        build_subtree_groups_for_document(self.document, self.user.id)
        # Then run the structural-set migration the way save_parsed_data does.
        parser._create_structural_annotation_set(self.document, self.user)

        self.document.refresh_from_db()
        struct_set_id = self.document.structural_annotation_set_id
        assert struct_set_id is not None
        struct_set = StructuralAnnotationSet.objects.get(id=struct_set_id)
        migrated = Relationship.objects.filter(
            structural_set=struct_set,
            relationship_label__text=OC_SUBTREE_GROUP_LABEL_NAME,
        )
        self.assertEqual(migrated.count(), 2)
        # And nothing left on the document side.
        self.assertEqual(
            Relationship.objects.filter(
                document=self.document,
                relationship_label__text=OC_SUBTREE_GROUP_LABEL_NAME,
            ).count(),
            0,
        )

    def test_subtree_groups_respect_size_cap(self) -> None:
        # Add 6 leaves under C so that C's descendant count = 6.
        extras = [self._make_annot(raw_text=f"c{i}", parent=self.C) for i in range(6)]

        # Cap at 5: N (now has 11 descendants) and the C subtree (6 descs)
        # should both be skipped. A (2 descendants) still emits.
        created = build_subtree_groups_for_document(
            self.document, self.user.id, max_descendants=5
        )
        self.assertEqual(created, 1)
        groups = self._subtree_groups()
        self.assertEqual(len(groups), 1)
        only = groups[0]
        sources = list(only.source_annotations.values_list("id", flat=True))
        self.assertEqual(sources, [self.A.id])
        self.assertEqual(
            set(only.target_annotations.values_list("id", flat=True)),
            {self.x.id, self.y.id},
        )
        # Ensure all extras still exist (we did not delete annotations).
        self.assertEqual(
            Annotation.objects.filter(id__in=[e.id for e in extras]).count(), 6
        )

    def test_subtree_groups_handle_cycle(self) -> None:
        # Build a parent-child Relationship edge from x -> A that closes
        # the loop N -> A -> x -> A back into A. The DFS descends through
        # N -> A -> x and, when expanding x's children, finds A still on
        # the stack — the ``on_stack`` branch must fire (logging a
        # warning) instead of recursing forever.
        pc_label = AnnotationLabel.objects.create(
            text=OC_PARENT_CHILD_LABEL_NAME,
            label_type=RELATIONSHIP_LABEL,
            creator=self.user,
        )
        rel = Relationship.objects.create(
            relationship_label=pc_label,
            document=self.document,
            structural=True,
            creator=self.user,
        )
        rel.source_annotations.add(self.x)
        rel.target_annotations.add(self.A)

        with patch("opencontractserver.utils.subtree_groups.logger") as mock_logger:
            created = build_subtree_groups_for_document(self.document, self.user.id)

        # Should still materialise at least one group and not loop.
        self.assertGreaterEqual(created, 1)
        # ``on_stack`` detection must fire at least once for the cycle.
        cycle_warnings = [
            c
            for c in mock_logger.warning.call_args_list
            if "Cycle detected" in c.args[0]
        ]
        self.assertGreaterEqual(len(cycle_warnings), 1)

    def test_subtree_groups_respect_depth_cap(self) -> None:
        # Chain: deep0 -> deep1 -> deep2 -> deep3 -> deep4 (5 levels)
        deep0 = self._make_annot(raw_text="d0")
        prev = deep0
        chain = [deep0]
        for i in range(1, 5):
            curr = self._make_annot(raw_text=f"d{i}", parent=prev)
            chain.append(curr)
            prev = curr

        # max_depth=2 should prune below deep2; deep0's descendants set
        # only includes nodes the walker actually visited.
        build_subtree_groups_for_document(self.document, self.user.id, max_depth=2)
        deep0_group = Relationship.objects.filter(
            source_annotations=deep0,
            relationship_label__text=OC_SUBTREE_GROUP_LABEL_NAME,
        ).first()
        assert deep0_group is not None
        target_ids = set(deep0_group.target_annotations.values_list("id", flat=True))
        # depth-1 (deep1) and depth-2 (deep2) visited; deeper not.
        self.assertIn(chain[1].id, target_ids)
        self.assertIn(chain[2].id, target_ids)
        self.assertNotIn(chain[3].id, target_ids)
        self.assertNotIn(chain[4].id, target_ids)

    def test_default_max_depth_pins_constant(self) -> None:
        """Exercise the depth cap via its default — guards against a future
        constant change silently regressing the walker. The walker prunes
        when ``depth + 1 > max_depth``, so a chain with one node beyond the
        cap (root at depth 0 + ``SUBTREE_GROUP_MAX_DEPTH + 1`` descendants)
        is needed to force a single pruned tail node."""
        # Total nodes = SUBTREE_GROUP_MAX_DEPTH + 2 (depths 0..MAX_DEPTH+1).
        chain_len = SUBTREE_GROUP_MAX_DEPTH + 2
        head = self._make_annot(raw_text="h0")
        chain = [head]
        prev = head
        for i in range(1, chain_len):
            curr = self._make_annot(raw_text=f"h{i}", parent=prev)
            chain.append(curr)
            prev = curr

        # Call without overriding max_depth so the constant is exercised.
        build_subtree_groups_for_document(self.document, self.user.id)
        head_group = Relationship.objects.filter(
            source_annotations=head,
            relationship_label__text=OC_SUBTREE_GROUP_LABEL_NAME,
        ).first()
        assert head_group is not None
        target_ids = set(head_group.target_annotations.values_list("id", flat=True))
        # Nodes at depths 1..SUBTREE_GROUP_MAX_DEPTH are visited; the tail
        # node sits at depth MAX_DEPTH+1 and must be pruned.
        for i in range(1, SUBTREE_GROUP_MAX_DEPTH + 1):
            self.assertIn(chain[i].id, target_ids)
        self.assertNotIn(chain[chain_len - 1].id, target_ids)

    def test_skips_when_no_structural_annotations(self) -> None:
        doc = Document.objects.create(title="Empty", creator=self.user)
        created = build_subtree_groups_for_document(doc, self.user.id)
        self.assertEqual(created, 0)
        self.assertFalse(
            Relationship.objects.filter(
                document=doc,
                relationship_label__text=OC_SUBTREE_GROUP_LABEL_NAME,
            ).exists()
        )

    def test_consumes_parent_child_relationship_edges(self) -> None:
        """Future-proofing: parent-child Relationship rows participate."""
        # Detach z from the FK tree; link it via a parent-child Relationship instead.
        z = self._make_annot(raw_text="z")  # standalone (no parent FK)
        pc_label = AnnotationLabel.objects.create(
            text=OC_PARENT_CHILD_LABEL_NAME,
            label_type=RELATIONSHIP_LABEL,
            creator=self.user,
        )
        rel = Relationship.objects.create(
            relationship_label=pc_label,
            document=self.document,
            structural=True,
            creator=self.user,
        )
        rel.source_annotations.add(self.C)
        rel.target_annotations.add(z)

        build_subtree_groups_for_document(self.document, self.user.id)

        c_group = Relationship.objects.filter(
            source_annotations=self.C,
            relationship_label__text=OC_SUBTREE_GROUP_LABEL_NAME,
        ).first()
        assert c_group is not None
        self.assertEqual(
            set(c_group.target_annotations.values_list("id", flat=True)), {z.id}
        )
        # And N's group should now include z via the parent-child edge.
        n_group = Relationship.objects.filter(
            source_annotations=self.N,
            relationship_label__text=OC_SUBTREE_GROUP_LABEL_NAME,
        ).first()
        assert n_group is not None
        self.assertIn(
            z.id, set(n_group.target_annotations.values_list("id", flat=True))
        )

    def test_label_does_not_proliferate_per_user(self) -> None:
        """The OC_SUBTREE_GROUP label is system-wide; running the builder for
        a different user must not fork a second label."""
        build_subtree_groups_for_document(self.document, self.user.id)
        other = User.objects.create_user(username="ernie", password="pw")
        # Wipe groups so the second invocation re-creates them under a
        # different user_id.
        Relationship.objects.filter(
            document=self.document,
            relationship_label__text=OC_SUBTREE_GROUP_LABEL_NAME,
        ).delete()
        build_subtree_groups_for_document(self.document, other.id)
        labels = AnnotationLabel.objects.filter(
            text=OC_SUBTREE_GROUP_LABEL_NAME,
            label_type=RELATIONSHIP_LABEL,
            analyzer=None,
        )
        self.assertEqual(labels.count(), 1)

    def test_re_parse_after_structural_set_exists(self) -> None:
        """Re-running the builder after a structural set has been migrated
        attaches new rows to the set and cleans up the prior generation."""
        parser = _ShimParser()

        # First parse: groups under document, then migrate to structural set.
        build_subtree_groups_for_document(self.document, self.user.id)
        parser._create_structural_annotation_set(self.document, self.user)
        self.document.refresh_from_db()
        struct_set_id = self.document.structural_annotation_set_id
        assert struct_set_id is not None

        # Second invocation simulates a re-parse: structural set already
        # exists, no document-scoped structural annotations remain.
        created = build_subtree_groups_for_document(self.document, self.user.id)

        # New rows are scoped directly to the structural set …
        self.assertEqual(created, 2)
        on_set = Relationship.objects.filter(
            structural_set_id=struct_set_id,
            relationship_label__text=OC_SUBTREE_GROUP_LABEL_NAME,
        )
        self.assertEqual(on_set.count(), 2)
        # … and no orphaned document-scoped rows are left behind.
        self.assertEqual(
            Relationship.objects.filter(
                document=self.document,
                relationship_label__text=OC_SUBTREE_GROUP_LABEL_NAME,
            ).count(),
            0,
        )

    def test_size_cap_warning_logged(self) -> None:
        with patch("opencontractserver.utils.subtree_groups.logger") as mock_logger:
            build_subtree_groups_for_document(
                self.document, self.user.id, max_descendants=1
            )
            warning_calls = [
                c
                for c in mock_logger.warning.call_args_list
                if "exceeds cap" in c.args[0]
            ]
            self.assertGreaterEqual(len(warning_calls), 1)
