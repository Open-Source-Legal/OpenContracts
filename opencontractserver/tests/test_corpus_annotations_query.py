"""
Tests for corpus-wide annotation queries including structural annotations.

These tests verify that the GetAnnotationsForCards query correctly returns
both document-attached annotations and structural annotations when querying
by corpus_id without a document_id.
"""

from django.test import TestCase

from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
    StructuralAnnotationSet,
)
from opencontractserver.annotations.services import AnnotationService
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.types.enums import LabelType, PermissionTypes
from opencontractserver.users.models import User
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user


class TestCorpusAnnotationsQuery(TestCase):
    """Test the AnnotationService.get_corpus_annotations method."""

    owner: User
    viewer: User
    superuser: User
    corpus: Corpus
    structural_set: StructuralAnnotationSet
    doc_with_structural: Document
    doc_without_structural: Document
    structural_label: AnnotationLabel
    user_label: AnnotationLabel
    structural_annotation: Annotation
    user_annotation: Annotation

    @classmethod
    def setUpTestData(cls):
        """Set up test data once for all tests in this class."""
        # Create users
        cls.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test123"
        )
        cls.viewer = User.objects.create_user(
            username="viewer", email="viewer@test.com", password="test123"
        )
        cls.superuser = User.objects.create_superuser(
            username="admin", email="admin@test.com", password="admin123"
        )

        # Create corpus
        cls.corpus = Corpus.objects.create(
            title="Test Corpus",
            creator=cls.owner,
        )

        # Create a structural annotation set (shared across documents)
        cls.structural_set = StructuralAnnotationSet.objects.create()

        # Create documents - one with structural_set, one without
        cls.doc_with_structural = Document.objects.create(
            title="Document with Structural Annotations",
            creator=cls.owner,
            structural_annotation_set=cls.structural_set,
        )
        cls.doc_without_structural = Document.objects.create(
            title="Document without Structural Annotations",
            creator=cls.owner,
        )

        # Create DocumentPaths to link documents to corpus
        DocumentPath.objects.create(
            document=cls.doc_with_structural,
            corpus=cls.corpus,
            path="/doc_with_structural.pdf",
            is_current=True,
            is_deleted=False,
            version_number=1,
            creator=cls.owner,
        )
        DocumentPath.objects.create(
            document=cls.doc_without_structural,
            corpus=cls.corpus,
            path="/doc_without_structural.pdf",
            is_current=True,
            is_deleted=False,
            version_number=1,
            creator=cls.owner,
        )

        # Create annotation labels
        cls.structural_label = AnnotationLabel.objects.create(
            text="Paragraph",
            label_type=LabelType.TOKEN_LABEL,
            creator=cls.owner,
        )
        cls.user_label = AnnotationLabel.objects.create(
            text="Important",
            label_type=LabelType.TOKEN_LABEL,
            creator=cls.owner,
        )

        # Create structural annotations (linked via structural_set, NOT document)
        # These have document=NULL and corpus=NULL
        cls.structural_annotation = Annotation.objects.create(
            annotation_label=cls.structural_label,
            structural_set=cls.structural_set,
            document=None,  # NULL - linked via structural_set instead
            corpus=None,  # NULL - shared across corpuses
            structural=True,
            creator=cls.owner,
            raw_text="This is a structural annotation",
        )

        # Create document-attached user annotations (corpus-specific)
        cls.user_annotation = Annotation.objects.create(
            annotation_label=cls.user_label,
            document=cls.doc_with_structural,
            corpus=cls.corpus,
            structural=False,
            creator=cls.owner,
            raw_text="This is a user annotation",
        )

        # Grant permissions to owner (creator also needs explicit permissions for the test)
        set_permissions_for_obj_to_user(cls.owner, cls.corpus, [PermissionTypes.CRUD])
        set_permissions_for_obj_to_user(
            cls.owner, cls.doc_with_structural, [PermissionTypes.CRUD]
        )
        set_permissions_for_obj_to_user(
            cls.owner, cls.doc_without_structural, [PermissionTypes.CRUD]
        )

        # Grant permissions to viewer
        set_permissions_for_obj_to_user(cls.viewer, cls.corpus, [PermissionTypes.READ])
        set_permissions_for_obj_to_user(
            cls.viewer, cls.doc_with_structural, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            cls.viewer, cls.doc_without_structural, [PermissionTypes.READ]
        )

    def test_superuser_has_no_blanket_access_to_annotations(self):
        """Scoped admin access (2026-05): a no-grant superuser is computed like
        a normal user. The corpus is private and the superuser is neither
        creator nor grantee, so ``get_corpus_annotations`` returns nothing —
        the corpus-READ gate is not satisfied. Granting corpus + document READ
        via the normal path then surfaces both annotation types.
        """
        # No grant: superuser fails the corpus-READ gate → empty.
        denied = AnnotationService.get_corpus_annotations(
            corpus_id=self.corpus.id,
            user=self.superuser,
        )
        self.assertEqual(denied.count(), 0)

        # Positive path: grant corpus + document READ via the normal guardian
        # path so the superuser passes through exactly like an authorized user.
        set_permissions_for_obj_to_user(
            self.superuser, self.corpus, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.superuser, self.doc_with_structural, [PermissionTypes.READ]
        )
        result = AnnotationService.get_corpus_annotations(
            corpus_id=self.corpus.id,
            user=self.superuser,
        )
        self.assertIn(self.structural_annotation, result)
        self.assertIn(self.user_annotation, result)

    def test_owner_sees_all_annotations(self):
        """Owner should see both structural and document-attached annotations."""
        result = AnnotationService.get_corpus_annotations(
            corpus_id=self.corpus.id,
            user=self.owner,
        )

        self.assertIn(self.structural_annotation, result)
        self.assertIn(self.user_annotation, result)

    def test_viewer_with_permission_sees_annotations(self):
        """Viewer with corpus and document permissions should see annotations."""
        result = AnnotationService.get_corpus_annotations(
            corpus_id=self.corpus.id,
            user=self.viewer,
        )

        # Viewer should see both types
        self.assertIn(self.structural_annotation, result)
        self.assertIn(self.user_annotation, result)

    def test_filter_structural_only(self):
        """Filtering by structural=True should return only structural annotations."""
        result = AnnotationService.get_corpus_annotations(
            corpus_id=self.corpus.id,
            user=self.owner,
            structural=True,
        )

        self.assertIn(self.structural_annotation, result)
        self.assertNotIn(self.user_annotation, result)

    def test_filter_non_structural_only(self):
        """Filtering by structural=False should return only user annotations."""
        result = AnnotationService.get_corpus_annotations(
            corpus_id=self.corpus.id,
            user=self.owner,
            structural=False,
        )

        self.assertNotIn(self.structural_annotation, result)
        self.assertIn(self.user_annotation, result)

    def test_user_without_corpus_permission_sees_nothing(self):
        """User without corpus permission should see no annotations."""
        no_access_user = User.objects.create_user(
            username="no_access", email="no_access@test.com", password="test123"
        )

        result = AnnotationService.get_corpus_annotations(
            corpus_id=self.corpus.id,
            user=no_access_user,
        )

        self.assertEqual(result.count(), 0)

    def test_structural_annotation_with_document_null(self):
        """Verify that structural annotations have document=NULL but are still found."""
        # Verify our test data is correct
        self.assertIsNone(self.structural_annotation.document)
        self.assertIsNotNone(self.structural_annotation.structural_set)
        self.assertTrue(self.structural_annotation.structural)

        # Query should still find it
        result = AnnotationService.get_corpus_annotations(
            corpus_id=self.corpus.id,
            user=self.owner,
            structural=True,
        )

        self.assertIn(self.structural_annotation, result)

    def test_deleted_document_path_excludes_annotations(self):
        """Annotations for documents with deleted paths should not be returned."""
        # Mark the document path as deleted
        path = DocumentPath.objects.get(
            document=self.doc_with_structural, corpus=self.corpus
        )
        path.is_deleted = True
        path.save()

        try:
            result = AnnotationService.get_corpus_annotations(
                corpus_id=self.corpus.id,
                user=self.owner,
            )

            # User annotation should be excluded (document path is deleted)
            self.assertNotIn(self.user_annotation, result)
            # Structural annotation should also be excluded (linked document path is deleted)
            self.assertNotIn(self.structural_annotation, result)
        finally:
            # Restore for other tests
            path.is_deleted = False
            path.save()


class TestAnnotationQuerySetVisibleToUser(TestCase):
    """Test the AnnotationQuerySet.visible_to_user method with structural annotations."""

    owner: User
    structural_set: StructuralAnnotationSet
    document: Document
    label: AnnotationLabel
    structural_annotation: Annotation

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.owner = User.objects.create_user(
            username="owner2", email="owner2@test.com", password="test123"
        )

        # Create structural annotation set and document
        cls.structural_set = StructuralAnnotationSet.objects.create()
        cls.document = Document.objects.create(
            title="Test Doc",
            creator=cls.owner,
            structural_annotation_set=cls.structural_set,
        )

        cls.label = AnnotationLabel.objects.create(
            text="Token",
            label_type=LabelType.TOKEN_LABEL,
            creator=cls.owner,
        )

        # Create structural annotation with document=NULL
        cls.structural_annotation = Annotation.objects.create(
            annotation_label=cls.label,
            structural_set=cls.structural_set,
            document=None,
            corpus=None,
            structural=True,
            creator=cls.owner,
        )

    def test_visible_to_user_includes_structural_annotations(self):
        """visible_to_user should include structural annotations with document=NULL."""
        result = Annotation.objects.visible_to_user(self.owner)

        # Structural annotation should be visible via structural_set relationship
        self.assertIn(self.structural_annotation, result)


class TestCorpusAnnotationsQueryEdgeCases(TestCase):
    """Test edge cases for AnnotationService.get_corpus_annotations."""

    owner: User
    superuser: User
    private_corpus: Corpus
    structural_set: StructuralAnnotationSet
    document: Document
    label: AnnotationLabel
    structural_annotation: Annotation
    user_annotation: Annotation

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.owner = User.objects.create_user(
            username="edge_owner", email="edge_owner@test.com", password="test123"
        )
        cls.superuser = User.objects.create_superuser(
            username="edge_admin", email="edge_admin@test.com", password="admin123"
        )

        # Create a private corpus
        cls.private_corpus = Corpus.objects.create(
            title="Private Corpus",
            creator=cls.owner,
            is_public=False,
        )

        # Create structural annotation set and document
        cls.structural_set = StructuralAnnotationSet.objects.create()
        cls.document = Document.objects.create(
            title="Edge Test Doc",
            creator=cls.owner,
            structural_annotation_set=cls.structural_set,
        )

        # Link document to corpus
        DocumentPath.objects.create(
            document=cls.document,
            corpus=cls.private_corpus,
            path="/edge_test.pdf",
            is_current=True,
            is_deleted=False,
            version_number=1,
            creator=cls.owner,
        )

        cls.label = AnnotationLabel.objects.create(
            text="EdgeLabel",
            label_type=LabelType.TOKEN_LABEL,
            creator=cls.owner,
        )

        # Create annotations
        cls.structural_annotation = Annotation.objects.create(
            annotation_label=cls.label,
            structural_set=cls.structural_set,
            document=None,
            corpus=None,
            structural=True,
            creator=cls.owner,
        )
        cls.user_annotation = Annotation.objects.create(
            annotation_label=cls.label,
            document=cls.document,
            corpus=cls.private_corpus,
            structural=False,
            creator=cls.owner,
        )

        # Grant permissions to owner
        set_permissions_for_obj_to_user(
            cls.owner, cls.private_corpus, [PermissionTypes.CRUD]
        )
        set_permissions_for_obj_to_user(cls.owner, cls.document, [PermissionTypes.CRUD])

    def test_nonexistent_corpus_returns_empty(self):
        """Querying a non-existent corpus should return empty queryset."""
        result = AnnotationService.get_corpus_annotations(
            corpus_id=999999,  # Non-existent
            user=self.owner,
        )

        self.assertEqual(result.count(), 0)

    def test_anonymous_user_private_corpus_returns_empty(self):
        """Anonymous user cannot access private corpus annotations."""
        from django.contrib.auth.models import AnonymousUser

        anon_user = AnonymousUser()

        result = AnnotationService.get_corpus_annotations(
            corpus_id=self.private_corpus.id,
            user=anon_user,
        )

        self.assertEqual(result.count(), 0)

    def test_authorized_superuser_with_structural_filter(self):
        """The structural filter behaves correctly for an *authorized* superuser.

        Scoped admin access (2026-05): a superuser no longer gets a blanket
        bypass in ``get_corpus_annotations`` — it goes through the normal
        corpus-permission path. We grant corpus + document READ via the normal
        guardian path so the filter case executes meaningfully, then assert the
        ``structural=True`` filter returns only structural annotations.
        """
        set_permissions_for_obj_to_user(
            self.superuser, self.private_corpus, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.superuser, self.document, [PermissionTypes.READ]
        )
        result = AnnotationService.get_corpus_annotations(
            corpus_id=self.private_corpus.id,
            user=self.superuser,
            structural=True,
        )

        self.assertIn(self.structural_annotation, result)
        self.assertNotIn(self.user_annotation, result)

    def test_authorized_superuser_with_analysis_isnull_filter(self):
        """The analysis-isnull filter behaves correctly for an *authorized*
        superuser.

        As above, the superuser is granted corpus + document READ through the
        normal path (no blanket bypass; scoped admin access 2026-05). Both
        annotations are manual (analysis=NULL), so the filter returns both.
        """
        set_permissions_for_obj_to_user(
            self.superuser, self.private_corpus, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.superuser, self.document, [PermissionTypes.READ]
        )
        result = AnnotationService.get_corpus_annotations(
            corpus_id=self.private_corpus.id,
            user=self.superuser,
            analysis_isnull=True,
        )

        # Both annotations have analysis=NULL (manual annotations)
        self.assertIn(self.structural_annotation, result)
        self.assertIn(self.user_annotation, result)

    def test_no_grant_superuser_sees_no_private_corpus_annotations(self):
        """A no-grant superuser fails the corpus-READ gate on a private corpus
        and therefore sees no annotations (parity with a stranger)."""
        result = AnnotationService.get_corpus_annotations(
            corpus_id=self.private_corpus.id,
            user=self.superuser,
        )
        self.assertEqual(result.count(), 0)

    def test_regular_user_with_analysis_isnull_filter(self):
        """Regular user can filter by analysis_isnull=True."""
        result = AnnotationService.get_corpus_annotations(
            corpus_id=self.private_corpus.id,
            user=self.owner,
            analysis_isnull=True,
        )

        # Both annotations have analysis=NULL (manual annotations)
        self.assertIn(self.structural_annotation, result)
        self.assertIn(self.user_annotation, result)

    def test_user_with_corpus_access_but_no_document_access(self):
        """User with corpus access but no visible documents sees nothing."""
        # Create a user with corpus access but no document access
        limited_user = User.objects.create_user(
            username="limited", email="limited@test.com", password="test123"
        )
        set_permissions_for_obj_to_user(
            limited_user, self.private_corpus, [PermissionTypes.READ]
        )
        # Deliberately NOT granting document permissions

        result = AnnotationService.get_corpus_annotations(
            corpus_id=self.private_corpus.id,
            user=limited_user,
        )

        # No visible documents = no annotations
        self.assertEqual(result.count(), 0)


class TestSearchCorpusAnnotationText(TestCase):
    """``AnnotationService.search_corpus_annotation_text`` — the citeable
    exact-phrase lookup behind the deep-research ``find_citable_passages`` tool
    (issue #2201)."""

    # Declared for mypy: ``setUpTestData`` assigns these on the class, which the
    # checker cannot infer (same pattern as TestCorpusAnnotationsQuery above).
    owner: User
    outsider: User
    corpus: Corpus
    doc: Document
    other_doc: Document
    label: AnnotationLabel
    wide: Annotation
    tight: Annotation
    other: Annotation

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="phrase-owner", email="po@test.com", password="test123"
        )
        cls.outsider = User.objects.create_user(
            username="phrase-outsider", email="pd@test.com", password="test123"
        )
        cls.corpus = Corpus.objects.create(title="Phrase Corpus", creator=cls.owner)
        cls.doc = Document.objects.create(title="Lease.pdf", creator=cls.owner)
        cls.other_doc = Document.objects.create(title="MSA.pdf", creator=cls.owner)
        for doc, path in ((cls.doc, "/lease.pdf"), (cls.other_doc, "/msa.pdf")):
            DocumentPath.objects.create(
                document=doc,
                corpus=cls.corpus,
                path=path,
                is_current=True,
                is_deleted=False,
                version_number=1,
                creator=cls.owner,
            )
        cls.label = AnnotationLabel.objects.create(
            text="SENTENCE", label_type=LabelType.TOKEN_LABEL, creator=cls.owner
        )
        # Two annotations contain the phrase; the tighter one must come first.
        cls.wide = Annotation.objects.create(
            annotation_label=cls.label,
            document=cls.doc,
            corpus=cls.corpus,
            creator=cls.owner,
            raw_text=(
                "Section 8.1. The tenant shall maintain the premises in good "
                "repair throughout the term and shall surrender them in like "
                "condition, ordinary wear and tear excepted."
            ),
        )
        cls.tight = Annotation.objects.create(
            annotation_label=cls.label,
            document=cls.doc,
            corpus=cls.corpus,
            creator=cls.owner,
            raw_text="The tenant shall maintain the premises in good repair.",
        )
        cls.other = Annotation.objects.create(
            annotation_label=cls.label,
            document=cls.other_doc,
            corpus=cls.corpus,
            creator=cls.owner,
            raw_text=(
                "Supplier shall at its sole cost and expense maintain the "
                "premises in good repair at all times during the term."
            ),
        )
        set_permissions_for_obj_to_user(cls.owner, cls.corpus, [PermissionTypes.CRUD])
        for doc in (cls.doc, cls.other_doc):
            set_permissions_for_obj_to_user(cls.owner, doc, [PermissionTypes.CRUD])

    def test_returns_real_citeable_anchors_tightest_first(self):
        hits = list(
            AnnotationService.search_corpus_annotation_text(
                corpus_id=self.corpus.id,
                user=self.owner,
                phrase="maintain the premises in good repair",
            )
        )
        self.assertEqual([h.pk for h in hits][:1], [self.tight.pk])
        self.assertIn(self.wide, hits)
        self.assertIn(self.other, hits)
        # Every id is a real (positive) Annotation PK — the whole point versus
        # search_exact_text_as_sources' synthetic negative ids.
        self.assertTrue(all(h.pk > 0 for h in hits))

    def test_scopes_to_a_single_document_and_respects_limit(self):
        hits = list(
            AnnotationService.search_corpus_annotation_text(
                corpus_id=self.corpus.id,
                user=self.owner,
                phrase="maintain the premises",
                document_id=self.doc.id,
                limit=1,
            )
        )
        self.assertEqual([h.pk for h in hits], [self.tight.pk])

    def test_empty_phrase_and_no_match_return_nothing(self):
        for phrase in ("", "   ", "a phrase that appears nowhere at all"):
            with self.subTest(phrase=phrase):
                self.assertEqual(
                    AnnotationService.search_corpus_annotation_text(
                        corpus_id=self.corpus.id, user=self.owner, phrase=phrase
                    ).count(),
                    0,
                )

    def test_visibility_is_delegated_to_get_corpus_annotations(self):
        # No corpus grant -> nothing, even though the phrase matches.
        self.assertEqual(
            AnnotationService.search_corpus_annotation_text(
                corpus_id=self.corpus.id,
                user=self.outsider,
                phrase="maintain the premises",
            ).count(),
            0,
        )
