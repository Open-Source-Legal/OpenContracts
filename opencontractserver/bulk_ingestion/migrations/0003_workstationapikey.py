import django.db.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("bulk_ingestion", "0002_add_claim_tracking"),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkstationApiKey",
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
                    "name",
                    models.CharField(
                        help_text="Human-readable label (e.g. 'gpu-workstation-01')",
                        max_length=255,
                    ),
                ),
                (
                    "key_prefix",
                    models.CharField(
                        help_text="First 12 characters of the raw key, for display only",
                        max_length=12,
                    ),
                ),
                (
                    "key_hash",
                    models.CharField(
                        db_index=True,
                        help_text="SHA-256 hex digest of the full raw key",
                        max_length=64,
                        unique=True,
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        help_text="Set to False to revoke this key",
                    ),
                ),
                (
                    "expires_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="Optional expiry timestamp; null means no expiry",
                        null=True,
                    ),
                ),
                (
                    "last_used_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="Timestamp of the most recent successful authentication",
                        null=True,
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    "creator",
                    django.db.models.ForeignKey(
                        help_text="User this key authenticates as",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="workstation_api_keys",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "job",
                    django.db.models.ForeignKey(
                        blank=True,
                        help_text="Optional: restrict this key to a single job",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="workstation_api_keys",
                        to="bulk_ingestion.bulkingestionjob",
                    ),
                ),
            ],
            options={
                "indexes": [
                    django.db.models.Index(
                        fields=["key_hash"],
                        name="bulk_ingest_key_has_idx",
                    ),
                    django.db.models.Index(
                        fields=["creator", "is_active"],
                        name="bulk_ingest_creator_active_idx",
                    ),
                ],
            },
        ),
    ]
