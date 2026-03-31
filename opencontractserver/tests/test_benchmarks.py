"""Tests for the benchmarks app models and utilities."""

import logging
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from opencontractserver.annotations.models import Annotation, AnnotationLabel
from opencontractserver.benchmarks.management.commands.setup_legal_rag_benchmark import (
    _extract_chapter_key,
    _fetch_hf_rows,
)
from opencontractserver.benchmarks.management.commands.run_legal_rag_benchmark import (
    _build_reverse_passage_map,
)
from opencontractserver.benchmarks.models import (
    BenchmarkCorpus,
    BenchmarkQuestion,
    BenchmarkQuestionResult,
    BenchmarkRun,
    BenchmarkStatus,
)
from opencontractserver.corpuses.models import Corpus

User = get_user_model()
logger = logging.getLogger(__name__)


@override_settings(
    STORAGES={
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    },
    MEDIA_ROOT="test_media/",
)
class TestBenchmarkModels(TestCase):
    """Test benchmark model creation and constraints."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="benchtest", password="testpass123"
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            creator=self.user,
        )

    def test_create_benchmark_corpus(self):
        benchmark = BenchmarkCorpus.objects.create(
            name="Test Benchmark",
            dataset_source="test/dataset",
            corpus=self.corpus,
            creator=self.user,
        )
        self.assertEqual(benchmark.status, BenchmarkStatus.PENDING)
        self.assertEqual(benchmark.passage_count, 0)
        self.assertEqual(benchmark.question_count, 0)
        self.assertEqual(str(benchmark), "Test Benchmark (pending)")

    def test_unique_benchmark_per_source_per_user(self):
        BenchmarkCorpus.objects.create(
            name="Test 1",
            dataset_source="test/dataset",
            corpus=self.corpus,
            creator=self.user,
        )
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            BenchmarkCorpus.objects.create(
                name="Test 2",
                dataset_source="test/dataset",
                corpus=self.corpus,
                creator=self.user,
            )

    def test_create_benchmark_question(self):
        benchmark = BenchmarkCorpus.objects.create(
            name="Test",
            dataset_source="test/dataset",
            corpus=self.corpus,
            creator=self.user,
        )
        question = BenchmarkQuestion.objects.create(
            benchmark=benchmark,
            external_id="1",
            question="What is the test?",
            expected_answer="This is the answer.",
            relevant_passage_id="1.1-c1-s1",
        )
        self.assertEqual(question.external_id, "1")
        self.assertIn("What is the test", str(question))

    def test_create_benchmark_run(self):
        benchmark = BenchmarkCorpus.objects.create(
            name="Test",
            dataset_source="test/dataset",
            corpus=self.corpus,
            creator=self.user,
        )
        run = BenchmarkRun.objects.create(
            benchmark=benchmark,
            embedder_path="test.embedder.Path",
            top_k=5,
            creator=self.user,
        )
        self.assertEqual(run.status, BenchmarkStatus.PENDING)
        self.assertEqual(run.top_k, 5)
        self.assertIsNone(run.retrieval_recall_at_k)

    def test_create_question_result(self):
        benchmark = BenchmarkCorpus.objects.create(
            name="Test",
            dataset_source="test/dataset",
            corpus=self.corpus,
            creator=self.user,
        )
        question = BenchmarkQuestion.objects.create(
            benchmark=benchmark,
            external_id="1",
            question="Test question?",
            expected_answer="Test answer.",
            relevant_passage_id="1.1-c1-s1",
        )
        run = BenchmarkRun.objects.create(
            benchmark=benchmark,
            embedder_path="test.Embedder",
            creator=self.user,
        )
        result = BenchmarkQuestionResult.objects.create(
            run=run,
            question=question,
            relevant_passage_retrieved=True,
            relevant_passage_rank=3,
            retrieved_passage_ids=["1.1-c1-s1", "1.2-c1-s2", "1.1-c1-s1"],
            similarity_scores=[0.95, 0.87, 0.82],
        )
        self.assertTrue(result.relevant_passage_retrieved)
        self.assertEqual(result.relevant_passage_rank, 3)

    def test_cascade_delete(self):
        """Deleting a benchmark should cascade to questions, runs, and results."""
        benchmark = BenchmarkCorpus.objects.create(
            name="Test",
            dataset_source="test/cascade",
            corpus=self.corpus,
            creator=self.user,
        )
        question = BenchmarkQuestion.objects.create(
            benchmark=benchmark,
            external_id="1",
            question="Test?",
            expected_answer="Yes.",
            relevant_passage_id="1.1",
        )
        run = BenchmarkRun.objects.create(
            benchmark=benchmark,
            embedder_path="test.Embedder",
            creator=self.user,
        )
        BenchmarkQuestionResult.objects.create(
            run=run,
            question=question,
        )

        benchmark.delete()
        self.assertEqual(BenchmarkQuestion.objects.count(), 0)
        self.assertEqual(BenchmarkRun.objects.count(), 0)
        self.assertEqual(BenchmarkQuestionResult.objects.count(), 0)


class TestUtilityFunctions(TestCase):
    """Test utility functions used by management commands."""

    def test_extract_chapter_key_standard(self):
        self.assertEqual(_extract_chapter_key("1.1-c1-s1"), "1")
        self.assertEqual(_extract_chapter_key("12.3-c2-s5"), "12")
        self.assertEqual(_extract_chapter_key("3-c1-s1"), "3")

    def test_extract_chapter_key_misc(self):
        self.assertEqual(_extract_chapter_key("appendix-a"), "misc")
        self.assertEqual(_extract_chapter_key(""), "misc")

    def test_build_reverse_passage_map(self):
        forward = {"1.1-c1-s1": 100, "1.2-c1-s2": 200, "2.1-c1-s1": 300}
        reverse = _build_reverse_passage_map(forward)
        self.assertEqual(reverse[100], "1.1-c1-s1")
        self.assertEqual(reverse[200], "1.2-c1-s2")
        self.assertEqual(reverse[300], "2.1-c1-s1")

    @patch("opencontractserver.benchmarks.management.commands.setup_legal_rag_benchmark.requests.get")
    def test_fetch_hf_rows_pagination(self, mock_get):
        """Test that _fetch_hf_rows handles pagination correctly."""
        # First page
        response1 = MagicMock()
        response1.json.return_value = {
            "rows": [{"row": {"id": "1", "text": "passage 1"}}],
            "num_rows_total": 2,
        }
        response1.raise_for_status = MagicMock()

        # Second page
        response2 = MagicMock()
        response2.json.return_value = {
            "rows": [{"row": {"id": "2", "text": "passage 2"}}],
            "num_rows_total": 2,
        }
        response2.raise_for_status = MagicMock()

        # Third call returns empty (past end)
        response3 = MagicMock()
        response3.json.return_value = {"rows": [], "num_rows_total": 2}
        response3.raise_for_status = MagicMock()

        mock_get.side_effect = [response1, response2, response3]

        rows = _fetch_hf_rows("https://example.com/rows?dataset=test&split=test")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["id"], "1")
        self.assertEqual(rows[1]["id"], "2")

    @patch("opencontractserver.benchmarks.management.commands.setup_legal_rag_benchmark.requests.get")
    def test_fetch_hf_rows_max_rows(self, mock_get):
        """Test that max_rows limits the number of rows fetched."""
        response = MagicMock()
        response.json.return_value = {
            "rows": [
                {"row": {"id": str(i), "text": f"passage {i}"}} for i in range(100)
            ],
            "num_rows_total": 5000,
        }
        response.raise_for_status = MagicMock()
        mock_get.return_value = response

        rows = _fetch_hf_rows(
            "https://example.com/rows?dataset=test&split=test", max_rows=10
        )
        self.assertEqual(len(rows), 10)
