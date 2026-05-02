from django.contrib import admin
from django.urls import URLPattern, path
from guardian.admin import GuardedModelAdmin

from opencontractserver.analyzer.admin_views import AnalyzerSyncView
from opencontractserver.analyzer.models import Analysis, Analyzer, GremlinEngine


@admin.register(GremlinEngine)
class GremlinEngineAdmin(GuardedModelAdmin):
    list_display = ["id", "url", "install_started", "install_completed"]


@admin.register(Analyzer)
class AnalyzerAdmin(GuardedModelAdmin):
    list_display = ["id", "description", "task_name", "host_gremlin"]
    change_list_template = "admin/analyzer/analyzer_changelist.html"

    def get_urls(self) -> list[URLPattern]:
        urls = super().get_urls()
        custom_urls = [
            path(
                "sync/",
                self.admin_site.admin_view(AnalyzerSyncView.as_view()),
                name="analyzer_sync",
            ),
        ]
        return custom_urls + urls


@admin.register(Analysis)
class AnalysisAdmin(GuardedModelAdmin):
    list_display = ["id", "analysis_started", "analysis_completed", "status"]
    search_fields = [
        "id",
        "analyzer__id",
        "analyzed_corpus__title",
        "creator__username",
    ]
    list_filter = ("status", "created", "analysis_started", "analysis_completed")
    raw_id_fields = (
        "analyzer",
        "analyzed_corpus",
        "corpus_action",
        "creator",
        "analyzed_documents",
    )
    date_hierarchy = "created"
