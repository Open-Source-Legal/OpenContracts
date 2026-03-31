from django.contrib import admin

from .models import (
    BenchmarkCorpus,
    BenchmarkQuestion,
    BenchmarkQuestionResult,
    BenchmarkRun,
)


class BenchmarkQuestionInline(admin.TabularInline):
    model = BenchmarkQuestion
    extra = 0
    readonly_fields = ("external_id", "question", "expected_answer", "relevant_passage_id")


class BenchmarkQuestionResultInline(admin.TabularInline):
    model = BenchmarkQuestionResult
    extra = 0
    readonly_fields = (
        "question",
        "relevant_passage_retrieved",
        "relevant_passage_rank",
        "judge_correct",
        "judge_grounded",
    )


@admin.register(BenchmarkCorpus)
class BenchmarkCorpusAdmin(admin.ModelAdmin):
    list_display = ("name", "dataset_source", "status", "passage_count", "question_count", "creator")
    list_filter = ("status",)
    inlines = [BenchmarkQuestionInline]


@admin.register(BenchmarkRun)
class BenchmarkRunAdmin(admin.ModelAdmin):
    list_display = (
        "benchmark",
        "embedder_path",
        "llm_model",
        "top_k",
        "status",
        "retrieval_recall_at_k",
        "retrieval_mrr",
    )
    list_filter = ("status",)
    inlines = [BenchmarkQuestionResultInline]
