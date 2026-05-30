from django.urls import path

from opencontractserver.document_imports.views import (
    ChunkedUploadCompleteView,
    ChunkedUploadPartView,
    ChunkedUploadStartView,
    ChunkedUploadStatusView,
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
    # Chunked (resumable) uploads — work around the 100 MB upstream proxy cap.
    path(
        "chunked/start/",
        ChunkedUploadStartView.as_view(),
        name="chunked_upload_start",
    ),
    path(
        "chunked/<uuid:upload_id>/parts/<int:index>/",
        ChunkedUploadPartView.as_view(),
        name="chunked_upload_part",
    ),
    path(
        "chunked/<uuid:upload_id>/complete/",
        ChunkedUploadCompleteView.as_view(),
        name="chunked_upload_complete",
    ),
    path(
        "chunked/<uuid:upload_id>/",
        ChunkedUploadStatusView.as_view(),
        name="chunked_upload_status",
    ),
]
