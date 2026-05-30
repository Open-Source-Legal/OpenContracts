import uuid

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

import opencontractserver.document_imports.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ChunkedUploadSession",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("document", "Single document"),
                            ("documents_zip", "Bulk documents zip"),
                            (
                                "zip_to_corpus",
                                "Zip into corpus (folders preserved)",
                            ),
                            ("corpus_export", "OpenContracts corpus export"),
                        ],
                        max_length=32,
                    ),
                ),
                ("filename", models.CharField(max_length=512)),
                (
                    "total_size",
                    models.BigIntegerField(
                        help_text="Expected total assembled size in bytes (declared at start)."
                    ),
                ),
                (
                    "chunk_size",
                    models.BigIntegerField(
                        help_text="Client part size in bytes (every part except the last)."
                    ),
                ),
                (
                    "total_chunks",
                    models.PositiveIntegerField(
                        help_text="Number of parts the client will upload."
                    ),
                ),
                (
                    "metadata",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Import parameters for the target service (title, description, corpus id, ...). Shape depends on ``kind``.",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("ASSEMBLING", "Assembling"),
                            ("COMPLETED", "Completed"),
                            ("FAILED", "Failed"),
                        ],
                        db_index=True,
                        default="PENDING",
                        max_length=20,
                    ),
                ),
                ("error_message", models.TextField(blank=True, default="")),
                (
                    "created",
                    models.DateTimeField(
                        db_index=True, default=django.utils.timezone.now
                    ),
                ),
                ("modified", models.DateTimeField(auto_now=True)),
                (
                    "creator",
                    models.ForeignKey(
                        help_text="User who owns this upload (enforces per-user isolation).",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chunked_upload_sessions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["created"],
            },
        ),
        migrations.CreateModel(
            name="ChunkedUploadPart",
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
                    "index",
                    models.PositiveIntegerField(help_text="Zero-based part index."),
                ),
                (
                    "file",
                    models.FileField(
                        upload_to=opencontractserver.document_imports.models._chunk_part_path
                    ),
                ),
                (
                    "size",
                    models.BigIntegerField(default=0, help_text="Part size in bytes."),
                ),
                ("created", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="parts",
                        to="document_imports.chunkeduploadsession",
                    ),
                ),
            ],
            options={
                "ordering": ["index"],
            },
        ),
        migrations.AddIndex(
            model_name="chunkeduploadsession",
            index=models.Index(
                fields=["creator", "status"], name="chunkup_creator_status_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="chunkeduploadsession",
            index=models.Index(
                fields=["status", "created"], name="chunkup_status_created_idx"
            ),
        ),
        migrations.AddConstraint(
            model_name="chunkeduploadpart",
            constraint=models.UniqueConstraint(
                fields=["session", "index"], name="uniq_chunk_part_per_session"
            ),
        ),
    ]
