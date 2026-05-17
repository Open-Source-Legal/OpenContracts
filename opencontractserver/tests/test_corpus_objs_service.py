"""
Tests for the new ``CorpusObjsService`` convenience methods that close the
buggy corpus-document fusion pattern flagged in the MCP review.

Covered methods:

- ``get_corpus_document_by_slug(user, corpus, slug, include_deleted=False)``
- ``get_corpus_document_by_id(user, corpus, document_id, include_deleted=False)``
- ``is_document_in_corpus(user, corpus, document_id, include_deleted=False)``

All three methods share a single guarantee: corpus READ acts as the gate.
If the user lacks corpus READ, the result is "not found" — for the lookup
methods that means ``Document.DoesNotExist``, for the boolean check that
means ``False``. Same exception/return whether the document doesn't exist,
isn't in the corpus, or the user lacks READ — IDOR-safe.

These methods replace the buggy
``corpus.get_documents().values_list("id", flat=True)`` +
``Document.objects.visible_to_user(user).get(id__in=..., slug=...)``
fusion that the PR review flagged.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TransactionTestCase

from opencontractserver.corpuses.corpus_objs_service import CorpusObjsService
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class CorpusObjsServiceTestBase(TransactionTestCase):
    """
    Shared fixture: a public corpus and a private corpus, each containing a
    document with a known slug.  Used to exercise the corpus-READ gate.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.stranger = User.objects.create_user(
            username="stranger", email="stranger@test.com", password="test"
        )
        self.anonymous = AnonymousUser()

        # Public corpus + a document with slug "shared-slug"
        self.public_corpus = Corpus.objects.create(
            title="Public Corpus", creator=self.owner, is_public=True
        )
        self.public_doc = Document.objects.create(
            title="Public Doc",
            creator=self.owner,
            pdf_file="public.pdf",
            slug="shared-slug",
        )
        DocumentPath.objects.create(
            document=self.public_doc,
            corpus=self.public_corpus,
            creator=self.owner,
            folder=None,
            path="/public.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        # Private corpus + a *different* document, also with slug "shared-slug".
        # This is the IDOR oracle: an anonymous lookup against the private
        # corpus must not leak the public doc, must not return the private
        # doc, must not raise anything other than ``DoesNotExist``.
        self.private_corpus = Corpus.objects.create(
            title="Private Corpus", creator=self.owner, is_public=False
        )
        self.private_doc = Document.objects.create(
            title="Private Doc",
            creator=self.owner,
            pdf_file="private.pdf",
            slug="shared-slug",
        )
        DocumentPath.objects.create(
            document=self.private_doc,
            corpus=self.private_corpus,
            creator=self.owner,
            folder=None,
            path="/private.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )


# =============================================================================
# get_corpus_document_by_slug
# =============================================================================


class TestGetCorpusDocumentBySlug_HappyPath(CorpusObjsServiceTestBase):
    """
    SCENARIO: Looking up a document by slug inside a corpus the user can read.

    BUSINESS RULE: When corpus READ is satisfied, the matching document is
    returned regardless of whether the user owns the document.
    """

    def test_owner_can_lookup_doc_in_public_corpus(self):
        doc = CorpusObjsService.get_corpus_document_by_slug(
            user=self.owner, corpus=self.public_corpus, slug="shared-slug"
        )
        self.assertEqual(doc.pk, self.public_doc.pk)

    def test_owner_can_lookup_doc_in_private_corpus(self):
        doc = CorpusObjsService.get_corpus_document_by_slug(
            user=self.owner, corpus=self.private_corpus, slug="shared-slug"
        )
        self.assertEqual(doc.pk, self.private_doc.pk)

    def test_anonymous_can_lookup_doc_in_public_corpus(self):
        doc = CorpusObjsService.get_corpus_document_by_slug(
            user=self.anonymous, corpus=self.public_corpus, slug="shared-slug"
        )
        self.assertEqual(doc.pk, self.public_doc.pk)


class TestGetCorpusDocumentBySlug_IDORSafety(CorpusObjsServiceTestBase):
    """
    SCENARIO: Looking up a document by slug when the gate denies access.

    BUSINESS RULE: The same ``Document.DoesNotExist`` fires regardless of
    why the lookup failed — corpus READ denied, doc not in corpus, slug
    typo. Prevents a per-corpus enumeration oracle via timing or different
    error messages.
    """

    def test_anonymous_lookup_in_private_corpus_raises_doesnotexist(self):
        with self.assertRaises(Document.DoesNotExist):
            CorpusObjsService.get_corpus_document_by_slug(
                user=self.anonymous,
                corpus=self.private_corpus,
                slug="shared-slug",
            )

    def test_stranger_lookup_in_private_corpus_raises_doesnotexist(self):
        with self.assertRaises(Document.DoesNotExist):
            CorpusObjsService.get_corpus_document_by_slug(
                user=self.stranger,
                corpus=self.private_corpus,
                slug="shared-slug",
            )

    def test_lookup_with_unknown_slug_raises_doesnotexist(self):
        with self.assertRaises(Document.DoesNotExist):
            CorpusObjsService.get_corpus_document_by_slug(
                user=self.owner,
                corpus=self.public_corpus,
                slug="nope-not-a-real-slug",
            )

    def test_anonymous_lookup_in_private_corpus_does_not_return_public_doc(self):
        """
        MCP regression: same slug exists in BOTH the public and the private
        corpus. Looking up the slug against the private corpus from an
        anonymous user must not silently return the public doc.
        """
        with self.assertRaises(Document.DoesNotExist):
            CorpusObjsService.get_corpus_document_by_slug(
                user=self.anonymous,
                corpus=self.private_corpus,
                slug="shared-slug",
            )


class TestGetCorpusDocumentBySlug_GrantedAccess(CorpusObjsServiceTestBase):
    """
    SCENARIO: A stranger explicitly granted corpus READ can look up documents.

    BUSINESS RULE: Guardian grants flow through ``corpus.user_can`` so the
    service-layer gate uses the same authorization machinery as the rest
    of the codebase.
    """

    def test_grantee_with_corpus_read_can_lookup(self):
        set_permissions_for_obj_to_user(
            self.stranger, self.private_corpus, [PermissionTypes.READ]
        )
        doc = CorpusObjsService.get_corpus_document_by_slug(
            user=self.stranger,
            corpus=self.private_corpus,
            slug="shared-slug",
        )
        self.assertEqual(doc.pk, self.private_doc.pk)


# =============================================================================
# get_corpus_document_by_id
# =============================================================================


class TestGetCorpusDocumentById_HappyPath(CorpusObjsServiceTestBase):
    def test_owner_can_lookup_by_id_in_public_corpus(self):
        doc = CorpusObjsService.get_corpus_document_by_id(
            user=self.owner,
            corpus=self.public_corpus,
            document_id=self.public_doc.pk,
        )
        self.assertEqual(doc.pk, self.public_doc.pk)


class TestGetCorpusDocumentById_IDORSafety(CorpusObjsServiceTestBase):
    def test_anonymous_lookup_in_private_corpus_raises_doesnotexist(self):
        with self.assertRaises(Document.DoesNotExist):
            CorpusObjsService.get_corpus_document_by_id(
                user=self.anonymous,
                corpus=self.private_corpus,
                document_id=self.private_doc.pk,
            )

    def test_lookup_of_other_corpus_doc_raises_doesnotexist(self):
        """
        IDOR: Looking up the public doc's PK against the private corpus
        must not return it. The doc exists, just not in this corpus.
        """
        with self.assertRaises(Document.DoesNotExist):
            CorpusObjsService.get_corpus_document_by_id(
                user=self.owner,
                corpus=self.private_corpus,
                document_id=self.public_doc.pk,
            )


# =============================================================================
# is_document_in_corpus
# =============================================================================


class TestIsDocumentInCorpus_Boolean(CorpusObjsServiceTestBase):
    """
    SCENARIO: Membership check that also enforces corpus READ.

    BUSINESS RULE: Returns ``False`` for any failing condition — never
    leaks the difference between "doc doesn't exist", "doc not in corpus",
    and "user lacks corpus READ".
    """

    def test_returns_true_when_doc_is_in_corpus_and_user_has_read(self):
        self.assertTrue(
            CorpusObjsService.is_document_in_corpus(
                user=self.owner,
                corpus=self.public_corpus,
                document_id=self.public_doc.pk,
            )
        )

    def test_returns_false_when_doc_is_in_different_corpus(self):
        self.assertFalse(
            CorpusObjsService.is_document_in_corpus(
                user=self.owner,
                corpus=self.public_corpus,
                document_id=self.private_doc.pk,
            )
        )

    def test_returns_false_when_user_lacks_corpus_read(self):
        self.assertFalse(
            CorpusObjsService.is_document_in_corpus(
                user=self.anonymous,
                corpus=self.private_corpus,
                document_id=self.private_doc.pk,
            )
        )

    def test_returns_false_when_doc_does_not_exist(self):
        self.assertFalse(
            CorpusObjsService.is_document_in_corpus(
                user=self.owner,
                corpus=self.public_corpus,
                document_id=99999999,
            )
        )


class TestIsDocumentInCorpus_SoftDeleted(TransactionTestCase):
    """
    SCENARIO: ``include_deleted`` flag controls whether soft-deleted
    documents count as members.

    BUSINESS RULE: Default is ``include_deleted=False`` — soft-deleted
    docs are invisible. ``include_deleted=True`` is the trash-view path.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )
        self.doc = Document.objects.create(
            title="Soft-Deleted Doc",
            creator=self.owner,
            pdf_file="deleted.pdf",
            slug="deleted-slug",
        )
        # Create an active path, then a soft-deleted successor.
        active = DocumentPath.objects.create(
            document=self.doc,
            corpus=self.corpus,
            creator=self.owner,
            folder=None,
            path="/deleted.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )
        active.is_current = False
        active.save(update_fields=["is_current"])
        DocumentPath.objects.create(
            document=self.doc,
            corpus=self.corpus,
            creator=self.owner,
            folder=None,
            path="/deleted.pdf",
            version_number=1,
            parent=active,
            is_current=True,
            is_deleted=True,
        )

    def test_default_excludes_soft_deleted(self):
        """``include_deleted=False`` (default) hides soft-deleted docs."""
        self.assertFalse(
            CorpusObjsService.is_document_in_corpus(
                user=self.owner,
                corpus=self.corpus,
                document_id=self.doc.pk,
            )
        )

    def test_include_deleted_surfaces_soft_deleted(self):
        self.assertTrue(
            CorpusObjsService.is_document_in_corpus(
                user=self.owner,
                corpus=self.corpus,
                document_id=self.doc.pk,
                include_deleted=True,
            )
        )

    def test_lookup_by_slug_with_include_deleted(self):
        doc = CorpusObjsService.get_corpus_document_by_slug(
            user=self.owner,
            corpus=self.corpus,
            slug="deleted-slug",
            include_deleted=True,
        )
        self.assertEqual(doc.pk, self.doc.pk)

    def test_lookup_by_slug_without_include_deleted_raises(self):
        with self.assertRaises(Document.DoesNotExist):
            CorpusObjsService.get_corpus_document_by_slug(
                user=self.owner,
                corpus=self.corpus,
                slug="deleted-slug",
            )
