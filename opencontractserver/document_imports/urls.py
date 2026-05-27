from django.urls import path

from opencontractserver.document_imports.views import (
    CorpusExportImportView,
    DocumentImportView,
    DocumentsZipImportView,
    ZipToCorpusImportView,
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
    path(
        "zip-to-corpus/",
        ZipToCorpusImportView.as_view(),
        name="import_zip_to_corpus",
    ),
    path(
        "corpus/",
        CorpusExportImportView.as_view(),
        name="import_corpus_export",
    ),
]
