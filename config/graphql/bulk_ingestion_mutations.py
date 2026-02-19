"""
GraphQL mutations for bulk ingestion operations.

Provides mutations to create, pause, resume, and cancel bulk ingestion jobs,
as well as workstation claim/complete mutations for distributed processing.
"""

import logging

import graphene
from graphene_django import DjangoObjectType
from graphql_jwt.decorators import login_required

from config.graphql.ratelimits import RateLimits, graphql_ratelimit
from opencontractserver.bulk_ingestion.constants import (
    BULK_INGESTION_MAX_CLAIM_BATCH_SIZE,
)
from opencontractserver.bulk_ingestion.models import (
    BulkIngestionItem,
    BulkIngestionJob,
    BulkIngestionJobStatus,
    IngestionSourceType,
    ParsingStrategy,
)
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

logger = logging.getLogger(__name__)

# ============================================================================
# GraphQL Types
# ============================================================================


class BulkIngestionJobType(DjangoObjectType):
    """GraphQL type for BulkIngestionJob."""

    progress_fraction = graphene.Float(
        description="Overall progress as a float from 0.0 to 1.0"
    )
    is_terminal = graphene.Boolean(description="Whether the job is in a terminal state")
    item_summary = graphene.Field(
        "config.graphql.bulk_ingestion_mutations.BulkIngestionItemSummaryType",
        description="Summary counts of items by status",
    )

    class Meta:
        model = BulkIngestionJob
        fields = [
            "id",
            "corpus",
            "status",
            "source_type",
            "source_config",
            "parsing_strategy",
            "total_items",
            "downloaded_count",
            "imported_count",
            "parsed_count",
            "embedded_count",
            "failed_count",
            "skipped_count",
            "download_batch_size",
            "import_batch_size",
            "max_concurrent_parse",
            "last_processed_external_id",
            "started_at",
            "completed_at",
            "error_message",
            "created",
            "modified",
            "creator",
        ]

    def resolve_progress_fraction(self, info):
        return self.progress_fraction

    def resolve_is_terminal(self, info):
        return self.is_terminal

    def resolve_item_summary(self, info):
        from django.db.models import Count, Q

        counts = BulkIngestionItem.objects.filter(job=self).aggregate(
            pending=Count("id", filter=Q(status="pending")),
            downloaded=Count("id", filter=Q(status="downloaded")),
            imported=Count("id", filter=Q(status="imported")),
            parsing=Count("id", filter=Q(status="parsing")),
            parsed=Count("id", filter=Q(status="parsed")),
            embedding=Count("id", filter=Q(status="embedding")),
            completed=Count("id", filter=Q(status="completed")),
            failed=Count("id", filter=Q(status="failed")),
            skipped=Count("id", filter=Q(status="skipped")),
        )
        return counts


class BulkIngestionItemSummaryType(graphene.ObjectType):
    """Summary counts of items by status."""

    pending = graphene.Int()
    downloaded = graphene.Int()
    imported = graphene.Int()
    parsing = graphene.Int()
    parsed = graphene.Int()
    embedding = graphene.Int()
    completed = graphene.Int()
    failed = graphene.Int()
    skipped = graphene.Int()


class BulkIngestionItemType(DjangoObjectType):
    """GraphQL type for BulkIngestionItem."""

    class Meta:
        model = BulkIngestionItem
        fields = [
            "id",
            "job",
            "external_id",
            "source_url",
            "staged_path",
            "document",
            "status",
            "error_message",
            "file_type",
            "file_size_bytes",
            "content_hash",
            "claimed_at",
            "claimed_by",
            "created_at",
            "updated_at",
        ]


class ClaimedItemType(graphene.ObjectType):
    """An item claimed by a workstation for external processing."""

    id = graphene.ID(description="BulkIngestionItem ID")
    external_id = graphene.String(description="External document identifier")
    staged_path = graphene.String(description="Storage path to the source PDF")
    download_url = graphene.String(
        description="Pre-signed URL for downloading the source file (24h expiry)"
    )
    source_url = graphene.String(description="Source URL if applicable")
    file_type = graphene.String(description="Detected MIME type")


# ============================================================================
# Mutations
# ============================================================================


class CreateBulkIngestionJob(graphene.Mutation):
    """
    Create a new bulk ingestion job.

    The job is created in CREATED state. Call StartBulkIngestionJob
    to begin processing, or the job will auto-start if auto_start=True.
    """

    class Arguments:
        corpus_id = graphene.ID(required=True)
        source_type = graphene.String(
            required=True,
            description="One of: url_pattern, storage_prefix, manifest, pre_parsed",
        )
        source_config = graphene.JSONString(
            required=True,
            description="Source-specific configuration (JSON object)",
        )
        parsing_strategy = graphene.String(
            required=False,
            description="One of: full, text_only, pre_parsed, skip (default: full)",
        )
        download_batch_size = graphene.Int(required=False)
        import_batch_size = graphene.Int(required=False)
        max_concurrent_parse = graphene.Int(required=False)
        auto_start = graphene.Boolean(
            required=False,
            default_value=False,
            description="If True, start processing immediately after creation",
        )

    ok = graphene.Boolean()
    message = graphene.String()
    job = graphene.Field(BulkIngestionJobType)

    @staticmethod
    @login_required
    def mutate(root, info, corpus_id, source_type, source_config, **kwargs):
        from opencontractserver.corpuses.models import Corpus

        user = info.context.user

        # Validate corpus access
        try:
            corpus = Corpus.objects.visible_to_user(user).get(pk=corpus_id)
        except Corpus.DoesNotExist:
            return CreateBulkIngestionJob(
                ok=False, message="Corpus not found or no access", job=None
            )

        # Validate source_type
        valid_source_types = [c[0] for c in IngestionSourceType.choices]
        if source_type not in valid_source_types:
            return CreateBulkIngestionJob(
                ok=False,
                message=f"Invalid source_type. Must be one of: {valid_source_types}",
                job=None,
            )

        # Validate parsing_strategy
        parsing_strategy = kwargs.get("parsing_strategy", ParsingStrategy.FULL)
        valid_strategies = [c[0] for c in ParsingStrategy.choices]
        if parsing_strategy not in valid_strategies:
            return CreateBulkIngestionJob(
                ok=False,
                message=f"Invalid parsing_strategy. Must be one of: {valid_strategies}",
                job=None,
            )

        job = BulkIngestionJob.objects.create(
            corpus=corpus,
            creator=user,
            source_type=source_type,
            source_config=source_config,
            parsing_strategy=parsing_strategy,
            download_batch_size=kwargs.get("download_batch_size", 500),
            import_batch_size=kwargs.get("import_batch_size", 200),
            max_concurrent_parse=kwargs.get("max_concurrent_parse", 10),
        )

        # Set permissions
        set_permissions_for_obj_to_user(user, job, [PermissionTypes.ALL])

        # Auto-start if requested
        auto_start = kwargs.get("auto_start", False)
        if auto_start:
            _dispatch_job(job)

        return CreateBulkIngestionJob(ok=True, message="Job created", job=job)


class StartBulkIngestionJob(graphene.Mutation):
    """Start a previously created bulk ingestion job."""

    class Arguments:
        job_id = graphene.ID(required=True)

    ok = graphene.Boolean()
    message = graphene.String()
    job = graphene.Field(BulkIngestionJobType)

    @staticmethod
    @login_required
    def mutate(root, info, job_id):
        user = info.context.user

        try:
            job = BulkIngestionJob.objects.get(pk=job_id, creator=user)
        except BulkIngestionJob.DoesNotExist:
            return StartBulkIngestionJob(ok=False, message="Job not found", job=None)

        if job.status != BulkIngestionJobStatus.CREATED:
            return StartBulkIngestionJob(
                ok=False,
                message=f"Job cannot be started from status '{job.status}'",
                job=job,
            )

        _dispatch_job(job)

        return StartBulkIngestionJob(ok=True, message="Job started", job=job)


class PauseBulkIngestionJob(graphene.Mutation):
    """Pause a running bulk ingestion job."""

    class Arguments:
        job_id = graphene.ID(required=True)

    ok = graphene.Boolean()
    message = graphene.String()
    job = graphene.Field(BulkIngestionJobType)

    @staticmethod
    @login_required
    def mutate(root, info, job_id):
        user = info.context.user

        try:
            job = BulkIngestionJob.objects.get(pk=job_id, creator=user)
        except BulkIngestionJob.DoesNotExist:
            return PauseBulkIngestionJob(ok=False, message="Job not found", job=None)

        from opencontractserver.bulk_ingestion.tasks import pause_bulk_ingestion

        pause_bulk_ingestion.delay(job.id)

        return PauseBulkIngestionJob(ok=True, message="Pause requested", job=job)


class ResumeBulkIngestionJob(graphene.Mutation):
    """Resume a paused bulk ingestion job."""

    class Arguments:
        job_id = graphene.ID(required=True)

    ok = graphene.Boolean()
    message = graphene.String()
    job = graphene.Field(BulkIngestionJobType)

    @staticmethod
    @login_required
    def mutate(root, info, job_id):
        user = info.context.user

        try:
            job = BulkIngestionJob.objects.get(pk=job_id, creator=user)
        except BulkIngestionJob.DoesNotExist:
            return ResumeBulkIngestionJob(ok=False, message="Job not found", job=None)

        if job.status != BulkIngestionJobStatus.PAUSED:
            return ResumeBulkIngestionJob(
                ok=False,
                message=f"Job cannot be resumed from status '{job.status}'",
                job=job,
            )

        from opencontractserver.bulk_ingestion.tasks import resume_bulk_ingestion

        resume_bulk_ingestion.delay(job.id)

        return ResumeBulkIngestionJob(ok=True, message="Resume requested", job=job)


class CancelBulkIngestionJob(graphene.Mutation):
    """Cancel a bulk ingestion job. Already-processed items are kept."""

    class Arguments:
        job_id = graphene.ID(required=True)

    ok = graphene.Boolean()
    message = graphene.String()
    job = graphene.Field(BulkIngestionJobType)

    @staticmethod
    @login_required
    def mutate(root, info, job_id):
        user = info.context.user

        try:
            job = BulkIngestionJob.objects.get(pk=job_id, creator=user)
        except BulkIngestionJob.DoesNotExist:
            return CancelBulkIngestionJob(ok=False, message="Job not found", job=None)

        if job.is_terminal:
            return CancelBulkIngestionJob(
                ok=False,
                message=f"Job is already in terminal state '{job.status}'",
                job=job,
            )

        from django.utils import timezone

        job.status = BulkIngestionJobStatus.CANCELLED
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "completed_at"])

        return CancelBulkIngestionJob(ok=True, message="Job cancelled", job=job)


# ============================================================================
# Workstation Claim / Complete Mutations
# ============================================================================


class ClaimBulkIngestionBatch(graphene.Mutation):
    """
    Claim a batch of pending items for external processing.

    Used by GPU workstations to pull work from a bulk ingestion job.
    Items are atomically transitioned from pending to parsing status,
    with a claim timestamp for TTL-based expiry. Expired claims are
    automatically released back to pending before each new claim.

    Returns the claimed items with pre-signed download URLs (24h expiry)
    so the workstation can fetch source documents without needing
    separate bucket credentials. Also returns a pre-signed upload URL
    for submitting JSONL results back to staging storage.
    """

    class Arguments:
        job_id = graphene.ID(required=True, description="Bulk ingestion job ID")
        batch_size = graphene.Int(
            required=False,
            default_value=100,
            description="Number of items to claim (max 500)",
        )
        workstation_id = graphene.String(
            required=False,
            default_value="",
            description="Identifier for the claiming workstation",
        )

    ok = graphene.Boolean()
    message = graphene.String()
    items = graphene.List(ClaimedItemType, description="Claimed items")
    results_upload_url = graphene.String(
        description="Pre-signed PUT URL for uploading JSONL results (24h expiry)"
    )
    results_upload_path = graphene.String(
        description="Storage path to pass to completeBulkIngestionBatch"
    )

    @staticmethod
    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_MEDIUM)
    def mutate(root, info, job_id, batch_size=100, workstation_id=""):
        import uuid

        from django.db import transaction
        from django.utils import timezone

        from opencontractserver.bulk_ingestion.tasks import release_expired_claims
        from opencontractserver.bulk_ingestion.utils import (
            generate_download_url,
            generate_upload_url,
            staging_path_for_job,
        )

        user = info.context.user

        try:
            job = BulkIngestionJob.objects.get(pk=job_id, creator=user)
        except BulkIngestionJob.DoesNotExist:
            return ClaimBulkIngestionBatch(ok=False, message="Job not found", items=[])

        if job.is_terminal:
            return ClaimBulkIngestionBatch(
                ok=False,
                message=f"Job is in terminal state '{job.status}'",
                items=[],
            )

        # Clamp batch size
        batch_size = max(1, min(batch_size, BULK_INGESTION_MAX_CLAIM_BATCH_SIZE))

        # Release expired claims first
        release_expired_claims(job.id)

        # Atomically claim items using SELECT FOR UPDATE with skip_locked
        # to allow concurrent workstation claims without blocking
        with transaction.atomic():
            candidate_ids = list(
                BulkIngestionItem.objects.filter(job_id=job.id, status="pending")
                .order_by("id")
                .values_list("id", flat=True)[:batch_size]
            )

            if not candidate_ids:
                return ClaimBulkIngestionBatch(
                    ok=True, message="No items available to claim", items=[]
                )

            # Lock rows — skip_locked avoids contention with concurrent claims
            locked_ids = list(
                BulkIngestionItem.objects.select_for_update(skip_locked=True)
                .filter(id__in=candidate_ids, status="pending")
                .values_list("id", flat=True)
            )

            if not locked_ids:
                return ClaimBulkIngestionBatch(
                    ok=True, message="No items available to claim", items=[]
                )

            now = timezone.now()
            BulkIngestionItem.objects.filter(id__in=locked_ids).update(
                status="parsing",
                claimed_at=now,
                claimed_by=workstation_id or "",
            )

        # Fetch claimed items and generate pre-signed download URLs
        claimed = BulkIngestionItem.objects.filter(id__in=locked_ids).values(
            "id", "external_id", "staged_path", "source_url", "file_type"
        )
        items = []
        for item in claimed:
            download_url = ""
            if item["staged_path"]:
                try:
                    download_url = generate_download_url(item["staged_path"])
                except Exception:
                    logger.warning(
                        f"Failed to generate download URL for {item['staged_path']}",
                        exc_info=True,
                    )
            items.append(
                ClaimedItemType(
                    id=item["id"],
                    external_id=item["external_id"],
                    staged_path=item["staged_path"],
                    download_url=download_url,
                    source_url=item["source_url"],
                    file_type=item["file_type"],
                )
            )

        # Generate a pre-signed upload URL for the results JSONL
        batch_id = uuid.uuid4().hex[:12]
        upload_path = staging_path_for_job(job.id, f"results/{batch_id}.jsonl")
        try:
            upload_url = generate_upload_url(upload_path)
        except Exception:
            logger.warning(
                "Failed to generate upload URL for results",
                exc_info=True,
            )
            upload_url = ""

        logger.info(
            f"Workstation '{workstation_id}' claimed {len(items)} items "
            f"from job {job.id}"
        )

        return ClaimBulkIngestionBatch(
            ok=True,
            message=f"Claimed {len(items)} items",
            items=items,
            results_upload_url=upload_url,
            results_upload_path=upload_path,
        )


class CompleteBulkIngestionBatch(graphene.Mutation):
    """
    Submit processed results from a workstation.

    The workstation writes a JSONL file of PreParsedDocumentBundle objects
    to staging storage, then calls this mutation with the file path.
    The server dispatches an import task to create Documents from the
    bundles and link them to the pre-existing BulkIngestionItems.

    The JSONL bundles must include `external_id` values matching the
    items originally returned by ClaimBulkIngestionBatch.
    """

    class Arguments:
        job_id = graphene.ID(required=True, description="Bulk ingestion job ID")
        results_path = graphene.String(
            required=True,
            description="Path to the JSONL results file in staging storage",
        )

    ok = graphene.Boolean()
    message = graphene.String()

    @staticmethod
    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_MEDIUM)
    def mutate(root, info, job_id, results_path):
        from django.db import transaction
        from django.utils import timezone

        user = info.context.user

        try:
            job = BulkIngestionJob.objects.get(pk=job_id, creator=user)
        except BulkIngestionJob.DoesNotExist:
            return CompleteBulkIngestionBatch(ok=False, message="Job not found")

        if job.is_terminal:
            return CompleteBulkIngestionBatch(
                ok=False,
                message=f"Job is in terminal state '{job.status}'",
            )

        if not results_path or not results_path.strip():
            return CompleteBulkIngestionBatch(
                ok=False, message="results_path is required"
            )

        # Transition job to importing if it hasn't started yet
        if job.status == BulkIngestionJobStatus.CREATED:
            job.status = BulkIngestionJobStatus.IMPORTING
            job.started_at = timezone.now()
            job.save(update_fields=["status", "started_at"])

        # Dispatch the import task
        from opencontractserver.bulk_ingestion.tasks import batch_import_preparsed

        transaction.on_commit(
            lambda: batch_import_preparsed.delay(job.id, results_path, 0)
        )

        logger.info(f"Workstation submitted results for job {job.id}: {results_path}")

        return CompleteBulkIngestionBatch(
            ok=True,
            message="Results submitted for import",
        )


# ============================================================================
# Helper
# ============================================================================


def _dispatch_job(job: BulkIngestionJob):
    """Dispatch the appropriate orchestration task for a job."""
    from django.db import transaction

    if job.source_type == IngestionSourceType.PRE_PARSED:
        from opencontractserver.bulk_ingestion.tasks import (
            orchestrate_preparsed_ingestion,
        )

        transaction.on_commit(lambda: orchestrate_preparsed_ingestion.delay(job.id))
    else:
        # For non-pre-parsed types, mark as downloading
        # (download tasks would be dispatched here in a future phase)
        job.status = BulkIngestionJobStatus.CREATED
        job.save(update_fields=["status"])
