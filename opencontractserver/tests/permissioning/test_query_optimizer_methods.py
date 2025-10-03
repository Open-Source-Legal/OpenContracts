"""
Comprehensive tests for Query Optimizer methods with permission filtering.

This test suite provides comprehensive coverage for query optimizer methods that were
previously untested, focusing on:

1. AnnotationQueryOptimizer.get_extract_annotation_summary()
   - Tests annotation summaries for extracts with various permission levels
   - Tests label counting and page aggregation
   - Tests access control based on document and corpus permissions

2. RelationshipQueryOptimizer.get_document_relationships()
   - Tests relationship retrieval with permission filtering
   - Tests corpus/document/analysis scoping
   - Tests structural vs non-structural relationships
   - Tests extract-based relationship filtering (strict and non-strict modes)
   - Tests page filtering

3. RelationshipQueryOptimizer.get_relationship_summary()
   - Tests relationship counting by type
   - Tests permission-based visibility
   - Tests aggregation across multiple relationship types

4. ExtractQueryOptimizer.get_visible_extracts()
   - Tests extract visibility based on hybrid permission model
   - Tests corpus-level filtering
   - Tests that extract permission + corpus permission both required
   - Tests list-based filtering for users with various permission levels
"""

import logging

from django.contrib.auth import get_user_model
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
from opencontractserver.annotations.query_optimizer import (
    AnnotationQueryOptimizer,
    ExtractQueryOptimizer,
    RelationshipQueryOptimizer,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.extracts.models import Column, Datacell, Extract, Fieldset
from opencontractserver.tests.fixtures import SAMPLE_PDF_FILE_ONE_PATH
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()
logger = logging.getLogger(__name__)


class AnnotationQueryOptimizerTestCase(TestCase):
    """
    Tests for AnnotationQueryOptimizer.get_extract_annotation_summary()
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
        self.corpus.documents.add(self.doc1, self.doc2)

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

        summary = AnnotationQueryOptimizer.get_extract_annotation_summary(
            document_id=self.doc1.id,
            extract_id=self.extract.id,
            user=self.owner,
            use_cache=False,
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

        summary = AnnotationQueryOptimizer.get_extract_annotation_summary(
            document_id=self.doc1.id,
            extract_id=self.extract.id,
            user=self.stranger,
            use_cache=False,
        )

        # Should see nothing
        self.assertEqual(summary["total_source_annotations"], 0)
        self.assertEqual(summary["by_label"], {})
        self.assertEqual(summary["pages_with_sources"], [])

        logger.info("✓ User without document permission sees empty summary")

    def test_get_extract_annotation_summary_superuser(self):
        """
        Superuser should see everything regardless of permissions.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Superuser sees complete summary")
        logger.info("=" * 80)

        # Don't grant any explicit permissions to superuser

        summary = AnnotationQueryOptimizer.get_extract_annotation_summary(
            document_id=self.doc1.id,
            extract_id=self.extract.id,
            user=self.superuser,
            use_cache=False,
        )

        # Should see all 3 annotations
        self.assertEqual(summary["total_source_annotations"], 3)
        self.assertEqual(summary["by_label"]["Contract Term"], 2)
        self.assertEqual(summary["by_label"]["Party Name"], 1)

        logger.info("✓ Superuser sees complete summary without explicit permissions")

    def test_get_extract_annotation_summary_nonexistent_extract(self):
        """
        Test behavior with non-existent extract (should handle gracefully).
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Non-existent extract handled gracefully")
        logger.info("=" * 80)

        set_permissions_for_obj_to_user(self.owner, self.doc1, [PermissionTypes.READ])
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.READ])

        summary = AnnotationQueryOptimizer.get_extract_annotation_summary(
            document_id=self.doc1.id,
            extract_id=99999,  # Non-existent ID
            user=self.owner,
            use_cache=False,
        )

        # Should return empty summary
        self.assertEqual(summary["total_source_annotations"], 0)
        self.assertEqual(summary["by_label"], {})
        self.assertEqual(summary["pages_with_sources"], [])

        logger.info("✓ Non-existent extract returns empty summary")


class RelationshipQueryOptimizerTestCase(TestCase):
    """
    Tests for RelationshipQueryOptimizer methods:
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
        self.corpus.documents.add(self.doc1)

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
        Owner with full permissions should see all relationships in corpus.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Owner sees all relationships")
        logger.info("=" * 80)

        set_permissions_for_obj_to_user(self.owner, self.doc1, [PermissionTypes.READ])
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.READ])

        qs = RelationshipQueryOptimizer.get_document_relationships(
            document_id=self.doc1.id,
            user=self.owner,
            corpus_id=self.corpus.id,
            use_cache=False,
        )

        # Should see all 4 corpus-based relationships (not structural)
        self.assertEqual(qs.count(), 4)

        logger.info("✓ Owner sees all corpus relationships")

    def test_get_document_relationships_no_permission(self):
        """
        User without document permission should see no relationships.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: No permission = no relationships")
        logger.info("=" * 80)

        # Don't grant any permissions to stranger

        qs = RelationshipQueryOptimizer.get_document_relationships(
            document_id=self.doc1.id,
            user=self.stranger,
            corpus_id=self.corpus.id,
            use_cache=False,
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

        qs = RelationshipQueryOptimizer.get_document_relationships(
            document_id=self.doc1.id,
            user=self.owner,
            corpus_id=None,  # No corpus
            use_cache=False,
        )

        # Should see only structural relationship
        self.assertEqual(qs.count(), 1)
        self.assertTrue(qs.first().structural)

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

        qs = RelationshipQueryOptimizer.get_document_relationships(
            document_id=self.doc1.id,
            user=self.owner,
            corpus_id=self.corpus.id,
            analysis_id=self.analysis.id,
            use_cache=False,
        )

        # Should see only the analysis relationship
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first().analysis, self.analysis)

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
        qs = RelationshipQueryOptimizer.get_document_relationships(
            document_id=self.doc1.id,
            user=self.owner,
            corpus_id=self.corpus.id,
            pages=[1],
            use_cache=False,
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
        qs = RelationshipQueryOptimizer.get_document_relationships(
            document_id=self.doc1.id,
            user=self.owner,
            corpus_id=self.corpus.id,
            extract_id=self.extract.id,
            strict_extract_mode=False,
            use_cache=False,
        )

        # Should see relationships involving ann1 or ann2 (in extract)
        self.assertGreater(qs.count(), 0)

        # Strict mode: both source and target must be in extract
        qs_strict = RelationshipQueryOptimizer.get_document_relationships(
            document_id=self.doc1.id,
            user=self.owner,
            corpus_id=self.corpus.id,
            extract_id=self.extract.id,
            strict_extract_mode=True,
            use_cache=False,
        )

        # Should only see relationships where both ends are in extract
        # ann1 and ann2 are both in extract, so relationships between them qualify
        self.assertGreater(qs_strict.count(), 0)

        logger.info("✓ Extract filtering (strict and non-strict) works correctly")

    def test_get_document_relationships_superuser(self):
        """
        Superuser should see all relationships without explicit permissions.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Superuser sees all relationships")
        logger.info("=" * 80)

        qs = RelationshipQueryOptimizer.get_document_relationships(
            document_id=self.doc1.id,
            user=self.superuser,
            corpus_id=self.corpus.id,
            use_cache=False,
        )

        # Should see all corpus-based relationships
        self.assertEqual(qs.count(), 4)

        logger.info("✓ Superuser sees all relationships without explicit permissions")

    def test_get_document_relationships_structural_filter(self):
        """
        Testing explicit structural filter parameter.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Structural filter works correctly")
        logger.info("=" * 80)

        set_permissions_for_obj_to_user(self.owner, self.doc1, [PermissionTypes.READ])
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.READ])

        # Filter to only non-structural
        qs = RelationshipQueryOptimizer.get_document_relationships(
            document_id=self.doc1.id,
            user=self.owner,
            corpus_id=self.corpus.id,
            structural=False,
            use_cache=False,
        )

        # All our corpus relationships are non-structural
        self.assertEqual(qs.count(), 4)
        for rel in qs:
            self.assertFalse(rel.structural)

        logger.info("✓ Structural filter correctly filters relationships")

    # =========================================================================
    # Tests for get_relationship_summary()
    # =========================================================================

    def test_get_relationship_summary_owner(self):
        """
        Owner should see complete summary of all relationships by type.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Owner sees complete relationship summary")
        logger.info("=" * 80)

        set_permissions_for_obj_to_user(self.owner, self.doc1, [PermissionTypes.READ])
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.READ])

        summary = RelationshipQueryOptimizer.get_relationship_summary(
            document_id=self.doc1.id, corpus_id=self.corpus.id, user=self.owner
        )

        # Should see total count
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

        summary = RelationshipQueryOptimizer.get_relationship_summary(
            document_id=self.doc1.id, corpus_id=self.corpus.id, user=self.stranger
        )

        self.assertEqual(summary["total"], 0)
        self.assertEqual(summary["by_type"], {})

        logger.info("✓ User without permission sees empty summary")

    def test_get_relationship_summary_superuser(self):
        """
        Superuser should see complete summary without explicit permissions.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Superuser sees complete summary")
        logger.info("=" * 80)

        summary = RelationshipQueryOptimizer.get_relationship_summary(
            document_id=self.doc1.id, corpus_id=self.corpus.id, user=self.superuser
        )

        self.assertEqual(summary["total"], 4)
        self.assertEqual(summary["by_type"]["References"], 3)
        self.assertEqual(summary["by_type"]["Defines"], 1)

        logger.info("✓ Superuser sees complete summary")


class ExtractQueryOptimizerTestCase(TestCase):
    """
    Tests for ExtractQueryOptimizer.get_visible_extracts()
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
        self.corpus1.documents.add(self.doc1)

        self.corpus2 = Corpus.objects.create(
            title="Corpus 2", creator=self.owner, is_public=False
        )
        self.corpus2.documents.add(self.doc2)

        self.public_corpus = Corpus.objects.create(
            title="Public Corpus", creator=self.owner, is_public=True
        )
        self.public_corpus.documents.add(self.doc1, self.doc2)

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

        qs = ExtractQueryOptimizer.get_visible_extracts(user=self.owner)

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

        qs = ExtractQueryOptimizer.get_visible_extracts(user=self.collaborator)

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

        qs = ExtractQueryOptimizer.get_visible_extracts(user=self.collaborator)

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

        qs = ExtractQueryOptimizer.get_visible_extracts(user=self.collaborator)

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

        qs = ExtractQueryOptimizer.get_visible_extracts(user=self.collaborator)

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

        qs = ExtractQueryOptimizer.get_visible_extracts(
            user=self.owner, corpus_id=self.corpus1.id
        )

        # Should see only extract1
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first().name, "Extract 1 (Corpus 1)")

        logger.info("✓ Corpus filtering returns correct extracts")

    def test_get_visible_extracts_superuser(self):
        """
        Superuser should see all extracts without explicit permissions.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Superuser sees all extracts")
        logger.info("=" * 80)

        qs = ExtractQueryOptimizer.get_visible_extracts(user=self.superuser)

        # Should see all 4 extracts
        self.assertEqual(qs.count(), 4)

        logger.info("✓ Superuser sees all extracts without explicit permissions")

    def test_get_visible_extracts_stranger_no_permission(self):
        """
        User with no permissions should see no extracts.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: No permissions = no extracts")
        logger.info("=" * 80)

        qs = ExtractQueryOptimizer.get_visible_extracts(user=self.stranger)

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
        collab_corpus.documents.add(self.doc1)

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

        qs = ExtractQueryOptimizer.get_visible_extracts(user=self.collaborator)

        # Collaborator should see the extract (they created the corpus)
        extract_names = [e.name for e in qs]
        self.assertIn("Extract on Collab Corpus", extract_names)

        logger.info("✓ Corpus creator can see permitted extracts on their corpus")
