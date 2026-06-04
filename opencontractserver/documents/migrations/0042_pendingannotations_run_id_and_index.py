from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0041_pendingdocumentannotations"),
    ]

    operations = [
        migrations.AddField(
            model_name="pendingdocumentannotations",
            name="ingestion_run_id",
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
        migrations.AddIndex(
            model_name="pendingdocumentannotations",
            index=models.Index(
                fields=["document", "status"], name="pending_doc_status_idx"
            ),
        ),
    ]
