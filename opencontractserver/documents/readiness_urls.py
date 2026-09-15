from django.urls import path

from opencontractserver.documents.readiness_views import (
    CorpusReadinessView,
    DocumentReadinessView,
    WorkerCorpusReadinessView,
    WorkerReadinessView,
)

urlpatterns = [
    path("documents/<int:document_id>/", DocumentReadinessView.as_view()),
    path("corpuses/<int:corpus_id>/", CorpusReadinessView.as_view()),
    path("worker/", WorkerCorpusReadinessView.as_view()),
    path("worker/<uuid:upload_id>/", WorkerReadinessView.as_view()),
]
