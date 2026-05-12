"""
Tests for annotation/relationship visibility when documents are soft-deleted.

Architecture context:
- ``RemoveDocumentsFromCorpus`` soft-deletes a doc by creating
  ``DocumentPath(is_current=True, is_deleted=True)``. The Document and its
  annotations/relationships remain in the DB so ``RestoreDeletedDocument``
  can recover them.
- ``AnnotationQuerySet.visible_to_user()`` and ``RelationshipManager
  .visible_to_user()`` must hide those rows from user-facing queries —
  otherwise a global annotation search returns rows pointing at documents
  the user cannot navigate to ("annotations linked to unknown document").
- The hidden rows must reappear after a doc is restored from trash, and
  must vanish permanently after ``permanently_delete_document``.
- Superusers see everything (intentional bypass for admin/audit tooling).
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
    Relationship,
    StructuralAnnotationSet,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.documents.versioning import (
    delete_document,
    import_document,
    permanently_delete_document,
    restore_document,
)

User = get_user_model()


class SoftDeleteVisibilityBase(TestCase):
    """Shared setup: a corpus with a doc, a user-created annotation, and a
    user-created relationship between two annotations on that doc."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="visibility_owner",
            password="testpass123",
            email="owner@test.com",
        )
        self.other_user = User.objects.create_user(
            username="visibility_other",
            password="testpass123",
            email="other@test.com",
        )
        self.superuser = User.objects.create_superuser(
            username="visibility_super",
            password="testpass123",
            email="super@test.com",
        )

        self.corpus = Corpus.objects.create(
            title="Soft-Delete Visibility Corpus",
            creator=self.user,
            is_public=True,  # so visibility filter passes on doc/corpus
        )

        self.label = AnnotationLabel.objects.create(
            text="VisLabel",
            creator=self.user,
        )

        self.doc, _, _ = import_document(
            corpus=self.corpus,
            path="/vis_doc.pdf",
            content=b"visibility test content",
            user=self.user,
            title="Visibility Doc",
            is_public=True,
        )

        self.source_ann = Annotation.objects.create(
            document=self.doc,
            corpus=self.corpus,
            annotation_label=self.label,
            creator=self.user,
            raw_text="source",
            page=1,
            json={},
            is_public=True,
        )
        self.target_ann = Annotation.objects.create(
            document=self.doc,
            corpus=self.corpus,
            annotation_label=self.label,
            creator=self.user,
            raw_text="target",
            page=1,
            json={},
            is_public=True,
        )

        rel_label = AnnotationLabel.objects.create(
            text="VisRel",
            label_type="RELATIONSHIP_LABEL",
            creator=self.user,
        )
        self.relationship = Relationship.objects.create(
            relationship_label=rel_label,
            document=self.doc,
            corpus=self.corpus,
            creator=self.user,
            is_public=True,
        )
        self.relationship.source_annotations.add(self.source_ann)
        self.relationship.target_annotations.add(self.target_ann)


class AnnotationVisibilityWhenSoftDeletedTests(SoftDeleteVisibilityBase):
    """``visible_to_user`` must hide annotations on trashed docs."""

    def test_visible_before_soft_delete(self):
        """Baseline: annotations are visible while the doc is in the corpus."""
        visible_ids = set(
            Annotation.objects.visible_to_user(self.user).values_list("id", flat=True)
        )
        self.assertIn(self.source_ann.id, visible_ids)
        self.assertIn(self.target_ann.id, visible_ids)

    def test_hidden_after_soft_delete_for_owner(self):
        """Soft-delete the doc and the annotations vanish from visibility queries."""
        delete_document(self.corpus, "/vis_doc.pdf", self.user)

        visible_ids = set(
            Annotation.objects.visible_to_user(self.user).values_list("id", flat=True)
        )
        self.assertNotIn(self.source_ann.id, visible_ids)
        self.assertNotIn(self.target_ann.id, visible_ids)

        # But the data is preserved in the DB for restore.
        self.assertTrue(Annotation.objects.filter(id=self.source_ann.id).exists())
        self.assertTrue(Annotation.objects.filter(id=self.target_ann.id).exists())

    def test_hidden_after_soft_delete_for_other_user(self):
        """A different (non-owner) user also doesn't see them after soft-delete."""
        delete_document(self.corpus, "/vis_doc.pdf", self.user)

        visible_ids = set(
            Annotation.objects.visible_to_user(self.other_user).values_list(
                "id", flat=True
            )
        )
        self.assertNotIn(self.source_ann.id, visible_ids)

    def test_superuser_still_sees_trashed_annotations(self):
        """Admin tooling explicitly bypasses the trash filter."""
        delete_document(self.corpus, "/vis_doc.pdf", self.user)

        visible_ids = set(
            Annotation.objects.visible_to_user(self.superuser).values_list(
                "id", flat=True
            )
        )
        self.assertIn(self.source_ann.id, visible_ids)
        self.assertIn(self.target_ann.id, visible_ids)

    def test_restore_makes_annotations_visible_again(self):
        """The data round-trips: soft-delete hides, restore unhides."""
        delete_document(self.corpus, "/vis_doc.pdf", self.user)
        restore_document(self.corpus, "/vis_doc.pdf", self.user)

        visible_ids = set(
            Annotation.objects.visible_to_user(self.user).values_list("id", flat=True)
        )
        self.assertIn(self.source_ann.id, visible_ids)
        self.assertIn(self.target_ann.id, visible_ids)

    def test_hidden_after_soft_delete_for_anonymous_user(self):
        """The anonymous-user branch of ``visible_to_user`` takes a different
        code path (public-structural-only); make sure the soft-delete filter
        still hides trashed-doc annotations on it.
        """
        # Mark one annotation structural so it would normally pass the
        # anonymous filter — only the soft-delete predicate should hide it.
        self.source_ann.structural = True
        self.source_ann.save(update_fields=["structural"])

        # Sanity check: before soft-delete, the anonymous viewer sees the
        # structural public annotation.
        baseline_ids = set(
            Annotation.objects.visible_to_user(None).values_list("id", flat=True)
        )
        self.assertIn(self.source_ann.id, baseline_ids)

        delete_document(self.corpus, "/vis_doc.pdf", self.user)

        visible_ids = set(
            Annotation.objects.visible_to_user(None).values_list("id", flat=True)
        )
        self.assertNotIn(self.source_ann.id, visible_ids)

    def test_standalone_doc_annotations_not_hidden(self):
        """Regression guard: annotations on a doc with NO DocumentPath at all
        (e.g. test fixtures, legacy / pre-corpus-isolation data) must remain
        visible. The filter only fires when the (doc, corpus) pair was ever
        pathed.
        """
        standalone_doc = Document.objects.create(
            title="Standalone",
            creator=self.user,
            is_public=True,
        )
        ann = Annotation.objects.create(
            document=standalone_doc,
            corpus=self.corpus,
            annotation_label=self.label,
            creator=self.user,
            raw_text="standalone",
            page=1,
            json={},
            is_public=True,
        )
        # No DocumentPath was created for (standalone_doc, corpus), so the
        # filter must NOT fire.
        visible_ids = set(
            Annotation.objects.visible_to_user(self.user).values_list("id", flat=True)
        )
        self.assertIn(ann.id, visible_ids)


class RelationshipVisibilityWhenSoftDeletedTests(SoftDeleteVisibilityBase):
    """Mirror of the annotation tests, for Relationship."""

    def test_visible_before_soft_delete(self):
        visible_ids = set(
            Relationship.objects.visible_to_user(self.user).values_list("id", flat=True)
        )
        self.assertIn(self.relationship.id, visible_ids)

    def test_hidden_after_soft_delete(self):
        delete_document(self.corpus, "/vis_doc.pdf", self.user)

        visible_ids = set(
            Relationship.objects.visible_to_user(self.user).values_list("id", flat=True)
        )
        self.assertNotIn(self.relationship.id, visible_ids)

        # Data is preserved for restore.
        self.assertTrue(Relationship.objects.filter(id=self.relationship.id).exists())

    def test_hidden_after_soft_delete_for_other_user(self):
        """Non-owner viewers must also lose visibility once the doc is trashed."""
        delete_document(self.corpus, "/vis_doc.pdf", self.user)

        visible_ids = set(
            Relationship.objects.visible_to_user(self.other_user).values_list(
                "id", flat=True
            )
        )
        self.assertNotIn(self.relationship.id, visible_ids)

    def test_superuser_still_sees_trashed_relationships(self):
        delete_document(self.corpus, "/vis_doc.pdf", self.user)

        visible_ids = set(
            Relationship.objects.visible_to_user(self.superuser).values_list(
                "id", flat=True
            )
        )
        self.assertIn(self.relationship.id, visible_ids)

    def test_restore_makes_relationship_visible_again(self):
        delete_document(self.corpus, "/vis_doc.pdf", self.user)
        restore_document(self.corpus, "/vis_doc.pdf", self.user)

        visible_ids = set(
            Relationship.objects.visible_to_user(self.user).values_list("id", flat=True)
        )
        self.assertIn(self.relationship.id, visible_ids)


class PermanentDeleteRelationshipCleanupTests(SoftDeleteVisibilityBase):
    """``permanently_delete_document`` must remove corpus-scoped relationships
    even when the relationship's source/target annotations live elsewhere or
    the relationship is empty — anything tagged ``document=doc, structural_set
    IS NULL`` is corpus-scoped and must go.
    """

    def test_permanent_delete_removes_relationship_without_annotation_links(self):
        # Create a relationship tagged to this document but with no
        # source/target annotations (i.e. orphan that would survive the
        # original "filter by source/target annotation IDs" predicate).
        empty_label = AnnotationLabel.objects.create(
            text="EmptyRel",
            label_type="RELATIONSHIP_LABEL",
            creator=self.user,
        )
        orphan_rel = Relationship.objects.create(
            relationship_label=empty_label,
            document=self.doc,
            corpus=self.corpus,
            creator=self.user,
        )
        rel_id = orphan_rel.id

        delete_document(self.corpus, "/vis_doc.pdf", self.user)
        success, msg = permanently_delete_document(self.corpus, self.doc, self.user)
        self.assertTrue(success, msg)

        self.assertFalse(Relationship.objects.filter(id=rel_id).exists())


class StructuralSetGCAcrossCorpusCopiesTests(TestCase):
    """The structural annotation set is shared across corpus-isolated copies
    of a document with the same ``content_hash``. Permanently deleting one
    copy must NOT drop the set as long as another copy still references it;
    permanently deleting the last copy MUST drop it (with its structural
    annotations and relationships).

    Documents are constructed directly here (bypassing ``import_document``)
    so the ingestion pipeline doesn't race the structural-set assignment
    or generate its own ``StructuralAnnotationSet`` for the test content.
    """

    def setUp(self):
        from django.utils import timezone

        self.user = User.objects.create_user(
            username="ss_gc_user",
            password="testpass123",
            email="ssgc@test.com",
        )

        self.corpus_a = Corpus.objects.create(
            title="Corpus A",
            creator=self.user,
        )
        self.corpus_b = Corpus.objects.create(
            title="Corpus B",
            creator=self.user,
        )

        # Create the shared StructuralAnnotationSet and one structural
        # annotation on it.
        self.structural_set = StructuralAnnotationSet.objects.create(
            content_hash="shared-hash-xyz",
            creator=self.user,
        )
        self.label = AnnotationLabel.objects.create(
            text="StructLabel",
            creator=self.user,
        )
        self.structural_ann = Annotation.objects.create(
            structural_set=self.structural_set,
            annotation_label=self.label,
            creator=self.user,
            raw_text="structural",
            page=1,
            json={},
            structural=True,
        )

        # First corpus-isolated copy in corpus_a — constructed directly with
        # ``processing_started`` set to skip the ingestion pipeline so the
        # ``structural_annotation_set`` we assigned isn't clobbered.
        self.copy_a = Document.objects.create(
            title="Copy A",
            creator=self.user,
            processing_started=timezone.now(),
            structural_annotation_set=self.structural_set,
        )
        DocumentPath.objects.create(
            document=self.copy_a,
            corpus=self.corpus_a,
            path="/source.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )

        # Second copy via ``Corpus.add_document`` so we exercise the real
        # corpus-isolation path that reuses ``structural_annotation_set``.
        self.copy_b, _, self.path_b = self.corpus_b.add_document(
            document=self.copy_a,
            user=self.user,
        )
        self.copy_b.refresh_from_db()
        self.assertEqual(
            self.copy_b.structural_annotation_set_id,
            self.structural_set.id,
            "Corpus.add_document should reuse structural_annotation_set",
        )

    def test_structural_set_preserved_when_other_copy_references_it(self):
        """Permanently delete from corpus_a; copy_b still references the set,
        so the set (and its structural annotations) must remain.
        """
        delete_document(self.corpus_a, "/source.pdf", self.user)
        success, msg = permanently_delete_document(
            self.corpus_a, self.copy_a, self.user
        )
        self.assertTrue(success, msg)

        # copy_a is deleted; copy_b survives.
        self.assertFalse(Document.objects.filter(id=self.copy_a.id).exists())
        self.assertTrue(Document.objects.filter(id=self.copy_b.id).exists())

        # Structural set + its structural annotation are preserved because
        # copy_b still references the set.
        self.assertTrue(
            StructuralAnnotationSet.objects.filter(id=self.structural_set.id).exists()
        )
        self.assertTrue(Annotation.objects.filter(id=self.structural_ann.id).exists())

    def test_structural_set_gc_when_last_copy_deleted(self):
        """Permanently delete BOTH copies; the structural set is GC'd by the
        post_delete signal (no Document left referencing it), and its
        structural annotations vanish via CASCADE.
        """
        # First copy.
        delete_document(self.corpus_a, "/source.pdf", self.user)
        success_a, msg_a = permanently_delete_document(
            self.corpus_a, self.copy_a, self.user
        )
        self.assertTrue(success_a, msg_a)
        # Set still alive because copy_b references it.
        self.assertTrue(
            StructuralAnnotationSet.objects.filter(id=self.structural_set.id).exists()
        )

        # Second copy — soft-delete via its actual path in corpus_b, then
        # permanent-delete.
        delete_document(self.corpus_b, self.path_b.path, self.user)
        success_b, msg_b = permanently_delete_document(
            self.corpus_b, self.copy_b, self.user
        )
        self.assertTrue(success_b, msg_b)

        # Both copies gone, structural set GC'd, structural annotation gone.
        self.assertFalse(Document.objects.filter(id=self.copy_a.id).exists())
        self.assertFalse(Document.objects.filter(id=self.copy_b.id).exists())
        self.assertFalse(
            StructuralAnnotationSet.objects.filter(id=self.structural_set.id).exists()
        )
        self.assertFalse(Annotation.objects.filter(id=self.structural_ann.id).exists())
