"""
Bulk Ingestion Models

Provides models for orchestrating large-scale document ingestion into
OpenContracts. Supports three ingestion modes:

1. **URL-based**: Download documents from URLs (with rate limiting)
2. **Storage-based**: Import from S3/GCS/local staging directories
3. **Pre-parsed**: Import documents with pre-computed parsing output,
   enabling offline parsing on GPU workstations

The architecture uses a two-level job/item model:
- BulkIngestionJob: Orchestrates the overall import, tracks progress
- BulkIngestionItem: Tracks individual document state through the pipeline
"""

import django
from django.contrib.auth import get_user_model
from django.db import models

from opencontractserver.shared.defaults import jsonfield_default_value
from opencontractserver.shared.fields import NullableJSONField
from opencontractserver.shared.Models import BaseOCModel

User = get_user_model()


class IngestionSourceType(models.TextChoices):
    """How documents are sourced for ingestion."""

    URL_PATTERN = "url_pattern", "URL Pattern"
    STORAGE_PREFIX = "storage_prefix", "Storage Prefix"
    MANIFEST = "manifest", "Manifest File"
    PRE_PARSED = "pre_parsed", "Pre-Parsed Bundles"


class BulkIngestionJobStatus(models.TextChoices):
    """Lifecycle states for a bulk ingestion job."""

    CREATED = "created", "Created"
    DOWNLOADING = "downloading", "Downloading"
    IMPORTING = "importing", "Importing"
    PROCESSING = "processing", "Processing"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    PAUSED = "paused", "Paused"
    CANCELLED = "cancelled", "Cancelled"


class BulkIngestionItemStatus(models.TextChoices):
    """Lifecycle states for an individual ingestion item."""

    PENDING = "pending", "Pending"
    DOWNLOADED = "downloaded", "Downloaded"
    IMPORTED = "imported", "Imported"
    PARSING = "parsing", "Parsing"
    PARSED = "parsed", "Parsed"
    EMBEDDING = "embedding", "Embedding"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    SKIPPED = "skipped", "Skipped"


class ParsingStrategy(models.TextChoices):
    """How documents should be parsed during ingestion."""

    FULL = "full", "Full Structural Parsing"
    TEXT_ONLY = "text_only", "Text Extraction Only"
    PRE_PARSED = "pre_parsed", "Pre-Parsed (Skip Parsing)"
    SKIP = "skip", "Skip Parsing Entirely"


class BulkIngestionJob(BaseOCModel):
    """
    Orchestrates a large-scale document ingestion into a corpus.

    Tracks overall progress across download, import, parse, and embed phases.
    Supports pause/resume via checkpoint_data and per-item status tracking.

    The job dispatches batches of work to dedicated Celery queues, using
    backpressure to avoid overwhelming Redis or downstream services.
    """

    corpus = django.db.models.ForeignKey(
        "corpuses.Corpus",
        on_delete=django.db.models.CASCADE,
        related_name="bulk_ingestion_jobs",
    )

    status = django.db.models.CharField(
        max_length=20,
        choices=BulkIngestionJobStatus.choices,
        default=BulkIngestionJobStatus.CREATED,
        db_index=True,
    )

    # Source configuration
    source_type = django.db.models.CharField(
        max_length=30,
        choices=IngestionSourceType.choices,
        help_text="How documents are sourced (URL, storage path, manifest, pre-parsed)",
    )

    source_config = NullableJSONField(
        default=jsonfield_default_value,
        blank=True,
        help_text=(
            "Source-specific configuration. Examples:\n"
            '  url_pattern: {"url_template": "https://example.com/docs/{id}.pdf", '
            '"id_range": [1, 50000]}\n'
            '  storage_prefix: {"backend": "s3", "bucket": "my-bucket", '
            '"prefix": "staging/job-001/"}\n'
            '  manifest: {"path": "s3://bucket/manifest.json"}\n'
            '  pre_parsed: {"manifest_path": "s3://bucket/parsed/manifest.json"}'
        ),
    )

    # Parsing configuration
    parsing_strategy = django.db.models.CharField(
        max_length=20,
        choices=ParsingStrategy.choices,
        default=ParsingStrategy.FULL,
        help_text="How documents should be parsed during ingestion",
    )

    # Progress counters (updated atomically via F() expressions)
    total_items = django.db.models.IntegerField(
        default=0,
        help_text="Total number of items to process",
    )
    downloaded_count = django.db.models.IntegerField(
        default=0,
        help_text="Items successfully downloaded/staged",
    )
    imported_count = django.db.models.IntegerField(
        default=0,
        help_text="Items imported into database (Document records created)",
    )
    parsed_count = django.db.models.IntegerField(
        default=0,
        help_text="Items fully parsed (annotations created)",
    )
    embedded_count = django.db.models.IntegerField(
        default=0,
        help_text="Items with embeddings generated",
    )
    failed_count = django.db.models.IntegerField(
        default=0,
        help_text="Items that failed at any stage",
    )
    skipped_count = django.db.models.IntegerField(
        default=0,
        help_text="Items skipped (unsupported type, duplicate, etc.)",
    )

    # Batch configuration
    download_batch_size = django.db.models.IntegerField(
        default=500,
        help_text="Number of documents per download batch",
    )
    import_batch_size = django.db.models.IntegerField(
        default=200,
        help_text="Number of documents per database import batch",
    )
    max_concurrent_parse = django.db.models.IntegerField(
        default=10,
        help_text="Maximum concurrent parsing tasks",
    )

    # Resumability
    last_processed_external_id = django.db.models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Last successfully processed external ID (for resume)",
    )
    checkpoint_data = NullableJSONField(
        default=jsonfield_default_value,
        blank=True,
        help_text="Arbitrary checkpoint state for resuming interrupted jobs",
    )

    # Timing
    started_at = django.db.models.DateTimeField(
        null=True,
        blank=True,
        help_text="When processing actually began",
    )
    completed_at = django.db.models.DateTimeField(
        null=True,
        blank=True,
        help_text="When processing finished (success or failure)",
    )

    # Error tracking
    error_message = django.db.models.TextField(
        blank=True,
        default="",
        help_text="Job-level error message if status is FAILED",
    )

    class Meta:
        indexes = [
            django.db.models.Index(fields=["status"]),
            django.db.models.Index(fields=["corpus", "status"]),
            django.db.models.Index(fields=["creator"]),
            django.db.models.Index(fields=["created"]),
        ]
        ordering = ["-created"]
        permissions = (
            ("create_bulkingestionjob", "create BulkIngestionJob"),
            ("read_bulkingestionjob", "read BulkIngestionJob"),
            ("update_bulkingestionjob", "update BulkIngestionJob"),
            ("remove_bulkingestionjob", "delete BulkIngestionJob"),
        )

    def __str__(self):
        return (
            f"BulkIngestionJob({self.id}) corpus={self.corpus_id} "
            f"status={self.status} {self.imported_count}/{self.total_items}"
        )

    @property
    def progress_fraction(self) -> float:
        """Overall progress as a float from 0.0 to 1.0."""
        if self.total_items == 0:
            return 0.0
        # Weight each phase: import=40%, parse=40%, embed=20%
        weighted = (
            self.imported_count * 0.4
            + self.parsed_count * 0.4
            + self.embedded_count * 0.2
        )
        return min(weighted / self.total_items, 1.0)

    @property
    def is_terminal(self) -> bool:
        """Whether the job is in a terminal state (no more work will happen)."""
        return self.status in (
            BulkIngestionJobStatus.COMPLETED,
            BulkIngestionJobStatus.FAILED,
            BulkIngestionJobStatus.CANCELLED,
        )


class BulkIngestionItem(models.Model):
    """
    Tracks an individual document through the bulk ingestion pipeline.

    Each item represents one source document and moves through states:
    PENDING → DOWNLOADED → IMPORTED → PARSING → PARSED → EMBEDDING → COMPLETED

    Items are intentionally lightweight (no BaseOCModel overhead) since
    there may be millions per job. No guardian permissions needed; access
    is controlled via the parent job.
    """

    job = django.db.models.ForeignKey(
        BulkIngestionJob,
        on_delete=django.db.models.CASCADE,
        related_name="items",
    )

    # Source identification
    external_id = django.db.models.CharField(
        max_length=255,
        db_index=True,
        help_text="External identifier for this document (e.g., Bates number, filename)",
    )
    source_url = django.db.models.URLField(
        max_length=1024,
        blank=True,
        default="",
        help_text="Source URL if downloaded from the web",
    )

    # Staging location
    staged_path = django.db.models.CharField(
        max_length=1024,
        blank=True,
        default="",
        help_text="Path in staging storage (S3 key, local path, etc.)",
    )

    # Pre-parsed data location (for pre_parsed source type)
    parsed_data_path = django.db.models.CharField(
        max_length=1024,
        blank=True,
        default="",
        help_text="Path to pre-parsed OpenContractDocExport JSON",
    )

    # Link to created Document
    document = django.db.models.ForeignKey(
        "documents.Document",
        null=True,
        blank=True,
        on_delete=django.db.models.SET_NULL,
        related_name="bulk_ingestion_items",
        help_text="The Document created from this item",
    )

    # Lifecycle
    status = django.db.models.CharField(
        max_length=20,
        choices=BulkIngestionItemStatus.choices,
        default=BulkIngestionItemStatus.PENDING,
        db_index=True,
    )
    error_message = django.db.models.TextField(
        blank=True,
        default="",
        help_text="Error details if this item failed",
    )

    # File metadata
    file_type = django.db.models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Detected MIME type",
    )
    file_size_bytes = django.db.models.BigIntegerField(
        null=True,
        blank=True,
        help_text="File size in bytes (for progress estimation)",
    )
    content_hash = django.db.models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        help_text="SHA-256 hash of file content",
    )

    # Workstation claim tracking
    claimed_at = django.db.models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this item was claimed by a workstation for processing",
    )
    claimed_by = django.db.models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Identifier of the workstation that claimed this item",
    )

    # Timestamps (no auto_now_add to keep model lightweight)
    created_at = django.db.models.DateTimeField(auto_now_add=True)
    updated_at = django.db.models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            django.db.models.Index(fields=["job", "status"]),
            django.db.models.Index(fields=["external_id"]),
            django.db.models.Index(fields=["content_hash"]),
            django.db.models.Index(fields=["status"]),
        ]
        constraints = [
            django.db.models.UniqueConstraint(
                fields=["job", "external_id"],
                name="unique_item_per_job",
            ),
        ]

    def __str__(self):
        return (
            f"BulkIngestionItem({self.id}) job={self.job_id} "
            f"ext_id={self.external_id} status={self.status}"
        )
