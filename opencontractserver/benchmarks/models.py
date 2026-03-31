import logging

import django
from django.conf import settings
from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


class BenchmarkStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    IMPORTING = "importing", "Importing"
    EMBEDDING = "embedding", "Embedding"
    READY = "ready", "Ready"
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class BenchmarkCorpus(models.Model):
    """Tracks a benchmark dataset imported into OpenContracts.

    Links a HuggingFace dataset to an OpenContracts corpus and stores
    benchmark-specific metadata like the dataset source and question count.
    """

    name = models.CharField(
        max_length=256,
        help_text="Human-readable benchmark name (e.g., 'Legal RAG Bench')",
    )
    dataset_source = models.CharField(
        max_length=512,
        help_text="HuggingFace dataset identifier (e.g., 'isaacus/legal-rag-bench')",
    )
    corpus = models.ForeignKey(
        "corpuses.Corpus",
        on_delete=models.CASCADE,
        related_name="benchmarks",
        help_text="The OpenContracts corpus containing the benchmark documents",
    )
    status = models.CharField(
        max_length=20,
        choices=BenchmarkStatus.choices,
        default=BenchmarkStatus.PENDING,
        db_index=True,
    )
    error_message = models.TextField(blank=True, default="")
    passage_count = models.IntegerField(
        default=0, help_text="Number of passages imported"
    )
    question_count = models.IntegerField(
        default=0, help_text="Number of Q&A pairs imported"
    )
    # Maps benchmark passage IDs to OpenContracts annotation IDs
    # Format: {"passage_id": annotation_pk, ...}
    passage_id_map = models.JSONField(
        default=dict,
        blank=True,
        help_text="Maps benchmark passage IDs to annotation PKs",
    )
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=False,
    )
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "benchmark corpuses"
        constraints = [
            models.UniqueConstraint(
                fields=["dataset_source", "creator"],
                name="unique_benchmark_per_source_per_user",
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.status})"


class BenchmarkQuestion(models.Model):
    """A single question-answer pair from a benchmark dataset.

    Links to the benchmark corpus and references the expected relevant
    passage by its benchmark-level ID (resolved to annotation PKs via
    BenchmarkCorpus.passage_id_map at evaluation time).
    """

    benchmark = models.ForeignKey(
        BenchmarkCorpus,
        on_delete=models.CASCADE,
        related_name="questions",
    )
    external_id = models.CharField(
        max_length=64,
        help_text="Original question ID from the benchmark dataset",
    )
    question = models.TextField()
    expected_answer = models.TextField()
    relevant_passage_id = models.CharField(
        max_length=128,
        help_text="Benchmark passage ID that should be retrieved",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["benchmark", "external_id"],
                name="unique_question_per_benchmark",
            )
        ]

    def __str__(self):
        return f"Q{self.external_id}: {self.question[:80]}"


class BenchmarkRun(models.Model):
    """A single evaluation run of a benchmark.

    Captures the configuration (embedder, LLM, k value) and aggregate
    results for one pass through all questions in a benchmark.
    """

    benchmark = models.ForeignKey(
        BenchmarkCorpus,
        on_delete=models.CASCADE,
        related_name="runs",
    )
    embedder_path = models.CharField(
        max_length=1024,
        help_text="Embedder used for retrieval",
    )
    llm_model = models.CharField(
        max_length=256,
        blank=True,
        default="",
        help_text="LLM used for answer generation (empty = retrieval-only eval)",
    )
    top_k = models.IntegerField(
        default=5,
        help_text="Number of passages retrieved per query",
    )
    status = models.CharField(
        max_length=20,
        choices=BenchmarkStatus.choices,
        default=BenchmarkStatus.PENDING,
    )
    error_message = models.TextField(blank=True, default="")

    # Aggregate metrics
    retrieval_recall_at_k = models.FloatField(
        null=True,
        blank=True,
        help_text="Fraction of questions where the relevant passage was in top-k",
    )
    retrieval_mrr = models.FloatField(
        null=True,
        blank=True,
        help_text="Mean Reciprocal Rank of the relevant passage",
    )
    answer_correctness = models.FloatField(
        null=True,
        blank=True,
        help_text="Fraction of answers judged correct (if LLM eval enabled)",
    )
    answer_groundedness = models.FloatField(
        null=True,
        blank=True,
        help_text="Fraction of answers judged grounded in retrieved context",
    )
    results_file = models.TextField(
        blank=True,
        default="",
        help_text="Path to detailed JSONL results file",
    )
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=False,
    )
    started = models.DateTimeField(null=True, blank=True)
    finished = models.DateTimeField(null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Run {self.pk} ({self.status}) - Recall@{self.top_k}: {self.retrieval_recall_at_k}"


class BenchmarkQuestionResult(models.Model):
    """Result for a single question within a benchmark run."""

    run = models.ForeignKey(
        BenchmarkRun,
        on_delete=models.CASCADE,
        related_name="question_results",
    )
    question = models.ForeignKey(
        BenchmarkQuestion,
        on_delete=models.CASCADE,
        related_name="results",
    )
    # Retrieval metrics
    relevant_passage_retrieved = models.BooleanField(
        default=False,
        help_text="Whether the expected passage was in the top-k results",
    )
    relevant_passage_rank = models.IntegerField(
        null=True,
        blank=True,
        help_text="Rank position of the expected passage (1-indexed, null if not found)",
    )
    retrieved_passage_ids = models.JSONField(
        default=list,
        blank=True,
        help_text="Ordered list of retrieved benchmark passage IDs",
    )
    similarity_scores = models.JSONField(
        default=list,
        blank=True,
        help_text="Similarity scores for each retrieved passage",
    )

    # Generation metrics (populated when LLM eval is enabled)
    generated_answer = models.TextField(
        blank=True,
        default="",
    )
    judge_correct = models.BooleanField(
        null=True,
        blank=True,
        help_text="Whether the judge LLM deemed the answer correct",
    )
    judge_grounded = models.BooleanField(
        null=True,
        blank=True,
        help_text="Whether the judge LLM deemed the answer grounded in context",
    )
    judge_reasoning = models.TextField(
        blank=True,
        default="",
    )

    # Timing
    retrieval_time_ms = models.IntegerField(
        null=True, blank=True, help_text="Time taken for retrieval in milliseconds"
    )
    generation_time_ms = models.IntegerField(
        null=True, blank=True, help_text="Time taken for LLM generation in milliseconds"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["run", "question"],
                name="unique_result_per_run_per_question",
            )
        ]

    def __str__(self):
        return f"Q{self.question.external_id} - Retrieved: {self.relevant_passage_retrieved}"
