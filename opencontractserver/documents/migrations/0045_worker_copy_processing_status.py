"""Reconcile copies from worker transactions completed before readiness existed."""

from django.db import migrations


def reconcile_completed_uploads(apps, schema_editor):
    Upload = apps.get_model("worker_uploads", "WorkerDocumentUpload")
    Document = apps.get_model("documents", "Document")
    uploads = Upload.objects.filter(
        status="COMPLETED",
        result_document__processing_status="pending",
        result_document__backend_lock=False,
        result_document__source_document__processing_status="completed",
    ).values_list(
        "result_document_id",
        "processing_finished",
        "result_document__source_document__processing_started",
        "result_document__source_document__processing_finished",
    )
    for document_id, receipt_finished, started, finished in uploads.iterator(
        chunk_size=1000
    ):
        Document.objects.filter(
            pk=document_id, processing_status="pending", backend_lock=False
        ).update(
            processing_status="completed",
            processing_started=started,
            processing_finished=finished or receipt_finished,
            processing_error="",
        )


class Migration(migrations.Migration):
    dependencies = [("documents", "0044_embeddingrepair")]
    operations = [
        migrations.RunPython(reconcile_completed_uploads, migrations.RunPython.noop)
    ]
