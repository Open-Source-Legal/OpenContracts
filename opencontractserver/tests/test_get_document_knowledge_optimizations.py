"""
Backend regression tests for the optimisations on
``GetDocumentKnowledgeAndAnnotations``.

These guard against silently re-introducing the per-row N+1 patterns the
refactor in ``query_optimizer.py`` removed:

* ``_compute_effective_permissions`` is meant to be cached on the GraphQL
  request context — without that cache, every sibling resolver
  (``allAnnotations`` + ``allRelationships`` + ``docAnnotations``) re-runs
  its 10 permission round-trips.
* The parent ``Document``/``Corpus`` rows are also meant to be cached on
  the context so the same row isn't re-fetched per resolver.
* ``user_feedback`` is meant to be prefetched on the annotation queryset so
  the connection resolver in
  ``GetDocumentKnowledgeAndAnnotations`` doesn't fire ``count() + .all()``
  per annotation.
"""

from __future__ import annotations

from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from opencontractserver.annotations.models import Annotation, AnnotationLabel
from opencontractserver.annotations.query_optimizer import AnnotationQueryOptimizer
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.feedback.models import UserFeedback
from opencontractserver.types.enums import LabelType
from opencontractserver.users.models import User

UserModel = get_user_model()


class _FakeContext(SimpleNamespace):
    """Stand-in for ``info.context`` carrying only the fields we cache on."""


def _superuser_request_context() -> _FakeContext:
    """Return a fresh context with no caches initialised."""
    return _FakeContext()


class ComputeEffectivePermissionsCacheTests(TestCase):
    owner: User
    corpus: Corpus
    document: Document

    @classmethod
    def setUpTestData(cls) -> None:
        cls.owner = UserModel.objects.create_superuser(
            username="opt_owner", email="opt_owner@test.com", password="x"
        )
        cls.corpus = Corpus.objects.create(title="Optim Corpus", creator=cls.owner)
        cls.document = Document.objects.create(
            title="Optim Document", creator=cls.owner
        )
        DocumentPath.objects.create(
            document=cls.document,
            corpus=cls.corpus,
            path="/doc.pdf",
            is_current=True,
            is_deleted=False,
            version_number=1,
            creator=cls.owner,
        )

    def test_permissions_cached_on_context(self) -> None:
        ctx = _superuser_request_context()
        first = AnnotationQueryOptimizer._compute_effective_permissions(
            self.owner, self.document.pk, self.corpus.pk, context=ctx
        )
        cache = ctx._effective_perms_cache
        self.assertIn((self.owner.pk, self.document.pk, self.corpus.pk), cache)

        # The second call must consult the cache (same context, same key).
        second = AnnotationQueryOptimizer._compute_effective_permissions(
            self.owner, self.document.pk, self.corpus.pk, context=ctx
        )
        self.assertEqual(first, second)

    def test_document_and_corpus_lookups_cached_on_context(self) -> None:
        """
        The Document/Corpus instance caches are meant to be primed by the
        first ``_get_*_for_request`` call so subsequent calls avoid the
        round-trip. With request-level caching the second invocation must
        run zero queries.
        """
        ctx = _superuser_request_context()

        with CaptureQueriesContext(connection) as queries_first:
            AnnotationQueryOptimizer._get_document_for_request(self.document.pk, ctx)
            AnnotationQueryOptimizer._get_corpus_for_request(self.corpus.pk, ctx)
        self.assertGreater(len(queries_first), 0)

        with CaptureQueriesContext(connection) as queries_second:
            doc_again = AnnotationQueryOptimizer._get_document_for_request(
                self.document.pk, ctx
            )
            corpus_again = AnnotationQueryOptimizer._get_corpus_for_request(
                self.corpus.pk, ctx
            )
        self.assertEqual(len(queries_second), 0)
        self.assertEqual(doc_again.pk, self.document.pk)
        self.assertEqual(corpus_again.pk, self.corpus.pk)

    def test_no_context_falls_through_without_crashing(self) -> None:
        """``context=None`` must still work — the helper is callable from
        non-GraphQL code paths."""
        result = AnnotationQueryOptimizer._compute_effective_permissions(
            self.owner, self.document.pk, self.corpus.pk, context=None
        )
        self.assertEqual(result, (True, True, True, True, True))


class AnnotationFeedbackPrefetchTests(TestCase):
    owner: User
    corpus: Corpus
    document: Document
    annotations: list[Annotation]

    @classmethod
    def setUpTestData(cls) -> None:
        cls.owner = UserModel.objects.create_superuser(
            username="fb_owner", email="fb_owner@test.com", password="x"
        )
        cls.corpus = Corpus.objects.create(title="FB Corpus", creator=cls.owner)
        cls.document = Document.objects.create(title="FB Doc", creator=cls.owner)
        DocumentPath.objects.create(
            document=cls.document,
            corpus=cls.corpus,
            path="/fb.pdf",
            is_current=True,
            is_deleted=False,
            version_number=1,
            creator=cls.owner,
        )
        label = AnnotationLabel.objects.create(
            text="Paragraph",
            label_type=LabelType.TOKEN_LABEL,
            creator=cls.owner,
        )
        # Fan out 10 annotations + 2 feedbacks each. The exact numbers don't
        # matter; what matters is that resolving feedback should be a single
        # batched ``IN (...)`` SELECT, not one per annotation.
        cls.annotations = []
        for index in range(10):
            ann = Annotation.objects.create(
                creator=cls.owner,
                document=cls.document,
                corpus=cls.corpus,
                annotation_label=label,
                page=1,
                raw_text=f"text {index}",
            )
            cls.annotations.append(ann)
            UserFeedback.objects.create(commented_annotation=ann, creator=cls.owner)
            UserFeedback.objects.create(commented_annotation=ann, creator=cls.owner)

    def test_user_feedback_is_prefetched(self) -> None:
        """
        Resolving ``user_feedback`` for every annotation must not fire a
        separate query per row. ``QuerySet.prefetch_related("user_feedback")``
        registered by the optimiser collapses every per-row access into one
        batch SELECT. We verify by counting queries while iterating the full
        result and accessing the prefetched cache.
        """
        qs = AnnotationQueryOptimizer.get_document_annotations(
            document_id=self.document.pk,
            user=self.owner,
            corpus_id=self.corpus.pk,
        )
        with CaptureQueriesContext(connection) as captured:
            results = list(qs)
            for ann in results:
                # Going through the public ``RelatedManager`` API exercises
                # Django's prefetch dispatch — if the prefetch dropped, this
                # would issue a fresh query per row instead of reading the
                # cached list, which the query-count assertion below catches.
                feedback_list = list(ann.user_feedback.all())
                self.assertEqual(len(feedback_list), 2)

        # Permitted: the annotation SELECT plus the related-table SELECTs
        # (annotation_label/creator/analysis are select_related so no extra
        # round trips, user_feedback is one batched IN SELECT). Allow some
        # slack for the privacy filter subqueries against analyses/extracts.
        # Critically: must NOT scale with len(results).
        self.assertLess(
            len(captured.captured_queries),
            len(results),
            f"Expected far fewer queries than annotations; got "
            f"{len(captured.captured_queries)} queries for {len(results)} "
            f"annotations — looks like the prefetch was dropped.",
        )

    def test_feedback_count_uses_prefetched_cache(self) -> None:
        """
        ``AnnotationType.resolve_feedback_count`` must consult the prefetched
        ``user_feedback`` list rather than firing ``COUNT(*)`` per row.
        """
        from config.graphql.annotation_types import AnnotationType

        qs = AnnotationQueryOptimizer.get_document_annotations(
            document_id=self.document.pk,
            user=self.owner,
            corpus_id=self.corpus.pk,
        )
        results = list(qs)

        with CaptureQueriesContext(connection) as captured:
            counts = [
                AnnotationType.resolve_feedback_count(ann, info=None) for ann in results
            ]
        self.assertEqual(counts, [2] * len(results))
        # Zero new queries — every count came from the prefetch cache.
        self.assertEqual(len(captured.captured_queries), 0)


class ComputeEffectivePermissionsBranchTests(TestCase):
    """
    Cover the non-superuser permission-resolution branches of
    ``_compute_effective_permissions``. These branches drive the security
    contract for anonymous and authenticated readers, so a regression here
    silently widens or narrows access; codecov was hitting only the
    superuser fast-path before this suite landed.
    """

    owner: User
    public_doc: Document
    private_doc: Document
    public_corpus: Corpus
    private_corpus: Corpus

    @classmethod
    def setUpTestData(cls) -> None:
        cls.owner = UserModel.objects.create_superuser(
            username="branch_owner", email="branch_owner@test.com", password="x"
        )
        cls.public_doc = Document.objects.create(
            title="Public Doc", creator=cls.owner, is_public=True
        )
        cls.private_doc = Document.objects.create(
            title="Private Doc", creator=cls.owner, is_public=False
        )
        cls.public_corpus = Corpus.objects.create(
            title="Public Corpus", creator=cls.owner, is_public=True
        )
        cls.private_corpus = Corpus.objects.create(
            title="Private Corpus", creator=cls.owner, is_public=False
        )

    def test_anonymous_reads_public_doc_with_no_corpus(self) -> None:
        from django.contrib.auth.models import AnonymousUser

        result = AnnotationQueryOptimizer._compute_effective_permissions(
            AnonymousUser(), self.public_doc.pk, None
        )
        self.assertEqual(result, (True, False, False, False, False))

    def test_anonymous_blocked_on_private_doc(self) -> None:
        from django.contrib.auth.models import AnonymousUser

        result = AnnotationQueryOptimizer._compute_effective_permissions(
            AnonymousUser(), self.private_doc.pk, None
        )
        self.assertEqual(result, (False, False, False, False, False))

    def test_anonymous_blocked_when_corpus_is_private(self) -> None:
        from django.contrib.auth.models import AnonymousUser

        result = AnnotationQueryOptimizer._compute_effective_permissions(
            AnonymousUser(), self.public_doc.pk, self.private_corpus.pk
        )
        self.assertEqual(result, (False, False, False, False, False))

    def test_anonymous_reads_public_doc_in_public_corpus(self) -> None:
        from django.contrib.auth.models import AnonymousUser

        result = AnnotationQueryOptimizer._compute_effective_permissions(
            AnonymousUser(), self.public_doc.pk, self.public_corpus.pk
        )
        self.assertEqual(result, (True, False, False, False, False))

    def test_missing_document_denies_everything(self) -> None:
        result = AnnotationQueryOptimizer._compute_effective_permissions(
            self.owner, 9_999_999, None
        )
        # Superusers short-circuit before fetching, so use a non-superuser.
        regular = UserModel.objects.create_user(
            username="regular_branch", email="r@b.com", password="x"
        )
        result = AnnotationQueryOptimizer._compute_effective_permissions(
            regular, 9_999_999, None
        )
        self.assertEqual(result, (False, False, False, False, False))

    def test_authenticated_without_doc_read_is_denied(self) -> None:
        """
        A regular user without explicit permissions on a private document
        must hit the ``not doc_read`` branch and be denied entirely.
        """
        regular = UserModel.objects.create_user(
            username="regular_no_perm", email="r2@b.com", password="x"
        )
        result = AnnotationQueryOptimizer._compute_effective_permissions(
            regular, self.private_doc.pk, None
        )
        self.assertEqual(result, (False, False, False, False, False))


class GetDocumentAnnotationsBranchTests(TestCase):
    """
    Exercise the corpus-less and version-aware filter branches of
    ``get_document_annotations``. These are silent if regressed (the wrong
    set of annotations comes back) and aren't otherwise covered.
    """

    owner: User
    corpus: Corpus
    document: Document
    structural_label: AnnotationLabel
    user_label: AnnotationLabel

    @classmethod
    def setUpTestData(cls) -> None:
        cls.owner = UserModel.objects.create_superuser(
            username="branch2_owner", email="b2@test.com", password="x"
        )
        cls.corpus = Corpus.objects.create(title="B2 Corpus", creator=cls.owner)
        cls.document = Document.objects.create(title="B2 Doc", creator=cls.owner)
        DocumentPath.objects.create(
            document=cls.document,
            corpus=cls.corpus,
            path="/b2.pdf",
            is_current=True,
            is_deleted=False,
            version_number=1,
            creator=cls.owner,
        )
        cls.user_label = AnnotationLabel.objects.create(
            text="User Para",
            label_type=LabelType.TOKEN_LABEL,
            creator=cls.owner,
        )
        cls.structural_label = AnnotationLabel.objects.create(
            text="Heading",
            label_type=LabelType.TOKEN_LABEL,
            creator=cls.owner,
        )
        # One non-structural annotation.
        Annotation.objects.create(
            creator=cls.owner,
            document=cls.document,
            corpus=cls.corpus,
            annotation_label=cls.user_label,
            page=1,
            raw_text="user text",
            structural=False,
        )
        # One structural annotation.
        Annotation.objects.create(
            creator=cls.owner,
            document=cls.document,
            corpus=cls.corpus,
            annotation_label=cls.structural_label,
            page=1,
            raw_text="structural text",
            structural=True,
        )

    def test_corpus_less_call_returns_only_structural(self) -> None:
        qs = AnnotationQueryOptimizer.get_document_annotations(
            document_id=self.document.pk,
            user=self.owner,
            corpus_id=None,
        )
        results = list(qs)
        self.assertTrue(all(ann.structural for ann in results))
        self.assertGreaterEqual(len(results), 1)

    def test_corpus_less_call_with_structural_false_returns_empty(self) -> None:
        qs = AnnotationQueryOptimizer.get_document_annotations(
            document_id=self.document.pk,
            user=self.owner,
            corpus_id=None,
            structural=False,
        )
        self.assertEqual(qs.count(), 0)

    def test_no_active_path_returns_empty(self) -> None:
        """
        When the document has no current, non-deleted ``DocumentPath`` in the
        corpus, ``get_document_annotations`` must return an empty queryset
        even though the user can read both objects.
        """
        ghost_doc = Document.objects.create(title="Ghost", creator=self.owner)
        # No DocumentPath created — version-aware check should bail.
        qs = AnnotationQueryOptimizer.get_document_annotations(
            document_id=ghost_doc.pk,
            user=self.owner,
            corpus_id=self.corpus.pk,
        )
        self.assertEqual(qs.count(), 0)


class GetAnnotationsForPathTests(TestCase):
    """
    Cover ``get_annotations_for_path`` — the corpus-scoped path lookup.
    The unhappy paths (missing path, specific version) are not exercised
    elsewhere.
    """

    owner: User
    corpus: Corpus
    document: Document

    @classmethod
    def setUpTestData(cls) -> None:
        cls.owner = UserModel.objects.create_superuser(
            username="path_owner", email="p@test.com", password="x"
        )
        cls.corpus = Corpus.objects.create(title="Path Corpus", creator=cls.owner)
        cls.document = Document.objects.create(title="Path Doc", creator=cls.owner)
        DocumentPath.objects.create(
            document=cls.document,
            corpus=cls.corpus,
            path="/contracts/active.pdf",
            is_current=True,
            is_deleted=False,
            version_number=2,
            creator=cls.owner,
        )

    def test_resolves_current_version(self) -> None:
        qs = AnnotationQueryOptimizer.get_annotations_for_path(
            corpus_id=self.corpus.pk,
            path="/contracts/active.pdf",
            user=self.owner,
        )
        # Returns a queryset (no annotations on this doc but the call must
        # not raise and must return ``.none()``-compatible queryset).
        self.assertEqual(qs.count(), 0)

    def test_returns_empty_for_unknown_path(self) -> None:
        qs = AnnotationQueryOptimizer.get_annotations_for_path(
            corpus_id=self.corpus.pk,
            path="/contracts/missing.pdf",
            user=self.owner,
        )
        self.assertEqual(qs.count(), 0)

    def test_returns_empty_when_specific_version_missing(self) -> None:
        qs = AnnotationQueryOptimizer.get_annotations_for_path(
            corpus_id=self.corpus.pk,
            path="/contracts/active.pdf",
            user=self.owner,
            version=99,
        )
        self.assertEqual(qs.count(), 0)


class RequestCachedFetcherTests(TestCase):
    """
    Direct coverage for ``_get_document_for_request`` and
    ``_get_corpus_for_request`` — including the ``DoesNotExist`` paths and
    the ``context=None`` fallback that ``_compute_effective_permissions``
    doesn't otherwise reach.
    """

    owner: User
    document: Document
    corpus: Corpus

    @classmethod
    def setUpTestData(cls) -> None:
        cls.owner = UserModel.objects.create_superuser(
            username="cache_owner", email="c@test.com", password="x"
        )
        cls.document = Document.objects.create(title="Cache Doc", creator=cls.owner)
        cls.corpus = Corpus.objects.create(title="Cache Corpus", creator=cls.owner)

    def test_get_document_with_no_context_returns_instance(self) -> None:
        instance = AnnotationQueryOptimizer._get_document_for_request(
            self.document.pk, None
        )
        self.assertIsNotNone(instance)
        self.assertEqual(instance.pk, self.document.pk)

    def test_get_document_with_no_context_returns_none_for_missing(self) -> None:
        self.assertIsNone(
            AnnotationQueryOptimizer._get_document_for_request(9_999_999, None)
        )

    def test_get_corpus_with_no_context_returns_instance(self) -> None:
        instance = AnnotationQueryOptimizer._get_corpus_for_request(
            self.corpus.pk, None
        )
        self.assertIsNotNone(instance)
        self.assertEqual(instance.pk, self.corpus.pk)

    def test_get_corpus_with_no_context_returns_none_for_missing(self) -> None:
        self.assertIsNone(
            AnnotationQueryOptimizer._get_corpus_for_request(9_999_999, None)
        )

    def test_missing_document_caches_none_for_subsequent_calls(self) -> None:
        ctx = SimpleNamespace()
        first = AnnotationQueryOptimizer._get_document_for_request(9_999_999, ctx)
        self.assertIsNone(first)
        # Second call must hit the cache (zero queries).
        with CaptureQueriesContext(connection) as captured:
            second = AnnotationQueryOptimizer._get_document_for_request(9_999_999, ctx)
        self.assertIsNone(second)
        self.assertEqual(len(captured.captured_queries), 0)

    def test_missing_corpus_caches_none_for_subsequent_calls(self) -> None:
        ctx = SimpleNamespace()
        first = AnnotationQueryOptimizer._get_corpus_for_request(9_999_999, ctx)
        self.assertIsNone(first)
        with CaptureQueriesContext(connection) as captured:
            second = AnnotationQueryOptimizer._get_corpus_for_request(9_999_999, ctx)
        self.assertIsNone(second)
        self.assertEqual(len(captured.captured_queries), 0)
