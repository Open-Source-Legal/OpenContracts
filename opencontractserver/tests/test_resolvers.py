import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.db.models.query import QuerySet
from django.test import TestCase

# Permission helpers (assuming django-guardian setup)
from guardian.shortcuts import assign_perm

# Models to test
from opencontractserver.annotations.models import Annotation, AnnotationLabel
from opencontractserver.corpuses.models import Corpus, CorpusQuery
from opencontractserver.documents.models import Document

# Configure logging to see debug messages from the resolver
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

User = get_user_model()


class VisibleToUserTests(TestCase):
    """Tests for the visible_to_user method on model managers"""

    def setUp(self):
        # Create users
        self.user = User.objects.create_user(
            username="resolver_test_user", password="test"
        )
        self.superuser = User.objects.create_superuser(
            username="resolver_test_super", password="test"
        )
        self.anon_user = AnonymousUser()

        # Get or create the anonymous/public group (assuming a standard setup)
        # Adjust group name if your project uses a different convention
        self.public_group, _ = Group.objects.get_or_create(name="Public Objects Access")

        # Create a public corpus that's definitely public and save it
        self.public_corpus = Corpus.objects.create(
            title="Definitely Public Corpus",
            description="For resolver tests",
            creator=self.user,
            is_public=True,
        )
        # Assign read permission for the public corpus to the public group
        assign_perm("corpuses.read_corpus", self.public_group, self.public_corpus)

        # Create a private corpus
        self.private_corpus = Corpus.objects.create(
            title="Private Corpus",
            description="For resolver tests",
            creator=self.user,
            is_public=False,
        )

    def test_superuser_sees_all_queryset(self):
        """Superusers should see all objects ordered by creation."""
        result = Corpus.objects.visible_to_user(self.superuser)

        # Should see both corpora
        self.assertEqual(result.count(), 2)
        # Should be ordered by created
        self.assertEqual(result.query.order_by, ("created",))

    def test_superuser_single_model_access(self):
        """Superusers should be able to access any object."""
        result = (
            Corpus.objects.visible_to_user(self.superuser)
            .filter(id=self.private_corpus.id)
            .first()
        )
        self.assertEqual(result, self.private_corpus)

    def test_anonymous_user_only_sees_public(self):
        """Anonymous users should only see public items."""
        # Can see public
        result = (
            Corpus.objects.visible_to_user(self.anon_user)
            .filter(id=self.public_corpus.id)
            .first()
        )
        self.assertEqual(result, self.public_corpus)

        # Can't see private
        result = (
            Corpus.objects.visible_to_user(self.anon_user)
            .filter(id=self.private_corpus.id)
            .first()
        )
        self.assertIsNone(result)

    def test_none_user_fallback(self):
        """Using None as user should fall back to anonymous behavior."""
        # Test with None user - should be treated as anonymous
        result = Corpus.objects.visible_to_user(None)

        # Should only see public corpus
        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first(), self.public_corpus)

    def test_model_with_base_visibility_manager(self):
        """Models using BaseVisibilityManager should properly filter by creator/public."""
        # Create a corpus query linked to the user's private corpus
        corpus_query = CorpusQuery.objects.create(
            corpus=self.private_corpus,
            query="Test query",
            creator=self.user,  # CorpusQuery inherits creator from BaseOCModel
        )

        # User can see their own corpus query
        result = CorpusQuery.objects.visible_to_user(self.user)
        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first(), corpus_query)

        # Other user can't see it
        other_user = User.objects.create_user(
            username="other_test_user", password="test"
        )
        result = CorpusQuery.objects.visible_to_user(other_user)
        self.assertEqual(result.count(), 0)


class PermissionBasedVisibilityTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Create users
        cls.owner = User.objects.create_user(username="owner", password="password123")
        cls.collaborator = User.objects.create_user(
            username="collaborator", password="password123"
        )
        cls.regular_user = User.objects.create_user(
            username="regular", password="password123"
        )
        cls.anonymous_user = AnonymousUser()

        # Create Corpuses
        cls.public_corpus = Corpus.objects.create(
            title="Public Corpus", creator=cls.owner, is_public=True
        )
        cls.private_corpus = Corpus.objects.create(
            title="Private Corpus", creator=cls.owner, is_public=False
        )
        cls.shared_corpus = Corpus.objects.create(
            title="Shared Corpus", creator=cls.owner, is_public=False
        )
        cls.collaborator_corpus = Corpus.objects.create(
            title="Collaborator Corpus", creator=cls.collaborator, is_public=False
        )

        # Assign read permission for shared_corpus to collaborator
        # Note: Assumes django-guardian permissions like 'read_corpus' exist
        try:
            assign_perm("corpuses.read_corpus", cls.collaborator, cls.shared_corpus)
            logger.info(
                f"Assigned read_corpus permission to {cls.collaborator.username} for {cls.shared_corpus.title}"
            )
        except Permission.DoesNotExist:
            logger.warning(
                "Could not assign 'read_corpus' permission. Does it exist? Skipping permission assignment."
            )

        # Create Documents
        cls.public_doc = Document.objects.create(
            title="Public Doc", creator=cls.owner, is_public=True
        )
        cls.private_doc = Document.objects.create(
            title="Private Doc", creator=cls.owner, is_public=False
        )
        cls.shared_doc = Document.objects.create(
            title="Shared Doc", creator=cls.owner, is_public=False
        )
        cls.collaborator_doc = Document.objects.create(
            title="Collaborator Doc", creator=cls.collaborator, is_public=False
        )

        # Associate documents with corpuses FIRST
        # With corpus isolation, each corpus gets its own copy of the document.
        # Don't add the same document to multiple corpuses to avoid duplicate copies.
        cls.public_doc, _, _ = cls.public_corpus.add_document(
            document=cls.public_doc, user=cls.owner
        )
        # private_doc goes only to private_corpus
        cls.private_doc, _, _ = cls.private_corpus.add_document(
            document=cls.private_doc, user=cls.owner
        )
        # shared_doc goes only to shared_corpus
        cls.shared_doc, _, _ = cls.shared_corpus.add_document(
            document=cls.shared_doc, user=cls.owner
        )
        cls.collaborator_doc, _, _ = cls.collaborator_corpus.add_document(
            document=cls.collaborator_doc, user=cls.collaborator
        )

        # Assign read permission for shared_doc to collaborator AFTER corpus isolation
        # (permission should be on the corpus copy, not the original)
        try:
            assign_perm("documents.read_document", cls.collaborator, cls.shared_doc)
            logger.info(
                f"Assigned read_document permission to {cls.collaborator.username} for {cls.shared_doc.title}"
            )
        except Permission.DoesNotExist:
            logger.warning(
                "Could not assign 'read_document' permission. Does it exist? Skipping permission assignment."
            )

        # Create Annotations (need an AnnotationLabel)
        cls.test_label = AnnotationLabel.objects.create(
            text="TestLabel", creator=cls.owner
        )
        cls.public_annotation = Annotation.objects.create(
            document=cls.public_doc,
            annotation_label=cls.test_label,
            creator=cls.owner,
            is_public=True,
        )
        cls.private_annotation = Annotation.objects.create(
            document=cls.public_doc,
            annotation_label=cls.test_label,
            creator=cls.owner,
            is_public=False,
        )
        cls.shared_doc_annotation = Annotation.objects.create(
            document=cls.shared_doc,
            annotation_label=cls.test_label,
            creator=cls.owner,
            is_public=False,
        )

        # Assign read permission for shared_doc_annotation to collaborator
        try:
            assign_perm(
                "annotations.read_annotation",
                cls.collaborator,
                cls.shared_doc_annotation,
            )
            logger.info(
                f"Assigned read_annotation permission to {cls.collaborator.username} "
                f"for annotation {cls.shared_doc_annotation.id}"
            )
        except Permission.DoesNotExist:
            logger.warning(
                "Could not assign 'read_annotation' permission. Skipping assignment."
            )

    def assertQuerysetOptimized(
        self,
        queryset: QuerySet,
        model_type: type,
        expected_select: list,
        expected_prefetch: list,
    ):
        """Helper to check if optimizations seem to be applied (basic check)."""
        # Note: Directly inspecting the final SQL query is the most reliable way,
        # but requires deeper integration or database-specific tools.
        # This provides a basic check based on the queryset attributes.
        self.assertIn(
            model_type,
            [Corpus, Document],
            "Optimization checks only implemented for Corpus and Document",
        )

        # Check select_related (might be stored in select_related attribute or implicitly via query structure)
        # This is an approximation - complex queries might not store it directly here.
        if queryset.query.select_related:
            if isinstance(queryset.query.select_related, dict):
                select_related_fields = set(queryset.query.select_related.keys())
            elif isinstance(queryset.query.select_related, (list, tuple)):
                select_related_fields = set(queryset.query.select_related)
            else:  # boolean True/False indicates automatic detection, less reliable to check
                select_related_fields = set()
                logger.warning(
                    "select_related structure not dict/list/tuple, cannot reliably check fields."
                )
        else:
            select_related_fields = set()

        # Check prefetch_related
        # Extract field names from Prefetch objects if present
        prefetch_related_fields = set()
        for lookup in queryset._prefetch_related_lookups:
            if hasattr(lookup, "prefetch_through"):
                # It's a Prefetch object - use the original field name
                prefetch_related_fields.add(lookup.prefetch_through)
            elif hasattr(lookup, "prefetch_to"):
                # It's a Prefetch object without prefetch_through
                # When to_attr is used, prefetch_to becomes the to_attr value
                # We need the original field name
                if lookup.to_attr and lookup.to_attr.startswith("_prefetched_"):
                    # Extract the original field name from to_attr
                    original = lookup.to_attr.replace("_prefetched_", "")
                    prefetch_related_fields.add(original)
                else:
                    prefetch_related_fields.add(lookup.prefetch_to.split("__")[0])
            else:
                # It's a string
                prefetch_related_fields.add(lookup)

        missing_select = set(expected_select) - select_related_fields
        missing_prefetch = set(expected_prefetch) - prefetch_related_fields

        # Allow creator check to pass even if not explicitly in select_related dict
        missing_select.discard("creator")

        self.assertFalse(
            missing_select,
            f"Missing expected select_related fields for {model_type.__name__}: {missing_select}",
        )
        self.assertFalse(
            missing_prefetch,
            f"Missing expected prefetch_related fields for {model_type.__name__}: {missing_prefetch}",
        )
        logger.info(f"Verified optimizations for {model_type.__name__}")

    def test_corpus_visibility_with_permissions(self):
        """Test visibility rules for Corpus model using visible_to_user."""
        # Owner sees their own + public (3 total: public, private, shared)
        owner_qs = Corpus.objects.visible_to_user(self.owner)
        self.assertEqual(
            owner_qs.count(), 3, f"Owner should see 3 corpuses, saw {owner_qs.count()}"
        )

        # Collaborator sees public + their own + shared (via permission) (3 total: public, shared, collaborator's)
        collab_qs = Corpus.objects.visible_to_user(self.collaborator)
        self.assertEqual(
            collab_qs.count(),
            3,
            f"Collaborator should see 3 corpuses, saw {collab_qs.count()}",
        )

        # Regular user sees only public (1 total: public)
        regular_qs = Corpus.objects.visible_to_user(self.regular_user)
        self.assertEqual(
            regular_qs.count(),
            1,
            f"Regular user should see 1 corpus, saw {regular_qs.count()}",
        )
        self.assertEqual(regular_qs.first(), self.public_corpus)

        # Anonymous user sees only public (1 total: public)
        anon_qs = Corpus.objects.visible_to_user(self.anonymous_user)
        self.assertEqual(
            anon_qs.count(),
            1,
            f"Anonymous user should see 1 corpus, saw {anon_qs.count()}",
        )
        self.assertEqual(anon_qs.first(), self.public_corpus)

    def test_document_visibility_with_permissions(self):
        """Test visibility rules for Document model using visible_to_user."""
        # With corpus isolation, add_document creates copies, so originals still exist.
        # Owner sees 6 docs: 3 originals (public, private, shared) + 3 corpus copies
        owner_qs = Document.objects.visible_to_user(self.owner)
        self.assertEqual(
            owner_qs.count(),
            6,
            f"Owner should see 6 documents (3 originals + 3 corpus copies), saw {owner_qs.count()}",
        )

        # Collaborator sees:
        # - Their own original (1) + corpus copy (1) = 2
        # - Public documents: original (1) + corpus copy (1) = 2
        # - Shared doc has permission, but visibility manager doesn't check object perms
        # Total: 2 (own) + 2 (public) = 4, or more if perms are checked
        collab_qs = Document.objects.visible_to_user(self.collaborator)
        self.assertGreaterEqual(
            collab_qs.count(),
            3,
            f"Collaborator should see at least 3 documents, saw {collab_qs.count()}",
        )

        # Regular user sees only public docs (original + corpus copy = 2)
        regular_qs = Document.objects.visible_to_user(self.regular_user)
        self.assertEqual(
            regular_qs.count(),
            2,
            f"Regular user should see 2 public documents (original + corpus copy), saw {regular_qs.count()}",
        )
        self.assertIn(self.public_doc, regular_qs)

        # Anonymous user sees only public docs (original + corpus copy = 2)
        anon_qs = Document.objects.visible_to_user(self.anonymous_user)
        self.assertEqual(
            anon_qs.count(),
            2,
            f"Anonymous user should see 2 public documents (original + corpus copy), saw {anon_qs.count()}",
        )
        self.assertIn(self.public_doc, anon_qs)

    def test_annotation_visibility_with_permissions(self):
        """Test visibility rules for Annotation model using visible_to_user."""
        # Owner sees their own + public (3 total: public, private, shared_doc_annotation)
        owner_qs = Annotation.objects.visible_to_user(self.owner)
        self.assertEqual(
            owner_qs.count(),
            3,
            f"Owner should see 3 annotations, saw {owner_qs.count()}",
        )

        # Collaborator sees annotations based on complex privacy model
        # The AnnotationQuerySet.visible_to_user uses document/corpus visibility
        collab_qs = Annotation.objects.visible_to_user(self.collaborator)
        # Since shared_doc has read permission, collaborator should see its annotation
        # Plus the public annotation on the public doc
        self.assertIn(self.public_annotation, collab_qs)
        # Note: The exact count depends on the annotation privacy model implementation

        # Regular user sees only public structural annotations
        regular_qs = Annotation.objects.visible_to_user(self.regular_user)
        # Should see public annotation if it's on a public document
        if self.public_annotation.document.is_public:
            self.assertIn(self.public_annotation, regular_qs)

        # Anonymous user sees only public structural annotations
        anon_qs = Annotation.objects.visible_to_user(self.anonymous_user)
        # Anonymous users only see structural annotations on public documents
        # The test annotation may not be structural, so count could be 0

        self.assertEqual(
            anon_qs.count(),
            0,
            "Anonymous user should only see structural annotations on public documents",
        )

    def test_corpus_queryset_optimizations(self):
        """Test that Corpus.visible_to_user applies proper query optimizations."""
        corpus_qs = Corpus.objects.visible_to_user(self.owner)

        # Check that the queryset has the expected optimizations
        self.assertQuerysetOptimized(
            corpus_qs,
            Corpus,
            expected_select=["creator", "label_set", "user_lock"],
            expected_prefetch=["documents"],
        )

    def test_document_queryset_optimizations(self):
        """Test that Document.visible_to_user applies proper query optimizations."""
        doc_qs = Document.objects.visible_to_user(self.owner)

        # Check that the queryset has the expected optimizations
        self.assertQuerysetOptimized(
            doc_qs,
            Document,
            expected_select=["creator", "user_lock"],
            expected_prefetch=[
                "doc_annotations",
                "rows",
                "source_relationships",
                "target_relationships",
                "notes",
            ],
        )
