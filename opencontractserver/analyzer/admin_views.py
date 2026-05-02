from typing import Any

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View

from opencontractserver.analyzer.models import Analyzer
from opencontractserver.analyzer.utils import auto_create_doc_analyzers
from opencontractserver.utils.celery_tasks import (
    celery_app,
    get_doc_analyzer_task_by_name,
)


@method_decorator(staff_member_required, name="dispatch")
class AnalyzerSyncView(View):
    """Custom admin view for syncing doc analyzer tasks"""

    template_name: str = "admin/analyzer/analyzer_sync.html"

    def get_available_analyzers(self) -> list[dict[str, Any]]:
        """Get info about all available doc analyzer tasks"""
        analyzers: list[dict[str, Any]] = []

        for task_name in celery_app.tasks.keys():
            analyzer_task = get_doc_analyzer_task_by_name(task_name)
            if analyzer_task is None:
                continue

            analyzer_id = task_name
            exists = (
                Analyzer.objects.filter(id=analyzer_id).exists()
                or Analyzer.objects.filter(task_name=task_name).exists()
            )

            docstring = (analyzer_task.__doc__ or "").strip()[:200]
            schema = getattr(analyzer_task, "_oc_doc_analyzer_input_schema", None)

            analyzers.append(
                {
                    "task_name": task_name,
                    "exists": exists,
                    "description": docstring,
                    "has_schema": bool(schema),
                }
            )

        return sorted(analyzers, key=lambda x: (x["exists"], x["task_name"]))

    def get(self, request: HttpRequest) -> HttpResponse:
        context: dict[str, Any] = {
            "title": "Sync Doc Analyzer Tasks",
            "analyzers": self.get_available_analyzers(),
            "opts": Analyzer._meta,
            "has_view_permission": True,
            "has_change_permission": request.user.has_perm("analyzer.change_analyzer"),
            "has_add_permission": request.user.has_perm("analyzer.add_analyzer"),
        }
        return render(request, self.template_name, context)

    def post(self, request: HttpRequest) -> HttpResponse:
        if not request.user.has_perm("analyzer.add_analyzer"):
            messages.error(request, "You don't have permission to create analyzers.")
            return redirect(reverse("admin:analyzer_sync"))

        from django.contrib.auth import get_user_model

        UserModel = get_user_model()

        auto_create_doc_analyzers(AnalyzerModel=Analyzer, UserModel=UserModel)

        messages.success(request, "Successfully synchronized doc-based analyzers.")
        return redirect(reverse("admin:analyzer_analyzer_changelist"))
