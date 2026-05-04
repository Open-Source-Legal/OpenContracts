from django.urls import path

from opencontractserver.document_uploads.views import (
    DocumentsZipUploadView,
    DocumentUploadView,
)

app_name = "document_uploads"

urlpatterns = [
    path(
        "documents/",
        DocumentUploadView.as_view(),
        name="upload_document",
    ),
    path(
        "documents-zip/",
        DocumentsZipUploadView.as_view(),
        name="upload_documents_zip",
    ),
]
