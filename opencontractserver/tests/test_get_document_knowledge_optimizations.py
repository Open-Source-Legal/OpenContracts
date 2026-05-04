"""
Backend regression tests for the optimisations on
``GetDocumentKnowledgeAndAnnotations``.

These guard against silently re-introducing the per-row N+1 patterns the
refactor in ``query_optimizer.py`` removed:

* ``_compute_effective_permissions`` is meant to be cached on the GraphQL
  request context — without that cache, every sibling resolver
  (``allAnnotations`` + ``allRelationships`` + ``docAnnotations``) re-runs
  its 10 ``user_has_permission_for_obj`` round-trips.
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

User = get_user_model()


class _FakeContext(SimpleNamespace):
    """Stand-in for ``info.context`` carrying only the fields we cache on."""


def _superuser_request_context() -> _FakeContext:
    """Return a fresh context with no caches initialised."""
    return _FakeContext()


class ComputeEffectivePermissionsCacheTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.owner = User.objects.create_superuser(
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
            AnnotationQueryOptimizer._get_document_for_request(
                self.document.pk, ctx
            )
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
    @classmethod
    def setUpTestData(cls) -> None:
        cls.owner = User.objects.create_superuser(
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
        cls.annotations: list[Annotation] = []
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
                feedback_list = ann._prefetched_objects_cache["user_feedback"]
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
                AnnotationType.resolve_feedback_count(ann, info=None)
                for ann in results
            ]
        self.assertEqual(counts, [2] * len(results))
        # Zero new queries — every count came from the prefetch cache.
        self.assertEqual(len(captured.captured_queries), 0)
