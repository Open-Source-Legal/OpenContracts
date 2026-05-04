from django.urls import path

from opencontractserver.document_imports.views import (
    DocumentImportView,
    DocumentsZipImportView,
)

app_name = "document_imports"

urlpatterns = [
    path(
        "documents/",
        DocumentImportView.as_view(),
        name="import_document",
    ),
    path(
        "documents-zip/",
        DocumentsZipImportView.as_view(),
        name="import_documents_zip",
    ),
]
