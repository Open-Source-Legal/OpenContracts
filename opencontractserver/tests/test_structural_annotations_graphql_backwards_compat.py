"""
Tests for structural annotation GraphQL backwards compatibility.

This test suite proves that structural annotations created BEFORE the v3.0.0.b3
migration (when structural annotations were attached directly to documents) remain
fully accessible via GraphQL queries AFTER migrating to use StructuralAnnotationSet.

CRITICAL VERIFICATION:
- Pre-migration: structural annotations have document FK set, structural_set FK null
- Post-migration: structural annotations have document FK null, structural_set FK set
- BOTH states must return identical structural annotations via GraphQL

This ensures legacy users don't lose access to their structural annotations.
"""

import io

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TransactionTestCase
from django.utils import timezone
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
    Relationship,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.types.enums import LabelType, PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class StructuralAnnotationGraphQLBackwardsCompatibilityTests(TransactionTestCase):
    """
    Prove that structural annotations remain accessible via GraphQL
    in both pre-migration and post-migration states.

    This is critical backwards compatibility testing for v3.0.0.b3.
    """

    def setUp(self):
        """Create test fixtures simulating pre-migration state."""
        self.client = Client(schema)

        self.user = User.objects.create_user(
            username="graphql_compat_user",
            password="testpass123",
            email="compat@test.com",
        )

        # Create corpus with full permissions for user
        self.corpus = Corpus.objects.create(
            title="GraphQL Compat Test Corpus",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user,
            self.corpus,
            [PermissionTypes.READ, PermissionTypes.UPDATE, PermissionTypes.DELETE],
        )

        # Create document with content hash (for structural set keying)
        # Set processing_started to prevent the document processing signal
        # from firing (it would fail because test documents have no actual files).
        self.doc = Document.objects.create(
            title="Document With Structural Annotations",
            pdf_file_hash="graphql_compat_hash_001",
            creator=self.user,
            page_count=5,
            processing_started=timezone.now(),
        )
        set_permissions_for_obj_to_user(
            self.user,
            self.doc,
            [PermissionTypes.READ, PermissionTypes.UPDATE, PermissionTypes.DELETE],
        )

        # Create DocumentPath to link document to corpus
        self.doc_path = DocumentPath.objects.create(
            document=self.doc,
            corpus=self.corpus,
            path="/documents/test_doc",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )
        # Document is now linked via DocumentPath above

        # Create labels for structural annotations
        self.header_label = AnnotationLabel.objects.create(
            text="Header",
            label_type=LabelType.DOC_TYPE_LABEL,
            creator=self.user,
        )
        self.section_label = AnnotationLabel.objects.create(
            text="Section",
            label_type=LabelType.DOC_TYPE_LABEL,
            creator=self.user,
        )
        self.paragraph_label = AnnotationLabel.objects.create(
            text="Paragraph",
            label_type=LabelType.DOC_TYPE_LABEL,
            creator=self.user,
        )

        # Create STRUCTURAL annotations in PRE-MIGRATION state
        # (attached to document directly, structural_set=null)
        self.struct_header = Annotation.objects.create(
            document=self.doc,
            corpus=self.corpus,
            annotation_label=self.header_label,
            page=1,
            raw_text="Chapter 1: Introduction",
            structural=True,
            creator=self.user,
        )
        self.struct_section1 = Annotation.objects.create(
            document=self.doc,
            corpus=self.corpus,
            annotation_label=self.section_label,
            page=1,
            raw_text="1.1 Background",
            structural=True,
            creator=self.user,
        )
        self.struct_section2 = Annotation.objects.create(
            document=self.doc,
            corpus=self.corpus,
            annotation_label=self.section_label,
            page=2,
            raw_text="1.2 Objectives",
            structural=True,
            creator=self.user,
        )
        self.struct_para1 = Annotation.objects.create(
            document=self.doc,
            corpus=self.corpus,
            annotation_label=self.paragraph_label,
            page=1,
            raw_text="This document describes the framework for...",
            structural=True,
            creator=self.user,
        )
        self.struct_para2 = Annotation.objects.create(
            document=self.doc,
            corpus=self.corpus,
            annotation_label=self.paragraph_label,
            page=2,
            raw_text="The primary objectives of this work are...",
            structural=True,
            creator=self.user,
        )

        # Create NON-STRUCTURAL (user) annotation for contrast
        self.user_annot = Annotation.objects.create(
            document=self.doc,
            corpus=self.corpus,
            annotation_label=self.header_label,
            page=1,
            raw_text="User highlighted text",
            structural=False,
            creator=self.user,
        )

        # Store original annotation IDs for comparison
        self.original_struct_ids = {
            self.struct_header.id,
            self.struct_section1.id,
            self.struct_section2.id,
            self.struct_para1.id,
            self.struct_para2.id,
        }

    def _get_request_context(self):
        """Create a mock request context with the user."""
        return type("Request", (), {"user": self.user})()

    def _call_migrate(self, *args, **kwargs):
        """Helper to call migrate_structural_annotations with correct user."""
        return call_command(
            "migrate_structural_annotations",
            f"--system-user-id={self.user.id}",
            *args,
            **kwargs,
        )

    # =========================================================================
    # TEST 1: Pre-migration GraphQL access via document.allStructuralAnnotations
    # =========================================================================

    def test_pre_migration_document_all_structural_annotations_query(self):
        """
        BEFORE migration: structural annotations with document FK set
        should be accessible via document.allStructuralAnnotations.
        """
        # Verify pre-migration state
        for annot in [
            self.struct_header,
            self.struct_section1,
            self.struct_section2,
            self.struct_para1,
            self.struct_para2,
        ]:
            annot.refresh_from_db()
            self.assertIsNotNone(
                annot.document_id, "Pre-migration: document should be set"
            )
            self.assertIsNone(
                annot.structural_set_id, "Pre-migration: structural_set should be null"
            )

        doc_global_id = to_global_id("DocumentType", self.doc.id)

        query = """
            query GetDocStructuralAnnotations($id: ID!) {
                document(id: $id) {
                    id
                    title
                    allStructuralAnnotations {
                        id
                        rawText
                        structural
                        page
                        annotationLabel {
                            text
                        }
                    }
                }
            }
        """

        result = self.client.execute(
            query,
            variables={"id": doc_global_id},
            context_value=self._get_request_context(),
        )

        self.assertIsNone(
            result.get("errors"), f"GraphQL errors: {result.get('errors')}"
        )

        annotations = result["data"]["document"]["allStructuralAnnotations"]

        # Should return all 5 structural annotations
        self.assertEqual(
            len(annotations),
            5,
            f"Expected 5 structural annotations, got {len(annotations)}",
        )

        # All should be marked as structural
        for annot in annotations:
            self.assertTrue(annot["structural"])

        # Verify the expected content is returned
        raw_texts = {annot["rawText"] for annot in annotations}
        expected_texts = {
            "Chapter 1: Introduction",
            "1.1 Background",
            "1.2 Objectives",
            "This document describes the framework for...",
            "The primary objectives of this work are...",
        }
        self.assertEqual(raw_texts, expected_texts)

    # =========================================================================
    # TEST 2: Pre-migration GraphQL access via annotations query with filter
    # =========================================================================

    def test_pre_migration_annotations_query_with_structural_filter(self):
        """
        BEFORE migration: structural annotations should be queryable via
        the main annotations query with structural=true filter.
        """
        doc_global_id = to_global_id("DocumentType", self.doc.id)
        corpus_global_id = to_global_id("CorpusType", self.corpus.id)

        query = """
            query GetAnnotations($documentId: ID!, $corpusId: ID!) {
                annotations(
                    documentId: $documentId
                    corpusId: $corpusId
                    structural: true
                ) {
                    edges {
                        node {
                            id
                            rawText
                            structural
                            page
                        }
                    }
                }
            }
        """

        result = self.client.execute(
            query,
            variables={"documentId": doc_global_id, "corpusId": corpus_global_id},
            context_value=self._get_request_context(),
        )

        self.assertIsNone(
            result.get("errors"), f"GraphQL errors: {result.get('errors')}"
        )

        edges = result["data"]["annotations"]["edges"]
        self.assertEqual(
            len(edges), 5, f"Expected 5 structural annotations, got {len(edges)}"
        )

    # =========================================================================
    # TEST 3: Post-migration GraphQL access - same queries, same results
    # =========================================================================

    def test_post_migration_structural_annotations_remain_accessible(self):
        """
        AFTER migration: structural annotations moved to StructuralAnnotationSet
        MUST still be accessible via the same GraphQL queries.

        This is the critical backwards compatibility test.
        """
        # Capture pre-migration query results
        doc_global_id = to_global_id("DocumentType", self.doc.id)

        pre_migration_query = """
            query GetDocStructuralAnnotations($id: ID!) {
                document(id: $id) {
                    allStructuralAnnotations {
                        id
                        rawText
                        structural
                        page
                    }
                }
            }
        """

        pre_result = self.client.execute(
            pre_migration_query,
            variables={"id": doc_global_id},
            context_value=self._get_request_context(),
        )

        pre_annotations = pre_result["data"]["document"]["allStructuralAnnotations"]
        pre_raw_texts = {annot["rawText"] for annot in pre_annotations}
        pre_count = len(pre_annotations)

        self.assertEqual(
            pre_count, 5, "Pre-migration should have 5 structural annotations"
        )

        # =====================================================================
        # RUN THE MIGRATION
        # =====================================================================
        out = io.StringIO()
        self._call_migrate(stdout=out)

        # Verify migration occurred
        self.doc.refresh_from_db()
        self.assertIsNotNone(
            self.doc.structural_annotation_set,
            "Document should now have structural_annotation_set",
        )

        # Verify structural annotations moved
        self.struct_header.refresh_from_db()
        self.assertIsNone(
            self.struct_header.document_id,
            "Post-migration: structural annotation should have document=NULL",
        )
        self.assertIsNotNone(
            self.struct_header.structural_set_id,
            "Post-migration: structural annotation should have structural_set set",
        )

        # =====================================================================
        # QUERY AGAIN - SAME QUERY SHOULD RETURN SAME RESULTS
        # =====================================================================
        post_result = self.client.execute(
            pre_migration_query,
            variables={"id": doc_global_id},
            context_value=self._get_request_context(),
        )

        self.assertIsNone(
            post_result.get("errors"),
            f"GraphQL errors post-migration: {post_result.get('errors')}",
        )

        post_annotations = post_result["data"]["document"]["allStructuralAnnotations"]
        post_raw_texts = {annot["rawText"] for annot in post_annotations}
        post_count = len(post_annotations)

        # =====================================================================
        # CRITICAL ASSERTIONS: Same results before and after migration
        # =====================================================================
        self.assertEqual(
            post_count,
            pre_count,
            f"Post-migration count ({post_count}) should equal pre-migration ({pre_count})",
        )

        self.assertEqual(
            post_raw_texts,
            pre_raw_texts,
            "Post-migration should return identical structural annotation content",
        )

        # Verify all structural annotations are accessible
        self.assertEqual(
            post_raw_texts,
            {
                "Chapter 1: Introduction",
                "1.1 Background",
                "1.2 Objectives",
                "This document describes the framework for...",
                "The primary objectives of this work are...",
            },
        )

    # =========================================================================
    # TEST 4: Post-migration - annotations query also works
    # =========================================================================

    def test_post_migration_annotations_query_returns_structural(self):
        """
        AFTER migration: main annotations query with structural=true filter
        must still return migrated structural annotations.
        """
        # Run migration first
        out = io.StringIO()
        self._call_migrate(stdout=out)

        doc_global_id = to_global_id("DocumentType", self.doc.id)
        corpus_global_id = to_global_id("CorpusType", self.corpus.id)

        query = """
            query GetAnnotations($documentId: ID!, $corpusId: ID!) {
                annotations(
                    documentId: $documentId
                    corpusId: $corpusId
                    structural: true
                ) {
                    edges {
                        node {
                            id
                            rawText
                            structural
                        }
                    }
                }
            }
        """

        result = self.client.execute(
            query,
            variables={"documentId": doc_global_id, "corpusId": corpus_global_id},
            context_value=self._get_request_context(),
        )

        self.assertIsNone(
            result.get("errors"), f"GraphQL errors: {result.get('errors')}"
        )

        edges = result["data"]["annotations"]["edges"]
        self.assertEqual(
            len(edges),
            5,
            f"Post-migration: Expected 5 structural annotations, got {len(edges)}",
        )

        # All should be structural
        for edge in edges:
            self.assertTrue(edge["node"]["structural"])

    # =========================================================================
    # TEST 5: Non-structural annotations remain separate
    # =========================================================================

    def test_migration_preserves_user_annotations_separation(self):
        """
        User-created (non-structural) annotations should remain on the document
        and not be moved to structural_annotation_set.
        """
        # Run migration
        out = io.StringIO()
        self._call_migrate(stdout=out)

        # Check user annotation is still attached to document
        self.user_annot.refresh_from_db()
        self.assertIsNotNone(
            self.user_annot.document_id,
            "User annotation should still have document set after migration",
        )
        self.assertIsNone(
            self.user_annot.structural_set_id,
            "User annotation should NOT have structural_set after migration",
        )

        # Query for non-structural annotations
        doc_global_id = to_global_id("DocumentType", self.doc.id)
        corpus_global_id = to_global_id("CorpusType", self.corpus.id)

        query = """
            query GetUserAnnotations($documentId: ID!, $corpusId: ID!) {
                annotations(
                    documentId: $documentId
                    corpusId: $corpusId
                    structural: false
                ) {
                    edges {
                        node {
                            id
                            rawText
                            structural
                        }
                    }
                }
            }
        """

        result = self.client.execute(
            query,
            variables={"documentId": doc_global_id, "corpusId": corpus_global_id},
            context_value=self._get_request_context(),
        )

        self.assertIsNone(result.get("errors"))
        edges = result["data"]["annotations"]["edges"]

        # Should have exactly 1 user annotation
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["node"]["rawText"], "User highlighted text")
        self.assertFalse(edges[0]["node"]["structural"])

    # =========================================================================
    # TEST 6: Multiple documents share structural set after migration
    # =========================================================================

    def test_shared_structural_set_accessible_from_multiple_documents(self):
        """
        When two documents with the same content hash share a StructuralAnnotationSet,
        both should be able to access the shared structural annotations via GraphQL.
        """
        # Create second document with same hash
        doc2 = Document.objects.create(
            title="Second Document With Same Content",
            pdf_file_hash=self.doc.pdf_file_hash,  # SAME HASH!
            creator=self.user,
            page_count=5,
            processing_started=timezone.now(),
        )
        set_permissions_for_obj_to_user(
            self.user,
            doc2,
            [PermissionTypes.READ, PermissionTypes.UPDATE, PermissionTypes.DELETE],
        )

        # Add to same corpus via DocumentPath
        DocumentPath.objects.create(
            document=doc2,
            corpus=self.corpus,
            path="/documents/test_doc_2",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )
        # Document is now linked via DocumentPath above

        # Create structural annotation on doc2
        Annotation.objects.create(
            document=doc2,
            corpus=self.corpus,
            annotation_label=self.header_label,
            page=1,
            raw_text="Doc2 Header",
            structural=True,
            creator=self.user,
        )

        # Run migration
        out = io.StringIO()
        self._call_migrate(stdout=out)

        # Verify both documents share the same structural_annotation_set
        self.doc.refresh_from_db()
        doc2.refresh_from_db()

        self.assertIsNotNone(self.doc.structural_annotation_set)
        self.assertIsNotNone(doc2.structural_annotation_set)
        self.assertEqual(
            self.doc.structural_annotation_set_id,
            doc2.structural_annotation_set_id,
            "Documents with same hash should share structural_annotation_set",
        )

        # Query structural annotations via GraphQL for BOTH documents
        doc1_global_id = to_global_id("DocumentType", self.doc.id)
        doc2_global_id = to_global_id("DocumentType", doc2.id)

        query = """
            query GetDocStructuralAnnotations($id: ID!) {
                document(id: $id) {
                    id
                    title
                    allStructuralAnnotations {
                        rawText
                    }
                }
            }
        """

        result1 = self.client.execute(
            query,
            variables={"id": doc1_global_id},
            context_value=self._get_request_context(),
        )
        result2 = self.client.execute(
            query,
            variables={"id": doc2_global_id},
            context_value=self._get_request_context(),
        )

        self.assertIsNone(result1.get("errors"))
        self.assertIsNone(result2.get("errors"))

        annots1 = result1["data"]["document"]["allStructuralAnnotations"]
        annots2 = result2["data"]["document"]["allStructuralAnnotations"]

        # Both should return ALL structural annotations from the shared set
        # (5 from doc1 + 1 from doc2 = 6 total in shared set)
        self.assertEqual(len(annots1), 6)
        self.assertEqual(len(annots2), 6)

        # Same content for both
        texts1 = {a["rawText"] for a in annots1}
        texts2 = {a["rawText"] for a in annots2}
        self.assertEqual(texts1, texts2)

    # =========================================================================
    # TEST 7: document.allAnnotations also works with structural filter
    # =========================================================================

    def test_document_all_annotations_with_structural_filter(self):
        """
        document.allAnnotations(isStructural: true) should work both
        before and after migration.
        """
        doc_global_id = to_global_id("DocumentType", self.doc.id)
        corpus_global_id = to_global_id("CorpusType", self.corpus.id)

        query = """
            query GetDocAnnotations($id: ID!, $corpusId: ID!) {
                document(id: $id) {
                    allAnnotations(corpusId: $corpusId, isStructural: true) {
                        id
                        rawText
                        structural
                    }
                }
            }
        """

        # Pre-migration query
        pre_result = self.client.execute(
            query,
            variables={"id": doc_global_id, "corpusId": corpus_global_id},
            context_value=self._get_request_context(),
        )
        self.assertIsNone(pre_result.get("errors"))
        pre_annots = pre_result["data"]["document"]["allAnnotations"]
        pre_count = len(pre_annots)

        # Run migration
        out = io.StringIO()
        self._call_migrate(stdout=out)

        # Post-migration query
        post_result = self.client.execute(
            query,
            variables={"id": doc_global_id, "corpusId": corpus_global_id},
            context_value=self._get_request_context(),
        )
        self.assertIsNone(post_result.get("errors"))
        post_annots = post_result["data"]["document"]["allAnnotations"]
        post_count = len(post_annots)

        # Same count before and after
        self.assertEqual(
            post_count,
            pre_count,
            f"allAnnotations should return same count: pre={pre_count}, post={post_count}",
        )

    # =========================================================================
    # TEST 8: Edge case - document without structural annotations
    # =========================================================================

    def test_document_without_structural_annotations(self):
        """
        Documents with no structural annotations should return empty list,
        not error, both before and after migration.
        """
        # Create document with no structural annotations
        empty_doc = Document.objects.create(
            title="Document Without Structural",
            pdf_file_hash="empty_doc_hash",
            creator=self.user,
            processing_started=timezone.now(),
        )
        set_permissions_for_obj_to_user(
            self.user,
            empty_doc,
            [PermissionTypes.READ],
        )

        doc_global_id = to_global_id("DocumentType", empty_doc.id)

        query = """
            query GetDocStructuralAnnotations($id: ID!) {
                document(id: $id) {
                    allStructuralAnnotations {
                        rawText
                    }
                }
            }
        """

        # Pre-migration
        pre_result = self.client.execute(
            query,
            variables={"id": doc_global_id},
            context_value=self._get_request_context(),
        )
        self.assertIsNone(pre_result.get("errors"))
        self.assertEqual(
            len(pre_result["data"]["document"]["allStructuralAnnotations"]), 0
        )

        # Run migration (nothing to migrate for this doc)
        self._call_migrate()

        # Post-migration
        post_result = self.client.execute(
            query,
            variables={"id": doc_global_id},
            context_value=self._get_request_context(),
        )
        self.assertIsNone(post_result.get("errors"))
        self.assertEqual(
            len(post_result["data"]["document"]["allStructuralAnnotations"]), 0
        )


class StructuralRelationshipGraphQLBackwardsCompatibilityTests(TransactionTestCase):
    """
    Prove that structural RELATIONSHIPS also remain accessible via GraphQL
    after migration to StructuralAnnotationSet.
    """

    def setUp(self):
        """Create test fixtures with structural relationships."""
        self.client = Client(schema)

        self.user = User.objects.create_user(
            username="rel_graphql_user",
            password="testpass123",
        )

        self.corpus = Corpus.objects.create(
            title="Relationship Test Corpus",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user,
            self.corpus,
            [PermissionTypes.READ, PermissionTypes.UPDATE, PermissionTypes.DELETE],
        )

        # Set processing_started to prevent the document processing signal
        # from firing (it would fail because test documents have no actual files).
        self.doc = Document.objects.create(
            title="Document With Structural Relationships",
            pdf_file_hash="rel_test_hash_001",
            creator=self.user,
            processing_started=timezone.now(),
        )
        set_permissions_for_obj_to_user(
            self.user,
            self.doc,
            [PermissionTypes.READ, PermissionTypes.UPDATE, PermissionTypes.DELETE],
        )

        DocumentPath.objects.create(
            document=self.doc,
            corpus=self.corpus,
            path="/documents/rel_doc",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )
        # Document is now linked via DocumentPath above

        # Create labels
        self.header_label = AnnotationLabel.objects.create(
            text="Header",
            label_type=LabelType.DOC_TYPE_LABEL,
            creator=self.user,
        )
        self.contains_label = AnnotationLabel.objects.create(
            text="Contains",
            label_type=LabelType.RELATIONSHIP_LABEL,
            creator=self.user,
        )

        # Create structural annotations for relationships
        self.parent_annot = Annotation.objects.create(
            document=self.doc,
            corpus=self.corpus,
            annotation_label=self.header_label,
            page=1,
            raw_text="Chapter 1",
            structural=True,
            creator=self.user,
        )
        self.child_annot = Annotation.objects.create(
            document=self.doc,
            corpus=self.corpus,
            annotation_label=self.header_label,
            page=1,
            raw_text="Section 1.1",
            structural=True,
            creator=self.user,
        )

        # Create structural relationship
        self.struct_rel = Relationship.objects.create(
            document=self.doc,
            corpus=self.corpus,
            relationship_label=self.contains_label,
            structural=True,
            creator=self.user,
        )
        self.struct_rel.source_annotations.add(self.parent_annot)
        self.struct_rel.target_annotations.add(self.child_annot)

    def _get_request_context(self):
        return type("Request", (), {"user": self.user})()

    def _call_migrate(self, *args, **kwargs):
        return call_command(
            "migrate_structural_annotations",
            f"--system-user-id={self.user.id}",
            *args,
            **kwargs,
        )

    def test_structural_relationships_accessible_after_migration(self):
        """
        Structural relationships must remain accessible after migration
        via the RelationshipQueryOptimizer (used by GraphQL resolvers).

        Note: The relationships GraphQL filter doesn't expose 'structural' directly,
        but the query optimizer handles both pre and post-migration states.
        """
        from opencontractserver.annotations.query_optimizer import (
            RelationshipQueryOptimizer,
        )

        # Pre-migration: verify relationship is attached to document
        self.struct_rel.refresh_from_db()
        self.assertIsNotNone(self.struct_rel.document_id)
        self.assertIsNone(self.struct_rel.structural_set_id)

        # Pre-migration query via optimizer (same as GraphQL resolver uses)
        pre_rels = RelationshipQueryOptimizer.get_document_relationships(
            document_id=self.doc.id,
            user=self.user,
            corpus_id=self.corpus.id,
            structural=True,
        )
        pre_count = pre_rels.count()
        self.assertEqual(
            pre_count, 1, "Pre-migration: should find 1 structural relationship"
        )

        # Verify content
        pre_rel = pre_rels.first()
        self.assertTrue(pre_rel.structural)
        self.assertEqual(pre_rel.relationship_label.text, "Contains")

        # Run migration
        out = io.StringIO()
        self._call_migrate(stdout=out)

        # Verify migration occurred
        self.struct_rel.refresh_from_db()
        self.assertIsNone(
            self.struct_rel.document_id,
            "Post-migration: structural relationship should have document=NULL",
        )
        self.assertIsNotNone(
            self.struct_rel.structural_set_id,
            "Post-migration: structural relationship should have structural_set set",
        )

        # Verify document is linked to structural set
        self.doc.refresh_from_db()
        self.assertIsNotNone(self.doc.structural_annotation_set)

        # Post-migration query - SAME OPTIMIZER SHOULD FIND THE RELATIONSHIP
        post_rels = RelationshipQueryOptimizer.get_document_relationships(
            document_id=self.doc.id,
            user=self.user,
            corpus_id=self.corpus.id,
            structural=True,
        )
        post_count = post_rels.count()

        # CRITICAL: Same count before and after migration
        self.assertEqual(
            post_count,
            pre_count,
            f"Post-migration should find same relationship count: pre={pre_count}, post={post_count}",
        )

        # Verify relationship content is intact
        post_rel = post_rels.first()
        self.assertTrue(post_rel.structural)
        self.assertEqual(post_rel.relationship_label.text, "Contains")

        # Verify source/target annotations are accessible
        source_annots = list(post_rel.source_annotations.all())
        target_annots = list(post_rel.target_annotations.all())

        self.assertEqual(len(source_annots), 1)
        self.assertEqual(len(target_annots), 1)
        self.assertEqual(source_annots[0].raw_text, "Chapter 1")
        self.assertEqual(target_annots[0].raw_text, "Section 1.1")

    # =========================================================================
    # TEST: GraphQL allRelationships filter — isStructural=False
    # =========================================================================

    def test_all_relationships_isStructural_false_excludes_structural(self):
        """
        ``Document.allRelationships(isStructural: false)`` excludes structural
        relationships. This is the hot-path filter the frontend uses to keep
        the initial document load lean (structural relationships are loaded
        lazily via ``allStructuralRelationships``).
        """
        # Add a non-structural user relationship to verify the filter
        # actually returns something rather than silently returning [].
        user_relation_label = AnnotationLabel.objects.create(
            text="UserRel",
            label_type=LabelType.RELATIONSHIP_LABEL,
            creator=self.user,
        )
        user_rel = Relationship.objects.create(
            document=self.doc,
            corpus=self.corpus,
            relationship_label=user_relation_label,
            structural=False,
            creator=self.user,
        )
        user_rel.source_annotations.add(self.parent_annot)
        user_rel.target_annotations.add(self.child_annot)

        doc_global_id = to_global_id("DocumentType", self.doc.id)
        corpus_global_id = to_global_id("CorpusType", self.corpus.id)

        query = """
            query GetDocRelationships($id: ID!, $corpusId: ID!) {
                document(id: $id) {
                    allRelationships(corpusId: $corpusId, isStructural: false) {
                        id
                        structural
                        relationshipLabel {
                            text
                        }
                    }
                }
            }
        """

        result = self.client.execute(
            query,
            variables={"id": doc_global_id, "corpusId": corpus_global_id},
            context_value=self._get_request_context(),
        )
        self.assertIsNone(
            result.get("errors"), f"GraphQL errors: {result.get('errors')}"
        )

        rels = result["data"]["document"]["allRelationships"]
        # Only the non-structural user relationship should come back.
        self.assertEqual(len(rels), 1)
        self.assertFalse(rels[0]["structural"])
        self.assertEqual(rels[0]["relationshipLabel"]["text"], "UserRel")

    def test_all_relationships_isStructural_true_returns_only_structural(self):
        """
        Symmetric coverage: ``isStructural: true`` returns ONLY structural
        relationships, parallel to the existing ``allAnnotations`` filter.
        """
        doc_global_id = to_global_id("DocumentType", self.doc.id)
        corpus_global_id = to_global_id("CorpusType", self.corpus.id)

        query = """
            query GetDocRelationships($id: ID!, $corpusId: ID!) {
                document(id: $id) {
                    allRelationships(corpusId: $corpusId, isStructural: true) {
                        id
                        structural
                        relationshipLabel {
                            text
                        }
                    }
                }
            }
        """

        result = self.client.execute(
            query,
            variables={"id": doc_global_id, "corpusId": corpus_global_id},
            context_value=self._get_request_context(),
        )
        self.assertIsNone(
            result.get("errors"), f"GraphQL errors: {result.get('errors')}"
        )

        rels = result["data"]["document"]["allRelationships"]
        self.assertEqual(len(rels), 1)
        self.assertTrue(rels[0]["structural"])
        self.assertEqual(rels[0]["relationshipLabel"]["text"], "Contains")

    # =========================================================================
    # TEST: GraphQL allStructuralRelationships lazy field
    # =========================================================================

    def test_all_structural_relationships_lazy_field(self):
        """
        ``Document.allStructuralRelationships`` is the dedicated lazy field
        the frontend uses (alongside ``allStructuralAnnotations``) when the
        user toggles structural visibility on. Verifies it returns the
        document's structural relationships pre- and post-migration.
        """
        doc_global_id = to_global_id("DocumentType", self.doc.id)

        query = """
            query GetDocStructuralRelationships($id: ID!) {
                document(id: $id) {
                    allStructuralRelationships {
                        id
                        structural
                        relationshipLabel {
                            text
                        }
                        sourceAnnotations {
                            edges {
                                node {
                                    id
                                    rawText
                                }
                            }
                        }
                        targetAnnotations {
                            edges {
                                node {
                                    id
                                    rawText
                                }
                            }
                        }
                    }
                }
            }
        """

        # Pre-migration: structural relationship has document FK set
        pre_result = self.client.execute(
            query,
            variables={"id": doc_global_id},
            context_value=self._get_request_context(),
        )
        self.assertIsNone(
            pre_result.get("errors"), f"GraphQL errors: {pre_result.get('errors')}"
        )
        pre_rels = pre_result["data"]["document"]["allStructuralRelationships"]
        self.assertEqual(len(pre_rels), 1)
        self.assertTrue(pre_rels[0]["structural"])
        self.assertEqual(pre_rels[0]["relationshipLabel"]["text"], "Contains")

        # Source/target annotations exposed in the same response
        pre_sources = [
            e["node"]["rawText"] for e in pre_rels[0]["sourceAnnotations"]["edges"]
        ]
        pre_targets = [
            e["node"]["rawText"] for e in pre_rels[0]["targetAnnotations"]["edges"]
        ]
        self.assertEqual(pre_sources, ["Chapter 1"])
        self.assertEqual(pre_targets, ["Section 1.1"])

        # Run migration → structural rel moves to structural_set
        out = io.StringIO()
        self._call_migrate(stdout=out)

        post_result = self.client.execute(
            query,
            variables={"id": doc_global_id},
            context_value=self._get_request_context(),
        )
        self.assertIsNone(
            post_result.get("errors"),
            f"GraphQL errors: {post_result.get('errors')}",
        )
        post_rels = post_result["data"]["document"]["allStructuralRelationships"]
        # Same count before and after migration
        self.assertEqual(len(post_rels), 1)
        self.assertTrue(post_rels[0]["structural"])
        self.assertEqual(post_rels[0]["relationshipLabel"]["text"], "Contains")
