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
- Scoped admin access (2026-05): superusers are computed like a normal user
  and therefore do NOT see trashed annotations/relationships through the
  manager. Audit/repair of trashed data is done via the Django admin site.
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

    def test_superuser_does_not_see_trashed_annotations(self):
        """Scoped admin access (2026-05): a superuser is computed like a normal
        user, so trashed annotations are hidden from the manager. They are
        reachable only via the Django admin site, not ``visible_to_user``."""
        delete_document(self.corpus, "/vis_doc.pdf", self.user)

        visible_ids = set(
            Annotation.objects.visible_to_user(self.superuser).values_list(
                "id", flat=True
            )
        )
        self.assertNotIn(self.source_ann.id, visible_ids)
        self.assertNotIn(self.target_ann.id, visible_ids)

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

    def test_null_document_id_annotation_not_excluded_by_orphan_filter(self):
        """Regression guard for the ``Q(document_id__isnull=False)`` clause in
        ``_exclude_soft_deleted_doc_orphans``: an annotation with
        ``document=None`` (e.g. structural annotations linked only via
        ``structural_set``) must NOT be filtered out by the orphan predicate
        regardless of any corpus state, because the ``(doc, corpus)``
        identity is undefined.
        """
        structural_set = StructuralAnnotationSet.objects.create(
            content_hash="null-doc-hash",
            creator=self.user,
        )
        # Wire the structural set to our public doc so the anonymous /
        # downstream visibility filters that look at ``structural_set
        # __documents`` see at least one visible doc.
        self.doc.structural_annotation_set = structural_set
        self.doc.save(update_fields=["structural_annotation_set"])

        struct_ann = Annotation.objects.create(
            document=None,
            corpus=self.corpus,
            structural_set=structural_set,
            annotation_label=self.label,
            creator=self.user,
            raw_text="structural-no-doc",
            page=1,
            json={},
            structural=True,
            is_public=True,
        )

        # Even after soft-deleting the only doc that references the set, the
        # structural annotation itself has ``document_id IS NULL`` so the
        # orphan predicate must leave it alone (downstream filters decide
        # visibility on other grounds).
        delete_document(self.corpus, "/vis_doc.pdf", self.user)

        from opencontractserver.shared.QuerySets import (
            _exclude_soft_deleted_doc_orphans,
        )

        kept_ids = set(
            _exclude_soft_deleted_doc_orphans(
                Annotation.objects.filter(id=struct_ann.id)
            ).values_list("id", flat=True)
        )
        self.assertIn(struct_ann.id, kept_ids)

    def test_null_corpus_id_annotation_not_excluded_by_orphan_filter(self):
        """Regression guard for the ``Q(corpus_id__isnull=False)`` clause:
        an annotation with ``corpus=None`` (e.g. corpus-agnostic annotations
        on standalone docs) must not be filtered out by the orphan predicate
        either — the ``(doc, corpus)`` pair is still undefined.
        """
        no_corpus_doc = Document.objects.create(
            title="NoCorpus",
            creator=self.user,
            is_public=True,
        )
        ann = Annotation.objects.create(
            document=no_corpus_doc,
            corpus=None,
            annotation_label=self.label,
            creator=self.user,
            raw_text="no-corpus",
            page=1,
            json={},
            is_public=True,
        )

        from opencontractserver.shared.QuerySets import (
            _exclude_soft_deleted_doc_orphans,
        )

        kept_ids = set(
            _exclude_soft_deleted_doc_orphans(
                Annotation.objects.filter(id=ann.id)
            ).values_list("id", flat=True)
        )
        self.assertIn(ann.id, kept_ids)

    def test_annotation_visible_in_active_corpus_when_trashed_in_other(self):
        """Multi-corpus regression: a document soft-deleted in Corpus A but
        still active in Corpus B must keep its Corpus-B-scoped annotations
        visible. The orphan predicate is corpus-scoped via
        ``OuterRef('corpus_id')`` — this test pins that scoping so a future
        change can't accidentally hide rows across corpus boundaries.
        """
        # Add a second public corpus and put a corpus-isolated copy of the
        # same source content into it via Corpus.add_document (the real
        # corpus-isolation path). Use ``processing_started`` to skip the
        # ingestion pipeline so we control the test state.
        from django.utils import timezone

        corpus_b = Corpus.objects.create(
            title="Soft-Delete Visibility Corpus B",
            creator=self.user,
            is_public=True,
        )
        copy_b, _, path_b = corpus_b.add_document(
            document=self.doc,
            user=self.user,
        )
        copy_b.refresh_from_db()
        copy_b.is_public = True
        copy_b.processing_started = timezone.now()
        copy_b.save(update_fields=["is_public", "processing_started"])

        # Annotation only in Corpus B, on the Corpus-B-scoped copy.
        ann_b = Annotation.objects.create(
            document=copy_b,
            corpus=corpus_b,
            annotation_label=self.label,
            creator=self.user,
            raw_text="corpus-b-only",
            page=1,
            json={},
            is_public=True,
        )

        # Soft-delete only in Corpus A. Corpus B's path remains active.
        delete_document(self.corpus, "/vis_doc.pdf", self.user)

        # Sanity: corpus B's path is still active.
        self.assertTrue(
            DocumentPath.objects.filter(
                document=copy_b,
                corpus=corpus_b,
                is_current=True,
                is_deleted=False,
            ).exists()
        )

        visible_ids = set(
            Annotation.objects.visible_to_user(self.user).values_list("id", flat=True)
        )
        # Corpus A annotations on the trashed copy must be hidden …
        self.assertNotIn(self.source_ann.id, visible_ids)
        # … but the Corpus B annotation on the still-active copy stays
        # visible.
        self.assertIn(ann_b.id, visible_ids)


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

    def test_superuser_does_not_see_trashed_relationships(self):
        """Scoped admin access (2026-05): a superuser is computed like a normal
        user, so trashed relationships are hidden from the manager. They are
        reachable only via the Django admin site, not ``visible_to_user``."""
        delete_document(self.corpus, "/vis_doc.pdf", self.user)

        visible_ids = set(
            Relationship.objects.visible_to_user(self.superuser).values_list(
                "id", flat=True
            )
        )
        self.assertNotIn(self.relationship.id, visible_ids)

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

    def test_permanent_delete_removes_corpus_scoped_annotations(self):
        """Focused regression test: ``permanently_delete_document`` deletes
        the corpus-scoped non-structural annotations on the document, not
        just the relationships pointing at them. The full-lifecycle tests
        above cover this implicitly via ``Relationship`` cascade behaviour,
        but a dedicated assertion catches regressions in step 5 of
        ``permanently_delete_document`` independently of the relationship
        cleanup path.
        """
        source_id = self.source_ann.id
        target_id = self.target_ann.id

        delete_document(self.corpus, "/vis_doc.pdf", self.user)
        success, msg = permanently_delete_document(self.corpus, self.doc, self.user)
        self.assertTrue(success, msg)

        # Both corpus-scoped annotations on the deleted doc must be gone
        # from the DB — not just hidden from visibility queries.
        self.assertFalse(Annotation.objects.filter(id=source_id).exists())
        self.assertFalse(Annotation.objects.filter(id=target_id).exists())


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
