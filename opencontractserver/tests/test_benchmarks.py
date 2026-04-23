"""Tests for the benchmark harness (``opencontractserver.benchmarks``).

Covers:

* Pure unit tests for the metrics module (no DB, no Celery).
* Adapter unit tests against the shipped micro fixture.
* A lightweight end-to-end runner test that mocks the structured-response
  agent so CI does not hit real LLMs.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest import TestCase as PyUnitTestCase
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from django.test.utils import override_settings

from opencontractserver.benchmarks.adapters.base import BenchmarkTask
from opencontractserver.benchmarks.adapters.legalbench_rag import (
    LEGALBENCH_RAG_SUBSETS,
    LegalBenchRAGAdapter,
)
from opencontractserver.benchmarks.loader import load_benchmark_into_corpus
from opencontractserver.benchmarks.metrics import (
    char_iou,
    exact_match,
    normalize_answer,
    precision_at_k,
    recall_at_k,
    token_f1,
)
from opencontractserver.benchmarks.runner import run_benchmark
from opencontractserver.documents.models import Document
from opencontractserver.extracts.models import Datacell
from opencontractserver.llms.api import AgentAPI

User = get_user_model()

MICRO_FIXTURE = (
    Path(__file__).resolve().parent.parent.parent
    / "fixtures"
    / "benchmarks"
    / "legalbench_rag_micro"
)


# --------------------------------------------------------------------------- #
# Pure-unit metric tests (no Django)
# --------------------------------------------------------------------------- #


class MetricsTestCase(PyUnitTestCase):
    """SQuAD + span metric sanity checks."""

    def test_normalize_answer_strips_articles_and_punctuation(self):
        self.assertEqual(normalize_answer("The Quick, Brown Fox!"), "quick brown fox")
        self.assertEqual(normalize_answer(None), "")

    def test_exact_match_is_normalization_aware(self):
        self.assertEqual(exact_match("The answer.", "answer"), 1.0)
        self.assertEqual(exact_match("different", "answer"), 0.0)

    def test_token_f1_perfect_and_zero(self):
        self.assertEqual(token_f1("hello world", "hello world"), 1.0)
        self.assertEqual(token_f1("hello world", "goodbye mars"), 0.0)

    def test_token_f1_partial_overlap(self):
        # Prediction = 3 tokens, gold = 3 tokens, 2 overlap
        # precision = 2/3, recall = 2/3, F1 = 2/3
        score = token_f1("hello brave world", "hello brave mars")
        self.assertAlmostEqual(score, 2 / 3, places=4)

    def test_token_f1_symmetric_empty(self):
        self.assertEqual(token_f1("", ""), 1.0)
        self.assertEqual(token_f1("", "something"), 0.0)

    def test_recall_at_k_and_precision_at_k(self):
        predicted = [(0, 10), (50, 60), (100, 110)]
        gold = [(5, 15), (200, 220)]
        # Top-2 predicted contains (0,10) which overlaps (5,15), and (50,60)
        # which overlaps nothing.  One of two gold is covered → recall 0.5.
        self.assertAlmostEqual(recall_at_k(predicted, gold, k=2), 0.5)
        # One of two top-2 predicted hits gold → precision 0.5.
        self.assertAlmostEqual(precision_at_k(predicted, gold, k=2), 0.5)

    def test_recall_at_k_zero_when_no_gold(self):
        self.assertEqual(recall_at_k([(0, 10)], [], k=5), 0.0)

    def test_char_iou(self):
        # Predicted union = {0..9}, gold union = {5..14}, intersection = {5..9}
        # |intersection| / |union| = 5 / 15
        self.assertAlmostEqual(char_iou([(0, 10)], [(5, 15)]), 5 / 15, places=4)
        self.assertEqual(char_iou([], []), 0.0)


# --------------------------------------------------------------------------- #
# Adapter unit tests
# --------------------------------------------------------------------------- #


class LegalBenchRAGAdapterTestCase(PyUnitTestCase):
    """Verify the adapter reads the micro fixture into the expected shape."""

    def test_adapter_yields_expected_documents_and_tasks(self):
        adapter = LegalBenchRAGAdapter(root=MICRO_FIXTURE)

        documents = list(adapter.iter_documents())
        tasks = list(adapter.iter_tasks())

        self.assertEqual(len(documents), 2)
        doc_keys = {doc.document_key for doc in documents}
        self.assertEqual(doc_keys, {"micro/contract.txt", "micro/privacy.txt"})

        self.assertEqual(len(tasks), 4)
        task_ids = [t.task_id for t in tasks]
        # Every task_id is prefixed with the subset stem.
        self.assertTrue(all(tid.startswith("micro::") for tid in task_ids))

        # One of the tasks should carry the termination-clause gold span.
        termination = next(t for t in tasks if "terminat" in t.query.lower())
        self.assertEqual(termination.document_keys, ("micro/contract.txt",))
        spans = termination.gold_spans["micro/contract.txt"]
        self.assertEqual(len(spans), 1)
        start, end = spans[0]
        self.assertGreater(end, start)
        # The slice must look like an actual termination clause.
        document = next(d for d in documents if d.document_key == "micro/contract.txt")
        self.assertIn("terminat", document.text[start:end].lower())
        # The adapter pre-computes the gold answer string.
        self.assertEqual(termination.gold_answer, document.text[start:end])

    def test_adapter_subset_filter_rejects_unknown(self):
        with self.assertRaises(ValueError):
            LegalBenchRAGAdapter(root=MICRO_FIXTURE, subsets=["does_not_exist"])

    def test_adapter_limit_caps_task_count(self):
        adapter = LegalBenchRAGAdapter(root=MICRO_FIXTURE, limit=2)
        self.assertEqual(len(list(adapter.iter_tasks())), 2)

    def test_known_subsets_are_the_official_four(self):
        self.assertEqual(
            set(LEGALBENCH_RAG_SUBSETS),
            {"contractnli", "cuad", "maud", "privacy_qa"},
        )


# --------------------------------------------------------------------------- #
# Integration test: loader + runner with mocked LLM
# --------------------------------------------------------------------------- #


def _make_fake_get_structured_response(answers_by_query: dict[str, str]):
    """Return a pair of async fakes mimicking the two extract API methods.

    Returns ``(fake_result_only, fake_result_and_sources)`` matching
    ``AgentAPI.get_structured_response_from_document`` and
    ``AgentAPI.get_structured_response_and_sources_from_document``
    respectively.  The sources variant returns an empty citation list so
    tests don't need real Annotation rows to pass.
    """

    # Accept arbitrary kwargs so these fakes don't break when new parameters
    # (e.g. ``embedder=``) are added to the real extract-API signatures — the
    # test only cares about mapping ``prompt`` to a canned answer.
    async def _fake_result_only(*, prompt, **kwargs):
        return answers_by_query.get(prompt, "")

    async def _fake_result_and_sources(*, prompt, **kwargs):
        return answers_by_query.get(prompt, ""), []

    return _fake_result_only, _fake_result_and_sources


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class BenchmarkRunnerIntegrationTestCase(TransactionTestCase):
    """End-to-end: fixture → loader → mocked extraction → evaluator → report."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="benchmark_user", password="testpass"
        )
        self.adapter = LegalBenchRAGAdapter(root=MICRO_FIXTURE)
        # Build a prompt -> canned answer map from the adapter so the
        # mocked agent "knows" the gold answer and we can sanity-check F1.
        self._canned_by_prompt = {
            task.query: task.gold_answer for task in self.adapter.iter_tasks()
        }

    def test_loader_materializes_corpus_fieldset_extract_and_datacells(self):
        loaded = load_benchmark_into_corpus(
            self.adapter, user=self.user, use_eager_ingestion=True
        )

        self.assertEqual(len(loaded.documents_by_key), 2)
        self.assertEqual(len(loaded.columns_by_task_id), 4)
        self.assertEqual(len(loaded.datacells), 4)
        # Every datacell has associated gold data ready for evaluation.
        for cell in loaded.datacells:
            self.assertIn(cell.id, loaded.gold_by_datacell_id)

        # Documents should exist in the database.
        for document in loaded.documents_by_key.values():
            document.refresh_from_db()
            self.assertTrue(Document.objects.filter(pk=document.pk).exists())

    def test_run_benchmark_produces_report_with_perfect_answer_metrics(self):
        fake_result_only, fake_with_sources = _make_fake_get_structured_response(
            self._canned_by_prompt
        )

        # Patch both APIs so this test is resilient to whichever entry point
        # the extract task uses.
        with patch.object(
            AgentAPI,
            "get_structured_response_from_document",
            staticmethod(fake_result_only),
        ), patch.object(
            AgentAPI,
            "get_structured_response_and_sources_from_document",
            staticmethod(fake_with_sources),
        ):
            report = run_benchmark(
                self.adapter,
                user=self.user,
                model="test:fake",
                top_k=5,
                write_report=False,
            )

        self.assertEqual(int(report.aggregates["task_count"]), 4)
        self.assertEqual(
            int(report.aggregates["extraction_success_count"]),
            4,
            "All four mocked extractions should have succeeded",
        )
        # Because the fake agent returns gold_answer, exact match and F1
        # should both be 1.0 on every task.
        self.assertAlmostEqual(report.aggregates["answer_exact_match"], 1.0, places=4)
        self.assertAlmostEqual(report.aggregates["answer_token_f1"], 1.0, places=4)
        # Retrieval recall is harder to assert deterministically because
        # the vector store depends on embeddings and sentence segmentation,
        # but it must be in [0, 1].
        self.assertGreaterEqual(report.aggregates["probe_recall_at_k"], 0.0)
        self.assertLessEqual(report.aggregates["probe_recall_at_k"], 1.0)

        # Every task result should have a populated prediction and the
        # datacell should have ``completed`` set.
        for result in report.task_results:
            cell = Datacell.objects.get(pk=result.datacell_id)
            self.assertIsNotNone(cell.completed)
            self.assertTrue(result.extraction_ok)
            self.assertEqual(result.prediction, result.gold_answer)

    def test_run_benchmark_writes_report_files_when_requested(self):
        fake_result_only, fake_with_sources = _make_fake_get_structured_response(
            self._canned_by_prompt
        )
        run_dir = Path(self._make_tmp_run_dir())

        with patch.object(
            AgentAPI,
            "get_structured_response_from_document",
            staticmethod(fake_result_only),
        ), patch.object(
            AgentAPI,
            "get_structured_response_and_sources_from_document",
            staticmethod(fake_with_sources),
        ):
            run_benchmark(
                self.adapter,
                user=self.user,
                model="test:fake",
                top_k=5,
                run_dir=run_dir,
                write_report=True,
            )

        self.assertTrue((run_dir / "report.json").exists())
        self.assertTrue((run_dir / "report.csv").exists())
        self.assertTrue((run_dir / "config.json").exists())
        self.assertTrue((run_dir / "gold.json").exists())

        report_data = json.loads((run_dir / "report.json").read_text())
        self.assertIn("aggregates", report_data)
        self.assertIn("task_results", report_data)
        self.assertEqual(len(report_data["task_results"]), 4)

    def _make_tmp_run_dir(self) -> str:
        import tempfile

        tmp = tempfile.mkdtemp(prefix="benchmark_run_")
        self.addCleanup(self._rmtree, tmp)
        return tmp

    @staticmethod
    def _rmtree(path: str) -> None:
        import shutil

        shutil.rmtree(path, ignore_errors=True)


class BenchmarkTaskDataclassTestCase(PyUnitTestCase):
    """Guard against accidental changes to the public BenchmarkTask shape."""

    def test_benchmark_task_is_frozen(self):
        task = BenchmarkTask(
            task_id="t1",
            query="q",
            document_keys=("d1",),
            gold_spans={"d1": ((0, 3),)},
            gold_answer="abc",
        )
        with self.assertRaises(Exception):
            task.query = "changed"  # type: ignore[misc]
