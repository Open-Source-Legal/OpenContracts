"""
Test Feedback Mutation Permissions (RejectAnnotation, ApproveAnnotation)

This test validates that feedback mutations properly enforce COMMENT permissions
with all inheritance rules, bacon mode, and visibility boundaries.

Permission Rules for Feedback:
1. User MUST have COMMENT permission on the annotation
2. COMMENT follows inheritance: effective_comment = MIN(doc_comment, corpus_comment)
3. Bacon mode (corpus.allow_comments=True): if can_read then can_comment
4. Private annotations (created_by_analysis/extract) require visibility of source
5. Cannot comment on annotations attached to objects user cannot see
"""

import logging

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.annotations.models import (
    TOKEN_LABEL,
    Annotation,
    AnnotationLabel,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.extracts.models import Extract, Fieldset
from opencontractserver.tests.fixtures import SAMPLE_PDF_FILE_ONE_PATH
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()
logger = logging.getLogger(__name__)


class TestContext:
    """Mock context for GraphQL client"""

    def __init__(self, user):
        self.user = user


class FeedbackMutationPermissionTestCase(TestCase):
    """
    Tests that RejectAnnotation and ApproveAnnotation mutations properly
    enforce COMMENT permissions across all scenarios.
    """

    def setUp(self):
        """Set up test users, documents, corpuses, and annotations"""
        # Create test users
        self.owner = User.objects.create_user(username="owner", password="test123")
        self.commenter = User.objects.create_user(
            username="commenter", password="test123"
        )
        self.reader = User.objects.create_user(username="reader", password="test123")
        self.outsider = User.objects.create_user(
            username="outsider", password="test123"
        )
        self.superuser = User.objects.create_superuser(
            username="super", password="admin"
        )

        # Create GraphQL clients
        self.client_owner = Client(schema, context_value=TestContext(self.owner))
        self.client_commenter = Client(
            schema, context_value=TestContext(self.commenter)
        )
        self.client_reader = Client(schema, context_value=TestContext(self.reader))
        self.client_outsider = Client(schema, context_value=TestContext(self.outsider))
        self.client_super = Client(schema, context_value=TestContext(self.superuser))

        # Create document with real PDF
        with open(SAMPLE_PDF_FILE_ONE_PATH, "rb") as pdf_file:
            pdf_content = pdf_file.read()

        self.document = Document.objects.create(
            title="Test Document",
            description="Test",
            creator=self.owner,
            pdf_file=ContentFile(pdf_content, name="test.pdf"),
        )

        # Create corpus
        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            description="Test",
            creator=self.owner,
            allow_comments=False,  # Start with standard mode
        )
        self.corpus.add_document(document=self.document, user=self.owner)

        # Create annotation label
        self.label = AnnotationLabel.objects.create(
            label_type=TOKEN_LABEL,
            text="Test Label",
            creator=self.owner,
        )

        # Create annotation
        self.annotation = Annotation.objects.create(
            annotation_label=self.label,
            document=self.document,
            corpus=self.corpus,
            page=1,
            creator=self.owner,
            raw_text="Sample text for feedback",
        )

        # Create fieldset for extract
        self.fieldset = Fieldset.objects.create(
            name="Test Fieldset",
            description="Test fieldset for extracts",
            creator=self.owner,
        )

        # Create extract for testing private annotations
        self.extract = Extract.objects.create(
            name="Test Extract",
            corpus=self.corpus,
            creator=self.owner,
            fieldset=self.fieldset,
        )

        # Create private annotation linked to extract
        self.private_annotation = Annotation.objects.create(
            annotation_label=self.label,
            document=self.document,
            corpus=self.corpus,
            page=1,
            creator=self.owner,
            created_by_extract=self.extract,
            raw_text="Private annotation text",
        )

        # Give owner ALL permissions
        set_permissions_for_obj_to_user(
            self.owner, self.document, [PermissionTypes.ALL]
        )
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.ALL])
        # Extract doesn't have PUBLISH, so use CRUD instead of ALL
        set_permissions_for_obj_to_user(
            self.owner,
            self.extract,
            [
                PermissionTypes.READ,
                PermissionTypes.CREATE,
                PermissionTypes.UPDATE,
                PermissionTypes.DELETE,
                PermissionTypes.COMMENT,
            ],
        )

    def _approve_annotation(self, client, annotation_id):
        """Helper to execute ApproveAnnotation mutation"""
        mutation = """
        mutation {{
            approveAnnotation(annotationId: "{}") {{
                ok
                message
            }}
        }}
        """.format(
            annotation_id
        )
        return client.execute(mutation)

    def _reject_annotation(self, client, annotation_id):
        """Helper to execute RejectAnnotation mutation"""
        mutation = """
        mutation {{
            rejectAnnotation(annotationId: "{}") {{
                ok
                message
            }}
        }}
        """.format(
            annotation_id
        )
        return client.execute(mutation)

    # =========================================================================
    # TEST SCENARIO 1: User with COMMENT permission can provide feedback
    # =========================================================================

    def test_user_with_comment_can_approve(self):
        """User with COMMENT permission can approve annotation"""
        logger.info("\n" + "=" * 80)
        logger.info("TEST: User with COMMENT → Can Approve")
        logger.info("=" * 80)

        # Give commenter COMMENT on document and corpus
        set_permissions_for_obj_to_user(
            self.commenter,
            self.document,
            [PermissionTypes.READ, PermissionTypes.COMMENT],
        )
        set_permissions_for_obj_to_user(
            self.commenter,
            self.corpus,
            [PermissionTypes.READ, PermissionTypes.COMMENT],
        )

        ann_id = to_global_id("AnnotationType", self.annotation.id)
        result = self._approve_annotation(self.client_commenter, ann_id)

        # Should succeed
        self.assertIsNone(result.get("errors"), "Should not have GraphQL errors")
        self.assertTrue(
            result["data"]["approveAnnotation"]["ok"],
            "Approval should succeed with COMMENT permission",
        )

        logger.info("✓ User with COMMENT permission can approve annotation")

    def test_user_with_comment_can_reject(self):
        """User with COMMENT permission can reject annotation"""
        logger.info("\n" + "=" * 80)
        logger.info("TEST: User with COMMENT → Can Reject")
        logger.info("=" * 80)

        # Give commenter COMMENT on document and corpus
        set_permissions_for_obj_to_user(
            self.commenter,
            self.document,
            [PermissionTypes.READ, PermissionTypes.COMMENT],
        )
        set_permissions_for_obj_to_user(
            self.commenter,
            self.corpus,
            [PermissionTypes.READ, PermissionTypes.COMMENT],
        )

        ann_id = to_global_id("AnnotationType", self.annotation.id)
        result = self._reject_annotation(self.client_commenter, ann_id)

        # Should succeed
        self.assertIsNone(result.get("errors"), "Should not have GraphQL errors")
        self.assertTrue(
            result["data"]["rejectAnnotation"]["ok"],
            "Rejection should succeed with COMMENT permission",
        )

        logger.info("✓ User with COMMENT permission can reject annotation")

    # =========================================================================
    # TEST SCENARIO 2: User without COMMENT permission cannot provide feedback
    # =========================================================================

    def test_user_without_comment_cannot_approve(self):
        """User with READ but no COMMENT cannot approve"""
        logger.info("\n" + "=" * 80)
        logger.info("TEST: User without COMMENT → Cannot Approve")
        logger.info("=" * 80)

        # Give reader only READ, no COMMENT
        set_permissions_for_obj_to_user(
            self.reader,
            self.document,
            [PermissionTypes.READ],
        )
        set_permissions_for_obj_to_user(
            self.reader,
            self.corpus,
            [PermissionTypes.READ],
        )

        ann_id = to_global_id("AnnotationType", self.annotation.id)
        result = self._approve_annotation(self.client_reader, ann_id)

        # Should fail
        self.assertFalse(
            result["data"]["approveAnnotation"]["ok"],
            "Should not be able to approve without COMMENT permission",
        )
        self.assertIn(
            "permission",
            result["data"]["approveAnnotation"]["message"].lower(),
            "Error message should mention permission",
        )

        logger.info("✓ User without COMMENT permission cannot approve")

    def test_user_without_comment_cannot_reject(self):
        """User with READ but no COMMENT cannot reject"""
        logger.info("\n" + "=" * 80)
        logger.info("TEST: User without COMMENT → Cannot Reject")
        logger.info("=" * 80)

        # Give reader only READ, no COMMENT
        set_permissions_for_obj_to_user(
            self.reader,
            self.document,
            [PermissionTypes.READ],
        )
        set_permissions_for_obj_to_user(
            self.reader,
            self.corpus,
            [PermissionTypes.READ],
        )

        ann_id = to_global_id("AnnotationType", self.annotation.id)
        result = self._reject_annotation(self.client_reader, ann_id)

        # Should fail
        self.assertFalse(
            result["data"]["rejectAnnotation"]["ok"],
            "Should not be able to reject without COMMENT permission",
        )
        self.assertIn(
            "permission",
            result["data"]["rejectAnnotation"]["message"].lower(),
            "Error message should mention permission",
        )

        logger.info("✓ User without COMMENT permission cannot reject")

    # =========================================================================
    # TEST SCENARIO 3: Most restrictive permission wins
    # =========================================================================

    def test_comment_on_doc_but_not_corpus_blocks_feedback(self):
        """COMMENT on document but not corpus blocks feedback"""
        logger.info("\n" + "=" * 80)
        logger.info("TEST: COMMENT on Doc, READ on Corpus → Cannot Comment")
        logger.info("=" * 80)

        # Give commenter COMMENT on document but only READ on corpus
        set_permissions_for_obj_to_user(
            self.commenter,
            self.document,
            [PermissionTypes.READ, PermissionTypes.COMMENT],
        )
        set_permissions_for_obj_to_user(
            self.commenter,
            self.corpus,
            [PermissionTypes.READ],  # No COMMENT
        )

        ann_id = to_global_id("AnnotationType", self.annotation.id)
        result = self._approve_annotation(self.client_commenter, ann_id)

        # Should fail (corpus restriction applies)
        self.assertFalse(
            result["data"]["approveAnnotation"]["ok"],
            "Should not approve when corpus lacks COMMENT permission",
        )

        logger.info("✓ Most restrictive permission (corpus) blocks feedback")

    def test_comment_on_corpus_but_not_doc_blocks_feedback(self):
        """COMMENT on corpus but not document blocks feedback"""
        logger.info("\n" + "=" * 80)
        logger.info("TEST: READ on Doc, COMMENT on Corpus → Cannot Comment")
        logger.info("=" * 80)

        # Give commenter only READ on document but COMMENT on corpus
        set_permissions_for_obj_to_user(
            self.commenter,
            self.document,
            [PermissionTypes.READ],  # No COMMENT
        )
        set_permissions_for_obj_to_user(
            self.commenter,
            self.corpus,
            [PermissionTypes.READ, PermissionTypes.COMMENT],
        )

        ann_id = to_global_id("AnnotationType", self.annotation.id)
        result = self._reject_annotation(self.client_commenter, ann_id)

        # Should fail (document restriction applies)
        self.assertFalse(
            result["data"]["rejectAnnotation"]["ok"],
            "Should not reject when document lacks COMMENT permission",
        )

        logger.info("✓ Most restrictive permission (document) blocks feedback")

    # =========================================================================
    # TEST SCENARIO 4: Bacon mode enables commenting for readers
    # =========================================================================

    def test_bacon_mode_enables_feedback_for_readers(self):
        """bacon mode: corpus.allow_comments=True enables feedback for readers"""
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Bacon Mode → Readers Can Comment")
        logger.info("=" * 80)

        # Enable bacon mode
        self.corpus.allow_comments = True
        self.corpus.save()

        # Give reader only READ (no explicit COMMENT)
        set_permissions_for_obj_to_user(
            self.reader,
            self.document,
            [PermissionTypes.READ],
        )
        set_permissions_for_obj_to_user(
            self.reader,
            self.corpus,
            [PermissionTypes.READ],
        )

        ann_id = to_global_id("AnnotationType", self.annotation.id)
        result = self._approve_annotation(self.client_reader, ann_id)

        # Should succeed (bacon mode!)
        self.assertTrue(
            result["data"]["approveAnnotation"]["ok"],
            "Should approve in bacon mode with just READ permission",
        )

        logger.info("✓ Bacon mode enables feedback for readers")

    def test_bacon_mode_respects_read_boundaries(self):
        """bacon mode doesn't grant access beyond READ boundaries"""
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Bacon Mode → Still Respects READ Boundaries")
        logger.info("=" * 80)

        # Enable bacon mode
        self.corpus.allow_comments = True
        self.corpus.save()

        # Give outsider corpus READ but NO document access
        set_permissions_for_obj_to_user(
            self.outsider,
            self.corpus,
            [PermissionTypes.READ],
        )
        # Explicitly no document permissions

        ann_id = to_global_id("AnnotationType", self.annotation.id)
        result = self._approve_annotation(self.client_outsider, ann_id)

        # Should fail (can't read document = can't comment)
        self.assertFalse(
            result["data"]["approveAnnotation"]["ok"],
            "Bacon mode should not grant access beyond READ boundaries",
        )

        logger.info("✓ Bacon mode respects READ boundaries")

    def test_bacon_mode_disabled_requires_explicit_comment(self):
        """bacon mode OFF requires explicit COMMENT permission"""
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Bacon Mode OFF → Requires Explicit COMMENT")
        logger.info("=" * 80)

        # Ensure bacon mode is OFF
        self.corpus.allow_comments = False
        self.corpus.save()

        # Give reader only READ
        set_permissions_for_obj_to_user(
            self.reader,
            self.document,
            [PermissionTypes.READ],
        )
        set_permissions_for_obj_to_user(
            self.reader,
            self.corpus,
            [PermissionTypes.READ],
        )

        ann_id = to_global_id("AnnotationType", self.annotation.id)
        result = self._reject_annotation(self.client_reader, ann_id)

        # Should fail (needs explicit COMMENT)
        self.assertFalse(
            result["data"]["rejectAnnotation"]["ok"],
            "Should require explicit COMMENT when bacon mode is OFF",
        )

        logger.info("✓ Bacon mode OFF requires explicit COMMENT permission")

    # =========================================================================
    # TEST SCENARIO 5: Private annotations respect source visibility
    # =========================================================================

    def test_cannot_comment_on_annotation_from_invisible_extract(self):
        """Cannot comment on annotation from extract user cannot see"""
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Cannot Comment on Annotation from Invisible Extract")
        logger.info("=" * 80)

        # Give commenter COMMENT on document and corpus
        set_permissions_for_obj_to_user(
            self.commenter,
            self.document,
            [PermissionTypes.READ, PermissionTypes.COMMENT],
        )
        set_permissions_for_obj_to_user(
            self.commenter,
            self.corpus,
            [PermissionTypes.READ, PermissionTypes.COMMENT],
        )
        # But NO permission on the extract

        ann_id = to_global_id("AnnotationType", self.private_annotation.id)
        result = self._approve_annotation(self.client_commenter, ann_id)

        # Should fail (can't see source extract)
        self.assertFalse(
            result["data"]["approveAnnotation"]["ok"],
            "Should not comment on annotation from invisible extract",
        )

        logger.info("✓ Cannot comment on annotations from invisible extracts")

    def test_cannot_comment_with_only_read_on_extract(self):
        """Cannot comment on annotation from extract with only READ permission"""
        logger.info("\n" + "=" * 80)
        logger.info("TEST: READ on Extract (no COMMENT) → Cannot Comment on Annotation")
        logger.info("=" * 80)

        # Give commenter COMMENT on document and corpus, but only READ on extract
        set_permissions_for_obj_to_user(
            self.commenter,
            self.document,
            [PermissionTypes.READ, PermissionTypes.COMMENT],
        )
        set_permissions_for_obj_to_user(
            self.commenter,
            self.corpus,
            [PermissionTypes.READ, PermissionTypes.COMMENT],
        )
        set_permissions_for_obj_to_user(
            self.commenter,
            self.extract,
            [PermissionTypes.READ],  # Can see extract but not comment
        )

        ann_id = to_global_id("AnnotationType", self.private_annotation.id)
        result = self._approve_annotation(self.client_commenter, ann_id)

        # Should fail (needs COMMENT on extract, not just READ)
        self.assertFalse(
            result["data"]["approveAnnotation"]["ok"],
            "Should not comment without COMMENT permission on extract",
        )

        logger.info("✓ READ on extract (no COMMENT) blocks annotation commenting")

    def test_can_comment_with_comment_on_extract(self):
        """Can comment on annotation when COMMENT granted on extract"""
        logger.info("\n" + "=" * 80)
        logger.info("TEST: COMMENT on Extract → Can Comment on Annotation")
        logger.info("=" * 80)

        # Give commenter COMMENT on document, corpus, AND extract
        set_permissions_for_obj_to_user(
            self.commenter,
            self.document,
            [PermissionTypes.READ, PermissionTypes.COMMENT],
        )
        set_permissions_for_obj_to_user(
            self.commenter,
            self.corpus,
            [PermissionTypes.READ, PermissionTypes.COMMENT],
        )
        set_permissions_for_obj_to_user(
            self.commenter,
            self.extract,
            [PermissionTypes.READ, PermissionTypes.COMMENT],  # COMMENT on extract
        )

        ann_id = to_global_id("AnnotationType", self.private_annotation.id)
        result = self._approve_annotation(self.client_commenter, ann_id)

        # Should succeed (has COMMENT on all sources)
        self.assertTrue(
            result["data"]["approveAnnotation"]["ok"],
            "Should comment on annotation when COMMENT granted on extract",
        )

        logger.info("✓ COMMENT on extract enables annotation commenting")

    # =========================================================================
    # TEST SCENARIO 6: No document access blocks feedback
    # =========================================================================

    def test_no_document_access_blocks_feedback(self):
        """No document access blocks feedback even with corpus COMMENT"""
        logger.info("\n" + "=" * 80)
        logger.info("TEST: No Document Access → No Feedback")
        logger.info("=" * 80)

        # Give commenter corpus COMMENT but NO document access
        set_permissions_for_obj_to_user(
            self.commenter,
            self.corpus,
            [PermissionTypes.READ, PermissionTypes.COMMENT],
        )
        # Explicitly no document permissions

        ann_id = to_global_id("AnnotationType", self.annotation.id)
        result = self._approve_annotation(self.client_commenter, ann_id)

        # Should fail (document is primary, must have access)
        self.assertFalse(
            result["data"]["approveAnnotation"]["ok"],
            "Should not provide feedback without document access",
        )

        logger.info("✓ No document access blocks feedback")

    def test_no_corpus_access_blocks_feedback_on_corpus_annotation(self):
        """No corpus access blocks feedback on corpus annotations"""
        logger.info("\n" + "=" * 80)
        logger.info("TEST: No Corpus Access → No Feedback on Corpus Annotations")
        logger.info("=" * 80)

        # Give commenter document COMMENT but NO corpus access
        set_permissions_for_obj_to_user(
            self.commenter,
            self.document,
            [PermissionTypes.READ, PermissionTypes.COMMENT],
        )
        # Explicitly no corpus permissions

        ann_id = to_global_id("AnnotationType", self.annotation.id)
        result = self._reject_annotation(self.client_commenter, ann_id)

        # Should fail (corpus annotation requires corpus permission)
        self.assertFalse(
            result["data"]["rejectAnnotation"]["ok"],
            "Should not provide feedback on corpus annotation without corpus access",
        )

        logger.info("✓ No corpus access blocks feedback on corpus annotations")

    # =========================================================================
    # TEST SCENARIO 7: Superuser always has access
    # =========================================================================

    def test_superuser_can_always_provide_feedback(self):
        """Superuser can always approve/reject regardless of permissions"""
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Superuser → Always Has Feedback Access")
        logger.info("=" * 80)

        ann_id = to_global_id("AnnotationType", self.annotation.id)

        # Test approve
        result_approve = self._approve_annotation(self.client_super, ann_id)
        self.assertTrue(
            result_approve["data"]["approveAnnotation"]["ok"],
            "Superuser should always be able to approve",
        )

        # Test reject
        result_reject = self._reject_annotation(self.client_super, ann_id)
        self.assertTrue(
            result_reject["data"]["rejectAnnotation"]["ok"],
            "Superuser should always be able to reject",
        )

        logger.info("✓ Superuser always has feedback access")

    # =========================================================================
    # TEST SCENARIO 8: Complete outsider has no access
    # =========================================================================

    def test_complete_outsider_cannot_provide_feedback(self):
        """User with no permissions at all cannot provide feedback"""
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Complete Outsider → No Feedback Access")
        logger.info("=" * 80)

        # Outsider has no permissions on anything

        ann_id = to_global_id("AnnotationType", self.annotation.id)

        # Test approve
        result_approve = self._approve_annotation(self.client_outsider, ann_id)
        self.assertFalse(
            result_approve["data"]["approveAnnotation"]["ok"],
            "Outsider should not be able to approve",
        )

        # Test reject
        result_reject = self._reject_annotation(self.client_outsider, ann_id)
        self.assertFalse(
            result_reject["data"]["rejectAnnotation"]["ok"],
            "Outsider should not be able to reject",
        )

        logger.info("✓ Complete outsider cannot provide feedback")

    # =========================================================================
    # TEST SCENARIO 9: UPDATE permission without COMMENT blocks feedback
    # =========================================================================

    def test_update_without_comment_blocks_feedback(self):
        """Having UPDATE but not COMMENT blocks feedback (no longer implicit)"""
        logger.info("\n" + "=" * 80)
        logger.info("TEST: UPDATE without COMMENT → Cannot Provide Feedback")
        logger.info("=" * 80)

        # Give commenter UPDATE but explicitly not COMMENT
        set_permissions_for_obj_to_user(
            self.commenter,
            self.document,
            [PermissionTypes.READ, PermissionTypes.UPDATE],
        )
        set_permissions_for_obj_to_user(
            self.commenter,
            self.corpus,
            [PermissionTypes.READ, PermissionTypes.UPDATE],
        )

        ann_id = to_global_id("AnnotationType", self.annotation.id)
        result = self._approve_annotation(self.client_commenter, ann_id)

        # Should fail (UPDATE doesn't imply COMMENT anymore)
        self.assertFalse(
            result["data"]["approveAnnotation"]["ok"],
            "UPDATE permission should not grant feedback access without COMMENT",
        )

        logger.info("✓ UPDATE without COMMENT does not grant feedback access")
