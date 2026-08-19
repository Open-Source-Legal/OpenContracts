"""Expensive diagnostics must be DEFERRED when debug logging is off, not deleted.

Python evaluates a logging call's *arguments* before it checks whether the level
is enabled, so::

    _logger.debug(await _safe_queryset_info(queryset, "After vector search"))

runs ``_safe_queryset_info`` — a ``COUNT(*)`` over the annotation table — on
every search and then discards the string.  Several sites were ``_logger.info``,
so they ran the count *and* emitted it in production.

Measured on a 4,679-section authority deployment before the guard: three of
these counts cost **12.9 s of a 16.5 s search**, 78% of the total.  The most
expensive counted the entire ``Annotation`` table unfiltered — 4,591,881 rows —
once per search, to log a number that changes only when someone uploads a
document.  A cross-corpus fan-out over an 18-member group went from 277 s to
45 s once they were gated.

The failure mode a guard like this introduces is the opposite one: silently
removing a diagnostic, or worse, skipping a line that was doing real work.  So
these tests assert both directions — nothing runs at INFO, everything still runs
at DEBUG, and the search returns the same rows either way.
"""

from __future__ import annotations

import logging
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
    StructuralAnnotationSet,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.llms.vector_stores.core_vector_stores import (
    CoreAnnotationVectorStore,
    VectorSearchQuery,
)
from opencontractserver.pipeline.utils import get_default_embedder_path
from opencontractserver.types.enums import ContentModality

User = get_user_model()

VECTOR_STORE_LOGGER = "opencontractserver.llms.vector_stores.core_vector_stores"


def _constant_vector(dimension: int = 384, value: float = 0.5) -> list[float]:
    return [value] * dimension


class DiagnosticsAreGatedTests(TestCase):
    """``_diagnostics_enabled()`` gates every count-issuing diagnostic."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="diag-user", password="x")
        self.label = AnnotationLabel.objects.create(text="Paragraph", creator=self.user)
        self.corpus = Corpus.objects.create(
            title="Diag Corpus", creator=self.user, is_public=True
        )
        self.structural_set = StructuralAnnotationSet.objects.create(creator=self.user)
        self.doc = Document.objects.create(
            title="Diag Doc",
            creator=self.user,
            is_public=True,
            structural_annotation_set=self.structural_set,
        )
        # DocumentPath is what links a document to a corpus; an active,
        # non-deleted path keeps the store's deletion-aware filter from
        # excluding it.
        DocumentPath.objects.create(
            document=self.doc,
            corpus=self.corpus,
            path="/diag_doc.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )
        for index in range(3):
            annotation = Annotation.objects.create(
                raw_text=f"paragraph {index}",
                annotation_label=self.label,
                creator=self.user,
                is_public=True,
                structural=True,
                structural_set=self.structural_set,
                page=1,
                content_modalities=[ContentModality.TEXT.value],
            )
            # The DEFAULT embedder path, so the vector lands in the column the
            # store reads back; a made-up path stores the row and then matches
            # nothing, which makes every assertion below vacuously true.
            annotation.add_embedding(
                get_default_embedder_path(), _constant_vector(384, 0.5)
            )

    def _search(self) -> list[int]:
        store = CoreAnnotationVectorStore(
            user_id=self.user.id,
            corpus_id=self.corpus.id,
            document_id=None,
            check_corpus_deletion=False,
        )
        query = VectorSearchQuery(
            query_embedding=_constant_vector(384, 0.5), similarity_top_k=10
        )
        return [result.annotation.id for result in store.search(query)]

    def test_no_count_diagnostics_run_when_debug_is_off(self) -> None:
        """At INFO the helper must not be CALLED — not merely not logged."""
        with patch(f"{VECTOR_STORE_LOGGER}._safe_queryset_info") as async_info, patch(
            f"{VECTOR_STORE_LOGGER}._safe_queryset_info_sync"
        ) as sync_info:
            with self.assertLogs(VECTOR_STORE_LOGGER, level=logging.INFO):
                # assertLogs needs at least one record; the hybrid-fusion INFO
                # line supplies it and is deliberately NOT gated (it counts two
                # already-materialised lists and costs nothing).
                logging.getLogger(VECTOR_STORE_LOGGER).info("probe")
                found = self._search()
        self.assertTrue(
            found, "search returned nothing; the assertion below is vacuous"
        )

        self.assertEqual(
            async_info.call_count + sync_info.call_count,
            0,
            "a COUNT(*) diagnostic ran with debug logging off — the logging "
            "call's arguments are being evaluated before the level is checked",
        )

    def test_diagnostics_still_run_when_debug_is_on(self) -> None:
        """Deferred, not deleted: turning DEBUG on must bring them back."""
        logger = logging.getLogger(VECTOR_STORE_LOGGER)
        previous = logger.level
        logger.setLevel(logging.DEBUG)
        try:
            with patch(
                f"{VECTOR_STORE_LOGGER}._safe_queryset_info"
            ) as async_info, patch(
                f"{VECTOR_STORE_LOGGER}._safe_queryset_info_sync"
            ) as sync_info:
                found = self._search()
            calls = async_info.call_count + sync_info.call_count
        finally:
            logger.setLevel(previous)

        self.assertTrue(
            found, "search returned nothing; the assertion below is vacuous"
        )
        self.assertGreater(
            calls,
            0,
            "no diagnostic ran at DEBUG — the guard deleted them rather than "
            "deferring them, and the debugging aid is gone",
        )

    def test_results_are_identical_either_way(self) -> None:
        """The guard must change timing and nothing else."""
        logger = logging.getLogger(VECTOR_STORE_LOGGER)
        previous = logger.level

        logger.setLevel(logging.INFO)
        try:
            quiet = self._search()
            logger.setLevel(logging.DEBUG)
            verbose = self._search()
        finally:
            logger.setLevel(previous)

        self.assertEqual(quiet, verbose)
        self.assertTrue(quiet, "search returned nothing; the comparison proves nothing")

    def test_must_have_text_modalities_and_metadata_diagnostics_run_at_debug(
        self,
    ) -> None:
        """The must_have_text / modalities / metadata-filter guards also defer.

        The three tests above only exercise the default (no ``must_have_text``,
        no ``modalities``, no ``filters``) path through ``_build_base_queryset``
        and ``_apply_metadata_filters``. Those guarded call sites live behind
        their own ``if <condition>:`` blocks, so a search that never sets
        these options never reaches the diagnostics guard at all — proving
        nothing about it either way.
        """
        store = CoreAnnotationVectorStore(
            user_id=self.user.id,
            corpus_id=self.corpus.id,
            document_id=None,
            check_corpus_deletion=False,
            must_have_text="paragraph",
            modalities=[ContentModality.TEXT.value],
        )
        query = VectorSearchQuery(
            query_embedding=_constant_vector(384, 0.5),
            similarity_top_k=10,
            filters={"label": "Paragraph"},
        )

        logger = logging.getLogger(VECTOR_STORE_LOGGER)
        previous = logger.level
        logger.setLevel(logging.DEBUG)
        try:
            with self.assertLogs(VECTOR_STORE_LOGGER, level=logging.DEBUG) as logs:
                found = [result.annotation.id for result in store.search(query)]
        finally:
            logger.setLevel(previous)

        self.assertTrue(
            found, "search returned nothing; the assertions below are vacuous"
        )
        joined = "\n".join(logs.output)
        for expected in (
            "After must_have_text=",
            "After modalities=",
            "After metadata filters",
        ):
            self.assertIn(
                expected, joined, f"{expected!r} diagnostic never ran at DEBUG"
            )

    def test_vector_only_mode_fallback_diagnostics_run_at_debug(self) -> None:
        """``mode='vector'`` with no usable embedding still defers, not deletes.

        Every other test here searches in the default hybrid mode, which
        never reaches ``_run_vector_only_sync``'s standard-filtering fallback
        (no embedding, no text) at all.
        """
        store = CoreAnnotationVectorStore(
            user_id=self.user.id,
            corpus_id=self.corpus.id,
            document_id=None,
            check_corpus_deletion=False,
        )
        query = VectorSearchQuery(
            query_embedding=None,
            query_text=None,
            similarity_top_k=10,
            mode="vector",
        )

        logger = logging.getLogger(VECTOR_STORE_LOGGER)
        previous = logger.level
        logger.setLevel(logging.DEBUG)
        try:
            with self.assertLogs(VECTOR_STORE_LOGGER, level=logging.DEBUG) as logs:
                found = [result.annotation.id for result in store.search(query)]
        finally:
            logger.setLevel(previous)

        self.assertTrue(
            found, "search returned nothing; the assertion below is vacuous"
        )
        self.assertIn(
            "After limiting results",
            "\n".join(logs.output),
            "the vector-only fallback diagnostic never ran at DEBUG",
        )

    def test_async_vector_only_mode_diagnostics_run_at_debug(self) -> None:
        """The async vector-only path defers on both its embedding and fallback arms.

        ``async_search(mode="vector")`` never runs from the other tests, so
        neither ``_async_vector_only`` branch (embedding found / fallback) is
        otherwise exercised.
        """
        store = CoreAnnotationVectorStore(
            user_id=self.user.id,
            corpus_id=self.corpus.id,
            document_id=None,
            check_corpus_deletion=False,
        )

        logger = logging.getLogger(VECTOR_STORE_LOGGER)
        previous = logger.level
        logger.setLevel(logging.DEBUG)
        try:
            with_embedding = VectorSearchQuery(
                query_embedding=_constant_vector(384, 0.5),
                similarity_top_k=10,
                mode="vector",
            )
            with self.assertLogs(
                VECTOR_STORE_LOGGER, level=logging.DEBUG
            ) as logs_with_embedding:
                found = async_to_sync(store.async_search)(with_embedding)

            without_embedding = VectorSearchQuery(
                query_embedding=None,
                query_text=None,
                similarity_top_k=10,
                mode="vector",
            )
            with self.assertLogs(
                VECTOR_STORE_LOGGER, level=logging.DEBUG
            ) as logs_fallback:
                async_to_sync(store.async_search)(without_embedding)
        finally:
            logger.setLevel(previous)

        self.assertTrue(
            found, "search returned nothing; the assertion below is vacuous"
        )
        self.assertIn("After vector search", "\n".join(logs_with_embedding.output))
        self.assertIn("After limiting results", "\n".join(logs_fallback.output))
