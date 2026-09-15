from django.urls import path

from opencontractserver.worker_uploads.run_views import (
    IngestionRunCreateView,
    IngestionRunView,
)
from opencontractserver.worker_uploads.views import (
    WorkerAuthoritySectionBatchListView,
    WorkerAuthoritySectionBatchStatusView,
    WorkerAuthoritySectionBatchView,
    WorkerDocumentUploadListView,
    WorkerDocumentUploadLookupView,
    WorkerDocumentUploadRetryView,
    WorkerDocumentUploadStatusView,
    WorkerDocumentUploadView,
)

app_name = "worker_uploads"

# IMPORTANT: "documents/list/" must precede "documents/<uuid:upload_id>/"
# because Django resolves URLs top-down and would otherwise try to parse
# the literal string "list" as a UUID.
urlpatterns = [
    path("runs/", IngestionRunCreateView.as_view(), name="run-create"),
    path("runs/<uuid:run_id>/", IngestionRunView.as_view(), name="run-detail"),
    path(
        "documents/by-key/<str:client_key>/",
        WorkerDocumentUploadLookupView.as_view(),
        name="lookup",
    ),
    path(
        "documents/<uuid:upload_id>/retry/",
        WorkerDocumentUploadRetryView.as_view(),
        name="retry",
    ),
    path(
        "documents/",
        WorkerDocumentUploadView.as_view(),
        name="upload",
    ),
    path(
        "documents/list/",
        WorkerDocumentUploadListView.as_view(),
        name="list",
    ),
    path(
        "documents/<uuid:upload_id>/",
        WorkerDocumentUploadStatusView.as_view(),
        name="status",
    ),
    # Same ordering rule: "authority-sections/list/" must precede the
    # "<uuid:batch_id>/" pattern.
    path(
        "authority-sections/",
        WorkerAuthoritySectionBatchView.as_view(),
        name="section-upload",
    ),
    path(
        "authority-sections/list/",
        WorkerAuthoritySectionBatchListView.as_view(),
        name="section-list",
    ),
    path(
        "authority-sections/<uuid:batch_id>/",
        WorkerAuthoritySectionBatchStatusView.as_view(),
        name="section-status",
    ),
]
