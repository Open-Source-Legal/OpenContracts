"""
Comprehensive tests for Query Optimizer methods with permission filtering.

This test suite provides comprehensive coverage for query optimizer methods that were
previously untested, focusing on:

1. AnnotationService.get_extract_annotation_summary()
   - Tests annotation summaries for extracts with various permission levels
   - Tests label counting and page aggregation
   - Tests access control based on document and corpus permissions

2. RelationshipService.get_document_relationships()
   - Tests relationship retrieval with permission filtering
   - Tests corpus/document/analysis scoping
   - Tests structural vs non-structural relationships
   - Tests extract-based relationship filtering (strict and non-strict modes)
   - Tests page filtering

3. RelationshipService.get_relationship_summary()
   - Tests relationship counting by type
   - Tests permission-based visibility
   - Tests aggregation across multiple relationship types

4. ExtractService.get_visible_extracts()
   - Tests extract visibility based on hybrid permission model
   - Tests corpus-level filtering
   - Tests that extract permission + corpus permission both required
   - Tests list-based filtering for users with various permission levels
"""

import logging

from django.core.files.base import ContentFile
from django.db import transaction
from django.test import TestCase

from opencontractserver.analyzer.models import Analysis, Analyzer, GremlinEngine
from opencontractserver.annotations.models import (
    RELATIONSHIP_LABEL,
    TOKEN_LABEL,
    Annotation,
    AnnotationLabel,
    Relationship,
)
from opencontractserver.annotations.services import (
    AnnotationService,
    RelationshipService,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.extracts.models import Column, Datacell, Extract, Fieldset
from opencontractserver.extracts.services import ExtractService
from opencontractserver.tests.fixtures import SAMPLE_PDF_FILE_ONE_PATH
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.users.models import User
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

logger = logging.getLogger(__name__)


class AnnotationServiceTestCase(TestCase):
    """
    Tests for AnnotationService.get_extract_annotation_summary()
    """

    def setUp(self):
        """Set up test scenario with extracts and annotations"""
        logger.info("\n" + "=" * 80)
        logger.info("SETTING UP ANNOTATION QUERY OPTIMIZER TEST")
        logger.info("=" * 80)

        # Create users
        self.owner = User.objects.create_user(username="owner", password="test123")
        self.collaborator = User.objects.create_user(
            username="collaborator", password="test123"
        )
        self.stranger = User.objects.create_user(
            username="stranger", password="test123"
        )
        self.superuser = User.objects.create_superuser(
            username="superuser", password="admin"
        )

        # Create documents
        self.doc1 = self._create_document("Doc 1", self.owner)
        self.doc2 = self._create_document("Doc 2", self.owner)

        # Create corpus
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )
        self.corpus.add_document(document=self.doc1, user=self.owner)
        self.corpus.add_document(document=self.doc2, user=self.owner)

        # Create annotation labels
        self.label1 = AnnotationLabel.objects.create(
            label_type=TOKEN_LABEL, text="Contract Term", creator=self.owner
        )
        self.label2 = AnnotationLabel.objects.create(
            label_type=TOKEN_LABEL, text="Party Name", creator=self.owner
        )

        # Create fieldset and extract
        self.fieldset = Fieldset.objects.create(
            name="Test Fieldset", creator=self.owner
        )
        self.column = Column.objects.create(
            name="Test Column",
            fieldset=self.fieldset,
            query="Test query",
            output_type="string",
            creator=self.owner,
        )
        self.extract = Extract.objects.create(
            name="Test Extract",
            corpus=self.corpus,
            fieldset=self.fieldset,
            creator=self.owner,
        )
        self.extract.documents.add(self.doc1, self.doc2)

        # Create annotations on different pages with different labels
        self.ann1 = Annotation.objects.create(
            annotation_label=self.label1,
            document=self.doc1,
            corpus=self.corpus,
            creator=self.owner,
            page=1,
            raw_text="Term A",
        )
        self.ann2 = Annotation.objects.create(
            annotation_label=self.label1,
            document=self.doc1,
            corpus=self.corpus,
            creator=self.owner,
            page=2,
            raw_text="Term B",
        )
        self.ann3 = Annotation.objects.create(
            annotation_label=self.label2,
            document=self.doc1,
            corpus=self.corpus,
            creator=self.owner,
            page=1,
            raw_text="Party X",
        )

        # Create datacells that reference these annotations as sources
        self.datacell1 = Datacell.objects.create(
            creator=self.owner,
            extract=self.extract,
            column=self.column,
            document=self.doc1,
            data={"value": "Data 1"},
            data_definition="Test data",
        )
        self.datacell1.sources.add(self.ann1, self.ann2)

        self.datacell2 = Datacell.objects.create(
            creator=self.owner,
            extract=self.extract,
            column=self.column,
            document=self.doc1,
            data={"value": "Data 2"},
            data_definition="Test data",
        )
        self.datacell2.sources.add(self.ann3)

        logger.info("Setup complete!")

    def _create_document(self, title, creator):
        """Helper to create a document with a real PDF"""
        with transaction.atomic():
            doc = Document.objects.create(
                title=title,
                description=f"Test document: {title}",
                creator=creator,
                is_public=False,
            )
            with SAMPLE_PDF_FILE_ONE_PATH.open("rb") as test_pdf:
                pdf_contents = ContentFile(test_pdf.read())
                doc.pdf_file.save("test.pdf", pdf_contents)
            return doc

    def test_get_extract_annotation_summary_owner(self):
        """
        Owner should see complete summary of all annotations in extract.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Owner sees complete extract annotation summary")
        logger.info("=" * 80)

        # Give owner full permissions
        set_permissions_for_obj_to_user(self.owner, self.doc1, [PermissionTypes.READ])
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.READ])

        summary = AnnotationService.get_extract_annotation_summary(
            document_id=self.doc1.id,
            extract_id=self.extract.id,
            user=self.owner,
        )

        # Should see all 3 annotations
        self.assertEqual(summary["total_source_annotations"], 3)

        # Should see correct label counts
        self.assertEqual(summary["by_label"]["Contract Term"], 2)
        self.assertEqual(summary["by_label"]["Party Name"], 1)

        # Should see both pages
        self.assertIn(1, summary["pages_with_sources"])
        self.assertIn(2, summary["pages_with_sources"])

        logger.info("✓ Owner sees complete annotation summary")

    def test_get_extract_annotation_summary_no_document_permission(self):
        """
        User without document READ permission should see empty summary.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: No document permission = empty summary")
        logger.info("=" * 80)

        # Give stranger corpus permission but NOT document permission
        set_permissions_for_obj_to_user(
            self.stranger, self.corpus, [PermissionTypes.READ]
        )

        summary = AnnotationService.get_extract_annotation_summary(
            document_id=self.doc1.id,
            extract_id=self.extract.id,
            user=self.stranger,
        )

        # Should see nothing
        self.assertEqual(summary["total_source_annotations"], 0)
        self.assertEqual(summary["by_label"], {})
        self.assertEqual(summary["pages_with_sources"], [])

        logger.info("✓ User without document permission sees empty summary")

    def test_get_extract_annotation_summary_superuser(self):
        """
        A no-grant superuser is computed like a stranger: with no READ on the
        private document/corpus it sees an empty summary. Once granted (or as
        creator) it sees the summary through the normal permission path.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: No-grant superuser sees empty; granted superuser sees all")
        logger.info("=" * 80)

        # No grants → no-grant superuser is a stranger → empty summary.
        summary = AnnotationService.get_extract_annotation_summary(
            document_id=self.doc1.id,
            extract_id=self.extract.id,
            user=self.superuser,
        )
        self.assertEqual(summary["total_source_annotations"], 0)
        self.assertEqual(summary["by_label"], {})
        self.assertEqual(summary["pages_with_sources"], [])

        # Grant the superuser READ on doc + corpus → normal path grants access.
        set_permissions_for_obj_to_user(
            self.superuser, self.doc1, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.superuser, self.corpus, [PermissionTypes.READ]
        )

        summary = AnnotationService.get_extract_annotation_summary(
            document_id=self.doc1.id,
            extract_id=self.extract.id,
            user=self.superuser,
        )
        self.assertEqual(summary["total_source_annotations"], 3)
        self.assertEqual(summary["by_label"]["Contract Term"], 2)
        self.assertEqual(summary["by_label"]["Party Name"], 1)

        logger.info("✓ Superuser computed like a normal user (denied → granted)")

    def test_get_extract_annotation_summary_nonexistent_extract(self):
        """
        Test behavior with non-existent extract (should handle gracefully).
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Non-existent extract handled gracefully")
        logger.info("=" * 80)

        set_permissions_for_obj_to_user(self.owner, self.doc1, [PermissionTypes.READ])
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.READ])

        summary = AnnotationService.get_extract_annotation_summary(
            document_id=self.doc1.id,
            extract_id=99999,  # Non-existent ID
            user=self.owner,
        )

        # Should return empty summary
        self.assertEqual(summary["total_source_annotations"], 0)
        self.assertEqual(summary["by_label"], {})
        self.assertEqual(summary["pages_with_sources"], [])

        logger.info("✓ Non-existent extract returns empty summary")

    def test_compute_effective_permissions_anonymous_user_public_doc(self):
        """
        Test that anonymous users can read public documents/corpuses.
        """
        from django.contrib.auth.models import AnonymousUser

        logger.info("\n" + "=" * 80)
        logger.info("TEST: Anonymous user can access public document")
        logger.info("=" * 80)

        # Make document and corpus public
        self.doc1.is_public = True
        self.doc1.save()
        self.corpus.is_public = True
        self.corpus.save()

        anon_user = AnonymousUser()

        (
            can_read,
            can_create,
            can_update,
            can_delete,
            can_comment,
        ) = AnnotationService._compute_effective_permissions(
            user=anon_user, document_id=self.doc1.id, corpus_id=self.corpus.id
        )

        # Anonymous user should have read permission for public doc/corpus
        self.assertTrue(can_read, "Anonymous user should read public document")

        # But no write/update/delete permissions
        self.assertFalse(can_create, "Anonymous user should not create annotations")
        self.assertFalse(can_update, "Anonymous user should not update annotations")
        self.assertFalse(can_delete, "Anonymous user should not delete annotations")
        self.assertFalse(can_comment, "Anonymous user should not comment")

        logger.info("✓ Anonymous user has read-only access to public resources")

    def test_compute_effective_permissions_anonymous_user_private_doc(self):
        """
        Test that anonymous users cannot access private documents/corpuses.
        """
        from django.contrib.auth.models import AnonymousUser

        logger.info("\n" + "=" * 80)
        logger.info("TEST: Anonymous user blocked from private document")
        logger.info("=" * 80)

        # Document and corpus are private by default
        anon_user = AnonymousUser()

        (
            can_read,
            can_create,
            can_update,
            can_delete,
            can_comment,
        ) = AnnotationService._compute_effective_permissions(
            user=anon_user, document_id=self.doc1.id, corpus_id=self.corpus.id
        )

        # Anonymous user should have NO permissions for private resources
        self.assertFalse(can_read, "Anonymous user should not read private document")
        self.assertFalse(can_create, "Anonymous user should not create annotations")
        self.assertFalse(can_update, "Anonymous user should not update annotations")
        self.assertFalse(can_delete, "Anonymous user should not delete annotations")
        self.assertFalse(can_comment, "Anonymous user should not comment")

        logger.info("✓ Anonymous user blocked from private resources")

    def test_compute_effective_permissions_anonymous_user_public_doc_private_corpus(
        self,
    ):
        """
        Test that anonymous users need both document AND corpus to be public.
        """
        from django.contrib.auth.models import AnonymousUser

        logger.info("\n" + "=" * 80)
        logger.info("TEST: Anonymous user needs both doc and corpus public")
        logger.info("=" * 80)

        # Make only document public, corpus stays private
        self.doc1.is_public = True
        self.doc1.save()

        anon_user = AnonymousUser()

        (
            can_read,
            can_create,
            can_update,
            can_delete,
            can_comment,
        ) = AnnotationService._compute_effective_permissions(
            user=anon_user, document_id=self.doc1.id, corpus_id=self.corpus.id
        )

        # Should be blocked because corpus is private
        self.assertFalse(can_read, "Should be blocked by private corpus")

        logger.info("✓ Private corpus blocks anonymous access even with public doc")

    def test_get_visible_analyses_anonymous_user(self):
        """
        Test that anonymous users can only see public analyses.
        """
        from django.contrib.auth.models import AnonymousUser

        from opencontractserver.analyzer.services import AnalysisService

        logger.info("\n" + "=" * 80)
        logger.info("TEST: Anonymous user sees only public analyses")
        logger.info("=" * 80)

        # Make corpus public
        self.corpus.is_public = True
        self.corpus.save()

        # Create an analyzer
        gremlin = GremlinEngine.objects.create(
            url="http://test.com", creator=self.owner
        )
        analyzer = Analyzer.objects.create(
            description="Test", creator=self.owner, host_gremlin=gremlin
        )

        # Create public and private analyses
        public_analysis = Analysis.objects.create(
            analyzer=analyzer,
            analyzed_corpus=self.corpus,
            creator=self.owner,
            is_public=True,
        )
        private_analysis = Analysis.objects.create(
            analyzer=analyzer,
            analyzed_corpus=self.corpus,
            creator=self.owner,
            is_public=False,
        )

        anon_user = AnonymousUser()

        visible = AnalysisService.get_visible_analyses(
            user=anon_user, corpus_id=self.corpus.id
        )

        # Should only see public analysis
        visible_ids = [a.id for a in visible]
        self.assertIn(public_analysis.id, visible_ids)
        self.assertNotIn(private_analysis.id, visible_ids)

        logger.info("✓ Anonymous user sees only public analyses")

    def test_compute_effective_permissions_anonymous_user_public_doc_no_corpus(self):
        """
        Test that anonymous users can access public documents without a corpus.
        """
        from django.contrib.auth.models import AnonymousUser

        logger.info("\n" + "=" * 80)
        logger.info("TEST: Anonymous user accessing public doc without corpus")
        logger.info("=" * 80)

        # Make document public
        self.doc1.is_public = True
        self.doc1.save()

        anon_user = AnonymousUser()

        (
            can_read,
            can_create,
            can_update,
            can_delete,
            can_comment,
        ) = AnnotationService._compute_effective_permissions(
            user=anon_user, document_id=self.doc1.id, corpus_id=None
        )

        # Anonymous user should only have read permission
        self.assertTrue(can_read, "Anonymous user should read public document")
        self.assertFalse(can_create, "Anonymous user cannot create annotations")
        self.assertFalse(can_update, "Anonymous user cannot update annotations")
        self.assertFalse(can_delete, "Anonymous user cannot delete annotations")
        self.assertFalse(can_comment, "Anonymous user cannot comment")

        logger.info("✓ Anonymous user can read public doc without corpus")

    def test_compute_effective_permissions_nonexistent_document(self):
        """
        Test that accessing a nonexistent document returns all False permissions.
        """
        from django.contrib.auth.models import AnonymousUser

        logger.info("\n" + "=" * 80)
        logger.info("TEST: Nonexistent document returns no permissions")
        logger.info("=" * 80)

        anon_user = AnonymousUser()

        # Use a document ID that doesn't exist
        nonexistent_id = 999999

        (
            can_read,
            can_create,
            can_update,
            can_delete,
            can_comment,
        ) = AnnotationService._compute_effective_permissions(
            user=anon_user, document_id=nonexistent_id, corpus_id=None
        )

        # All permissions should be False for nonexistent document
        self.assertFalse(can_read, "Should not read nonexistent document")
        self.assertFalse(can_create, "Should not create on nonexistent document")
        self.assertFalse(can_update, "Should not update on nonexistent document")
        self.assertFalse(can_delete, "Should not delete on nonexistent document")
        self.assertFalse(can_comment, "Should not comment on nonexistent document")

        logger.info("✓ Nonexistent document properly denied")


class RelationshipServiceTestCase(TestCase):
    """
    Tests for RelationshipService methods:
    - get_document_relationships()
    - get_relationship_summary()
    """

    def setUp(self):
        """Set up test scenario with relationships"""
        logger.info("\n" + "=" * 80)
        logger.info("SETTING UP RELATIONSHIP QUERY OPTIMIZER TEST")
        logger.info("=" * 80)

        # Create users
        self.owner = User.objects.create_user(username="owner", password="test123")
        self.collaborator = User.objects.create_user(
            username="collaborator", password="test123"
        )
        self.stranger = User.objects.create_user(
            username="stranger", password="test123"
        )
        self.superuser = User.objects.create_superuser(
            username="superuser", password="admin"
        )

        # Create documents
        self.doc1 = self._create_document("Doc 1", self.owner)

        # Create corpus
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )
        self.corpus.add_document(document=self.doc1, user=self.owner)

        # Create labels
        self.token_label = AnnotationLabel.objects.create(
            label_type=TOKEN_LABEL, text="Entity", creator=self.owner
        )
        self.rel_label1 = AnnotationLabel.objects.create(
            label_type=RELATIONSHIP_LABEL, text="References", creator=self.owner
        )
        self.rel_label2 = AnnotationLabel.objects.create(
            label_type=RELATIONSHIP_LABEL, text="Defines", creator=self.owner
        )

        # Create annotations on different pages
        self.ann1 = Annotation.objects.create(
            annotation_label=self.token_label,
            document=self.doc1,
            corpus=self.corpus,
            creator=self.owner,
            page=1,
            raw_text="Entity A",
        )
        self.ann2 = Annotation.objects.create(
            annotation_label=self.token_label,
            document=self.doc1,
            corpus=self.corpus,
            creator=self.owner,
            page=2,
            raw_text="Entity B",
        )
        self.ann3 = Annotation.objects.create(
            annotation_label=self.token_label,
            document=self.doc1,
            corpus=self.corpus,
            creator=self.owner,
            page=1,
            raw_text="Entity C",
        )

        # Create structural annotation (no corpus)
        self.structural_ann = Annotation.objects.create(
            annotation_label=self.token_label,
            document=self.doc1,
            creator=self.owner,
            page=1,
            raw_text="Structural Entity",
            structural=True,
        )

        # Create relationships
        # Relationship 1: References (page 1 -> page 2)
        self.rel1 = Relationship.objects.create(
            relationship_label=self.rel_label1,
            document=self.doc1,
            corpus=self.corpus,
            creator=self.owner,
        )
        self.rel1.source_annotations.add(self.ann1)
        self.rel1.target_annotations.add(self.ann2)

        # Relationship 2: References (page 1 -> page 1)
        self.rel2 = Relationship.objects.create(
            relationship_label=self.rel_label1,
            document=self.doc1,
            corpus=self.corpus,
            creator=self.owner,
        )
        self.rel2.source_annotations.add(self.ann1)
        self.rel2.target_annotations.add(self.ann3)

        # Relationship 3: Defines (page 2 -> page 1)
        self.rel3 = Relationship.objects.create(
            relationship_label=self.rel_label2,
            document=self.doc1,
            corpus=self.corpus,
            creator=self.owner,
        )
        self.rel3.source_annotations.add(self.ann2)
        self.rel3.target_annotations.add(self.ann3)

        # Structural relationship (no corpus)
        self.structural_rel = Relationship.objects.create(
            relationship_label=self.rel_label1,
            document=self.doc1,
            creator=self.owner,
            structural=True,
        )
        self.structural_rel.source_annotations.add(self.structural_ann)
        self.structural_rel.target_annotations.add(self.ann1)

        # Create analysis for testing analysis-specific filtering
        self._setup_analysis()

        # Create extract for testing extract-based filtering
        self._setup_extract()

        logger.info("Setup complete!")

    def _create_document(self, title, creator):
        """Helper to create a document with a real PDF"""
        with transaction.atomic():
            doc = Document.objects.create(
                title=title,
                description=f"Test document: {title}",
                creator=creator,
                is_public=False,
            )
            with SAMPLE_PDF_FILE_ONE_PATH.open("rb") as test_pdf:
                pdf_contents = ContentFile(test_pdf.read())
                doc.pdf_file.save("test.pdf", pdf_contents)
            return doc

    def _setup_analysis(self):
        """Set up analysis infrastructure"""
        self.gremlin = GremlinEngine.objects.create(
            url="http://dummy-gremlin:8000", creator=self.owner
        )
        self.analyzer = Analyzer.objects.create(
            id="TEST.ANALYZER",
            host_gremlin=self.gremlin,
            creator=self.owner,
        )
        self.analysis = Analysis.objects.create(
            analyzer=self.analyzer,
            analyzed_corpus=self.corpus,
            creator=self.owner,
            is_public=True,
        )
        self.analysis.analyzed_documents.add(self.doc1)

        # Create an analysis-specific relationship
        self.analysis_rel = Relationship.objects.create(
            relationship_label=self.rel_label1,
            document=self.doc1,
            corpus=self.corpus,
            analysis=self.analysis,
            creator=self.owner,
        )
        self.analysis_rel.source_annotations.add(self.ann1)
        self.analysis_rel.target_annotations.add(self.ann2)

    def _setup_extract(self):
        """Set up extract infrastructure"""
        self.fieldset = Fieldset.objects.create(
            name="Test Fieldset", creator=self.owner
        )
        self.column = Column.objects.create(
            name="Test Column",
            fieldset=self.fieldset,
            query="Test query",
            output_type="string",
            creator=self.owner,
        )
        self.extract = Extract.objects.create(
            name="Test Extract",
            corpus=self.corpus,
            fieldset=self.fieldset,
            creator=self.owner,
        )
        self.extract.documents.add(self.doc1)

        # Create datacells that reference annotations
        self.datacell1 = Datacell.objects.create(
            creator=self.owner,
            extract=self.extract,
            column=self.column,
            document=self.doc1,
            data={"value": "Data 1"},
            data_definition="Test data",
        )
        self.datacell1.sources.add(self.ann1, self.ann2)

    # =========================================================================
    # Tests for get_document_relationships()
    # =========================================================================

    def test_get_document_relationships_owner(self):
        """
        Owner with full permissions should see manual relationships in corpus.
        When analysis_id is not provided, only manual relationships are returned.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Owner sees all relationships")
        logger.info("=" * 80)

        set_permissions_for_obj_to_user(self.owner, self.doc1, [PermissionTypes.READ])
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.READ])

        qs = RelationshipService.get_document_relationships(
            document_id=self.doc1.id,
            user=self.owner,
            corpus_id=self.corpus.id,
        )

        # Should see only manual relationships (rel1, rel2, rel3)
        # analysis_rel is filtered out because analysis_id is not specified
        self.assertEqual(qs.count(), 3)

        logger.info("✓ Owner sees all manual corpus relationships")

    def test_get_document_relationships_no_permission(self):
        """
        User without document permission should see no relationships.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: No permission = no relationships")
        logger.info("=" * 80)

        # Don't grant any permissions to stranger

        qs = RelationshipService.get_document_relationships(
            document_id=self.doc1.id,
            user=self.stranger,
            corpus_id=self.corpus.id,
        )

        self.assertEqual(qs.count(), 0)

        logger.info("✓ User without permission sees no relationships")

    def test_get_document_relationships_structural_only(self):
        """
        Without corpus_id, should only see structural relationships.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: No corpus = structural relationships only")
        logger.info("=" * 80)

        set_permissions_for_obj_to_user(self.owner, self.doc1, [PermissionTypes.READ])

        qs = RelationshipService.get_document_relationships(
            document_id=self.doc1.id,
            user=self.owner,
            corpus_id=None,  # No corpus
        )

        # Should see only structural relationship
        self.assertEqual(qs.count(), 1)
        self.assertTrue(qs[0].structural)

        logger.info("✓ Without corpus, only structural relationships visible")

    def test_get_document_relationships_by_analysis(self):
        """
        Filtering by analysis_id should only return relationships from that analysis.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Analysis filtering works correctly")
        logger.info("=" * 80)

        set_permissions_for_obj_to_user(self.owner, self.doc1, [PermissionTypes.READ])
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.READ])

        qs = RelationshipService.get_document_relationships(
            document_id=self.doc1.id,
            user=self.owner,
            corpus_id=self.corpus.id,
            analysis_id=self.analysis.id,
        )

        # Should see only the analysis relationship
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs[0].analysis, self.analysis)

        logger.info("✓ Analysis filtering returns only analysis relationships")

    def test_get_document_relationships_by_pages(self):
        """
        Filtering by pages should return relationships with annotations on those pages.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Page filtering works correctly")
        logger.info("=" * 80)

        set_permissions_for_obj_to_user(self.owner, self.doc1, [PermissionTypes.READ])
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.READ])

        # Filter to only page 1
        qs = RelationshipService.get_document_relationships(
            document_id=self.doc1.id,
            user=self.owner,
            corpus_id=self.corpus.id,
            pages=[1],
        )

        # Should see relationships with at least one annotation on page 1
        # All our relationships have at least one annotation on page 1
        self.assertGreater(qs.count(), 0)

        logger.info("✓ Page filtering returns correct relationships")

    def test_get_document_relationships_extract_mode(self):
        """
        Extract filtering should return relationships connected to extract annotations.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Extract filtering works correctly")
        logger.info("=" * 80)

        set_permissions_for_obj_to_user(self.owner, self.doc1, [PermissionTypes.READ])
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.READ])

        # Non-strict mode: either source or target in extract
        qs = RelationshipService.get_document_relationships(
            document_id=self.doc1.id,
            user=self.owner,
            corpus_id=self.corpus.id,
            extract_id=self.extract.id,
            strict_extract_mode=False,
        )

        # Should see relationships involving ann1 or ann2 (in extract)
        self.assertGreater(qs.count(), 0)

        # Strict mode: both source and target must be in extract
        qs_strict = RelationshipService.get_document_relationships(
            document_id=self.doc1.id,
            user=self.owner,
            corpus_id=self.corpus.id,
            extract_id=self.extract.id,
            strict_extract_mode=True,
        )

        # Should only see relationships where both ends are in extract
        # ann1 and ann2 are both in extract, so relationships between them qualify
        self.assertGreater(qs_strict.count(), 0)

        logger.info("✓ Extract filtering (strict and non-strict) works correctly")

    def test_get_document_relationships_superuser(self):
        """
        A no-grant superuser is computed like a stranger: with no READ on the
        private document/corpus it sees no relationships. Once granted READ it
        sees the manual relationships through the normal permission path.
        When analysis_id is not provided, only manual relationships are returned.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: No-grant superuser sees none; granted superuser sees all")
        logger.info("=" * 80)

        # No grants → no-grant superuser is a stranger → no relationships.
        qs = RelationshipService.get_document_relationships(
            document_id=self.doc1.id,
            user=self.superuser,
            corpus_id=self.corpus.id,
        )
        self.assertEqual(qs.count(), 0)

        # Grant READ on doc + corpus → normal path grants access.
        set_permissions_for_obj_to_user(
            self.superuser, self.doc1, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.superuser, self.corpus, [PermissionTypes.READ]
        )

        qs = RelationshipService.get_document_relationships(
            document_id=self.doc1.id,
            user=self.superuser,
            corpus_id=self.corpus.id,
        )
        # Should see manual corpus-based relationships (rel1, rel2, rel3)
        # analysis_rel is filtered out because analysis_id is not specified
        self.assertEqual(qs.count(), 3)

        logger.info("✓ Superuser computed like a normal user (denied → granted)")

    def test_get_document_relationships_structural_filter(self):
        """
        Testing explicit structural filter parameter.
        When analysis_id is not provided, only manual relationships are returned.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Structural filter works correctly")
        logger.info("=" * 80)

        set_permissions_for_obj_to_user(self.owner, self.doc1, [PermissionTypes.READ])
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.READ])

        # Filter to only non-structural
        qs = RelationshipService.get_document_relationships(
            document_id=self.doc1.id,
            user=self.owner,
            corpus_id=self.corpus.id,
            structural=False,
        )

        # All our manual corpus relationships are non-structural (rel1, rel2, rel3)
        # analysis_rel is filtered out because analysis_id is not specified
        self.assertEqual(qs.count(), 3)
        for rel in qs:
            self.assertFalse(rel.structural)

        logger.info("✓ Structural filter correctly filters relationships")

    def test_get_document_relationships_private_analysis(self):
        """
        Relationships created by a private analysis should only be visible to users
        with access to that analysis.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Privacy filtering for analysis-created relationships")
        logger.info("=" * 80)

        set_permissions_for_obj_to_user(self.owner, self.doc1, [PermissionTypes.READ])
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.READ])
        set_permissions_for_obj_to_user(
            self.stranger, self.doc1, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.stranger, self.corpus, [PermissionTypes.READ]
        )

        # Create a private analysis (not public, owned by owner)
        from opencontractserver.analyzer.models import Analysis, Analyzer, GremlinEngine

        gremlin = GremlinEngine.objects.create(
            url="http://test-gremlin:8000", creator=self.owner
        )
        analyzer = Analyzer.objects.create(
            id="TEST.PRIVATE.ANALYZER",
            host_gremlin=gremlin,
            creator=self.owner,
        )
        private_analysis = Analysis.objects.create(
            analyzer=analyzer,
            analyzed_corpus=self.corpus,
            creator=self.owner,
            is_public=False,  # Private!
        )

        # Create a relationship with created_by_analysis set
        private_rel = Relationship.objects.create(
            relationship_label=self.rel_label1,
            document=self.doc1,
            corpus=self.corpus,
            analysis=private_analysis,
            created_by_analysis=private_analysis,  # Mark as private
            creator=self.owner,
        )
        private_rel.source_annotations.add(self.ann1)
        private_rel.target_annotations.add(self.ann2)

        # Owner should see it (they created the analysis)
        qs_owner = RelationshipService.get_document_relationships(
            document_id=self.doc1.id,
            user=self.owner,
            corpus_id=self.corpus.id,
            analysis_id=private_analysis.id,
        )
        self.assertGreater(qs_owner.count(), 0)

        # Stranger should NOT see it (no access to private analysis)
        qs_stranger = RelationshipService.get_document_relationships(
            document_id=self.doc1.id,
            user=self.stranger,
            corpus_id=self.corpus.id,
            analysis_id=private_analysis.id,
        )
        self.assertEqual(qs_stranger.count(), 0)

        logger.info("✓ Privacy filtering works for analysis-created relationships")

    def test_get_document_relationships_private_extract(self):
        """
        Relationships created by a private extract should only be visible to users
        with access to that extract.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Privacy filtering for extract-created relationships")
        logger.info("=" * 80)

        set_permissions_for_obj_to_user(self.owner, self.doc1, [PermissionTypes.READ])
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.READ])
        set_permissions_for_obj_to_user(
            self.stranger, self.doc1, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.stranger, self.corpus, [PermissionTypes.READ]
        )

        # Create a private extract
        from opencontractserver.extracts.models import Extract, Fieldset

        private_fieldset = Fieldset.objects.create(
            name="Private Fieldset", creator=self.owner
        )
        private_extract = Extract.objects.create(
            name="Private Extract",
            corpus=self.corpus,
            fieldset=private_fieldset,
            creator=self.owner,
        )

        # Create a relationship with created_by_extract set
        private_rel = Relationship.objects.create(
            relationship_label=self.rel_label1,
            document=self.doc1,
            corpus=self.corpus,
            created_by_extract=private_extract,  # Mark as private
            creator=self.owner,
        )
        private_rel.source_annotations.add(self.ann1)
        private_rel.target_annotations.add(self.ann2)

        # Owner should see it (they created the extract)
        qs_owner = RelationshipService.get_document_relationships(
            document_id=self.doc1.id,
            user=self.owner,
            corpus_id=self.corpus.id,
        )
        # Count includes manual relationships + extract relationship
        owner_count = qs_owner.count()
        self.assertGreater(owner_count, 0)

        # Stranger should see the 3 manual relationships but NOT the extract-created one
        qs_stranger = RelationshipService.get_document_relationships(
            document_id=self.doc1.id,
            user=self.stranger,
            corpus_id=self.corpus.id,
        )
        # Should see 3 manual relationships (rel1, rel2, rel3) but NOT the extract-created one
        stranger_count_before = qs_stranger.count()
        self.assertEqual(stranger_count_before, 3)

        # Give stranger access to extract
        set_permissions_for_obj_to_user(
            self.stranger, private_extract, [PermissionTypes.READ]
        )

        # Now stranger should see the extract-created relationship too
        qs_stranger_with_access = RelationshipService.get_document_relationships(
            document_id=self.doc1.id,
            user=self.stranger,
            corpus_id=self.corpus.id,
        )
        # Should now see 4 relationships (3 manual + 1 extract-created)
        self.assertEqual(qs_stranger_with_access.count(), 4)

        logger.info("✓ Privacy filtering works for extract-created relationships")

    # =========================================================================
    # Tests for get_relationship_summary()
    # =========================================================================

    def test_get_relationship_summary_owner(self):
        """
        Owner should see complete summary of all manual relationships by type.
        The summary method does not filter by analysis_id, so it shows all relationships.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Owner sees complete relationship summary")
        logger.info("=" * 80)

        set_permissions_for_obj_to_user(self.owner, self.doc1, [PermissionTypes.READ])
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.READ])

        summary = RelationshipService.get_relationship_summary(
            document_id=self.doc1.id, corpus_id=self.corpus.id, user=self.owner
        )

        # Should see total count of ALL relationships (manual + analysis)
        # rel1, rel2, rel3, analysis_rel = 4 total
        self.assertEqual(summary["total"], 4)

        # Should see breakdown by type
        # 3 "References" relationships (rel1, rel2, analysis_rel) + 1 "Defines" (rel3)
        self.assertEqual(summary["by_type"]["References"], 3)
        self.assertEqual(summary["by_type"]["Defines"], 1)

        logger.info("✓ Owner sees complete relationship summary")

    def test_get_relationship_summary_no_permission(self):
        """
        User without permission should see empty summary.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: No permission = empty summary")
        logger.info("=" * 80)

        summary = RelationshipService.get_relationship_summary(
            document_id=self.doc1.id, corpus_id=self.corpus.id, user=self.stranger
        )

        self.assertEqual(summary["total"], 0)
        self.assertEqual(summary["by_type"], {})

        logger.info("✓ User without permission sees empty summary")

    def test_get_relationship_summary_superuser(self):
        """
        A no-grant superuser is computed like a stranger: with no READ on the
        private document/corpus it sees an empty summary. Once granted READ it
        sees the full summary through the normal permission path.
        The summary method shows ALL relationships (manual + analysis).
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: No-grant superuser sees empty; granted superuser sees all")
        logger.info("=" * 80)

        # No grants → no-grant superuser is a stranger → empty summary.
        summary = RelationshipService.get_relationship_summary(
            document_id=self.doc1.id, corpus_id=self.corpus.id, user=self.superuser
        )
        self.assertEqual(summary["total"], 0)
        self.assertEqual(summary["by_type"], {})

        # Grant READ on doc + corpus → normal path grants access.
        set_permissions_for_obj_to_user(
            self.superuser, self.doc1, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.superuser, self.corpus, [PermissionTypes.READ]
        )

        summary = RelationshipService.get_relationship_summary(
            document_id=self.doc1.id, corpus_id=self.corpus.id, user=self.superuser
        )
        # Summary shows ALL relationships including analysis ones
        self.assertEqual(summary["total"], 4)
        self.assertEqual(summary["by_type"]["References"], 3)
        self.assertEqual(summary["by_type"]["Defines"], 1)

        logger.info("✓ Superuser computed like a normal user (denied → granted)")


class ExtractServiceTestCase(TestCase):
    """
    Tests for ExtractService.get_visible_extracts()
    """

    def setUp(self):
        """Set up test scenario with multiple extracts and varied permissions"""
        logger.info("\n" + "=" * 80)
        logger.info("SETTING UP EXTRACT QUERY OPTIMIZER TEST")
        logger.info("=" * 80)

        # Create users
        self.owner = User.objects.create_user(username="owner", password="test123")
        self.collaborator = User.objects.create_user(
            username="collaborator", password="test123"
        )
        self.stranger = User.objects.create_user(
            username="stranger", password="test123"
        )
        self.superuser = User.objects.create_superuser(
            username="superuser", password="admin"
        )

        # Create documents
        self.doc1 = self._create_document("Doc 1", self.owner)
        self.doc2 = self._create_document("Doc 2", self.owner)

        # Create corpuses
        self.corpus1 = Corpus.objects.create(
            title="Corpus 1", creator=self.owner, is_public=False
        )
        self.corpus1.add_document(document=self.doc1, user=self.owner)

        self.corpus2 = Corpus.objects.create(
            title="Corpus 2", creator=self.owner, is_public=False
        )
        self.corpus2.add_document(document=self.doc2, user=self.owner)

        self.public_corpus = Corpus.objects.create(
            title="Public Corpus", creator=self.owner, is_public=True
        )
        self.public_corpus.add_document(document=self.doc1, user=self.owner)
        self.public_corpus.add_document(document=self.doc2, user=self.owner)

        # Create fieldsets
        self.fieldset1 = Fieldset.objects.create(name="Fieldset 1", creator=self.owner)
        self.fieldset2 = Fieldset.objects.create(name="Fieldset 2", creator=self.owner)

        # Create extracts
        self.extract1 = Extract.objects.create(
            name="Extract 1 (Corpus 1)",
            corpus=self.corpus1,
            fieldset=self.fieldset1,
            creator=self.owner,
        )
        self.extract1.documents.add(self.doc1)

        self.extract2 = Extract.objects.create(
            name="Extract 2 (Corpus 2)",
            corpus=self.corpus2,
            fieldset=self.fieldset2,
            creator=self.owner,
        )
        self.extract2.documents.add(self.doc2)

        self.extract_public = Extract.objects.create(
            name="Extract Public",
            corpus=self.public_corpus,
            fieldset=self.fieldset1,
            creator=self.owner,
        )
        self.extract_public.documents.add(self.doc1, self.doc2)

        # Extract with no corpus
        self.extract_no_corpus = Extract.objects.create(
            name="Extract No Corpus",
            corpus=None,
            fieldset=self.fieldset1,
            creator=self.owner,
        )
        self.extract_no_corpus.documents.add(self.doc1)

        logger.info("Setup complete!")

    def _create_document(self, title, creator):
        """Helper to create a document with a real PDF"""
        with transaction.atomic():
            doc = Document.objects.create(
                title=title,
                description=f"Test document: {title}",
                creator=creator,
                is_public=False,
            )
            with SAMPLE_PDF_FILE_ONE_PATH.open("rb") as test_pdf:
                pdf_contents = ContentFile(test_pdf.read())
                doc.pdf_file.save("test.pdf", pdf_contents)
            return doc

    def test_get_visible_extracts_owner(self):
        """
        Owner (creator) should see all their extracts.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Owner sees all their extracts")
        logger.info("=" * 80)

        qs = ExtractService.get_visible_extracts(user=self.owner)

        # Should see all 4 extracts
        self.assertEqual(qs.count(), 4)

        logger.info("✓ Owner sees all their extracts")

    def test_get_visible_extracts_with_extract_permission_only(self):
        """
        User with extract permission but NOT corpus permission should NOT see extract.
        Demonstrates hybrid permission model requirement.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Extract permission alone is insufficient")
        logger.info("=" * 80)

        # Give collaborator permission to extract1 but NOT to corpus1
        set_permissions_for_obj_to_user(
            self.collaborator, self.extract1, [PermissionTypes.READ]
        )

        qs = ExtractService.get_visible_extracts(user=self.collaborator)

        # Should NOT see extract1 (no corpus permission)
        extract_names = [e.name for e in qs]
        self.assertNotIn("Extract 1 (Corpus 1)", extract_names)

        logger.info("✓ Extract permission alone is insufficient (need corpus too)")

    def test_get_visible_extracts_with_both_permissions(self):
        """
        User with BOTH extract and corpus permissions should see extract.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Both permissions required and sufficient")
        logger.info("=" * 80)

        # Give collaborator permission to both extract1 AND corpus1
        set_permissions_for_obj_to_user(
            self.collaborator, self.extract1, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.collaborator, self.corpus1, [PermissionTypes.READ]
        )

        qs = ExtractService.get_visible_extracts(user=self.collaborator)

        # Should see extract1
        extract_names = [e.name for e in qs]
        self.assertIn("Extract 1 (Corpus 1)", extract_names)

        logger.info("✓ Both permissions together grant access")

    def test_get_visible_extracts_public_corpus(self):
        """
        Extract on public corpus should be visible if user has extract permission.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Public corpus satisfies corpus permission requirement")
        logger.info("=" * 80)

        # Give collaborator permission to extract_public
        # Corpus is already public, so corpus permission is satisfied
        set_permissions_for_obj_to_user(
            self.collaborator, self.extract_public, [PermissionTypes.READ]
        )

        qs = ExtractService.get_visible_extracts(user=self.collaborator)

        # Should see extract_public
        extract_names = [e.name for e in qs]
        self.assertIn("Extract Public", extract_names)

        logger.info("✓ Public corpus satisfies corpus permission requirement")

    def test_get_visible_extracts_no_corpus(self):
        """
        Extract with no corpus should be visible if user has extract permission.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: No corpus extracts visible with extract permission")
        logger.info("=" * 80)

        # Give collaborator permission to extract_no_corpus
        set_permissions_for_obj_to_user(
            self.collaborator, self.extract_no_corpus, [PermissionTypes.READ]
        )

        qs = ExtractService.get_visible_extracts(user=self.collaborator)

        # Should see extract_no_corpus
        extract_names = [e.name for e in qs]
        self.assertIn("Extract No Corpus", extract_names)

        logger.info("✓ No corpus extracts visible with extract permission")

    def test_get_visible_extracts_filtered_by_corpus(self):
        """
        Filtering by corpus_id should return only extracts in that corpus.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Corpus filtering works correctly")
        logger.info("=" * 80)

        # Give owner explicit permissions to corpus (hybrid model requires both extract + corpus perms)
        set_permissions_for_obj_to_user(
            self.owner, self.corpus1, [PermissionTypes.READ]
        )

        qs = ExtractService.get_visible_extracts(
            user=self.owner, corpus_id=self.corpus1.id
        )

        # Should see only extract1
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs[0].name, "Extract 1 (Corpus 1)")

        logger.info("✓ Corpus filtering returns correct extracts")

    def test_get_visible_extracts_superuser(self):
        """
        A no-grant superuser sees only what a normal ungranted user would see
        (nothing here — all extracts are on private corpora owned by someone
        else). Once granted extract + corpus READ it sees that extract through
        the normal hybrid permission path, exactly like any other user.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: No-grant superuser sees none; granted sees only permitted")
        logger.info("=" * 80)

        # No grants → no-grant superuser is a stranger → no extracts.
        qs = ExtractService.get_visible_extracts(user=self.superuser)
        self.assertEqual(qs.count(), 0)

        # Grant extract1 + corpus1 READ → hybrid model now grants exactly one.
        set_permissions_for_obj_to_user(
            self.superuser, self.extract1, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.superuser, self.corpus1, [PermissionTypes.READ]
        )

        qs = ExtractService.get_visible_extracts(user=self.superuser)
        extract_names = [e.name for e in qs]
        self.assertIn("Extract 1 (Corpus 1)", extract_names)
        self.assertNotIn("Extract 2 (Corpus 2)", extract_names)

        logger.info("✓ Superuser computed like a normal user (denied → granted)")

    def test_get_visible_extracts_stranger_no_permission(self):
        """
        User with no permissions should see no extracts.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: No permissions = no extracts")
        logger.info("=" * 80)

        qs = ExtractService.get_visible_extracts(user=self.stranger)

        # Should see nothing
        self.assertEqual(qs.count(), 0)

        logger.info("✓ User without permissions sees no extracts")

    def test_get_visible_extracts_corpus_creator(self):
        """
        If user is corpus creator, they should see extracts they have permission to.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Corpus creator can see permitted extracts")
        logger.info("=" * 80)

        # Collaborator creates a new corpus
        collab_corpus = Corpus.objects.create(
            title="Collaborator Corpus", creator=self.collaborator, is_public=False
        )
        collab_corpus.add_document(document=self.doc1, user=self.collaborator)

        # Owner creates an extract on collaborator's corpus
        collab_extract = Extract.objects.create(
            name="Extract on Collab Corpus",
            corpus=collab_corpus,
            fieldset=self.fieldset1,
            creator=self.owner,
        )
        collab_extract.documents.add(self.doc1)

        # Give collaborator permission to the extract
        set_permissions_for_obj_to_user(
            self.collaborator, collab_extract, [PermissionTypes.READ]
        )

        qs = ExtractService.get_visible_extracts(user=self.collaborator)

        # Collaborator should see the extract (they created the corpus)
        extract_names = [e.name for e in qs]
        self.assertIn("Extract on Collab Corpus", extract_names)

        logger.info("✓ Corpus creator can see permitted extracts on their corpus")

    def test_check_extract_permission_superuser_computed_normally(self):
        """A no-grant superuser does NOT get blanket access to a private extract;
        it is computed like a stranger (denied) and only resolves the extract
        once granted extract + corpus READ through the normal path."""
        # No grants → no-grant superuser is a stranger → denied.
        ok, extract = ExtractService.check_extract_permission(
            self.superuser, self.extract1.id
        )
        self.assertFalse(ok)
        self.assertIsNone(extract)

        # Grant extract1 + corpus1 READ → normal hybrid path resolves it.
        set_permissions_for_obj_to_user(
            self.superuser, self.extract1, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.superuser, self.corpus1, [PermissionTypes.READ]
        )
        ok, extract = ExtractService.check_extract_permission(
            self.superuser, self.extract1.id
        )
        self.assertTrue(ok)
        self.assertEqual(extract, self.extract1)

    def test_check_extract_permission_creator_passes(self):
        """Creator-owned extract is visible to its owner."""
        ok, extract = ExtractService.check_extract_permission(
            self.owner, self.extract1.id
        )
        self.assertTrue(ok)
        self.assertEqual(extract, self.extract1)

    def test_check_extract_permission_unknown_id_returns_false(self):
        """A non-existent extract id resolves cleanly to (False, None)."""
        ok, extract = ExtractService.check_extract_permission(self.owner, 99999999)
        self.assertFalse(ok)
        self.assertIsNone(extract)

    def test_check_extract_permission_blocked_by_extract_perm(self):
        """Stranger with neither extract nor corpus access is denied."""
        ok, extract = ExtractService.check_extract_permission(
            self.stranger, self.extract1.id
        )
        self.assertFalse(ok)
        self.assertIsNone(extract)

    def test_check_extract_permission_extract_ok_but_corpus_blocks(self):
        """Extract READ alone is not enough when the parent corpus is private."""
        set_permissions_for_obj_to_user(
            self.stranger, self.extract1, [PermissionTypes.READ]
        )
        ok, extract = ExtractService.check_extract_permission(
            self.stranger, self.extract1.id
        )
        self.assertFalse(ok)
        self.assertIsNone(extract)

    def test_check_extract_permission_no_corpus_extract(self):
        """Corpus check is skipped when the extract has no corpus."""
        set_permissions_for_obj_to_user(
            self.stranger, self.extract_no_corpus, [PermissionTypes.READ]
        )
        ok, extract = ExtractService.check_extract_permission(
            self.stranger, self.extract_no_corpus.id
        )
        self.assertTrue(ok)
        self.assertEqual(extract, self.extract_no_corpus)

    def test_get_visible_extracts_anonymous_only_public(self):
        """Anonymous users see only public extracts in public/no corpora."""
        from django.contrib.auth.models import AnonymousUser

        # Mark the public extract truly public.
        self.extract_public.is_public = True
        self.extract_public.save()

        qs = ExtractService.get_visible_extracts(user=AnonymousUser())
        names = {e.name for e in qs}
        self.assertIn("Extract Public", names)
        self.assertNotIn("Extract 1 (Corpus 1)", names)

    def test_get_visible_extracts_corpus_id_unknown_returns_none(self):
        """A non-existent corpus_id resolves to an empty queryset (not 500)."""
        qs = ExtractService.get_visible_extracts(user=self.owner, corpus_id=99999999)
        self.assertEqual(qs.count(), 0)


class AnalysisServicePermissionTestCase(TestCase):
    """Tests for ``AnalysisService.check_analysis_permission`` covering the
    branches that were not exercised by the existing visibility-queryset
    suite — superuser, unknown id, denied-by-analysis, and denied-by-corpus
    paths plus the no-corpus skip."""

    owner: User
    stranger: User
    superuser: User
    corpus: Corpus
    doc: Document
    gremlin: GremlinEngine
    analyzer: Analyzer
    analysis: Analysis
    standalone_analysis: Analysis

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="asp_owner", password="test123")
        cls.stranger = User.objects.create_user(
            username="asp_stranger", password="test123"
        )
        cls.superuser = User.objects.create_superuser(
            username="asp_superuser", password="admin"
        )
        cls.corpus = Corpus.objects.create(
            title="ASP Corpus", creator=cls.owner, is_public=False
        )
        cls.doc = Document.objects.create(
            title="ASP Doc", creator=cls.owner, is_public=False
        )
        cls.corpus.add_document(document=cls.doc, user=cls.owner)
        cls.gremlin = GremlinEngine.objects.create(
            url="http://asp-gremlin:8000", creator=cls.owner
        )
        cls.analyzer = Analyzer.objects.create(
            id="ASP.ANALYZER", host_gremlin=cls.gremlin, creator=cls.owner
        )
        cls.analysis = Analysis.objects.create(
            analyzer=cls.analyzer,
            analyzed_corpus=cls.corpus,
            creator=cls.owner,
            is_public=False,
        )
        cls.standalone_analysis = Analysis.objects.create(
            analyzer=cls.analyzer,
            analyzed_corpus=None,
            creator=cls.owner,
            is_public=False,
        )

    def test_superuser_computed_normally_for_analysis(self):
        """A no-grant superuser cannot resolve a private analysis; it is computed
        like a stranger. Once granted analysis + corpus READ (the normal path)
        it resolves, exactly like any other user."""
        from opencontractserver.analyzer.services import AnalysisService

        # No grants → no-grant superuser is a stranger → denied.
        ok, analysis = AnalysisService.check_analysis_permission(
            self.superuser, self.analysis.id
        )
        self.assertFalse(ok)
        self.assertIsNone(analysis)

        # Grant analysis + corpus READ → normal path resolves it.
        set_permissions_for_obj_to_user(
            self.superuser, self.analysis, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.superuser, self.corpus, [PermissionTypes.READ]
        )
        ok, analysis = AnalysisService.check_analysis_permission(
            self.superuser, self.analysis.id
        )
        self.assertTrue(ok)
        self.assertEqual(analysis, self.analysis)

    def test_superuser_branch_unknown_id_returns_false(self):
        from opencontractserver.analyzer.services import AnalysisService

        ok, analysis = AnalysisService.check_analysis_permission(
            self.superuser, 99999999
        )
        self.assertFalse(ok)
        self.assertIsNone(analysis)

    def test_creator_passes(self):
        from opencontractserver.analyzer.services import AnalysisService

        ok, analysis = AnalysisService.check_analysis_permission(
            self.owner, self.analysis.id
        )
        self.assertTrue(ok)
        self.assertEqual(analysis, self.analysis)

    def test_unknown_id_returns_false(self):
        from opencontractserver.analyzer.services import AnalysisService

        ok, analysis = AnalysisService.check_analysis_permission(self.owner, 99999999)
        self.assertFalse(ok)
        self.assertIsNone(analysis)

    def test_stranger_blocked_by_analysis_perm(self):
        from opencontractserver.analyzer.services import AnalysisService

        ok, analysis = AnalysisService.check_analysis_permission(
            self.stranger, self.analysis.id
        )
        self.assertFalse(ok)
        self.assertIsNone(analysis)

    def test_analysis_ok_but_corpus_blocks(self):
        """READ on the analysis is not enough when the parent corpus is private."""
        from opencontractserver.analyzer.services import AnalysisService

        set_permissions_for_obj_to_user(
            self.stranger, self.analysis, [PermissionTypes.READ]
        )
        ok, analysis = AnalysisService.check_analysis_permission(
            self.stranger, self.analysis.id
        )
        self.assertFalse(ok)
        self.assertIsNone(analysis)

    def test_standalone_analysis_skips_corpus_check(self):
        """An analysis with analyzed_corpus=None does not gate on corpus READ."""
        from opencontractserver.analyzer.services import AnalysisService

        set_permissions_for_obj_to_user(
            self.stranger, self.standalone_analysis, [PermissionTypes.READ]
        )
        ok, analysis = AnalysisService.check_analysis_permission(
            self.stranger, self.standalone_analysis.id
        )
        self.assertTrue(ok)
        self.assertEqual(analysis, self.standalone_analysis)

    def test_get_visible_analyses_corpus_id_unknown_returns_none(self):
        """A non-existent corpus_id resolves cleanly to an empty queryset."""
        from opencontractserver.analyzer.services import AnalysisService

        qs = AnalysisService.get_visible_analyses(user=self.owner, corpus_id=99999999)
        self.assertEqual(qs.count(), 0)

    def test_get_visible_analyses_anonymous_blocked_by_private_corpus(self):
        """Anonymous user with corpus_id pointing at a private corpus gets none."""
        from django.contrib.auth.models import AnonymousUser

        from opencontractserver.analyzer.services import AnalysisService

        qs = AnalysisService.get_visible_analyses(
            user=AnonymousUser(), corpus_id=self.corpus.id
        )
        self.assertEqual(qs.count(), 0)


class DocumentPermissionFilterQueryCountTestCase(TestCase):
    """
    Pins the O(1)-queries contract for the document-permission filter in
    ``AnalysisService.get_analysis_annotations`` and
    ``ExtractService.get_extract_datacells``.

    Issue #1692 replaced per-document ``doc.user_can(...)`` Python loops with a
    single ``Document.objects.visible_to_user(user).filter(id__in=...)``
    intersection. These tests assert:

      1. Behavior parity — the returned annotation / datacell set matches the
         pre-fix per-document permission check.
      2. The query count for the visibility step does not scale with the number
         of documents bundled in the analysis / extract.
    """

    owner: User
    reader: User
    corpus: Corpus
    docs: list[Document]
    readable_docs: list[Document]
    unreadable_docs: list[Document]
    label: AnnotationLabel
    gremlin: GremlinEngine
    analyzer: Analyzer
    analysis: Analysis
    annotations_by_doc: dict[int, Annotation]
    fieldset: Fieldset
    column: Column
    extract: Extract
    datacells_by_doc: dict[int, Datacell]

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="dpf_owner", password="test123")
        cls.reader = User.objects.create_user(username="dpf_reader", password="test123")

        # Owner-only corpus — reader will only see docs via explicit grant.
        cls.corpus = Corpus.objects.create(
            title="DPF Corpus", creator=cls.owner, is_public=False
        )

        cls.docs = []
        for idx in range(5):
            doc = Document.objects.create(
                title=f"DPF Doc {idx}",
                description=f"DPF doc {idx}",
                creator=cls.owner,
                is_public=False,
            )
            cls.corpus.add_document(document=doc, user=cls.owner)
            cls.docs.append(doc)

        # Grant reader READ on the first two docs only (mix of readable/non-readable).
        cls.readable_docs = cls.docs[:2]
        cls.unreadable_docs = cls.docs[2:]
        for doc in cls.readable_docs:
            set_permissions_for_obj_to_user(cls.reader, doc, [PermissionTypes.READ])

        # Annotation label shared across docs.
        cls.label = AnnotationLabel.objects.create(
            label_type=TOKEN_LABEL, text="DPF Label", creator=cls.owner
        )

        # Analysis with all docs in cls.docs.
        cls.gremlin = GremlinEngine.objects.create(
            url="http://dpf-gremlin:8000", creator=cls.owner
        )
        cls.analyzer = Analyzer.objects.create(
            id="DPF.ANALYZER", host_gremlin=cls.gremlin, creator=cls.owner
        )
        cls.analysis = Analysis.objects.create(
            analyzer=cls.analyzer,
            analyzed_corpus=cls.corpus,
            creator=cls.owner,
        )
        cls.analysis.analyzed_documents.add(*cls.docs)

        # One annotation per doc, attached to the analysis.
        cls.annotations_by_doc = {}
        for doc in cls.docs:
            ann = Annotation.objects.create(
                annotation_label=cls.label,
                document=doc,
                corpus=cls.corpus,
                analysis=cls.analysis,
                creator=cls.owner,
                page=1,
                raw_text=f"ann for {doc.title}",
            )
            cls.annotations_by_doc[doc.id] = ann

        # Extract with all docs and one datacell per doc.
        cls.fieldset = Fieldset.objects.create(name="DPF Fieldset", creator=cls.owner)
        cls.column = Column.objects.create(
            name="DPF Column",
            fieldset=cls.fieldset,
            query="q",
            output_type="string",
            creator=cls.owner,
        )
        cls.extract = Extract.objects.create(
            name="DPF Extract",
            corpus=cls.corpus,
            fieldset=cls.fieldset,
            creator=cls.owner,
        )
        cls.extract.documents.add(*cls.docs)

        cls.datacells_by_doc = {}
        for doc in cls.docs:
            dc = Datacell.objects.create(
                creator=cls.owner,
                extract=cls.extract,
                column=cls.column,
                document=doc,
                data={"value": f"v-{doc.id}"},
                data_definition="DPF",
            )
            cls.datacells_by_doc[doc.id] = dc

    def test_get_analysis_annotations_parity_and_constant_queries(self):
        """
        ``get_analysis_annotations`` must return only annotations on readable
        docs and must not issue an O(N) burst of queries for the visibility
        filter.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from opencontractserver.analyzer.services import AnalysisService

        with CaptureQueriesContext(connection) as captured:
            qs = AnalysisService.get_analysis_annotations(self.analysis, self.reader)
            returned_ids = sorted(qs.values_list("id", flat=True))

        expected_ids = sorted(
            self.annotations_by_doc[doc.id].id for doc in self.readable_docs
        )
        self.assertEqual(returned_ids, expected_ids)

        # Hard ceiling — far below the ~5+ permission-lookup queries the
        # old per-doc loop required for N=5 (each doc.user_can typically
        # triggers a permission table SELECT in addition to deserialising
        # the doc row). Under the queryset intersection we expect a small
        # single-digit number.
        self.assertLess(
            len(captured.captured_queries),
            10,
            msg=(
                "get_analysis_annotations should issue a bounded number of "
                f"queries; saw {len(captured.captured_queries)}: "
                + "\n".join(q["sql"] for q in captured.captured_queries)
            ),
        )

    def test_get_extract_datacells_parity_and_constant_queries(self):
        """
        ``get_extract_datacells`` must return only datacells on readable
        docs and must not issue an O(N) burst of queries for the visibility
        filter.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as captured:
            qs = ExtractService.get_extract_datacells(self.extract, self.reader)
            returned_ids = sorted(qs.values_list("id", flat=True))

        expected_ids = sorted(
            self.datacells_by_doc[doc.id].id for doc in self.readable_docs
        )
        self.assertEqual(returned_ids, expected_ids)

        self.assertLess(
            len(captured.captured_queries),
            10,
            msg=(
                "get_extract_datacells should issue a bounded number of "
                f"queries; saw {len(captured.captured_queries)}: "
                + "\n".join(q["sql"] for q in captured.captured_queries)
            ),
        )

    def test_get_analysis_annotations_returns_none_when_no_readable_docs(self):
        """
        When the reader has no READ permission on any analyzed document the
        method must short-circuit to ``Annotation.objects.none()``.
        """
        from opencontractserver.analyzer.services import AnalysisService

        stranger = User.objects.create_user(username="dpf_stranger", password="x")
        qs = AnalysisService.get_analysis_annotations(self.analysis, stranger)
        self.assertEqual(qs.count(), 0)

    def test_get_extract_datacells_returns_none_when_no_readable_docs(self):
        """
        Mirror of the analysis case for ``get_extract_datacells``.
        """
        stranger = User.objects.create_user(username="dpf_stranger2", password="x")
        qs = ExtractService.get_extract_datacells(self.extract, stranger)
        self.assertEqual(qs.count(), 0)
