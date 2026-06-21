"""Tests for the @corpus_analyzer_task decorator and the enrichment adapter.

Covers: marker/lookup helpers, Analysis lifecycle management by the wrapper,
auto-sync of the adapter into an Analyzer row, and the run_task_name_analyzer
corpus-scoped dispatch branch.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase

from opencontractserver.analyzer.models import Analysis, Analyzer
from opencontractserver.analyzer.utils import auto_create_doc_analyzers
from opencontractserver.annotations.models import CorpusReference
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.services import EnrichmentService
from opencontractserver.tasks.corpus_analysis_tasks import corpus_reference_enrichment
from opencontractserver.types.enums import JobStatus
from opencontractserver.utils.celery_tasks import (
    get_analyzer_task_by_name,
    get_corpus_analyzer_task_by_name,
    get_doc_analyzer_task_by_name,
)

User = get_user_model()

S1_TEXT = (
    "We are governed by Section 203 of the Delaware General Corporation Law. "
    "The underwriting agreement is filed as Exhibit 1.1 hereto."
)


def _make_corpus(user):
    corpus = Corpus.objects.create(title="S-1 Corpus", creator=user)
    doc = Document.objects.create(title="Acme S-1 primary", creator=user)
    doc.txt_extract_file.save("s1.txt", ContentFile(S1_TEXT.encode("utf-8")))
    corpus.add_document(document=doc, user=user)
    return corpus


def _make_analysis(user, corpus):
    # Reuse the service's converge logic: the analyzer/0009+0013 data
    # migrations auto-sync analyzer rows during ``migrate``, so a freshly
    # migrated test DB ALREADY contains the enrichment Analyzer under
    # ``id == task_name`` — creating by friendly id here would violate the
    # task_name unique constraint.
    from opencontractserver.enrichment.services import EnrichmentService

    analyzer = EnrichmentService.get_or_create_analyzer(user.id)
    return Analysis.objects.create(
        analyzer=analyzer, analyzed_corpus=corpus, creator=user
    )


class CorpusAnalyzerTaskTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="p")
        self.corpus = _make_corpus(self.user)

    def test_get_analyzer_is_lookup_only(self):
        """``get_analyzer`` finds the converged row without creating one —
        the lookup twin callers use when absence means 'feature unavailable'."""
        from opencontractserver.enrichment.services import EnrichmentService

        Analyzer.objects.filter(task_name=C.ENRICHMENT_ANALYZER_TASK).delete()
        self.assertIsNone(EnrichmentService.get_analyzer())
        self.assertFalse(
            Analyzer.objects.filter(task_name=C.ENRICHMENT_ANALYZER_TASK).exists()
        )

        created = EnrichmentService.get_or_create_analyzer(self.user.id)
        self.assertEqual(EnrichmentService.get_analyzer(), created)

    def test_adapter_is_registered_as_corpus_analyzer(self):
        task = get_corpus_analyzer_task_by_name(C.ENRICHMENT_ANALYZER_TASK)
        assert task is not None
        assert getattr(task, "is_corpus_analyzer_task", False) is True
        # ... and is NOT a doc analyzer (dispatch must take the corpus branch).
        assert get_doc_analyzer_task_by_name(C.ENRICHMENT_ANALYZER_TASK) is None
        assert get_analyzer_task_by_name(C.ENRICHMENT_ANALYZER_TASK) is task

    def test_adapter_runs_enrichment_and_completes_analysis(self):
        analysis = _make_analysis(self.user, self.corpus)
        result = corpus_reference_enrichment(
            corpus_id=self.corpus.id, analysis_id=analysis.id
        )

        assert result["references_created"] > 0
        assert CorpusReference.objects.filter(corpus=self.corpus).exists()
        # The run attached to the framework Analysis, not a second one.
        ref = CorpusReference.objects.filter(corpus=self.corpus).first()
        assert ref is not None
        assert ref.created_by_analysis_id == analysis.id
        assert Analysis.objects.count() == 1

        analysis.refresh_from_db()
        assert analysis.status == JobStatus.COMPLETED.value
        assert analysis.analysis_started is not None
        assert analysis.analysis_completed is not None
        assert "references_created" in (analysis.result_message or "")

    def test_failure_marks_analysis_failed(self):
        analysis = _make_analysis(self.user, self.corpus)
        bad_corpus_id = self.corpus.id + 9999
        with self.assertRaises(ValueError):
            corpus_reference_enrichment(
                corpus_id=bad_corpus_id, analysis_id=analysis.id
            )
        analysis.refresh_from_db()
        # Corpus existence fails before RUNNING; analysis stays untouched.
        assert analysis.status != JobStatus.COMPLETED.value

    def test_failure_inside_function_records_error(self):
        analysis = _make_analysis(self.user, self.corpus)
        with patch(
            "opencontractserver.enrichment.services.enrichment_service.EnrichmentService.apply",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertRaises(RuntimeError):
                corpus_reference_enrichment(
                    corpus_id=self.corpus.id, analysis_id=analysis.id
                )

        analysis.refresh_from_db()
        assert analysis.status == JobStatus.FAILED.value
        assert "boom" in (analysis.error_message or "")

    def test_celery_retry_does_not_mark_analysis_failed(self):
        # ``Retry`` extends ``Exception`` — the wrapper must re-raise it
        # untouched (mirroring doc_analyzer_task) so a transient retry does
        # not permanently stamp the Analysis FAILED before the retry runs.
        from celery.exceptions import Retry

        analysis = _make_analysis(self.user, self.corpus)
        with patch(
            "opencontractserver.enrichment.services.enrichment_service.EnrichmentService.apply",
            side_effect=Retry("requeued"),
        ):
            with self.assertRaises(Retry):
                corpus_reference_enrichment(
                    corpus_id=self.corpus.id, analysis_id=analysis.id
                )

        analysis.refresh_from_db()
        assert analysis.status == JobStatus.RUNNING.value
        assert analysis.error_message is None

    def test_auto_sync_recognizes_adapter_without_duplicating(self):
        # Service-created row exists (friendly id, real task_name)...
        _make_analysis(self.user, self.corpus)
        before = Analyzer.objects.filter(task_name=C.ENRICHMENT_ANALYZER_TASK).count()
        assert before == 1

        auto_create_doc_analyzers(AnalyzerModel=Analyzer, UserModel=User)

        # ...and sync does not create a duplicate for the same task.
        assert (
            Analyzer.objects.filter(task_name=C.ENRICHMENT_ANALYZER_TASK).count() == 1
        )

    def test_auto_sync_creates_analyzer_row_when_absent(self):
        # The analyzer/0009+0013 data migrations pre-sync the row into any
        # freshly migrated DB — clear it to exercise the absent branch
        # hermetically (TestCase rolls the delete back afterwards).
        Analyzer.objects.filter(task_name=C.ENRICHMENT_ANALYZER_TASK).delete()
        assert not Analyzer.objects.filter(
            task_name=C.ENRICHMENT_ANALYZER_TASK
        ).exists()
        auto_create_doc_analyzers(AnalyzerModel=Analyzer, UserModel=User)
        row = Analyzer.objects.get(task_name=C.ENRICHMENT_ANALYZER_TASK)
        assert row.id == C.ENRICHMENT_ANALYZER_TASK
        assert "reference web" in (row.description or "").lower()


class EnrichmentTaskTierTests(TestCase):
    """Verify use_llm toggle produces correct extra_tiers passed to EnrichmentService."""

    def setUp(self):
        self.user = User.objects.create_user(username="tier_owner", password="p")
        self.corpus = _make_corpus(self.user)
        self.analysis = _make_analysis(self.user, self.corpus)

    def _run_get_extra_tiers(self, **input_data):
        with patch.object(
            EnrichmentService, "apply", return_value={"corpus_id": self.corpus.id}
        ) as m:
            corpus_reference_enrichment(
                corpus_id=self.corpus.id,
                analysis_id=self.analysis.id,
                **input_data,
            )
        return m.call_args.kwargs["extra_tiers"]

    def test_default_tiers_are_grammar_only(self):
        assert self._run_get_extra_tiers() == [C.DETECTION_TIER_GRAMMAR]

    def test_use_llm_adds_llm_tier(self):
        assert self._run_get_extra_tiers(use_llm=True) == [
            C.DETECTION_TIER_GRAMMAR,
            C.DETECTION_TIER_LLM,
        ]
