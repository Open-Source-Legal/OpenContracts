import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("corpuses", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="BenchmarkCorpus",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        help_text="Human-readable benchmark name (e.g., 'Legal RAG Bench')",
                        max_length=256,
                    ),
                ),
                (
                    "dataset_source",
                    models.CharField(
                        help_text="HuggingFace dataset identifier (e.g., 'isaacus/legal-rag-bench')",
                        max_length=512,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("importing", "Importing"),
                            ("embedding", "Embedding"),
                            ("ready", "Ready"),
                            ("running", "Running"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("error_message", models.TextField(blank=True, default="")),
                (
                    "passage_count",
                    models.IntegerField(
                        default=0, help_text="Number of passages imported"
                    ),
                ),
                (
                    "question_count",
                    models.IntegerField(
                        default=0, help_text="Number of Q&A pairs imported"
                    ),
                ),
                (
                    "passage_id_map",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Maps benchmark passage IDs to annotation PKs",
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("modified", models.DateTimeField(auto_now=True)),
                (
                    "corpus",
                    models.ForeignKey(
                        help_text="The OpenContracts corpus containing the benchmark documents",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="benchmarks",
                        to="corpuses.corpus",
                    ),
                ),
                (
                    "creator",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name_plural": "benchmark corpuses",
            },
        ),
        migrations.CreateModel(
            name="BenchmarkQuestion",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "external_id",
                    models.CharField(
                        help_text="Original question ID from the benchmark dataset",
                        max_length=64,
                    ),
                ),
                ("question", models.TextField()),
                ("expected_answer", models.TextField()),
                (
                    "relevant_passage_id",
                    models.CharField(
                        help_text="Benchmark passage ID that should be retrieved",
                        max_length=128,
                    ),
                ),
                (
                    "benchmark",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="questions",
                        to="benchmarks.benchmarkcorpus",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="BenchmarkRun",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "embedder_path",
                    models.CharField(
                        help_text="Embedder used for retrieval", max_length=1024
                    ),
                ),
                (
                    "llm_model",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="LLM used for answer generation (empty = retrieval-only eval)",
                        max_length=256,
                    ),
                ),
                (
                    "top_k",
                    models.IntegerField(
                        default=5,
                        help_text="Number of passages retrieved per query",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("importing", "Importing"),
                            ("embedding", "Embedding"),
                            ("ready", "Ready"),
                            ("running", "Running"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("error_message", models.TextField(blank=True, default="")),
                (
                    "retrieval_recall_at_k",
                    models.FloatField(
                        blank=True,
                        help_text="Fraction of questions where the relevant passage was in top-k",
                        null=True,
                    ),
                ),
                (
                    "retrieval_mrr",
                    models.FloatField(
                        blank=True,
                        help_text="Mean Reciprocal Rank of the relevant passage",
                        null=True,
                    ),
                ),
                (
                    "answer_correctness",
                    models.FloatField(
                        blank=True,
                        help_text="Fraction of answers judged correct (if LLM eval enabled)",
                        null=True,
                    ),
                ),
                (
                    "answer_groundedness",
                    models.FloatField(
                        blank=True,
                        help_text="Fraction of answers judged grounded in retrieved context",
                        null=True,
                    ),
                ),
                (
                    "results_file",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Path to detailed JSONL results file",
                    ),
                ),
                ("started", models.DateTimeField(blank=True, null=True)),
                ("finished", models.DateTimeField(blank=True, null=True)),
                ("created", models.DateTimeField(auto_now_add=True)),
                (
                    "benchmark",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="runs",
                        to="benchmarks.benchmarkcorpus",
                    ),
                ),
                (
                    "creator",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="BenchmarkQuestionResult",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "relevant_passage_retrieved",
                    models.BooleanField(
                        default=False,
                        help_text="Whether the expected passage was in the top-k results",
                    ),
                ),
                (
                    "relevant_passage_rank",
                    models.IntegerField(
                        blank=True,
                        help_text="Rank position of the expected passage (1-indexed, null if not found)",
                        null=True,
                    ),
                ),
                (
                    "retrieved_passage_ids",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text="Ordered list of retrieved benchmark passage IDs",
                    ),
                ),
                (
                    "similarity_scores",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text="Similarity scores for each retrieved passage",
                    ),
                ),
                ("generated_answer", models.TextField(blank=True, default="")),
                (
                    "judge_correct",
                    models.BooleanField(
                        blank=True,
                        help_text="Whether the judge LLM deemed the answer correct",
                        null=True,
                    ),
                ),
                (
                    "judge_grounded",
                    models.BooleanField(
                        blank=True,
                        help_text="Whether the judge LLM deemed the answer grounded in context",
                        null=True,
                    ),
                ),
                ("judge_reasoning", models.TextField(blank=True, default="")),
                (
                    "retrieval_time_ms",
                    models.IntegerField(
                        blank=True,
                        help_text="Time taken for retrieval in milliseconds",
                        null=True,
                    ),
                ),
                (
                    "generation_time_ms",
                    models.IntegerField(
                        blank=True,
                        help_text="Time taken for LLM generation in milliseconds",
                        null=True,
                    ),
                ),
                (
                    "question",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="results",
                        to="benchmarks.benchmarkquestion",
                    ),
                ),
                (
                    "run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="question_results",
                        to="benchmarks.benchmarkrun",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="benchmarkcorpus",
            constraint=models.UniqueConstraint(
                fields=("dataset_source", "creator"),
                name="unique_benchmark_per_source_per_user",
            ),
        ),
        migrations.AddConstraint(
            model_name="benchmarkquestion",
            constraint=models.UniqueConstraint(
                fields=("benchmark", "external_id"),
                name="unique_question_per_benchmark",
            ),
        ),
        migrations.AddConstraint(
            model_name="benchmarkquestionresult",
            constraint=models.UniqueConstraint(
                fields=("run", "question"),
                name="unique_result_per_run_per_question",
            ),
        ),
    ]
