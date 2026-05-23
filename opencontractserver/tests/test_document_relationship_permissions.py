"""
Test DocumentRelationship permission model.

NOTE: DocumentRelationship uses INHERITED permissions from source_document,
target_document, and corpus. This is different from objects with direct
django-guardian permissions.

Formula: Effective Permission = MIN(source_doc_perm, target_doc_perm, corpus_perm)

The tests verify:
1. Owner with CRUD on docs/corpus can fully manage relationships
2. Collaborator with READ-only has limited access
3. Outsider with no permissions cannot access private relationships
"""

import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.files.base import ContentFile
from django.test import TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.annotations.models import AnnotationLabel
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import (
    Document,
    DocumentPath,
    DocumentRelationship,
)
from opencontractserver.documents.services import DocumentRelationshipService
from opencontractserver.tests.fixtures import SAMPLE_PDF_FILE_TWO_PATH
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()
logger = logging.getLogger(__name__)


class DocumentRelationshipPermissionTestCase(TestCase):
    """Test that DocumentRelationship permissions work correctly.

    Uses inherited permission model where effective permission is
    MIN(source_doc_perm, target_doc_perm, corpus_perm).
    """

    def setUp(self):
        """Set up test data."""
        # Create users
        self.owner = User.objects.create_user(username="owner", password="test")
        self.collaborator = User.objects.create_user(
            username="collaborator", password="test"
        )
        self.outsider = User.objects.create_user(username="outsider", password="test")

        # Create test corpus
        self.corpus = Corpus.objects.create(
            title="TestCorpus",
            creator=self.owner,
            is_public=False,
        )

        # Create test documents
        pdf_file = ContentFile(
            SAMPLE_PDF_FILE_TWO_PATH.open("rb").read(), name="test.pdf"
        )

        self.source_doc = Document.objects.create(
            creator=self.owner,
            title="Source Doc",
            description="Source document",
            custom_meta={},
            pdf_file=pdf_file,
            backend_lock=True,
            is_public=False,
        )

        self.target_doc = Document.objects.create(
            creator=self.owner,
            title="Target Doc",
            description="Target document",
            custom_meta={},
            pdf_file=pdf_file,
            backend_lock=True,
            is_public=False,
        )

        # Create test annotation label
        self.annotation_label = AnnotationLabel.objects.create(
            text="Test Relationship Label",
            label_type="RELATIONSHIP_LABEL",
            creator=self.owner,
        )

        # Add documents to corpus via DocumentPath (required for DocumentRelationship)
        DocumentPath.objects.create(
            document=self.source_doc,
            corpus=self.corpus,
            creator=self.owner,
            path="/source_doc",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )
        DocumentPath.objects.create(
            document=self.target_doc,
            corpus=self.corpus,
            creator=self.owner,
            path="/target_doc",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        # Create document relationship
        self.relationship = DocumentRelationship.objects.create(
            source_document=self.source_doc,
            target_document=self.target_doc,
            relationship_type="RELATIONSHIP",
            annotation_label=self.annotation_label,
            creator=self.owner,
            corpus=self.corpus,
        )

        # Set up permissions on documents and corpus
        # (DocumentRelationship inherits permissions from these)
        # Owner gets full access to everything
        set_permissions_for_obj_to_user(
            self.owner, self.source_doc, [PermissionTypes.CRUD]
        )
        set_permissions_for_obj_to_user(
            self.owner, self.target_doc, [PermissionTypes.CRUD]
        )
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.CRUD])

        # Collaborator gets READ on documents and corpus
        # (inherited permission will be MIN of all = READ)
        set_permissions_for_obj_to_user(
            self.collaborator, self.source_doc, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.collaborator, self.target_doc, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.collaborator, self.corpus, [PermissionTypes.READ]
        )

        # Outsider gets nothing

    def test_owner_has_all_permissions(self):
        """Test that owner has full CRUD permissions on underlying documents."""
        # Owner has CRUD on source document
        self.assertTrue(
            DocumentRelationshipService.user_has_permission(
                self.owner,
                self.relationship,
                "READ",
            )
        )
        self.assertTrue(
            DocumentRelationshipService.user_has_permission(
                self.owner,
                self.relationship,
                "UPDATE",
            )
        )
        self.assertTrue(
            DocumentRelationshipService.user_has_permission(
                self.owner,
                self.relationship,
                "DELETE",
            )
        )

    def test_collaborator_can_read_but_not_modify(self):
        """Test that collaborator with READ permission cannot update or delete."""
        # Can READ (inherited from docs/corpus)
        self.assertTrue(
            DocumentRelationshipService.user_has_permission(
                self.collaborator,
                self.relationship,
                "READ",
            )
        )
        # Cannot UPDATE (inherited permission is READ only)
        self.assertFalse(
            DocumentRelationshipService.user_has_permission(
                self.collaborator,
                self.relationship,
                "UPDATE",
            )
        )
        # Cannot DELETE (inherited permission is READ only)
        self.assertFalse(
            DocumentRelationshipService.user_has_permission(
                self.collaborator,
                self.relationship,
                "DELETE",
            )
        )

    def test_outsider_has_no_permissions(self):
        """Test that outsider has no permissions on relationship."""
        # Outsider has no permissions on source/target docs or corpus
        self.assertFalse(
            DocumentRelationshipService.user_has_permission(
                self.outsider,
                self.relationship,
                "READ",
            )
        )
        self.assertFalse(
            DocumentRelationshipService.user_has_permission(
                self.outsider,
                self.relationship,
                "UPDATE",
            )
        )
        self.assertFalse(
            DocumentRelationshipService.user_has_permission(
                self.outsider,
                self.relationship,
                "DELETE",
            )
        )


class DocumentRelationshipVisibilityTestCase(TestCase):
    """Test that DocumentRelationship visibility queries work correctly."""

    def setUp(self):
        """Set up test data."""
        self.owner = User.objects.create_user(username="owner", password="test")
        self.other_user = User.objects.create_user(username="other", password="test")

        # Create test corpus
        self.corpus = Corpus.objects.create(
            title="TestCorpus",
            creator=self.owner,
            is_public=False,
        )

        # Create documents
        pdf_file = ContentFile(
            SAMPLE_PDF_FILE_TWO_PATH.open("rb").read(), name="test.pdf"
        )

        self.source_doc = Document.objects.create(
            creator=self.owner,
            title="Source Doc",
            pdf_file=pdf_file,
            backend_lock=True,
            is_public=False,
        )

        self.target_doc = Document.objects.create(
            creator=self.owner,
            title="Target Doc",
            pdf_file=pdf_file,
            backend_lock=True,
            is_public=False,
        )

        # Add documents to corpus via DocumentPath (required for DocumentRelationship)
        DocumentPath.objects.create(
            document=self.source_doc,
            corpus=self.corpus,
            creator=self.owner,
            path="/source_doc",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )
        DocumentPath.objects.create(
            document=self.target_doc,
            corpus=self.corpus,
            creator=self.owner,
            path="/target_doc",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        # Create private relationship
        self.private_relationship = DocumentRelationship.objects.create(
            source_document=self.source_doc,
            target_document=self.target_doc,
            relationship_type="NOTES",
            data={"note": "Private note"},
            creator=self.owner,
            corpus=self.corpus,
            is_public=False,
        )

        # Create public relationship
        self.public_relationship = DocumentRelationship.objects.create(
            source_document=self.source_doc,
            target_document=self.target_doc,
            relationship_type="NOTES",
            data={"note": "Public note"},
            creator=self.owner,
            corpus=self.corpus,
            is_public=True,
        )

        # Set permissions on documents and corpus (inherited by relationships)
        set_permissions_for_obj_to_user(
            self.owner, self.source_doc, [PermissionTypes.CRUD]
        )
        set_permissions_for_obj_to_user(
            self.owner, self.target_doc, [PermissionTypes.CRUD]
        )
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.CRUD])

    def test_owner_sees_all_own_relationships(self):
        """Test that owner can see both private and public relationships."""
        visible = DocumentRelationship.objects.visible_to_user(self.owner)
        self.assertEqual(visible.count(), 2)
        self.assertIn(self.private_relationship, visible)
        self.assertIn(self.public_relationship, visible)

    def test_other_user_sees_only_public_relationships(self):
        """Test that other user can only see public relationships."""
        visible = DocumentRelationship.objects.visible_to_user(self.other_user)
        self.assertEqual(visible.count(), 1)
        self.assertNotIn(self.private_relationship, visible)
        self.assertIn(self.public_relationship, visible)

    def test_shared_relationship_visible_to_collaborator(self):
        """Test that collaborator can check permissions via the optimizer.

        NOTE: The base visible_to_user() falls back to creator/public check when
        no permission table exists for DocumentRelationship. For full inherited
        permission support in visible_to_user(), a custom manager implementation
        would be needed. This test verifies the current behavior where only public
        relationships are visible via visible_to_user(), but individual permission
        checks via DocumentRelationshipService work correctly.
        """
        # Share with other_user via documents and corpus (inherited permission model)
        set_permissions_for_obj_to_user(
            self.other_user, self.source_doc, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.other_user, self.target_doc, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.other_user, self.corpus, [PermissionTypes.READ]
        )

        # visible_to_user() uses creator/public fallback, so only public is visible
        visible = DocumentRelationship.objects.visible_to_user(self.other_user)
        self.assertEqual(visible.count(), 1)
        self.assertIn(self.public_relationship, visible)

        # However, individual permission check via the service uses inherited model
        self.assertTrue(
            DocumentRelationshipService.user_has_permission(
                self.other_user,
                self.private_relationship,
                "READ",
            )
        )


class DocumentRelationshipPermissionEscalationTestCase(TestCase):
    """Test that permission escalation is prevented."""

    def setUp(self):
        """Set up test data."""
        self.owner = User.objects.create_user(username="owner", password="test")
        self.attacker = User.objects.create_user(username="attacker", password="test")

        # Create test corpus
        self.corpus = Corpus.objects.create(
            title="TestCorpus",
            creator=self.owner,
            is_public=True,  # Public so attacker can see it
        )

        # Create documents - attacker can see but not modify
        pdf_file = ContentFile(
            SAMPLE_PDF_FILE_TWO_PATH.open("rb").read(), name="test.pdf"
        )

        self.source_doc = Document.objects.create(
            creator=self.owner,
            title="Source Doc",
            pdf_file=pdf_file,
            backend_lock=True,
            is_public=True,  # Public so attacker can see it
        )

        self.target_doc = Document.objects.create(
            creator=self.owner,
            title="Target Doc",
            pdf_file=pdf_file,
            backend_lock=True,
            is_public=True,  # Public so attacker can see it
        )

        # Add documents to corpus via DocumentPath (required for DocumentRelationship)
        DocumentPath.objects.create(
            document=self.source_doc,
            corpus=self.corpus,
            creator=self.owner,
            path="/source_doc",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )
        DocumentPath.objects.create(
            document=self.target_doc,
            corpus=self.corpus,
            creator=self.owner,
            path="/target_doc",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        # Create relationship owned by owner
        self.relationship = DocumentRelationship.objects.create(
            source_document=self.source_doc,
            target_document=self.target_doc,
            relationship_type="NOTES",
            data={"sensitive": "data"},
            creator=self.owner,
            corpus=self.corpus,
            is_public=False,  # Private relationship
        )

        # Owner gets full permissions on documents and corpus (inherited by relationship)
        set_permissions_for_obj_to_user(
            self.owner, self.source_doc, [PermissionTypes.CRUD]
        )
        set_permissions_for_obj_to_user(
            self.owner, self.target_doc, [PermissionTypes.CRUD]
        )
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.CRUD])

        # Attacker only gets READ on documents (they're public), no corpus permission
        # Since attacker lacks corpus permission, they cannot modify the relationship
        set_permissions_for_obj_to_user(
            self.attacker, self.source_doc, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.attacker, self.target_doc, [PermissionTypes.READ]
        )

    def test_attacker_cannot_see_private_relationship(self):
        """Test that attacker cannot see private relationship (not creator, not public)."""
        visible = DocumentRelationship.objects.visible_to_user(self.attacker)
        self.assertNotIn(self.relationship, visible)

    def test_attacker_cannot_update_relationship(self):
        """Test that attacker cannot update relationship they don't have permission for."""
        # Attacker has READ on docs but no corpus permission, so inherited UPDATE = False
        self.assertFalse(
            DocumentRelationshipService.user_has_permission(
                self.attacker,
                self.relationship,
                "UPDATE",
            )
        )

    def test_attacker_cannot_delete_relationship(self):
        """Test that attacker cannot delete relationship they don't have permission for."""
        # Attacker has READ on docs but no corpus permission, so inherited DELETE = False
        self.assertFalse(
            DocumentRelationshipService.user_has_permission(
                self.attacker,
                self.relationship,
                "DELETE",
            )
        )


class DocumentRelationshipAnonymousAccessTestCase(TestCase):
    """Test that anonymous users can read document relationships on public resources.

    Document relationships inherit permissions from source_doc + target_doc + corpus.
    When all three are public, anonymous users should have READ access.
    """

    def setUp(self):
        """Set up public and private test data."""
        self.owner = User.objects.create_user(username="owner", password="test")
        self.anonymous_user = AnonymousUser()

        pdf_file = ContentFile(
            SAMPLE_PDF_FILE_TWO_PATH.open("rb").read(), name="test.pdf"
        )

        # --- Public corpus with public documents ---
        self.public_corpus = Corpus.objects.create(
            title="PublicCorpus",
            creator=self.owner,
            is_public=True,
        )
        self.public_source_doc = Document.objects.create(
            creator=self.owner,
            title="Public Source",
            pdf_file=pdf_file,
            backend_lock=True,
            is_public=True,
        )
        self.public_target_doc = Document.objects.create(
            creator=self.owner,
            title="Public Target",
            pdf_file=pdf_file,
            backend_lock=True,
            is_public=True,
        )
        DocumentPath.objects.create(
            document=self.public_source_doc,
            corpus=self.public_corpus,
            creator=self.owner,
            path="/pub_source",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )
        DocumentPath.objects.create(
            document=self.public_target_doc,
            corpus=self.public_corpus,
            creator=self.owner,
            path="/pub_target",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )
        self.public_relationship = DocumentRelationship.objects.create(
            source_document=self.public_source_doc,
            target_document=self.public_target_doc,
            relationship_type="RELATIONSHIP",
            annotation_label=AnnotationLabel.objects.create(
                text="Public Label",
                label_type="RELATIONSHIP_LABEL",
                creator=self.owner,
            ),
            creator=self.owner,
            corpus=self.public_corpus,
        )

        # --- Private corpus with private documents ---
        self.private_corpus = Corpus.objects.create(
            title="PrivateCorpus",
            creator=self.owner,
            is_public=False,
        )
        self.private_source_doc = Document.objects.create(
            creator=self.owner,
            title="Private Source",
            pdf_file=pdf_file,
            backend_lock=True,
            is_public=False,
        )
        self.private_target_doc = Document.objects.create(
            creator=self.owner,
            title="Private Target",
            pdf_file=pdf_file,
            backend_lock=True,
            is_public=False,
        )
        DocumentPath.objects.create(
            document=self.private_source_doc,
            corpus=self.private_corpus,
            creator=self.owner,
            path="/priv_source",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )
        DocumentPath.objects.create(
            document=self.private_target_doc,
            corpus=self.private_corpus,
            creator=self.owner,
            path="/priv_target",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )
        self.private_relationship = DocumentRelationship.objects.create(
            source_document=self.private_source_doc,
            target_document=self.private_target_doc,
            relationship_type="NOTES",
            data={"note": "Private note"},
            creator=self.owner,
            corpus=self.private_corpus,
        )

        # Owner permissions for private resources
        set_permissions_for_obj_to_user(
            self.owner, self.private_source_doc, [PermissionTypes.CRUD]
        )
        set_permissions_for_obj_to_user(
            self.owner, self.private_target_doc, [PermissionTypes.CRUD]
        )
        set_permissions_for_obj_to_user(
            self.owner, self.private_corpus, [PermissionTypes.CRUD]
        )

    def test_anonymous_can_see_public_relationships_via_optimizer(self):
        """Anonymous user can see relationships where docs and corpus are public."""
        visible = DocumentRelationshipService.get_visible_relationships(
            user=self.anonymous_user,
            corpus_id=self.public_corpus.id,
        )
        self.assertIn(self.public_relationship, visible)

    def test_anonymous_cannot_see_private_relationships_via_optimizer(self):
        """Anonymous user cannot see relationships on private resources."""
        visible = DocumentRelationshipService.get_visible_relationships(
            user=self.anonymous_user,
            corpus_id=self.private_corpus.id,
        )
        self.assertNotIn(self.private_relationship, visible)
        self.assertEqual(visible.count(), 0)

    def test_anonymous_gets_read_only_permissions(self):
        """Anonymous user should only get read permissions on public relationships."""
        visible = DocumentRelationshipService.get_visible_relationships(
            user=self.anonymous_user,
            corpus_id=self.public_corpus.id,
        )
        rel = visible.first()
        self.assertIsNotNone(rel)
        # Pre-computed permission flags should give read-only
        self.assertTrue(getattr(rel, "_can_read", False))
        self.assertFalse(getattr(rel, "_can_create", True))
        self.assertFalse(getattr(rel, "_can_update", True))
        self.assertFalse(getattr(rel, "_can_delete", True))


class TestContext:
    """Minimal GraphQL context stub for test client."""

    def __init__(self, user):
        self.user = user


class DocumentRelationshipGraphQLNodeTestCase(TestCase):
    """Test that the relay.Node.Field resolver for DocumentRelationshipType
    applies permission filtering via get_queryset.

    This validates that an anonymous user cannot fetch a private
    DocumentRelationship by its Relay global ID through the GraphQL layer.
    """

    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="test")
        self.anonymous_user = AnonymousUser()

        pdf_file = ContentFile(
            SAMPLE_PDF_FILE_TWO_PATH.open("rb").read(), name="test.pdf"
        )

        # --- Private corpus with private documents ---
        self.private_corpus = Corpus.objects.create(
            title="PrivateCorpus",
            creator=self.owner,
            is_public=False,
        )
        self.private_source_doc = Document.objects.create(
            creator=self.owner,
            title="Private Source",
            pdf_file=pdf_file,
            backend_lock=True,
            is_public=False,
        )
        self.private_target_doc = Document.objects.create(
            creator=self.owner,
            title="Private Target",
            pdf_file=pdf_file,
            backend_lock=True,
            is_public=False,
        )
        DocumentPath.objects.create(
            document=self.private_source_doc,
            corpus=self.private_corpus,
            creator=self.owner,
            path="/priv_source",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )
        DocumentPath.objects.create(
            document=self.private_target_doc,
            corpus=self.private_corpus,
            creator=self.owner,
            path="/priv_target",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )
        self.private_relationship = DocumentRelationship.objects.create(
            source_document=self.private_source_doc,
            target_document=self.private_target_doc,
            relationship_type="NOTES",
            data={"note": "Private note"},
            creator=self.owner,
            corpus=self.private_corpus,
        )

        # --- Public corpus with public documents ---
        self.public_corpus = Corpus.objects.create(
            title="PublicCorpus",
            creator=self.owner,
            is_public=True,
        )
        self.public_source_doc = Document.objects.create(
            creator=self.owner,
            title="Public Source",
            pdf_file=pdf_file,
            backend_lock=True,
            is_public=True,
        )
        self.public_target_doc = Document.objects.create(
            creator=self.owner,
            title="Public Target",
            pdf_file=pdf_file,
            backend_lock=True,
            is_public=True,
        )
        DocumentPath.objects.create(
            document=self.public_source_doc,
            corpus=self.public_corpus,
            creator=self.owner,
            path="/pub_source",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )
        DocumentPath.objects.create(
            document=self.public_target_doc,
            corpus=self.public_corpus,
            creator=self.owner,
            path="/pub_target",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )
        self.public_relationship = DocumentRelationship.objects.create(
            source_document=self.public_source_doc,
            target_document=self.public_target_doc,
            relationship_type="RELATIONSHIP",
            annotation_label=AnnotationLabel.objects.create(
                text="Public Label",
                label_type="RELATIONSHIP_LABEL",
                creator=self.owner,
            ),
            creator=self.owner,
            corpus=self.public_corpus,
        )

        # Owner permissions for private resources
        set_permissions_for_obj_to_user(
            self.owner, self.private_source_doc, [PermissionTypes.CRUD]
        )
        set_permissions_for_obj_to_user(
            self.owner, self.private_target_doc, [PermissionTypes.CRUD]
        )
        set_permissions_for_obj_to_user(
            self.owner, self.private_corpus, [PermissionTypes.CRUD]
        )

    def test_anonymous_cannot_fetch_private_relationship_via_graphql_node(self):
        """An anonymous user must NOT be able to fetch a private
        DocumentRelationship by its Relay global ID through the GraphQL layer.
        This exercises the get_queryset permission filter on DocumentRelationshipType.
        """
        client = Client(schema, context_value=TestContext(self.anonymous_user))
        global_id = to_global_id(
            "DocumentRelationshipType", self.private_relationship.id
        )
        query = """
            query {
                documentRelationship(id: "%s") {
                    id
                    relationshipType
                }
            }
        """ % global_id

        result = client.execute(query)

        # The query should error (DoesNotExist) or return null data
        errors = result.get("errors")
        data = result.get("data", {})
        relationship_data = data.get("documentRelationship") if data else None

        self.assertTrue(
            errors is not None or relationship_data is None,
            "Anonymous user should not be able to fetch a private "
            "DocumentRelationship via its Relay global ID.",
        )

    def test_anonymous_can_fetch_public_relationship_via_graphql_node(self):
        """An anonymous user CAN fetch a public DocumentRelationship
        (public docs + public corpus) via the GraphQL layer.
        """
        client = Client(schema, context_value=TestContext(self.anonymous_user))
        global_id = to_global_id(
            "DocumentRelationshipType", self.public_relationship.id
        )
        query = """
            query {
                documentRelationship(id: "%s") {
                    id
                    relationshipType
                }
            }
        """ % global_id

        result = client.execute(query)

        self.assertIsNone(
            result.get("errors"), f"Unexpected errors: {result.get('errors')}"
        )
        data = result["data"]["documentRelationship"]
        self.assertIsNotNone(data)
        self.assertEqual(data["id"], global_id)
        self.assertEqual(data["relationshipType"], "RELATIONSHIP")

    def test_owner_can_fetch_private_relationship_via_graphql_node(self):
        """The owner CAN fetch their own private DocumentRelationship."""
        client = Client(schema, context_value=TestContext(self.owner))
        global_id = to_global_id(
            "DocumentRelationshipType", self.private_relationship.id
        )
        query = """
            query {
                documentRelationship(id: "%s") {
                    id
                    relationshipType
                }
            }
        """ % global_id

        result = client.execute(query)

        self.assertIsNone(
            result.get("errors"), f"Unexpected errors: {result.get('errors')}"
        )
        data = result["data"]["documentRelationship"]
        self.assertIsNotNone(data)
        self.assertEqual(data["id"], global_id)
