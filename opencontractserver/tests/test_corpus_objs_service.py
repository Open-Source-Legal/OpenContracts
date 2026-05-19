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
        #
        # The ``uniq_document_slug_per_creator_cs`` constraint forbids two
        # ``Document`` rows sharing ``(creator, slug)``, so the private
        # twin uses a separate creator. The IDOR test exercises slug
        # collisions across corpora, not across creators, so this is
        # behaviourally equivalent.
        self.private_doc_creator = User.objects.create_user(
            username="private_doc_owner",
            email="pdo@test.com",
            password="test",
        )
        self.private_corpus = Corpus.objects.create(
            title="Private Corpus", creator=self.owner, is_public=False
        )
        self.private_doc = Document.objects.create(
            title="Private Doc",
            creator=self.private_doc_creator,
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


class TestGetCorpusDocuments_CamlAndDeleted(TransactionTestCase):
    """
    SCENARIO: ``get_corpus_documents`` composes the ``include_deleted`` and
    ``include_caml`` toggles via the shared
    :meth:`CorpusObjsService._build_corpus_documents_queryset` helper.

    BUSINESS RULE: CAML / markdown documents are excluded by default on
    BOTH branches (active-only and include-deleted) so downstream
    consumers — extractors, analyzers, agent contexts — never see CAML
    articles unless the caller explicitly opts in. The pre-fix split
    where ``include_deleted=True`` bypassed CAML filtering altogether
    is the regression this fixture is here to pin.
    """

    def setUp(self):
        from opencontractserver.constants.document_processing import (
            MARKDOWN_MIME_TYPE,
        )

        self.MARKDOWN_MIME_TYPE = MARKDOWN_MIME_TYPE

        self.owner = User.objects.create_user(
            username="caml_owner", email="caml@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="CAML Corpus", creator=self.owner, is_public=False
        )

        # Three docs: one regular PDF, one CAML article, one soft-deleted
        # PDF (so the include_deleted branch has something to surface).
        self.pdf = Document.objects.create(
            title="Regular PDF",
            creator=self.owner,
            pdf_file="regular.pdf",
            slug="regular-slug",
            file_type="application/pdf",
        )
        DocumentPath.objects.create(
            document=self.pdf,
            corpus=self.corpus,
            creator=self.owner,
            folder=None,
            path="/regular.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        self.caml = Document.objects.create(
            title="CAML Article",
            creator=self.owner,
            pdf_file="article.md",
            slug="caml-slug",
            file_type=MARKDOWN_MIME_TYPE,
        )
        DocumentPath.objects.create(
            document=self.caml,
            corpus=self.corpus,
            creator=self.owner,
            folder=None,
            path="/article.md",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        self.soft_deleted = Document.objects.create(
            title="Soft-Deleted PDF",
            creator=self.owner,
            pdf_file="trash.pdf",
            slug="trash-slug",
            file_type="application/pdf",
        )
        DocumentPath.objects.create(
            document=self.soft_deleted,
            corpus=self.corpus,
            creator=self.owner,
            folder=None,
            path="/trash.pdf",
            version_number=1,
            is_current=True,
            is_deleted=True,
        )

    def test_default_excludes_caml_and_deleted(self):
        """Default flags drop CAML and soft-deleted; only the PDF remains."""
        qs = CorpusObjsService.get_corpus_documents(user=self.owner, corpus=self.corpus)
        ids = set(qs.values_list("id", flat=True))
        self.assertEqual(ids, {self.pdf.id})

    def test_include_deleted_still_excludes_caml(self):
        """The include-deleted branch must keep filtering CAML —
        pre-fix this branch leaked CAML rows."""
        qs = CorpusObjsService.get_corpus_documents(
            user=self.owner, corpus=self.corpus, include_deleted=True
        )
        ids = set(qs.values_list("id", flat=True))
        self.assertIn(self.pdf.id, ids)
        self.assertIn(self.soft_deleted.id, ids)
        self.assertNotIn(
            self.caml.id,
            ids,
            "CAML documents must be excluded even on the include_deleted=True "
            "branch — both code paths now share _build_corpus_documents_queryset.",
        )

    def test_include_caml_surfaces_caml_but_not_deleted_by_default(self):
        """``include_caml=True`` on its own surfaces CAML but still
        keeps soft-deleted off the list."""
        qs = CorpusObjsService.get_corpus_documents(
            user=self.owner, corpus=self.corpus, include_caml=True
        )
        ids = set(qs.values_list("id", flat=True))
        self.assertEqual(ids, {self.pdf.id, self.caml.id})

    def test_both_flags_surface_everything(self):
        qs = CorpusObjsService.get_corpus_documents(
            user=self.owner,
            corpus=self.corpus,
            include_deleted=True,
            include_caml=True,
        )
        ids = set(qs.values_list("id", flat=True))
        self.assertEqual(ids, {self.pdf.id, self.caml.id, self.soft_deleted.id})

    def test_read_gate_returns_empty_for_stranger(self):
        """A user without corpus READ gets an empty queryset regardless
        of the toggles — the permission check stays load-bearing."""
        stranger = User.objects.create_user(
            username="caml_stranger",
            email="cs@test.com",
            password="test",
        )
        qs = CorpusObjsService.get_corpus_documents(
            user=stranger,
            corpus=self.corpus,
            include_deleted=True,
            include_caml=True,
        )
        self.assertEqual(qs.count(), 0)


# =============================================================================
# get_corpus_caml_articles
# =============================================================================


class TestGetCorpusCamlArticles(TransactionTestCase):
    """
    SCENARIO: ``get_corpus_caml_articles`` returns the corpus's
    ``Readme.CAML`` / ``text/markdown`` document(s) under the same
    corpus-as-gate semantic as the rest of the corpus-objs service.

    BUSINESS RULE: A CAML article is a Document with
    ``title="Readme.CAML"`` and ``file_type="text/markdown"``. The
    method returns at most one per corpus today but is shaped as a
    queryset so future multi-article designs don't break the signature.
    Permission denial returns an empty queryset (not an exception) —
    IDOR-safe.
    """

    def setUp(self):
        from opencontractserver.constants.document_processing import (
            CAML_ARTICLE_TITLE,
            MARKDOWN_MIME_TYPE,
        )

        self.CAML_ARTICLE_TITLE = CAML_ARTICLE_TITLE
        self.MARKDOWN_MIME_TYPE = MARKDOWN_MIME_TYPE

        self.owner = User.objects.create_user(
            username="caml_articles_owner",
            email="caml_articles@test.com",
            password="test",
        )
        self.stranger = User.objects.create_user(
            username="caml_articles_stranger",
            email="cas@test.com",
            password="test",
        )
        self.anonymous = AnonymousUser()

        # Private corpus with: regular PDF, CAML article, and a markdown
        # file that is NOT a CAML article (wrong title). The decoy
        # markdown is the load-bearing fixture for
        # ``test_excludes_non_caml_markdown``.
        self.private_corpus = Corpus.objects.create(
            title="Private CAML Corpus", creator=self.owner, is_public=False
        )
        self.pdf = Document.objects.create(
            title="Regular PDF",
            creator=self.owner,
            pdf_file="regular.pdf",
            slug="regular-doc",
            file_type="application/pdf",
        )
        DocumentPath.objects.create(
            document=self.pdf,
            corpus=self.private_corpus,
            creator=self.owner,
            folder=None,
            path="/regular.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )
        self.caml = Document.objects.create(
            title=CAML_ARTICLE_TITLE,
            creator=self.owner,
            pdf_file="readme-caml.md",
            slug="readme-caml",
            file_type=MARKDOWN_MIME_TYPE,
        )
        DocumentPath.objects.create(
            document=self.caml,
            corpus=self.private_corpus,
            creator=self.owner,
            folder=None,
            path="/Readme.CAML",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )
        self.decoy_markdown = Document.objects.create(
            title="Some Other Markdown",
            creator=self.owner,
            pdf_file="other.md",
            slug="other-markdown",
            file_type=MARKDOWN_MIME_TYPE,
        )
        DocumentPath.objects.create(
            document=self.decoy_markdown,
            corpus=self.private_corpus,
            creator=self.owner,
            folder=None,
            path="/other.md",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        # Public corpus with a CAML article — exercises the anonymous
        # / public READ path.
        self.public_corpus = Corpus.objects.create(
            title="Public CAML Corpus", creator=self.owner, is_public=True
        )
        self.public_caml = Document.objects.create(
            title=CAML_ARTICLE_TITLE,
            creator=self.owner,
            pdf_file="public-readme-caml.md",
            slug="public-readme-caml",
            file_type=MARKDOWN_MIME_TYPE,
        )
        DocumentPath.objects.create(
            document=self.public_caml,
            corpus=self.public_corpus,
            creator=self.owner,
            folder=None,
            path="/Readme.CAML",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        # An empty corpus (no CAML, no docs at all) for the empty-queryset
        # case.
        self.empty_corpus = Corpus.objects.create(
            title="Empty Corpus", creator=self.owner, is_public=False
        )

    def test_owner_sees_caml_article(self):
        """Owner of the corpus gets the corpus's CAML article."""
        qs = CorpusObjsService.get_corpus_caml_articles(
            user=self.owner, corpus=self.private_corpus
        )
        ids = list(qs.values_list("id", flat=True))
        self.assertEqual(ids, [self.caml.id])

    def test_empty_queryset_when_no_caml_present(self):
        """A corpus with no CAML article returns an empty queryset, not
        an exception."""
        qs = CorpusObjsService.get_corpus_caml_articles(
            user=self.owner, corpus=self.empty_corpus
        )
        self.assertEqual(qs.count(), 0)

    def test_excludes_non_caml_markdown(self):
        """A markdown file with a different title is NOT a CAML article
        and must be excluded — the title filter is load-bearing."""
        qs = CorpusObjsService.get_corpus_caml_articles(
            user=self.owner, corpus=self.private_corpus
        )
        ids = set(qs.values_list("id", flat=True))
        self.assertNotIn(self.decoy_markdown.id, ids)
        self.assertNotIn(self.pdf.id, ids)
        self.assertEqual(ids, {self.caml.id})

    def test_stranger_gets_empty_queryset_for_private_corpus(self):
        """A user without corpus READ gets an empty queryset, not an
        exception. IDOR-safe: no signal that the CAML exists."""
        qs = CorpusObjsService.get_corpus_caml_articles(
            user=self.stranger, corpus=self.private_corpus
        )
        self.assertEqual(qs.count(), 0)

    def test_anonymous_can_see_caml_in_public_corpus(self):
        """Anonymous user against a public corpus gets the CAML
        article — corpus READ via ``is_public=True`` is sufficient."""
        qs = CorpusObjsService.get_corpus_caml_articles(
            user=self.anonymous, corpus=self.public_corpus
        )
        ids = list(qs.values_list("id", flat=True))
        self.assertEqual(ids, [self.public_caml.id])

    def test_anonymous_blocked_from_private_corpus(self):
        """Anonymous against a private corpus → empty queryset."""
        qs = CorpusObjsService.get_corpus_caml_articles(
            user=self.anonymous, corpus=self.private_corpus
        )
        self.assertEqual(qs.count(), 0)
