import django.db.models
from django.conf import settings
from django.db import migrations, models

import opencontractserver.shared.defaults
import opencontractserver.shared.fields


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("corpuses", "0001_initial"),
        ("documents", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="BulkIngestionJob",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("user_lock", models.ForeignKey(
                    blank=True,
                    db_index=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="locked_%(class)s_objects",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("backend_lock", models.BooleanField(db_index=True, default=False)),
                ("is_public", models.BooleanField(default=False)),
                (
                    "creator",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("modified", models.DateTimeField(auto_now=True)),
                (
                    "corpus",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="bulk_ingestion_jobs",
                        to="corpuses.corpus",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("created", "Created"),
                            ("downloading", "Downloading"),
                            ("importing", "Importing"),
                            ("processing", "Processing"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                            ("paused", "Paused"),
                            ("cancelled", "Cancelled"),
                        ],
                        db_index=True,
                        default="created",
                        max_length=20,
                    ),
                ),
                (
                    "source_type",
                    models.CharField(
                        choices=[
                            ("url_pattern", "URL Pattern"),
                            ("storage_prefix", "Storage Prefix"),
                            ("manifest", "Manifest File"),
                            ("pre_parsed", "Pre-Parsed Bundles"),
                        ],
                        help_text="How documents are sourced (URL, storage path, manifest, pre-parsed)",
                        max_length=30,
                    ),
                ),
                (
                    "source_config",
                    opencontractserver.shared.fields.NullableJSONField(
                        blank=True,
                        default=opencontractserver.shared.defaults.jsonfield_default_value,
                        help_text=(
                            "Source-specific configuration. Examples:\n"
                            '  url_pattern: {"url_template": "https://example.com/docs/{id}.pdf", '
                            '"id_range": [1, 50000]}\n'
                            '  storage_prefix: {"backend": "s3", "bucket": "my-bucket", '
                            '"prefix": "staging/job-001/"}\n'
                            '  manifest: {"path": "s3://bucket/manifest.json"}\n'
                            '  pre_parsed: {"manifest_path": "s3://bucket/parsed/manifest.json"}'
                        ),
                    ),
                ),
                (
                    "parsing_strategy",
                    models.CharField(
                        choices=[
                            ("full", "Full Structural Parsing"),
                            ("text_only", "Text Extraction Only"),
                            ("pre_parsed", "Pre-Parsed (Skip Parsing)"),
                            ("skip", "Skip Parsing Entirely"),
                        ],
                        default="full",
                        help_text="How documents should be parsed during ingestion",
                        max_length=20,
                    ),
                ),
                (
                    "total_items",
                    models.IntegerField(
                        default=0,
                        help_text="Total number of items to process",
                    ),
                ),
                (
                    "downloaded_count",
                    models.IntegerField(
                        default=0,
                        help_text="Items successfully downloaded/staged",
                    ),
                ),
                (
                    "imported_count",
                    models.IntegerField(
                        default=0,
                        help_text="Items imported into database (Document records created)",
                    ),
                ),
                (
                    "parsed_count",
                    models.IntegerField(
                        default=0,
                        help_text="Items fully parsed (annotations created)",
                    ),
                ),
                (
                    "embedded_count",
                    models.IntegerField(
                        default=0,
                        help_text="Items with embeddings generated",
                    ),
                ),
                (
                    "failed_count",
                    models.IntegerField(
                        default=0,
                        help_text="Items that failed at any stage",
                    ),
                ),
                (
                    "skipped_count",
                    models.IntegerField(
                        default=0,
                        help_text="Items skipped (unsupported type, duplicate, etc.)",
                    ),
                ),
                (
                    "download_batch_size",
                    models.IntegerField(
                        default=500,
                        help_text="Number of documents per download batch",
                    ),
                ),
                (
                    "import_batch_size",
                    models.IntegerField(
                        default=200,
                        help_text="Number of documents per database import batch",
                    ),
                ),
                (
                    "max_concurrent_parse",
                    models.IntegerField(
                        default=10,
                        help_text="Maximum concurrent parsing tasks",
                    ),
                ),
                (
                    "last_processed_external_id",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Last successfully processed external ID (for resume)",
                        max_length=255,
                    ),
                ),
                (
                    "checkpoint_data",
                    opencontractserver.shared.fields.NullableJSONField(
                        blank=True,
                        default=opencontractserver.shared.defaults.jsonfield_default_value,
                        help_text="Arbitrary checkpoint state for resuming interrupted jobs",
                    ),
                ),
                (
                    "started_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="When processing actually began",
                        null=True,
                    ),
                ),
                (
                    "completed_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="When processing finished (success or failure)",
                        null=True,
                    ),
                ),
                (
                    "error_message",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Job-level error message if status is FAILED",
                    ),
                ),
            ],
            options={
                "ordering": ["-created"],
                "permissions": (
                    ("create_bulkingestionjob", "create BulkIngestionJob"),
                    ("read_bulkingestionjob", "read BulkIngestionJob"),
                    ("update_bulkingestionjob", "update BulkIngestionJob"),
                    ("remove_bulkingestionjob", "delete BulkIngestionJob"),
                ),
            },
        ),
        migrations.AddIndex(
            model_name="bulkingestionjob",
            index=models.Index(fields=["status"], name="bulk_ingest_status_idx"),
        ),
        migrations.AddIndex(
            model_name="bulkingestionjob",
            index=models.Index(
                fields=["corpus", "status"], name="bulk_ingest_corpus_status_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="bulkingestionjob",
            index=models.Index(
                fields=["creator"], name="bulk_ingest_creator_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="bulkingestionjob",
            index=models.Index(
                fields=["created"], name="bulk_ingest_created_idx"
            ),
        ),
        migrations.CreateModel(
            name="BulkIngestionItem",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "job",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="bulk_ingestion.bulkingestionjob",
                    ),
                ),
                (
                    "external_id",
                    models.CharField(
                        db_index=True,
                        help_text="External identifier for this document (e.g., Bates number, filename)",
                        max_length=255,
                    ),
                ),
                (
                    "source_url",
                    models.URLField(
                        blank=True,
                        default="",
                        help_text="Source URL if downloaded from the web",
                        max_length=1024,
                    ),
                ),
                (
                    "staged_path",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Path in staging storage (S3 key, local path, etc.)",
                        max_length=1024,
                    ),
                ),
                (
                    "parsed_data_path",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Path to pre-parsed OpenContractDocExport JSON",
                        max_length=1024,
                    ),
                ),
                (
                    "document",
                    models.ForeignKey(
                        blank=True,
                        help_text="The Document created from this item",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="bulk_ingestion_items",
                        to="documents.document",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("downloaded", "Downloaded"),
                            ("imported", "Imported"),
                            ("parsing", "Parsing"),
                            ("parsed", "Parsed"),
                            ("embedding", "Embedding"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                            ("skipped", "Skipped"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=20,
                    ),
                ),
                (
                    "error_message",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Error details if this item failed",
                    ),
                ),
                (
                    "file_type",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Detected MIME type",
                        max_length=255,
                    ),
                ),
                (
                    "file_size_bytes",
                    models.BigIntegerField(
                        blank=True,
                        help_text="File size in bytes (for progress estimation)",
                        null=True,
                    ),
                ),
                (
                    "content_hash",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        default="",
                        help_text="SHA-256 hash of file content",
                        max_length=64,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddIndex(
            model_name="bulkingestionitem",
            index=models.Index(
                fields=["job", "status"], name="bulk_item_job_status_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="bulkingestionitem",
            index=models.Index(
                fields=["external_id"], name="bulk_item_ext_id_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="bulkingestionitem",
            index=models.Index(
                fields=["content_hash"], name="bulk_item_hash_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="bulkingestionitem",
            index=models.Index(
                fields=["status"], name="bulk_item_status_idx"
            ),
        ),
        migrations.AddConstraint(
            model_name="bulkingestionitem",
            constraint=models.UniqueConstraint(
                fields=("job", "external_id"),
                name="unique_item_per_job",
            ),
        ),
    ]
