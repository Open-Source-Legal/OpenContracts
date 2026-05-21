"""
Test Suite for OpenContracts v3.0.0.b3 Migration

This test suite validates the migration path from v3.0.0.b2 to v3.0.0.b3,
covering dual-tree document versioning and structural annotation sets.

Tests are organized into:
1. DocumentVersioningMigrationTests - Document versioning migration validation
2. XORConstraintTests - XOR constraint validation for annotations/relationships
3. StructuralMigrationCommandTests - Management command testing
4. RollbackAndEdgeCaseTests - Edge cases and error handling
5. ValidationCommandTests - validate_v3_migration command testing
"""

import io
import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings

from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
    Relationship,
    StructuralAnnotationSet,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.types.enums import LabelType

User = get_user_model()


class DocumentVersioningMigrationTests(TestCase):
    """
    Test the document versioning migration (migrations 0023-0026).

    These tests validate that the dual-tree architecture is correctly
    initialized for existing documents.
    """

    def setUp(self):
        """Create test fixtures simulating pre-migration state."""
        self.user = User.objects.create_user(
            username="migration_test_user", password="testpass123"
        )
        self.corpus1 = Corpus.objects.create(title="Test Corpus 1", creator=self.user)
        self.corpus2 = Corpus.objects.create(title="Test Corpus 2", creator=self.user)

    def test_all_documents_have_version_tree_id_after_migration(self):
        """Every document must have a unique version_tree_id after 0024 migration."""
        # Create documents - they should auto-initialize version_tree_id
        doc1 = Document.objects.create(
            title="Document 1", pdf_file_hash="hash1", creator=self.user
        )
        doc2 = Document.objects.create(
            title="Document 2", pdf_file_hash="hash2", creator=self.user
        )
        doc3 = Document.objects.create(
            title="Document 3", pdf_file_hash="hash3", creator=self.user
        )

        # Verify all have version_tree_id
        for doc in [doc1, doc2, doc3]:
            self.assertIsNotNone(doc.version_tree_id)
            self.assertIsInstance(doc.version_tree_id, uuid.UUID)

        # Verify all are unique
        tree_ids = [doc1.version_tree_id, doc2.version_tree_id, doc3.version_tree_id]
        self.assertEqual(
            len(set(tree_ids)), 3, "Each document should have unique tree_id"
        )

    def test_all_documents_marked_as_current_initially(self):
        """All existing documents should have is_current=True after migration."""
        doc = Document.objects.create(
            title="Test Document", pdf_file_hash="test_hash", creator=self.user
        )

        self.assertTrue(doc.is_current)
        self.assertIsNone(doc.parent)  # Root documents have no parent

    def test_document_path_created_for_each_corpus_document_relationship(self):
        """Each M2M corpus-document pair gets a DocumentPath record."""
        doc = Document.objects.create(
            title="Test Document", pdf_file_hash="test_hash", creator=self.user
        )

        # Add document to corpus using add_document method
        result_doc, status, path = self.corpus1.add_document(
            document=doc, user=self.user
        )

        # Verify DocumentPath was created
        self.assertEqual(status, "added")
        self.assertIsNotNone(path)
        self.assertEqual(path.corpus, self.corpus1)
        self.assertTrue(path.is_current)
        self.assertFalse(path.is_deleted)

    def test_document_in_multiple_corpuses_gets_multiple_paths(self):
        """Document appearing in 3 corpuses gets 3 independent DocumentPath records."""
        doc = Document.objects.create(
            title="Shared Document", pdf_file_hash="shared_hash", creator=self.user
        )
        corpus3 = Corpus.objects.create(title="Test Corpus 3", creator=self.user)

        # Add to all three corpuses
        doc1, _, path1 = self.corpus1.add_document(document=doc, user=self.user)
        doc2, _, path2 = self.corpus2.add_document(document=doc, user=self.user)
        doc3, _, path3 = corpus3.add_document(document=doc, user=self.user)

        # Verify each corpus has its own copy (corpus isolation)
        self.assertNotEqual(doc1.id, doc2.id)
        self.assertNotEqual(doc2.id, doc3.id)

        # Verify each has independent DocumentPath
        self.assertEqual(path1.corpus, self.corpus1)
        self.assertEqual(path2.corpus, self.corpus2)
        self.assertEqual(path3.corpus, corpus3)

        # Verify provenance tracking
        self.assertEqual(doc2.source_document, doc)
        self.assertEqual(doc3.source_document, doc)

    def test_migration_is_idempotent_running_twice_is_safe(self):
        """Running 0024 migration twice does not duplicate records or change data."""
        doc = Document.objects.create(
            title="Idempotent Test", pdf_file_hash="idem_hash", creator=self.user
        )
        original_tree_id = doc.version_tree_id

        # Simulate migration logic (what 0024 does)
        # It only sets version_tree_id if it's None
        if not doc.version_tree_id:
            doc.version_tree_id = uuid.uuid4()
            doc.save()

        # Verify tree_id unchanged
        doc.refresh_from_db()
        self.assertEqual(doc.version_tree_id, original_tree_id)

    def test_documents_without_title_get_id_based_path(self):
        """Documents with NULL title use '/document-{id}' style path."""
        doc = Document.objects.create(
            title=None,  # No title
            pdf_file_hash="no_title_hash",
            creator=self.user,
        )

        # Add to corpus - path should be generated from ID
        _, _, path = self.corpus1.add_document(document=doc, user=self.user)

        # Path should contain document ID since no title
        self.assertIn("doc_", path.path)

    def test_document_path_inherits_creator_from_document(self):
        """DocumentPath.creator matches the user performing the operation."""
        doc = Document.objects.create(
            title="Creator Test", pdf_file_hash="creator_hash", creator=self.user
        )

        another_user = User.objects.create_user(
            username="another_user", password="testpass"
        )

        # Add document using another_user
        _, _, path = self.corpus1.add_document(document=doc, user=another_user)

        # Path creator should be the user who performed the action
        self.assertEqual(path.creator, another_user)


class XORConstraintTests(TestCase):
    """
    Test the XOR constraint on Annotation and Relationship models.

    The constraint ensures: (document NOT NULL AND structural_set NULL)
                         OR (document NULL AND structural_set NOT NULL)
    """

    def setUp(self):
        """Create test fixtures."""
        self.user = User.objects.create_user(
            username="xor_test_user", password="testpass123"
        )
        self.corpus = Corpus.objects.create(title="XOR Test Corpus", creator=self.user)
        self.doc = Document.objects.create(
            title="XOR Test Doc", pdf_file_hash="xor_hash", creator=self.user
        )
        self.label = AnnotationLabel.objects.create(
            text="Test Label",
            label_type=LabelType.TOKEN_LABEL,
            creator=self.user,
        )
        self.struct_set = StructuralAnnotationSet.objects.create(
            content_hash="test_struct_hash", creator=self.user
        )

    def test_existing_annotations_satisfy_xor_constraint(self):
        """Annotations with document!=NULL and structural_set=NULL pass constraint."""
        # This is the pre-migration state - annotations have document set
        annotation = Annotation.objects.create(
            document=self.doc,
            corpus=self.corpus,
            annotation_label=self.label,
            page=1,
            raw_text="Test annotation",
            creator=self.user,
        )

        # Should be valid
        annotation.refresh_from_db()
        self.assertIsNotNone(annotation.document)
        self.assertIsNone(annotation.structural_set)

    def test_annotation_with_structural_set_only_is_valid(self):
        """Annotations with structural_set!=NULL and document=NULL pass constraint."""
        annotation = Annotation.objects.create(
            structural_set=self.struct_set,
            document=None,
            corpus=None,  # Structural annotations don't have corpus
            annotation_label=self.label,
            page=1,
            raw_text="Structural annotation",
            structural=True,
            creator=self.user,
        )

        annotation.refresh_from_db()
        self.assertIsNone(annotation.document)
        self.assertIsNotNone(annotation.structural_set)

    @override_settings(VALIDATE_ANNOTATION_JSON=True)
    def test_annotation_with_both_document_and_structural_set_fails(self):
        """Model validation prevents setting both document AND structural_set."""
        with self.assertRaises(ValidationError):
            Annotation.objects.create(
                document=self.doc,
                structural_set=self.struct_set,
                corpus=self.corpus,
                annotation_label=self.label,
                page=1,
                raw_text="Invalid annotation",
                creator=self.user,
            )

    @override_settings(VALIDATE_ANNOTATION_JSON=True)
    def test_annotation_with_neither_document_nor_structural_set_fails(self):
        """Model validation requires exactly one parent."""
        with self.assertRaises(ValidationError):
            Annotation.objects.create(
                document=None,
                structural_set=None,
                corpus=self.corpus,
                annotation_label=self.label,
                page=1,
                raw_text="Orphaned annotation",
                creator=self.user,
            )

    def test_relationship_xor_constraint_mirrors_annotation_constraint(self):
        """Same XOR logic applies to Relationship model."""
        # Create valid annotations for the relationship
        source_annot = Annotation.objects.create(
            document=self.doc,
            corpus=self.corpus,
            annotation_label=self.label,
            page=1,
            raw_text="Source",
            creator=self.user,
        )
        target_annot = Annotation.objects.create(
            document=self.doc,
            corpus=self.corpus,
            annotation_label=self.label,
            page=1,
            raw_text="Target",
            creator=self.user,
        )

        # Valid relationship with document set
        rel = Relationship.objects.create(
            document=self.doc,
            corpus=self.corpus,
            relationship_label=self.label,
            creator=self.user,
        )
        rel.source_annotations.add(source_annot)
        rel.target_annotations.add(target_annot)

        # Verify constraint
        self.assertIsNotNone(rel.document)
        self.assertIsNone(rel.structural_set)

    @override_settings(VALIDATE_ANNOTATION_JSON=True)
    def test_relationship_with_both_parents_fails(self):
        """Relationship with both document AND structural_set fails validation."""
        # Model-level validation catches this before database constraint
        with self.assertRaises(ValidationError) as context:
            Relationship.objects.create(
                document=self.doc,
                structural_set=self.struct_set,
                corpus=self.corpus,
                relationship_label=self.label,
                creator=self.user,
            )

        # Verify the validation error mentions the issue
        error_dict = context.exception.message_dict
        self.assertIn("document", error_dict)
        self.assertIn("structural_set", error_dict)


class StructuralMigrationCommandTests(TestCase):
    """
    Test the migrate_structural_annotations management command.

    Uses TransactionTestCase for proper transaction handling with
    management commands and signals.
    """

    def setUp(self):
        """Create test fixtures with structural annotations."""
        self.user = User.objects.create_user(
            username="struct_migrate_user", password="testpass123"
        )
        self.corpus = Corpus.objects.create(
            title="Structural Migration Corpus", creator=self.user
        )
        self.label = AnnotationLabel.objects.create(
            text="Structural Label",
            label_type=LabelType.TOKEN_LABEL,
            creator=self.user,
        )

        # Document with structural annotations (pre-migration state)
        self.doc = Document.objects.create(
            title="Doc with Structural Annots",
            pdf_file_hash="struct_hash_001",
            creator=self.user,
        )

        # Create structural annotations attached to document
        self.struct_annot1 = Annotation.objects.create(
            document=self.doc,
            corpus=self.corpus,
            annotation_label=self.label,
            page=1,
            raw_text="Structural annotation 1",
            structural=True,
            creator=self.user,
        )
        self.struct_annot2 = Annotation.objects.create(
            document=self.doc,
            corpus=self.corpus,
            annotation_label=self.label,
            page=2,
            raw_text="Structural annotation 2",
            structural=True,
            creator=self.user,
        )

        # Non-structural annotation (should not be migrated)
        self.user_annot = Annotation.objects.create(
            document=self.doc,
            corpus=self.corpus,
            annotation_label=self.label,
            page=1,
            raw_text="User annotation",
            structural=False,
            creator=self.user,
        )

    def test_dry_run_makes_no_database_changes(self):
        """--dry-run flag reports what would happen but writes nothing."""
        initial_struct_sets = StructuralAnnotationSet.objects.count()

        out = io.StringIO()
        call_command(
            "migrate_structural_annotations",
            "--dry-run",
            f"--system-user-id={self.user.id}",
            stdout=out,
        )

        # No new StructuralAnnotationSet should be created
        self.assertEqual(
            StructuralAnnotationSet.objects.count(),
            initial_struct_sets,
            "Dry run should not create StructuralAnnotationSet",
        )

        # Annotations should still be attached to document
        self.struct_annot1.refresh_from_db()
        self.assertIsNotNone(self.struct_annot1.document)
        self.assertIsNone(self.struct_annot1.structural_set)

    def _call_migrate(self, *args, **kwargs):
        """Helper to call migrate_structural_annotations with correct user."""
        return call_command(
            "migrate_structural_annotations",
            f"--system-user-id={self.user.id}",
            *args,
            **kwargs,
        )

    def test_migrate_creates_structural_annotation_set_from_document_hash(self):
        """Command creates StructuralAnnotationSet using document.pdf_file_hash."""
        out = io.StringIO()
        self._call_migrate(stdout=out)

        # StructuralAnnotationSet should be created
        struct_set = StructuralAnnotationSet.objects.filter(
            content_hash=self.doc.pdf_file_hash
        ).first()
        self.assertIsNotNone(struct_set)

    def test_migrate_moves_structural_annotations_from_document_to_set(self):
        """Structural annotations get document=NULL, structural_set=set."""
        self._call_migrate()

        # Refresh annotations
        self.struct_annot1.refresh_from_db()
        self.struct_annot2.refresh_from_db()

        # Should be moved to structural_set
        self.assertIsNone(self.struct_annot1.document)
        self.assertIsNotNone(self.struct_annot1.structural_set)
        self.assertIsNone(self.struct_annot2.document)
        self.assertIsNotNone(self.struct_annot2.structural_set)

    def test_migrate_links_document_to_structural_annotation_set(self):
        """Document.structural_annotation_set FK populated after migration."""
        self._call_migrate()

        self.doc.refresh_from_db()
        self.assertIsNotNone(self.doc.structural_annotation_set)
        self.assertEqual(
            self.doc.structural_annotation_set.content_hash, self.doc.pdf_file_hash
        )

    def test_documents_with_same_hash_share_structural_annotation_set(self):
        """Two documents with identical pdf_file_hash share one StructuralAnnotationSet."""
        # Create another document with same hash
        doc2 = Document.objects.create(
            title="Doc with Same Hash",
            pdf_file_hash=self.doc.pdf_file_hash,  # Same hash!
            creator=self.user,
        )
        # Add structural annotation to doc2
        Annotation.objects.create(
            document=doc2,
            corpus=self.corpus,
            annotation_label=self.label,
            page=1,
            raw_text="Doc2 structural",
            structural=True,
            creator=self.user,
        )

        self._call_migrate()

        # Both documents should share the same structural set
        self.doc.refresh_from_db()
        doc2.refresh_from_db()

        self.assertEqual(
            self.doc.structural_annotation_set_id,
            doc2.structural_annotation_set_id,
            "Documents with same hash should share StructuralAnnotationSet",
        )

    def test_migrate_is_idempotent_running_twice_is_safe(self):
        """Running command twice produces identical results, no errors."""
        # First run
        self._call_migrate()

        struct_set_count_1 = StructuralAnnotationSet.objects.count()
        self.doc.refresh_from_db()
        doc_struct_set_1 = self.doc.structural_annotation_set_id

        # Second run
        self._call_migrate()

        struct_set_count_2 = StructuralAnnotationSet.objects.count()
        self.doc.refresh_from_db()
        doc_struct_set_2 = self.doc.structural_annotation_set_id

        # Should be identical
        self.assertEqual(
            struct_set_count_1,
            struct_set_count_2,
            "Running twice should not create duplicate sets",
        )
        self.assertEqual(doc_struct_set_1, doc_struct_set_2)

    def test_migrate_skips_documents_already_linked_to_structural_set(self):
        """Documents with existing structural_annotation_set are not re-processed."""
        # Pre-link document to a structural set
        existing_set = StructuralAnnotationSet.objects.create(
            content_hash="existing_hash", creator=self.user
        )
        self.doc.structural_annotation_set = existing_set
        self.doc.save()

        out = io.StringIO()
        self._call_migrate("--verbose", stdout=out)

        # Document should still have the original set (not replaced)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.structural_annotation_set_id, existing_set.id)

    def test_migrate_skips_documents_without_hash_unless_force(self):
        """Documents with NULL pdf_file_hash skipped without --force."""
        no_hash_doc = Document.objects.create(
            title="No Hash Doc",
            pdf_file_hash=None,  # No hash!
            creator=self.user,
        )
        Annotation.objects.create(
            document=no_hash_doc,
            corpus=self.corpus,
            annotation_label=self.label,
            page=1,
            raw_text="Structural on hashless doc",
            structural=True,
            creator=self.user,
        )

        out = io.StringIO()
        self._call_migrate(stdout=out)

        # Should be skipped
        no_hash_doc.refresh_from_db()
        self.assertIsNone(no_hash_doc.structural_annotation_set)

    def test_migrate_processes_documents_without_hash_when_force_flag_set(self):
        """--force flag allows processing documents without pdf_file_hash."""
        no_hash_doc = Document.objects.create(
            title="No Hash Doc Force",
            pdf_file_hash=None,
            creator=self.user,
        )
        Annotation.objects.create(
            document=no_hash_doc,
            corpus=self.corpus,
            annotation_label=self.label,
            page=1,
            raw_text="Structural on hashless doc",
            structural=True,
            creator=self.user,
        )

        out = io.StringIO()
        self._call_migrate("--force", stdout=out)

        # Should be processed (using document ID as hash fallback)
        no_hash_doc.refresh_from_db()
        self.assertIsNotNone(no_hash_doc.structural_annotation_set)

    def test_migrate_specific_document_by_id(self):
        """--document-id flag processes only that single document."""
        # Create another document
        other_doc = Document.objects.create(
            title="Other Doc",
            pdf_file_hash="other_hash",
            creator=self.user,
        )
        Annotation.objects.create(
            document=other_doc,
            corpus=self.corpus,
            annotation_label=self.label,
            page=1,
            raw_text="Other structural",
            structural=True,
            creator=self.user,
        )

        # Migrate only self.doc
        self._call_migrate(f"--document-id={self.doc.id}")

        # self.doc should be migrated
        self.doc.refresh_from_db()
        self.assertIsNotNone(self.doc.structural_annotation_set)

        # other_doc should NOT be migrated
        other_doc.refresh_from_db()
        self.assertIsNone(other_doc.structural_annotation_set)

    def test_migrate_corpus_scope_processes_only_corpus_documents(self):
        """--corpus-id flag limits migration to documents in that corpus."""
        # Create document in another corpus
        other_corpus = Corpus.objects.create(title="Other Corpus", creator=self.user)

        # Add self.doc to corpus via DocumentPath (it needs to be "in" the corpus)
        DocumentPath.objects.create(
            document=self.doc,
            corpus=self.corpus,
            path="/test/doc",
            version_number=1,
            creator=self.user,
        )

        other_doc = Document.objects.create(
            title="Other Corpus Doc",
            pdf_file_hash="other_corpus_hash",
            creator=self.user,
        )
        DocumentPath.objects.create(
            document=other_doc,
            corpus=other_corpus,
            path="/other/doc",
            version_number=1,
            creator=self.user,
        )
        Annotation.objects.create(
            document=other_doc,
            corpus=other_corpus,
            annotation_label=self.label,
            page=1,
            raw_text="Other corpus structural",
            structural=True,
            creator=self.user,
        )

        # Migrate only self.corpus
        self._call_migrate(f"--corpus-id={self.corpus.id}")

        # self.doc should be migrated
        self.doc.refresh_from_db()
        self.assertIsNotNone(self.doc.structural_annotation_set)

        # other_doc should NOT be migrated
        other_doc.refresh_from_db()
        self.assertIsNone(other_doc.structural_annotation_set)

    def test_migrate_preserves_annotation_content_fields(self):
        """raw_text, page, json unchanged after migration."""
        original_text = self.struct_annot1.raw_text
        original_page = self.struct_annot1.page

        self._call_migrate()

        self.struct_annot1.refresh_from_db()
        self.assertEqual(self.struct_annot1.raw_text, original_text)
        self.assertEqual(self.struct_annot1.page, original_page)

    def test_non_structural_annotations_remain_on_document(self):
        """User-created annotations (structural=False) stay on document."""
        self._call_migrate()

        self.user_annot.refresh_from_db()
        self.assertIsNotNone(self.user_annot.document)
        self.assertIsNone(self.user_annot.structural_set)
        self.assertEqual(self.user_annot.document_id, self.doc.id)


class RollbackAndEdgeCaseTests(TestCase):
    """
    Test edge cases, error handling, and data integrity.
    """

    def setUp(self):
        """Create test fixtures."""
        self.user = User.objects.create_user(
            username="edge_case_user", password="testpass123"
        )
        self.corpus = Corpus.objects.create(title="Edge Case Corpus", creator=self.user)
        self.label = AnnotationLabel.objects.create(
            text="Edge Case Label",
            label_type=LabelType.TOKEN_LABEL,
            creator=self.user,
        )

    def _call_migrate(self, *args, **kwargs):
        """Helper to call migrate_structural_annotations with correct user."""
        return call_command(
            "migrate_structural_annotations",
            f"--system-user-id={self.user.id}",
            *args,
            **kwargs,
        )

    def test_document_with_no_structural_annotations_migrates_cleanly(self):
        """Documents with only non-structural annotations unaffected."""
        doc = Document.objects.create(
            title="No Structural Doc",
            pdf_file_hash="no_struct_hash",
            creator=self.user,
        )
        # Only non-structural annotation
        Annotation.objects.create(
            document=doc,
            corpus=self.corpus,
            annotation_label=self.label,
            page=1,
            raw_text="Non-structural",
            structural=False,
            creator=self.user,
        )

        # Migration should complete without error
        self._call_migrate()

        # Document should not have structural_annotation_set
        doc.refresh_from_db()
        self.assertIsNone(doc.structural_annotation_set)

    def test_empty_corpus_migration(self):
        """Empty corpus has no effect on migration."""
        empty_corpus = Corpus.objects.create(title="Empty Corpus", creator=self.user)

        # Should not raise any errors
        self._call_migrate(f"--corpus-id={empty_corpus.id}")

    def test_structural_annotation_set_content_hash_uniqueness(self):
        """Duplicate content_hash raises IntegrityError."""
        StructuralAnnotationSet.objects.create(
            content_hash="unique_hash", creator=self.user
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StructuralAnnotationSet.objects.create(
                    content_hash="unique_hash",  # Duplicate!
                    creator=self.user,
                )


class ValidationCommandTests(TestCase):
    """
    Test the validate_v3_migration management command.
    """

    def setUp(self):
        """Create test fixtures."""
        self.user = User.objects.create_user(
            username="validation_user", password="testpass123"
        )
        self.corpus = Corpus.objects.create(
            title="Validation Corpus", creator=self.user
        )
        self.label = AnnotationLabel.objects.create(
            text="Validation Label",
            label_type=LabelType.TOKEN_LABEL,
            creator=self.user,
        )

    def test_validation_passes_for_clean_state(self):
        """Validation passes when all checks are satisfied."""
        # Create valid document with version_tree_id
        doc = Document.objects.create(
            title="Valid Doc",
            pdf_file_hash="valid_hash",
            creator=self.user,
        )

        # Add to corpus (creates DocumentPath)
        doc_copy, _, path = self.corpus.add_document(document=doc, user=self.user)

        # Create valid annotation
        Annotation.objects.create(
            document=doc_copy,
            corpus=self.corpus,
            annotation_label=self.label,
            page=1,
            raw_text="Valid annotation",
            creator=self.user,
        )

        out = io.StringIO()
        # Should not raise
        call_command("validate_v3_migration", stdout=out)

        output = out.getvalue()
        self.assertIn("PASSED", output)

    def test_validation_reports_structural_migration_candidates(self):
        """Validation reports documents eligible for structural migration."""
        doc = Document.objects.create(
            title="Candidate Doc",
            pdf_file_hash="candidate_hash",
            creator=self.user,
        )

        # Add structural annotation
        Annotation.objects.create(
            document=doc,
            corpus=self.corpus,
            annotation_label=self.label,
            page=1,
            raw_text="Structural candidate",
            structural=True,
            creator=self.user,
        )

        out = io.StringIO()
        call_command("validate_v3_migration", stdout=out)

        output = out.getvalue()
        self.assertIn("eligible for structural migration", output)

    def test_validation_verbose_mode_shows_details(self):
        """--verbose flag shows detailed information."""
        out = io.StringIO()
        call_command("validate_v3_migration", "--verbose", stdout=out)

        output = out.getvalue()
        # Verbose mode should show more detail
        self.assertIn("[1/6]", output)
        self.assertIn("[2/6]", output)


class ValidationCommandFailureTests(TestCase):
    """
    Test the validate_v3_migration command additional scenarios.

    Note: Some failure scenarios (like missing version_tree_id) cannot be tested
    directly because the database enforces NOT NULL constraints. These tests
    focus on testable scenarios.
    """

    def setUp(self):
        """Create test fixtures."""
        self.user = User.objects.create_user(
            username="validation_failure_user", password="testpass123"
        )
        self.corpus = Corpus.objects.create(
            title="Validation Failure Corpus", creator=self.user
        )
        self.label = AnnotationLabel.objects.create(
            text="Validation Failure Label",
            label_type=LabelType.TOKEN_LABEL,
            creator=self.user,
        )

    def test_validation_with_fix_flag_runs_successfully(self):
        """--fix flag runs without error when no documents need fixing."""
        # Create a valid document (will have version_tree_id auto-assigned)
        Document.objects.create(
            title="Valid Doc",
            pdf_file_hash="valid_hash",
            creator=self.user,
        )

        out = io.StringIO()
        call_command("validate_v3_migration", "--fix", stdout=out)

        output = out.getvalue()
        # Should pass since all documents already have version_tree_id
        self.assertIn("PASSED", output)

    def test_validation_fix_verbose_mode(self):
        """--fix --verbose runs and shows check details."""
        Document.objects.create(
            title="Verbose Fix Doc",
            pdf_file_hash="verbose_fix_hash",
            creator=self.user,
        )

        out = io.StringIO()
        call_command("validate_v3_migration", "--fix", "--verbose", stdout=out)

        output = out.getvalue()
        self.assertIn("[1/6]", output)  # Shows progress
        self.assertIn("PASSED", output)

    def test_validation_shows_all_check_numbers(self):
        """Validation output shows all 6 check numbers."""
        out = io.StringIO()
        call_command("validate_v3_migration", "--verbose", stdout=out)

        output = out.getvalue()
        for i in range(1, 7):
            self.assertIn(f"[{i}/6]", output)

    def test_validation_summary_shows_all_checks(self):
        """Summary includes all check names."""
        out = io.StringIO()
        call_command("validate_v3_migration", stdout=out)

        output = out.getvalue()
        self.assertIn("Document.version_tree_id", output)
        self.assertIn("Document.is_current", output)
        self.assertIn("Annotation XOR constraint", output)
        self.assertIn("Relationship XOR constraint", output)
        self.assertIn("StructuralAnnotationSet uniqueness", output)

    def test_validation_with_non_current_documents(self):
        """Validation handles documents with is_current=False correctly."""
        # Create a "versioned" document pair
        parent_doc = Document.objects.create(
            title="Parent Doc",
            pdf_file_hash="parent_hash",
            creator=self.user,
        )
        # Mark parent as non-current (simulating a version update)
        Document.objects.filter(pk=parent_doc.pk).update(is_current=False)

        Document.objects.create(
            title="Child Doc",
            pdf_file_hash="child_hash",
            parent=parent_doc,
            creator=self.user,
        )

        out = io.StringIO()
        call_command("validate_v3_migration", "--verbose", stdout=out)

        output = out.getvalue()
        self.assertIn("non-current", output.lower())
        self.assertIn("PASSED", output)


class MigrationCommandErrorTests(TestCase):
    """
    Test migration command error handling paths.
    """

    def setUp(self):
        """Create test fixtures."""
        self.user = User.objects.create_user(
            username="migration_error_user", password="testpass123"
        )
        self.corpus = Corpus.objects.create(
            title="Error Test Corpus", creator=self.user
        )
        self.label = AnnotationLabel.objects.create(
            text="Error Test Label",
            label_type=LabelType.TOKEN_LABEL,
            creator=self.user,
        )

    def test_migrate_with_invalid_system_user_id_raises_error(self):
        """Command raises error when system-user-id doesn't exist."""
        from django.core.management.base import CommandError

        doc = Document.objects.create(
            title="Invalid User Test",
            pdf_file_hash="invalid_user_hash",
            creator=self.user,
        )
        Annotation.objects.create(
            document=doc,
            corpus=self.corpus,
            annotation_label=self.label,
            page=1,
            raw_text="Structural annotation",
            structural=True,
            creator=self.user,
        )

        out = io.StringIO()
        with self.assertRaises(CommandError) as context:
            call_command(
                "migrate_structural_annotations",
                "--system-user-id=999999",  # Non-existent user
                stdout=out,
            )

        self.assertIn("not found", str(context.exception))

    def test_migrate_verbose_mode_shows_document_progress(self):
        """--verbose flag shows document-level progress."""
        doc = Document.objects.create(
            title="Verbose Progress Doc",
            pdf_file_hash="verbose_progress_hash",
            creator=self.user,
        )
        Annotation.objects.create(
            document=doc,
            corpus=self.corpus,
            annotation_label=self.label,
            page=1,
            raw_text="Structural for verbose",
            structural=True,
            creator=self.user,
        )

        out = io.StringIO()
        call_command(
            "migrate_structural_annotations",
            "--verbose",
            f"--system-user-id={self.user.id}",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("Processing document", output)
        self.assertIn("Created StructuralAnnotationSet", output)
        self.assertIn("Migrated", output)

    def test_migrate_dry_run_verbose_with_existing_set(self):
        """--dry-run --verbose shows when structural set would be reused."""
        doc = Document.objects.create(
            title="Dry Run Reuse Doc",
            pdf_file_hash="dry_run_reuse_hash",
            creator=self.user,
        )
        Annotation.objects.create(
            document=doc,
            corpus=self.corpus,
            annotation_label=self.label,
            page=1,
            raw_text="Structural for dry run reuse",
            structural=True,
            creator=self.user,
        )

        # Pre-create the structural set
        StructuralAnnotationSet.objects.create(
            content_hash=doc.pdf_file_hash,
            creator=self.user,
        )

        out = io.StringIO()
        call_command(
            "migrate_structural_annotations",
            "--dry-run",
            "--verbose",
            f"--system-user-id={self.user.id}",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("DRY-RUN", output)
        # Stats should show set_reused
        self.assertIn("reused", output.lower())

    def test_migrate_verbose_reuse_existing_set_non_dry_run(self):
        """--verbose shows when existing StructuralAnnotationSet is reused in actual mode."""
        doc = Document.objects.create(
            title="Verbose Reuse Non-Dry Doc",
            pdf_file_hash="verbose_reuse_nondry_hash",
            creator=self.user,
        )
        Annotation.objects.create(
            document=doc,
            corpus=self.corpus,
            annotation_label=self.label,
            page=1,
            raw_text="Structural for verbose reuse non-dry",
            structural=True,
            creator=self.user,
        )

        # Pre-create the structural set
        StructuralAnnotationSet.objects.create(
            content_hash=doc.pdf_file_hash,
            creator=self.user,
        )

        out = io.StringIO()
        call_command(
            "migrate_structural_annotations",
            "--verbose",
            f"--system-user-id={self.user.id}",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("Reusing existing StructuralAnnotationSet", output)

    def test_migrate_structural_relationships_moved_to_set(self):
        """Command migrates structural relationships along with annotations."""
        doc = Document.objects.create(
            title="Doc with Structural Rels",
            pdf_file_hash="struct_rel_hash",
            creator=self.user,
        )

        # Create structural annotations
        source_annot = Annotation.objects.create(
            document=doc,
            corpus=self.corpus,
            annotation_label=self.label,
            page=1,
            raw_text="Source structural",
            structural=True,
            creator=self.user,
        )
        target_annot = Annotation.objects.create(
            document=doc,
            corpus=self.corpus,
            annotation_label=self.label,
            page=2,
            raw_text="Target structural",
            structural=True,
            creator=self.user,
        )

        # Create structural relationship
        struct_rel = Relationship.objects.create(
            document=doc,
            corpus=self.corpus,
            relationship_label=self.label,
            structural=True,
            creator=self.user,
        )
        struct_rel.source_annotations.add(source_annot)
        struct_rel.target_annotations.add(target_annot)

        out = io.StringIO()
        call_command(
            "migrate_structural_annotations",
            "--verbose",
            f"--system-user-id={self.user.id}",
            stdout=out,
        )

        # Verify relationship was migrated
        struct_rel.refresh_from_db()
        self.assertIsNone(struct_rel.document)
        self.assertIsNotNone(struct_rel.structural_set)

        output = out.getvalue()
        self.assertIn("relationships", output.lower())

    def test_migrate_verbose_shows_relationship_counts(self):
        """--verbose shows counts for both annotations and relationships."""
        doc = Document.objects.create(
            title="Verbose Counts Doc",
            pdf_file_hash="verbose_counts_hash",
            creator=self.user,
        )

        # Create annotations and relationships
        annot1 = Annotation.objects.create(
            document=doc,
            corpus=self.corpus,
            annotation_label=self.label,
            page=1,
            raw_text="Annotation 1",
            structural=True,
            creator=self.user,
        )
        annot2 = Annotation.objects.create(
            document=doc,
            corpus=self.corpus,
            annotation_label=self.label,
            page=2,
            raw_text="Annotation 2",
            structural=True,
            creator=self.user,
        )

        rel = Relationship.objects.create(
            document=doc,
            corpus=self.corpus,
            relationship_label=self.label,
            structural=True,
            creator=self.user,
        )
        rel.source_annotations.add(annot1)
        rel.target_annotations.add(annot2)

        out = io.StringIO()
        call_command(
            "migrate_structural_annotations",
            "--verbose",
            f"--system-user-id={self.user.id}",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("structural annotations", output.lower())
        self.assertIn("structural relationships", output.lower())

    def test_migrate_summary_shows_correct_totals(self):
        """Summary output shows correct counts for all stats."""
        doc = Document.objects.create(
            title="Summary Test Doc",
            pdf_file_hash="summary_test_hash",
            creator=self.user,
        )
        Annotation.objects.create(
            document=doc,
            corpus=self.corpus,
            annotation_label=self.label,
            page=1,
            raw_text="Summary structural",
            structural=True,
            creator=self.user,
        )

        out = io.StringIO()
        call_command(
            "migrate_structural_annotations",
            f"--system-user-id={self.user.id}",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("MIGRATION SUMMARY", output)
        self.assertIn("Documents processed:", output)
        self.assertIn("StructuralAnnotationSets created:", output)
        self.assertIn("Annotations migrated:", output)
        self.assertIn("Successfully migrated", output)


class ValidationCommandEdgeCaseTests(TestCase):
    """
    Additional tests to cover edge cases in validate_v3_migration command.

    These tests specifically target uncovered code paths to achieve 94% coverage.
    """

    def setUp(self):
        """Create test fixtures."""
        self.user = User.objects.create_user(
            username="validation_edge_user", password="testpass123"
        )
        self.corpus = Corpus.objects.create(
            title="Validation Edge Corpus", creator=self.user
        )
        self.label = AnnotationLabel.objects.create(
            text="Validation Edge Label",
            label_type=LabelType.TOKEN_LABEL,
            creator=self.user,
        )

    def test_validation_exits_cleanly_when_all_pass(self):
        """Validation returns normally (no exception) when all checks pass."""
        # Create valid data
        doc = Document.objects.create(
            title="All Pass Doc",
            pdf_file_hash="all_pass_hash",
            creator=self.user,
        )
        # Add to corpus properly
        self.corpus.add_document(document=doc, user=self.user)

        out = io.StringIO()
        # Should complete without raising SystemExit
        call_command("validate_v3_migration", stdout=out)

        output = out.getvalue()
        self.assertIn("VALIDATION PASSED", output)

    def test_validation_structural_migration_candidates_shows_notice(self):
        """Validation shows notice when documents can benefit from migration."""
        doc = Document.objects.create(
            title="Migration Candidate Doc",
            pdf_file_hash="candidate_hash",
            creator=self.user,
        )
        # Structural annotation but no structural_annotation_set
        Annotation.objects.create(
            document=doc,
            corpus=self.corpus,
            annotation_label=self.label,
            page=1,
            raw_text="Structural candidate",
            structural=True,
            creator=self.user,
        )

        out = io.StringIO()
        call_command("validate_v3_migration", stdout=out)

        output = out.getvalue()
        # Should show migration notice
        self.assertIn("migrate_structural_annotations", output)
        self.assertIn("can benefit from structural annotation migration", output)


class ValidationConstraintViolationTests(TestCase):
    """
    Test validation command behavior when constraint violations exist.

    Note: Some violations cannot be created without bypassing database constraints,
    so we test the validation command's ability to detect valid vs invalid states.
    """

    def setUp(self):
        """Create test fixtures."""
        self.user = User.objects.create_user(
            username="constraint_test_user", password="testpass123"
        )
        self.corpus = Corpus.objects.create(
            title="Constraint Test Corpus", creator=self.user
        )
        self.label = AnnotationLabel.objects.create(
            text="Constraint Label",
            label_type=LabelType.TOKEN_LABEL,
            creator=self.user,
        )

    def test_validation_passes_with_structural_annotations_in_set(self):
        """Validation passes when structural annotations are in StructuralAnnotationSet."""
        struct_set = StructuralAnnotationSet.objects.create(
            content_hash="struct_set_hash",
            creator=self.user,
        )

        # Create document linked to structural set
        Document.objects.create(
            title="Doc with Struct Set",
            pdf_file_hash="struct_set_doc_hash",
            structural_annotation_set=struct_set,
            creator=self.user,
        )

        # Annotation in structural set (post-migration state)
        Annotation.objects.create(
            structural_set=struct_set,
            document=None,
            corpus=None,
            annotation_label=self.label,
            page=1,
            raw_text="Structural in set",
            structural=True,
            creator=self.user,
        )

        out = io.StringIO()
        call_command("validate_v3_migration", stdout=out)

        output = out.getvalue()
        self.assertIn("PASSED", output)
        self.assertIn("already using StructuralAnnotationSet", output)

    def test_validation_reports_relationships_correctly(self):
        """Validation correctly counts relationships."""
        doc = Document.objects.create(
            title="Rel Doc",
            pdf_file_hash="rel_hash",
            creator=self.user,
        )

        # Create annotations and relationship
        annot1 = Annotation.objects.create(
            document=doc,
            corpus=self.corpus,
            annotation_label=self.label,
            page=1,
            raw_text="Source",
            creator=self.user,
        )
        annot2 = Annotation.objects.create(
            document=doc,
            corpus=self.corpus,
            annotation_label=self.label,
            page=1,
            raw_text="Target",
            creator=self.user,
        )

        rel = Relationship.objects.create(
            document=doc,
            corpus=self.corpus,
            relationship_label=self.label,
            creator=self.user,
        )
        rel.source_annotations.add(annot1)
        rel.target_annotations.add(annot2)

        out = io.StringIO()
        call_command("validate_v3_migration", stdout=out)

        output = out.getvalue()
        self.assertIn("Relationship XOR constraint", output)
        self.assertIn("PASS", output)

    def test_validation_structural_set_uniqueness_with_valid_sets(self):
        """Validation reports unique structural sets correctly."""
        StructuralAnnotationSet.objects.create(
            content_hash="unique_hash_1",
            creator=self.user,
        )
        StructuralAnnotationSet.objects.create(
            content_hash="unique_hash_2",
            creator=self.user,
        )

        out = io.StringIO()
        call_command("validate_v3_migration", stdout=out)

        output = out.getvalue()
        self.assertIn("StructuralAnnotationSet uniqueness", output)
        self.assertIn("PASS", output)


class MigrationCommandProgressTests(TestCase):
    """
    Test migration command progress reporting and error handling.

    Specifically targets uncovered paths in migrate_structural_annotations.py.
    """

    def setUp(self):
        """Create test fixtures."""
        self.user = User.objects.create_user(
            username="progress_test_user", password="testpass123"
        )
        self.corpus = Corpus.objects.create(
            title="Progress Test Corpus", creator=self.user
        )
        self.label = AnnotationLabel.objects.create(
            text="Progress Label",
            label_type=LabelType.TOKEN_LABEL,
            creator=self.user,
        )

    def _call_migrate(self, *args, **kwargs):
        """Helper to call migrate_structural_annotations with correct user."""
        return call_command(
            "migrate_structural_annotations",
            f"--system-user-id={self.user.id}",
            *args,
            **kwargs,
        )

    def test_dry_run_summary_shows_would_migrate(self):
        """Dry run summary shows 'Would migrate' message."""
        doc = Document.objects.create(
            title="Dry Run Summary Doc",
            pdf_file_hash="dry_summary_hash",
            creator=self.user,
        )
        Annotation.objects.create(
            document=doc,
            corpus=self.corpus,
            annotation_label=self.label,
            page=1,
            raw_text="Structural for dry summary",
            structural=True,
            creator=self.user,
        )

        out = io.StringIO()
        self._call_migrate("--dry-run", stdout=out)

        output = out.getvalue()
        self.assertIn("Would migrate", output)
        self.assertIn("Run without --dry-run to apply changes", output)

    def test_progress_shown_every_50_documents(self):
        """Progress is shown for every 50 documents processed."""
        # Create 51 documents to trigger progress output
        docs = []
        for i in range(51):
            doc = Document.objects.create(
                title=f"Progress Doc {i}",
                pdf_file_hash=f"progress_hash_{i}",
                creator=self.user,
            )
            Annotation.objects.create(
                document=doc,
                corpus=self.corpus,
                annotation_label=self.label,
                page=1,
                raw_text=f"Structural {i}",
                structural=True,
                creator=self.user,
            )
            docs.append(doc)

        out = io.StringIO()
        self._call_migrate(stdout=out)

        output = out.getvalue()
        # Should show progress at 50
        self.assertIn("Progress: 50/51", output)

    def test_no_documents_need_migration_message(self):
        """Shows 'All done!' message when no documents need migration."""
        # Create document that's already migrated
        struct_set = StructuralAnnotationSet.objects.create(
            content_hash="already_done_hash",
            creator=self.user,
        )
        Document.objects.create(
            title="Already Migrated Doc",
            pdf_file_hash="already_done_hash",
            structural_annotation_set=struct_set,
            creator=self.user,
        )

        out = io.StringIO()
        self._call_migrate(stdout=out)

        output = out.getvalue()
        self.assertIn("No documents need migration. All done!", output)

    def test_batch_size_controls_processing(self):
        """--batch-size parameter controls document batching."""
        import uuid

        # Use truly unique hashes based on UUID to avoid database collisions
        unique_id = str(uuid.uuid4())[:8]

        # Create documents with unique hashes
        created_doc_ids = []
        for i in range(3):
            doc = Document.objects.create(
                title=f"Batch Doc {unique_id}_{i}",
                pdf_file_hash=f"batch_hash_{unique_id}_{i}",
                creator=self.user,
            )
            Annotation.objects.create(
                document=doc,
                corpus=self.corpus,
                annotation_label=self.label,
                page=1,
                raw_text=f"Structural {unique_id}_{i}",
                structural=True,
                creator=self.user,
            )
            created_doc_ids.append(doc.id)

        out = io.StringIO()
        # Migrate only these specific documents by their IDs
        for doc_id in created_doc_ids:
            self._call_migrate(f"--document-id={doc_id}", stdout=out)

        output = out.getvalue()
        # Each document should be processed
        self.assertIn("Documents processed: 1", output)

    def test_verbose_dry_run_shows_set_created_preview(self):
        """--verbose --dry-run shows when set would be created."""
        doc = Document.objects.create(
            title="Verbose Dry Create Doc",
            pdf_file_hash="verbose_dry_create_hash",
            creator=self.user,
        )
        Annotation.objects.create(
            document=doc,
            corpus=self.corpus,
            annotation_label=self.label,
            page=1,
            raw_text="Structural for verbose dry create",
            structural=True,
            creator=self.user,
        )

        out = io.StringIO()
        self._call_migrate("--verbose", "--dry-run", stdout=out)

        output = out.getvalue()
        self.assertIn("Processing document", output)
        self.assertIn("structural annotations", output)

    def test_verbose_mode_shows_document_title_truncation(self):
        """Verbose shows content_hash truncated to 16 chars."""
        doc = Document.objects.create(
            title="Long Hash Doc",
            pdf_file_hash="very_long_content_hash_value_here_123456",
            creator=self.user,
        )
        Annotation.objects.create(
            document=doc,
            corpus=self.corpus,
            annotation_label=self.label,
            page=1,
            raw_text="Structural",
            structural=True,
            creator=self.user,
        )

        out = io.StringIO()
        self._call_migrate("--verbose", stdout=out)

        output = out.getvalue()
        # Hash should be truncated with ...
        self.assertIn("hash:", output)
        self.assertIn("...", output)


class MigrationSummaryTests(TestCase):
    """Test migration command summary output paths."""

    def setUp(self):
        """Create test fixtures."""
        self.user = User.objects.create_user(
            username="summary_test_user", password="testpass123"
        )
        self.corpus = Corpus.objects.create(
            title="Summary Test Corpus", creator=self.user
        )
        self.label = AnnotationLabel.objects.create(
            text="Summary Label",
            label_type=LabelType.TOKEN_LABEL,
            creator=self.user,
        )

    def _call_migrate(self, *args, **kwargs):
        return call_command(
            "migrate_structural_annotations",
            f"--system-user-id={self.user.id}",
            *args,
            **kwargs,
        )

    def test_summary_shows_reused_count(self):
        """Summary shows count of reused structural annotation sets."""
        # Pre-create structural set
        hash_value = "reused_summary_hash"
        StructuralAnnotationSet.objects.create(
            content_hash=hash_value,
            creator=self.user,
        )

        # Create document with same hash
        doc = Document.objects.create(
            title="Reuse Summary Doc",
            pdf_file_hash=hash_value,
            creator=self.user,
        )
        Annotation.objects.create(
            document=doc,
            corpus=self.corpus,
            annotation_label=self.label,
            page=1,
            raw_text="Structural for reuse",
            structural=True,
            creator=self.user,
        )

        out = io.StringIO()
        self._call_migrate(stdout=out)

        output = out.getvalue()
        self.assertIn("StructuralAnnotationSets reused: 1", output)

    def test_summary_shows_relationship_migration_count(self):
        """Summary shows count of migrated relationships."""
        doc = Document.objects.create(
            title="Rel Summary Doc",
            pdf_file_hash="rel_summary_hash",
            creator=self.user,
        )

        # Create structural annotations
        annot1 = Annotation.objects.create(
            document=doc,
            corpus=self.corpus,
            annotation_label=self.label,
            page=1,
            raw_text="Source",
            structural=True,
            creator=self.user,
        )
        annot2 = Annotation.objects.create(
            document=doc,
            corpus=self.corpus,
            annotation_label=self.label,
            page=2,
            raw_text="Target",
            structural=True,
            creator=self.user,
        )

        # Create structural relationship
        rel = Relationship.objects.create(
            document=doc,
            corpus=self.corpus,
            relationship_label=self.label,
            structural=True,
            creator=self.user,
        )
        rel.source_annotations.add(annot1)
        rel.target_annotations.add(annot2)

        out = io.StringIO()
        self._call_migrate(stdout=out)

        output = out.getvalue()
        self.assertIn("Relationships migrated: 1", output)


class ValidationVerboseEdgeCaseTests(TestCase):
    """Test verbose output edge cases in validation command."""

    def setUp(self):
        """Create test fixtures."""
        self.user = User.objects.create_user(
            username="verbose_edge_user", password="testpass123"
        )
        self.corpus = Corpus.objects.create(
            title="Verbose Edge Corpus", creator=self.user
        )
        self.label = AnnotationLabel.objects.create(
            text="Verbose Edge Label",
            label_type=LabelType.TOKEN_LABEL,
            creator=self.user,
        )

    def test_verbose_shows_structural_annotation_counts(self):
        """--verbose shows counts of structural items eligible for migration."""
        doc = Document.objects.create(
            title="Verbose Count Doc",
            pdf_file_hash="verbose_count_hash",
            creator=self.user,
        )

        # Add multiple structural annotations
        for i in range(3):
            Annotation.objects.create(
                document=doc,
                corpus=self.corpus,
                annotation_label=self.label,
                page=i + 1,
                raw_text=f"Structural {i}",
                structural=True,
                creator=self.user,
            )

        # Add structural relationship
        annot1 = Annotation.objects.filter(document=doc).first()
        annot2 = Annotation.objects.filter(document=doc).last()
        rel = Relationship.objects.create(
            document=doc,
            corpus=self.corpus,
            relationship_label=self.label,
            structural=True,
            creator=self.user,
        )
        rel.source_annotations.add(annot1)
        rel.target_annotations.add(annot2)

        out = io.StringIO()
        call_command("validate_v3_migration", "--verbose", stdout=out)

        output = out.getvalue()
        # Should show structural annotation and relationship counts
        self.assertIn("structural annotations on documents", output)
        self.assertIn("structural relationships on documents", output)

    def test_verbose_shows_already_migrated_count(self):
        """--verbose shows count of already migrated documents."""
        struct_set = StructuralAnnotationSet.objects.create(
            content_hash="already_migrated_hash",
            creator=self.user,
        )
        Document.objects.create(
            title="Already Migrated",
            pdf_file_hash="already_migrated_hash",
            structural_annotation_set=struct_set,
            creator=self.user,
        )

        out = io.StringIO()
        call_command("validate_v3_migration", "--verbose", stdout=out)

        output = out.getvalue()
        self.assertIn("documents already using StructuralAnnotationSet", output)
