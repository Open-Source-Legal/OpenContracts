"""
Tests for IDOR protection fixes in GraphQL mutations.

This test suite verifies IDOR vulnerabilities have been properly fixed
by ensuring identical error messages for 'not found' vs 'no permission' cases.

Tests cover:
1. RemoveAnnotation - Cannot delete annotations without permission
2. RejectAnnotation - Cannot reject annotations without permission
3. ApproveAnnotation - Cannot approve annotations without permission
4. RemoveRelationship - Cannot delete relationships without permission
5. RemoveRelationships (batch) - Cannot batch-delete relationships without permission
6. UpdateRelations - Cannot update relationships without permission
7. StartCorpusFork - Cannot fork private corpuses
8. StartCorpusExport - Cannot export corpuses without permission
9. StartDocumentExtract - Cannot create extracts for inaccessible documents/fieldsets
10. DeleteMultipleLabelMutation - Cannot delete labels without permission
11. Badge IDOR protection - Same error for "not found" vs "no permission"
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.annotations.models import (
    AnnotationLabel,
    Note,
    Relationship,
)
from opencontractserver.badges.models import Badge, BadgeTypeChoices
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.extracts.models import Fieldset
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class MockContext:
    """Mock context for GraphQL client."""

    def __init__(self, user):
        self.user = user


class TestRemoveRelationshipsSecurity(TestCase):
    """Tests for RemoveRelationships mutation permission checks."""

    def setUp(self):
        """Create test users and relationships."""
        self.owner = User.objects.create_user(
            username="owner", password="test", email="owner@test.com"
        )
        self.unauthorized_user = User.objects.create_user(
            username="unauthorized", password="test", email="unauth@test.com"
        )

        # Create corpus and document
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )
        self.document = Document.objects.create(
            title="Test Document",
            creator=self.owner,
            is_public=False,
            backend_lock=False,
        )

        # Set permissions for owner
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.CRUD])
        set_permissions_for_obj_to_user(
            self.owner, self.document, [PermissionTypes.CRUD]
        )

        # Create relationship label (using AnnotationLabel)
        self.rel_label = AnnotationLabel.objects.create(
            text="Test Relation", creator=self.owner
        )

        # Create relationship
        self.relationship = Relationship.objects.create(
            relationship_label=self.rel_label,
            document=self.document,
            corpus=self.corpus,
            creator=self.owner,
        )

    def test_cannot_delete_relationship_without_permission(self):
        """
        GIVEN: An unauthorized user without DELETE permission on a relationship
        WHEN: User attempts to delete the relationship via RemoveRelationships mutation
        THEN: Mutation should fail with permission denied error
        """
        client = Client(schema, context_value=MockContext(self.unauthorized_user))

        mutation = """
            mutation RemoveRelationships($relationshipIds: [String]!) {
                removeRelationships(relationshipIds: $relationshipIds) {
                    ok
                    message
                }
            }
        """

        variables = {
            "relationshipIds": [to_global_id("RelationshipType", self.relationship.id)]
        }

        result = client.execute(mutation, variables=variables)

        # Mutation should fail with the unified IDOR-safe message (issue #1449)
        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["removeRelationships"]["ok"])
        self.assertIn(
            "do not have permission",
            result["data"]["removeRelationships"]["message"],
        )

        # Relationship should still exist
        self.assertTrue(Relationship.objects.filter(id=self.relationship.id).exists())

    def test_owner_can_delete_own_relationship(self):
        """
        GIVEN: An owner with DELETE permission on a relationship
        WHEN: Owner attempts to delete the relationship via RemoveRelationships mutation
        THEN: Mutation should succeed and relationship should be deleted
        """
        client = Client(schema, context_value=MockContext(self.owner))

        mutation = """
            mutation RemoveRelationships($relationshipIds: [String]!) {
                removeRelationships(relationshipIds: $relationshipIds) {
                    ok
                    message
                }
            }
        """

        variables = {
            "relationshipIds": [to_global_id("RelationshipType", self.relationship.id)]
        }

        result = client.execute(mutation, variables=variables)

        # Mutation should succeed
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["removeRelationships"]["ok"])

        # Relationship should be deleted
        self.assertFalse(Relationship.objects.filter(id=self.relationship.id).exists())

    def test_same_error_for_nonexistent_relationship(self):
        """
        GIVEN: An unauthorized user
        WHEN: User attempts to delete a non-existent relationship
        THEN: Error message should be same as when relationship exists but user lacks permission (IDOR protection)
        """
        client = Client(schema, context_value=MockContext(self.unauthorized_user))

        mutation = """
            mutation RemoveRelationships($relationshipIds: [String]!) {
                removeRelationships(relationshipIds: $relationshipIds) {
                    ok
                    message
                }
            }
        """

        # Use a fake ID
        variables = {"relationshipIds": [to_global_id("RelationshipType", 999999)]}

        result = client.execute(mutation, variables=variables)

        # Should get the same unified IDOR-safe message as the unauthorized
        # case above (issue #1449)
        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["removeRelationships"]["ok"])
        self.assertEqual(
            result["data"]["removeRelationships"]["message"],
            "Relationship not found or you do not have permission to access it",
        )


class TestUpdateRelationsSecurity(TestCase):
    """Tests for UpdateRelations mutation permission checks."""

    def setUp(self):
        """Create test users and relationships."""
        self.owner = User.objects.create_user(
            username="owner", password="test", email="owner@test.com"
        )
        self.unauthorized_user = User.objects.create_user(
            username="unauthorized", password="test", email="unauth@test.com"
        )

        # Create corpus and document
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )
        self.document = Document.objects.create(
            title="Test Document",
            creator=self.owner,
            is_public=False,
            backend_lock=False,
        )

        # Set permissions
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.CRUD])
        set_permissions_for_obj_to_user(
            self.owner, self.document, [PermissionTypes.CRUD]
        )

        # Create relationship label (using AnnotationLabel)
        self.rel_label = AnnotationLabel.objects.create(
            text="Test Relation", creator=self.owner
        )

        # Create relationship
        self.relationship = Relationship.objects.create(
            relationship_label=self.rel_label,
            document=self.document,
            corpus=self.corpus,
            creator=self.owner,
        )

    def test_cannot_update_relationship_without_permission(self):
        """
        GIVEN: An unauthorized user without UPDATE permission on a relationship
        WHEN: User attempts to update the relationship via UpdateRelations mutation
        THEN: Mutation should fail with permission denied error
        """
        client = Client(schema, context_value=MockContext(self.unauthorized_user))

        mutation = """
            mutation UpdateRelationships($relationships: [RelationInputType]!) {
                updateRelationships(relationships: $relationships) {
                    ok
                    message
                }
            }
        """

        variables = {
            "relationships": [
                {
                    "id": to_global_id("RelationshipType", self.relationship.id),
                    "relationshipLabelId": to_global_id(
                        "AnnotationLabelType", self.rel_label.id
                    ),
                    "corpusId": to_global_id("CorpusType", self.corpus.id),
                    "documentId": to_global_id("DocumentType", self.document.id),
                    "sourceIds": [],
                    "targetIds": [],
                }
            ]
        }

        result = client.execute(mutation, variables=variables)

        # Mutation should fail with the unified IDOR-safe message (issue #1449)
        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["updateRelationships"]["ok"])
        self.assertIn(
            "do not have permission",
            result["data"]["updateRelationships"]["message"],
        )


class TestStartCorpusForkSecurity(TestCase):
    """Tests for StartCorpusFork mutation permission checks."""

    def setUp(self):
        """Create test users and corpus."""
        self.owner = User.objects.create_user(
            username="owner", password="test", email="owner@test.com"
        )
        self.unauthorized_user = User.objects.create_user(
            username="unauthorized", password="test", email="unauth@test.com"
        )

        # Create private corpus
        self.private_corpus = Corpus.objects.create(
            title="Private Corpus", creator=self.owner, is_public=False
        )

        # Set permissions for owner only
        set_permissions_for_obj_to_user(
            self.owner, self.private_corpus, [PermissionTypes.CRUD]
        )

    def test_cannot_fork_private_corpus_without_permission(self):
        """
        GIVEN: A private corpus that user does not have READ permission for
        WHEN: Unauthorized user attempts to fork the corpus
        THEN: Mutation should fail with "Corpus not found" error (IDOR protection)
        """
        client = Client(schema, context_value=MockContext(self.unauthorized_user))

        mutation = """
            mutation StartCorpusFork($corpusId: String!) {
                forkCorpus(corpusId: $corpusId) {
                    ok
                    message
                    newCorpus {
                        id
                        title
                    }
                }
            }
        """

        variables = {"corpusId": to_global_id("CorpusType", self.private_corpus.id)}

        result = client.execute(mutation, variables=variables)

        # Mutation should fail with "not found" error (IDOR protection)
        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["forkCorpus"]["ok"])
        self.assertEqual(result["data"]["forkCorpus"]["message"], "Corpus not found")
        self.assertIsNone(result["data"]["forkCorpus"]["newCorpus"])

    def test_same_error_for_nonexistent_corpus(self):
        """
        GIVEN: A non-existent corpus ID
        WHEN: User attempts to fork it
        THEN: Same error message as when corpus exists but user lacks permission (IDOR protection)
        """
        client = Client(schema, context_value=MockContext(self.unauthorized_user))

        mutation = """
            mutation StartCorpusFork($corpusId: String!) {
                forkCorpus(corpusId: $corpusId) {
                    ok
                    message
                    newCorpus {
                        id
                    }
                }
            }
        """

        variables = {"corpusId": to_global_id("CorpusType", 999999)}

        result = client.execute(mutation, variables=variables)

        # Should get same "not found" error
        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["forkCorpus"]["ok"])
        self.assertEqual(result["data"]["forkCorpus"]["message"], "Corpus not found")


class TestStartCorpusExportSecurity(TestCase):
    """Tests for StartCorpusExport mutation permission checks."""

    def setUp(self):
        """Create test users and corpus."""
        self.owner = User.objects.create_user(
            username="owner", password="test", email="owner@test.com"
        )
        self.unauthorized_user = User.objects.create_user(
            username="unauthorized", password="test", email="unauth@test.com"
        )

        # Create private corpus
        self.private_corpus = Corpus.objects.create(
            title="Private Corpus", creator=self.owner, is_public=False
        )

        # Set permissions for owner only
        set_permissions_for_obj_to_user(
            self.owner, self.private_corpus, [PermissionTypes.CRUD]
        )

    def test_cannot_export_corpus_without_permission(self):
        """
        GIVEN: A corpus that user does not have READ permission for
        WHEN: Unauthorized user attempts to export the corpus
        THEN: Mutation should fail with "Corpus not found" error (IDOR protection)
        """
        client = Client(schema, context_value=MockContext(self.unauthorized_user))

        mutation = """
            mutation StartCorpusExport($corpusId: String!, $exportFormat: ExportType!) {
                exportCorpus(corpusId: $corpusId, exportFormat: $exportFormat) {
                    ok
                    message
                    export {
                        id
                    }
                }
            }
        """

        variables = {
            "corpusId": to_global_id("CorpusType", self.private_corpus.id),
            "exportFormat": "OPEN_CONTRACTS",
        }

        result = client.execute(mutation, variables=variables)

        # Mutation should fail
        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["exportCorpus"]["ok"])
        # Should use consistent error message for IDOR protection
        self.assertIn("not found", result["data"]["exportCorpus"]["message"].lower())


class TestStartDocumentExtractSecurity(TestCase):
    """Tests for StartDocumentExtract mutation permission checks."""

    def setUp(self):
        """Create test users, document, and fieldset."""
        self.owner = User.objects.create_user(
            username="owner", password="test", email="owner@test.com"
        )
        self.unauthorized_user = User.objects.create_user(
            username="unauthorized", password="test", email="unauth@test.com"
        )

        # Create private document
        self.private_document = Document.objects.create(
            title="Private Document",
            creator=self.owner,
            is_public=False,
            backend_lock=False,
        )

        # Create private fieldset
        self.private_fieldset = Fieldset.objects.create(
            name="Private Fieldset", creator=self.owner
        )

        # Set permissions for owner only
        set_permissions_for_obj_to_user(
            self.owner, self.private_document, [PermissionTypes.CRUD]
        )
        set_permissions_for_obj_to_user(
            self.owner, self.private_fieldset, [PermissionTypes.CRUD]
        )

    def test_cannot_create_extract_for_inaccessible_document(self):
        """
        GIVEN: A document and fieldset that user does not have access to
        WHEN: Unauthorized user attempts to create extract
        THEN: Mutation should fail with "Resource not found" error (IDOR protection)
        """
        client = Client(schema, context_value=MockContext(self.unauthorized_user))

        mutation = """
            mutation StartExtractForDoc($documentId: ID!, $fieldsetId: ID!) {
                startExtractForDoc(documentId: $documentId, fieldsetId: $fieldsetId) {
                    ok
                    message
                    obj {
                        id
                    }
                }
            }
        """

        variables = {
            "documentId": to_global_id("DocumentType", self.private_document.id),
            "fieldsetId": to_global_id("FieldsetType", self.private_fieldset.id),
        }

        result = client.execute(mutation, variables=variables)

        # Mutation should fail
        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["startExtractForDoc"]["ok"])
        self.assertEqual(
            result["data"]["startExtractForDoc"]["message"], "Resource not found"
        )

    def test_cannot_create_extract_for_inaccessible_fieldset(self):
        """
        GIVEN: User has access to document but not fieldset
        WHEN: User attempts to create extract
        THEN: Mutation should fail with "Resource not found" error
        """
        # Give unauthorized user access to document but not fieldset
        set_permissions_for_obj_to_user(
            self.unauthorized_user, self.private_document, [PermissionTypes.READ]
        )

        client = Client(schema, context_value=MockContext(self.unauthorized_user))

        mutation = """
            mutation StartExtractForDoc($documentId: ID!, $fieldsetId: ID!) {
                startExtractForDoc(documentId: $documentId, fieldsetId: $fieldsetId) {
                    ok
                    message
                    obj {
                        id
                    }
                }
            }
        """

        variables = {
            "documentId": to_global_id("DocumentType", self.private_document.id),
            "fieldsetId": to_global_id("FieldsetType", self.private_fieldset.id),
        }

        result = client.execute(mutation, variables=variables)

        # Mutation should fail
        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["startExtractForDoc"]["ok"])
        self.assertEqual(
            result["data"]["startExtractForDoc"]["message"], "Resource not found"
        )


class TestDeleteMultipleLabelMutationSecurity(TestCase):
    """
    Tests for DeleteMultipleLabelMutation permission checks.

    Note: AnnotationLabel uses creator-based permissions (no guardian object permissions).
    Only the creator or superuser can delete labels.
    """

    def setUp(self):
        """Create test users and labels."""
        self.owner = User.objects.create_user(
            username="owner", password="test", email="owner@test.com"
        )
        self.unauthorized_user = User.objects.create_user(
            username="unauthorized", password="test", email="unauth@test.com"
        )

        # Create label - creator-based permissions apply (owner is the creator)
        self.label = AnnotationLabel.objects.create(
            text="Test Label", creator=self.owner
        )
        # No guardian permissions needed - AnnotationLabel uses creator-based permissions

    def test_cannot_delete_label_without_permission(self):
        """
        GIVEN: A label that user does not have DELETE permission for
        WHEN: Unauthorized user attempts to delete the label
        THEN: Mutation should fail with IDOR-safe error message (Label not found)
        """
        client = Client(schema, context_value=MockContext(self.unauthorized_user))

        mutation = """
            mutation DeleteMultipleLabels($labelIds: [String]!) {
                deleteMultipleAnnotationLabels(annotationLabelIdsToDelete: $labelIds) {
                    ok
                    message
                }
            }
        """

        variables = {"labelIds": [to_global_id("AnnotationLabelType", self.label.id)]}

        result = client.execute(mutation, variables=variables)

        # Mutation should fail with IDOR-safe message
        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["deleteMultipleAnnotationLabels"]["ok"])
        # Same message for non-existent and permission denied (IDOR protection)
        self.assertEqual(
            "Label not found",
            result["data"]["deleteMultipleAnnotationLabels"]["message"],
        )

        # Label should still exist
        self.assertTrue(AnnotationLabel.objects.filter(id=self.label.id).exists())

    def test_owner_can_delete_own_label(self):
        """
        GIVEN: A user who is the creator of a label
        WHEN: Creator attempts to delete their own label
        THEN: Mutation should succeed and label should be deleted
        """
        client = Client(schema, context_value=MockContext(self.owner))

        mutation = """
            mutation DeleteMultipleLabels($labelIds: [String]!) {
                deleteMultipleAnnotationLabels(annotationLabelIdsToDelete: $labelIds) {
                    ok
                    message
                }
            }
        """

        variables = {"labelIds": [to_global_id("AnnotationLabelType", self.label.id)]}

        result = client.execute(mutation, variables=variables)

        # Mutation should succeed
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["deleteMultipleAnnotationLabels"]["ok"])

        # Label should be deleted
        self.assertFalse(AnnotationLabel.objects.filter(id=self.label.id).exists())


class TestBadgeMutationIDORProtection(TestCase):
    """Tests for Badge mutation IDOR protection."""

    def setUp(self):
        """Create test users, badges, and corpuses."""
        self.admin = User.objects.create_superuser(
            username="badge_idor_superuser",
            password="test",
            email="badge_idor_admin@test.com",
        )
        self.corpus_owner = User.objects.create_user(
            username="corpusowner", password="test", email="owner@test.com"
        )
        self.normal_user = User.objects.create_user(
            username="normaluser", password="test", email="normal@test.com"
        )

        # Create private corpus
        self.private_corpus = Corpus.objects.create(
            title="Private Corpus", creator=self.corpus_owner, is_public=False
        )
        set_permissions_for_obj_to_user(
            self.corpus_owner, self.private_corpus, [PermissionTypes.CRUD]
        )

        # Create global badge
        self.global_badge = Badge.objects.create(
            name="Test Badge",
            description="Test",
            icon="Star",
            badge_type=BadgeTypeChoices.GLOBAL,
            creator=self.admin,
        )

    def test_create_badge_same_error_for_nonexistent_and_inaccessible_corpus(self):
        """
        GIVEN: A normal user without access to a private corpus
        WHEN: User attempts to create a corpus badge for that corpus
        THEN: Should get same "Corpus not found" error as for non-existent corpus (IDOR protection)
        """
        client = Client(schema, context_value=MockContext(self.normal_user))

        # Test with inaccessible corpus
        mutation_inaccessible = f"""
            mutation CreateBadge {{
                createBadge(
                    name: "Test Badge"
                    description: "Test"
                    icon: "Trophy"
                    badgeType: "CORPUS"
                    corpusId: "{to_global_id("CorpusType", self.private_corpus.id)}"
                ) {{
                    ok
                    message
                }}
            }}
        """

        result1 = client.execute(mutation_inaccessible)
        self.assertIsNone(result1.get("errors"))
        self.assertFalse(result1["data"]["createBadge"]["ok"])
        error_msg_1 = result1["data"]["createBadge"]["message"]

        # Test with non-existent corpus
        mutation_nonexistent = f"""
            mutation CreateBadge {{
                createBadge(
                    name: "Test Badge 2"
                    description: "Test"
                    icon: "Trophy"
                    badgeType: "CORPUS"
                    corpusId: "{to_global_id("CorpusType", 999999)}"
                ) {{
                    ok
                    message
                }}
            }}
        """

        result2 = client.execute(mutation_nonexistent)
        self.assertIsNone(result2.get("errors"))
        self.assertFalse(result2["data"]["createBadge"]["ok"])
        error_msg_2 = result2["data"]["createBadge"]["message"]

        # Both should give same error message
        self.assertEqual(error_msg_1, "Corpus not found")
        self.assertEqual(error_msg_2, "Corpus not found")
        self.assertEqual(error_msg_1, error_msg_2)


class TestAnnotationMutationIDORProtection(TestCase):
    """Tests for IDOR protection in annotation mutations."""

    def setUp(self):
        """Create test users and annotations."""
        from opencontractserver.annotations.models import Annotation, AnnotationLabel
        from opencontractserver.documents.models import Document

        self.owner = User.objects.create_user(
            username="annot_owner", password="test", email="annot_owner@test.com"
        )
        self.unauthorized_user = User.objects.create_user(
            username="annot_unauth", password="test", email="annot_unauth@test.com"
        )

        # Create corpus
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.CRUD])

        # Create document
        self.document = Document.objects.create(
            title="Test Document",
            creator=self.owner,
            is_public=False,
            backend_lock=False,
        )
        set_permissions_for_obj_to_user(
            self.owner, self.document, [PermissionTypes.CRUD]
        )

        # Create label
        self.label = AnnotationLabel.objects.create(
            text="Test Label", creator=self.owner
        )

        # Create annotation
        self.annotation = Annotation.objects.create(
            document=self.document,
            corpus=self.corpus,
            annotation_label=self.label,
            creator=self.owner,
            raw_text="Test annotation",
        )
        set_permissions_for_obj_to_user(
            self.owner, self.annotation, [PermissionTypes.CRUD]
        )

    def test_remove_annotation_idor_protection(self):
        """
        IDOR Protection: RemoveAnnotation should return the same error message
        for non-existent and inaccessible annotations.
        """
        client = Client(schema, context_value=MockContext(self.unauthorized_user))

        mutation = """
            mutation RemoveAnnotation($annotationId: String!) {
                removeAnnotation(annotationId: $annotationId) {
                    ok
                    message
                }
            }
        """

        # Test 1: Inaccessible annotation
        result_no_perm = client.execute(
            mutation,
            variables={
                "annotationId": to_global_id("AnnotationType", self.annotation.id)
            },
        )
        self.assertIsNone(result_no_perm.get("errors"))
        error_msg_no_perm = result_no_perm["data"]["removeAnnotation"]["message"]

        # Test 2: Non-existent annotation
        result_not_found = client.execute(
            mutation,
            variables={"annotationId": to_global_id("AnnotationType", 999999)},
        )
        self.assertIsNone(result_not_found.get("errors"))
        error_msg_not_found = result_not_found["data"]["removeAnnotation"]["message"]

        # Both should return the same error message
        self.assertEqual(
            error_msg_no_perm,
            error_msg_not_found,
            "IDOR vulnerability: Different error messages allow ID enumeration",
        )
        self.assertFalse(result_no_perm["data"]["removeAnnotation"]["ok"])
        self.assertFalse(result_not_found["data"]["removeAnnotation"]["ok"])

    def test_reject_annotation_idor_protection(self):
        """
        IDOR Protection: RejectAnnotation should return the same error message
        for non-existent and inaccessible annotations.
        """
        client = Client(schema, context_value=MockContext(self.unauthorized_user))

        mutation = """
            mutation RejectAnnotation($annotationId: ID!) {
                rejectAnnotation(annotationId: $annotationId) {
                    ok
                    message
                }
            }
        """

        # Test 1: Inaccessible annotation
        result_no_perm = client.execute(
            mutation,
            variables={
                "annotationId": to_global_id("AnnotationType", self.annotation.id)
            },
        )
        self.assertIsNone(result_no_perm.get("errors"))
        error_msg_no_perm = result_no_perm["data"]["rejectAnnotation"]["message"]

        # Test 2: Non-existent annotation
        result_not_found = client.execute(
            mutation,
            variables={"annotationId": to_global_id("AnnotationType", 999999)},
        )
        self.assertIsNone(result_not_found.get("errors"))
        error_msg_not_found = result_not_found["data"]["rejectAnnotation"]["message"]

        # Both should return the same error message
        self.assertEqual(
            error_msg_no_perm,
            error_msg_not_found,
            "IDOR vulnerability: Different error messages allow ID enumeration",
        )
        self.assertFalse(result_no_perm["data"]["rejectAnnotation"]["ok"])
        self.assertFalse(result_not_found["data"]["rejectAnnotation"]["ok"])

    def test_approve_annotation_idor_protection(self):
        """
        IDOR Protection: ApproveAnnotation should return the same error message
        for non-existent and inaccessible annotations.
        """
        client = Client(schema, context_value=MockContext(self.unauthorized_user))

        mutation = """
            mutation ApproveAnnotation($annotationId: ID!) {
                approveAnnotation(annotationId: $annotationId) {
                    ok
                    message
                }
            }
        """

        # Test 1: Inaccessible annotation
        result_no_perm = client.execute(
            mutation,
            variables={
                "annotationId": to_global_id("AnnotationType", self.annotation.id)
            },
        )
        self.assertIsNone(result_no_perm.get("errors"))
        error_msg_no_perm = result_no_perm["data"]["approveAnnotation"]["message"]

        # Test 2: Non-existent annotation
        result_not_found = client.execute(
            mutation,
            variables={"annotationId": to_global_id("AnnotationType", 999999)},
        )
        self.assertIsNone(result_not_found.get("errors"))
        error_msg_not_found = result_not_found["data"]["approveAnnotation"]["message"]

        # Both should return the same error message
        self.assertEqual(
            error_msg_no_perm,
            error_msg_not_found,
            "IDOR vulnerability: Different error messages allow ID enumeration",
        )
        self.assertFalse(result_no_perm["data"]["approveAnnotation"]["ok"])
        self.assertFalse(result_not_found["data"]["approveAnnotation"]["ok"])


class TestRemoveRelationshipIDORProtection(TestCase):
    """Tests for IDOR protection in RemoveRelationship mutation."""

    def setUp(self):
        """Create test users and relationships."""
        from opencontractserver.annotations.models import AnnotationLabel, Relationship
        from opencontractserver.documents.models import Document

        self.owner = User.objects.create_user(
            username="rel_owner", password="test", email="rel_owner@test.com"
        )
        self.unauthorized_user = User.objects.create_user(
            username="rel_unauth", password="test", email="rel_unauth@test.com"
        )

        # Create corpus
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.CRUD])

        # Create document
        self.document = Document.objects.create(
            title="Test Document",
            creator=self.owner,
            is_public=False,
            backend_lock=False,
        )
        set_permissions_for_obj_to_user(
            self.owner, self.document, [PermissionTypes.CRUD]
        )

        # Create relationship label
        self.rel_label = AnnotationLabel.objects.create(
            text="Test Relation", creator=self.owner
        )

        # Create relationship
        self.relationship = Relationship.objects.create(
            relationship_label=self.rel_label,
            document=self.document,
            corpus=self.corpus,
            creator=self.owner,
        )

    def test_remove_relationship_idor_protection(self):
        """
        IDOR Protection: RemoveRelationship should return the same error message
        for non-existent and inaccessible relationships.
        """
        client = Client(schema, context_value=MockContext(self.unauthorized_user))

        mutation = """
            mutation RemoveRelationship($relationshipId: String!) {
                removeRelationship(relationshipId: $relationshipId) {
                    ok
                    message
                }
            }
        """

        # Test 1: Inaccessible relationship
        result_no_perm = client.execute(
            mutation,
            variables={
                "relationshipId": to_global_id("RelationshipType", self.relationship.id)
            },
        )
        self.assertIsNone(result_no_perm.get("errors"))
        error_msg_no_perm = result_no_perm["data"]["removeRelationship"]["message"]

        # Test 2: Non-existent relationship
        result_not_found = client.execute(
            mutation,
            variables={"relationshipId": to_global_id("RelationshipType", 999999)},
        )
        self.assertIsNone(result_not_found.get("errors"))
        error_msg_not_found = result_not_found["data"]["removeRelationship"]["message"]

        # Both should return the same error message
        self.assertEqual(
            error_msg_no_perm,
            error_msg_not_found,
            "IDOR vulnerability: Different error messages allow ID enumeration",
        )
        self.assertFalse(result_no_perm["data"]["removeRelationship"]["ok"])
        self.assertFalse(result_not_found["data"]["removeRelationship"]["ok"])


class TestUpdateNoteIDORProtection(TestCase):
    """``UpdateNote`` must return identical responses for missing-id, hidden-id,
    and visible-but-not-creator branches so an attacker cannot enumerate notes.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="note_owner", password="test", email="o@test.com"
        )
        self.outsider = User.objects.create_user(
            username="note_outsider", password="test", email="x@test.com"
        )
        self.document = Document.objects.create(
            title="Doc",
            creator=self.owner,
            is_public=True,  # outsider can see the doc but not the note
            backend_lock=False,
        )
        self.note = Note.objects.create(
            title="Private",
            content="secret",
            creator=self.owner,
            document=self.document,
        )

    def _execute(self, user, note_pk: int) -> dict:
        client = Client(schema, context_value=MockContext(user))
        return client.execute(
            """
            mutation UpdateNote($noteId: ID!, $newContent: String!) {
                updateNote(noteId: $noteId, newContent: $newContent) {
                    ok
                    message
                }
            }
            """,
            variables={
                "noteId": to_global_id("NoteType", note_pk),
                "newContent": "tampered",
            },
        )

    def test_missing_and_hidden_and_non_creator_collapse_to_one_message(self):
        # Branch A: note id does not exist
        missing = self._execute(self.outsider, 999_999)
        # Branch B: note exists but the caller is not the creator
        non_creator = self._execute(self.outsider, self.note.id)

        self.assertIsNone(missing.get("errors"))
        self.assertIsNone(non_creator.get("errors"))
        self.assertFalse(missing["data"]["updateNote"]["ok"])
        self.assertFalse(non_creator["data"]["updateNote"]["ok"])
        self.assertEqual(
            missing["data"]["updateNote"]["message"],
            non_creator["data"]["updateNote"]["message"],
            "IDOR: missing-id and not-creator branches must be byte-identical",
        )


class TestUpdateCorpusDescriptionIDORProtection(TestCase):
    """``UpdateCorpusDescription`` must collapse missing-id and not-creator
    branches to a single response."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username="cd_owner", password="test", email="cd@test.com"
        )
        self.outsider = User.objects.create_user(
            username="cd_outsider", password="test", email="cdo@test.com"
        )
        # Public corpus so the outsider passes ``visible_to_user`` and we
        # exercise the "visible but not the creator" branch.
        self.corpus = Corpus.objects.create(
            title="Public", creator=self.owner, is_public=True
        )

    def _execute(self, user, corpus_pk: int) -> dict:
        client = Client(schema, context_value=MockContext(user))
        return client.execute(
            """
            mutation UpdateCorpusDescription($corpusId: ID!, $new: String!) {
                updateCorpusDescription(corpusId: $corpusId, newContent: $new) {
                    ok
                    message
                }
            }
            """,
            variables={
                "corpusId": to_global_id("CorpusType", corpus_pk),
                "new": "tampered",
            },
        )

    def test_missing_and_non_creator_collapse_to_one_message(self):
        missing = self._execute(self.outsider, 999_999)
        non_creator = self._execute(self.outsider, self.corpus.id)

        self.assertIsNone(missing.get("errors"))
        self.assertIsNone(non_creator.get("errors"))
        self.assertFalse(missing["data"]["updateCorpusDescription"]["ok"])
        self.assertFalse(non_creator["data"]["updateCorpusDescription"]["ok"])
        self.assertEqual(
            missing["data"]["updateCorpusDescription"]["message"],
            non_creator["data"]["updateCorpusDescription"]["message"],
            "IDOR: missing-id and not-creator branches must be byte-identical",
        )


class TestRestoreDocumentToVersionIDORProtection(TestCase):
    """``RestoreDocumentToVersion`` collapses four prior branches (missing doc,
    missing corpus, doc-not-writable, corpus-not-writable) into one response.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="rv_owner", password="test", email="rv@test.com"
        )
        self.outsider = User.objects.create_user(
            username="rv_outsider", password="test", email="rvo@test.com"
        )
        # Public corpus + public doc — outsider passes ``visible_to_user`` but
        # has no UPDATE.
        self.corpus = Corpus.objects.create(
            title="Public", creator=self.owner, is_public=True
        )
        self.document = Document.objects.create(
            title="Doc",
            creator=self.owner,
            is_public=True,
            backend_lock=False,
        )

    def _execute(self, user, doc_pk: int, corpus_pk: int) -> dict:
        client = Client(schema, context_value=MockContext(user))
        return client.execute(
            """
            mutation Restore($documentId: String!, $corpusId: String!) {
                restoreDocumentToVersion(documentId: $documentId, corpusId: $corpusId) {
                    ok
                    message
                }
            }
            """,
            variables={
                "documentId": to_global_id("DocumentType", doc_pk),
                "corpusId": to_global_id("CorpusType", corpus_pk),
            },
        )

    def test_all_failure_branches_return_same_message(self):
        # Branch A: document id does not exist
        missing_doc = self._execute(self.outsider, 999_999, self.corpus.id)
        # Branch B: corpus id does not exist
        missing_corpus = self._execute(self.outsider, self.document.id, 999_999)
        # Branch C: both visible but caller has no UPDATE
        no_perm = self._execute(self.outsider, self.document.id, self.corpus.id)

        for r in (missing_doc, missing_corpus, no_perm):
            self.assertIsNone(r.get("errors"))
            self.assertFalse(r["data"]["restoreDocumentToVersion"]["ok"])

        message_a = missing_doc["data"]["restoreDocumentToVersion"]["message"]
        message_b = missing_corpus["data"]["restoreDocumentToVersion"]["message"]
        message_c = no_perm["data"]["restoreDocumentToVersion"]["message"]
        self.assertEqual(message_a, message_b)
        self.assertEqual(message_a, message_c)


class TestUploadDocumentCorpusIDORProtection(TestCase):
    """``UploadDocument`` with ``addToCorpusId`` must collapse missing-corpus
    and visible-but-no-EDIT branches to one response so an attacker cannot
    enumerate corpus IDs by attempting an upload."""

    def setUp(self):
        self.outsider = User.objects.create_user(
            username="up_outsider", password="test", email="up@test.com"
        )
        self.other_owner = User.objects.create_user(
            username="up_other_owner", password="test", email="upo@test.com"
        )
        # Public corpus — outsider is visible-to-user but has no EDIT.
        self.public_corpus = Corpus.objects.create(
            title="Public", creator=self.other_owner, is_public=True
        )

    def _execute(self, corpus_pk: int) -> dict:
        client = Client(schema, context_value=MockContext(self.outsider))
        return client.execute(
            """
            mutation Upload(
                $file: String!
                $filename: String!
                $title: String!
                $description: String!
                $makePublic: Boolean!
                $customMeta: GenericScalar!
                $addToCorpusId: ID!
            ) {
                uploadDocument(
                    base64FileString: $file
                    filename: $filename
                    title: $title
                    description: $description
                    makePublic: $makePublic
                    customMeta: $customMeta
                    addToCorpusId: $addToCorpusId
                ) {
                    ok
                    message
                    document { id }
                }
            }
            """,
            variables={
                # Garbage payload — the mutation rejects on the corpus gate
                # before it ever touches file bytes.
                "file": "QUJD",  # base64("ABC")
                "filename": "x.pdf",
                "title": "x",
                "description": "x",
                "makePublic": False,
                "customMeta": {},
                "addToCorpusId": to_global_id("CorpusType", corpus_pk),
            },
        )

    def test_missing_corpus_and_no_edit_return_same_message(self):
        missing = self._execute(999_999)
        no_edit = self._execute(self.public_corpus.id)

        self.assertIsNone(missing.get("errors"))
        self.assertIsNone(no_edit.get("errors"))
        self.assertFalse(missing["data"]["uploadDocument"]["ok"])
        self.assertFalse(no_edit["data"]["uploadDocument"]["ok"])
        self.assertEqual(
            missing["data"]["uploadDocument"]["message"],
            no_edit["data"]["uploadDocument"]["message"],
            "IDOR: missing-corpus and visible-but-no-EDIT branches must match",
        )
