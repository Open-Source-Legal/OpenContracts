"""Durable policy and accounting for opt-in remote ingestion runs."""

import uuid

from django.db import models
from django.utils import timezone


class IngestionRun(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE"
        PAUSED = "PAUSED"
        BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
        POLICY_VIOLATION = "POLICY_VIOLATION"
        CANCELLED = "CANCELLED"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    worker_account = models.ForeignKey(
        "worker_uploads.WorkerAccount", on_delete=models.PROTECT
    )
    corpus = models.ForeignKey("corpuses.Corpus", on_delete=models.PROTECT)
    policy = models.JSONField()
    policy_digest = models.CharField(max_length=64)
    ceiling_usd = models.DecimalField(max_digits=20, decimal_places=9)
    accounted_usd = models.DecimalField(max_digits=20, decimal_places=9, default=0)
    reserved_usd = models.DecimalField(max_digits=20, decimal_places=9, default=0)
    status = models.CharField(
        max_length=24, choices=Status.choices, default=Status.ACTIVE
    )
    last_error = models.CharField(max_length=64, blank=True)
    created = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(accounted_usd__gte=0, reserved_usd__gte=0),
                name="ingest_run_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    ceiling_usd__gte=models.F("accounted_usd")
                    + models.F("reserved_usd")
                ),
                name="ingest_run_within_ceiling",
            ),
        ]


class IngestionOperation(models.Model):
    class Status(models.TextChoices):
        WAITING = "WAITING"
        QUEUED = "QUEUED"
        RUNNING = "RUNNING"
        COMPLETED = "COMPLETED"
        FAILED = "FAILED"
        UNCERTAIN = "UNCERTAIN"
        CANCELLED = "CANCELLED"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(
        IngestionRun, on_delete=models.PROTECT, related_name="operations"
    )
    key = models.CharField(max_length=64)
    target_type = models.CharField(max_length=16)
    target_id = models.PositiveBigIntegerField()
    input_digest = models.CharField(max_length=64)
    estimated_usd = models.DecimalField(max_digits=20, decimal_places=9)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.WAITING
    )
    attempt_count = models.PositiveIntegerField(default=0)
    error_code = models.CharField(max_length=64, blank=True)
    created = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["run", "key"], name="ingest_operation_once")
        ]


class IngestionReservation(models.Model):
    class Status(models.TextChoices):
        RESERVED = "RESERVED"
        STARTED = "STARTED"
        SETTLED = "SETTLED"
        UNCERTAIN = "UNCERTAIN"
        CANCELLED = "CANCELLED"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    operation = models.ForeignKey(
        IngestionOperation, on_delete=models.PROTECT, related_name="reservations"
    )
    attempt = models.PositiveIntegerField()
    amount_usd = models.DecimalField(max_digits=20, decimal_places=9)
    accounted_usd = models.DecimalField(max_digits=20, decimal_places=9, null=True)
    accounted_tokens = models.PositiveIntegerField(null=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.RESERVED
    )
    created = models.DateTimeField(default=timezone.now)
    started = models.DateTimeField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["operation", "attempt"], name="ingest_attempt_once"
            )
        ]


class IngestionRunEvent(models.Model):
    run = models.ForeignKey(
        IngestionRun, on_delete=models.PROTECT, related_name="events"
    )
    code = models.CharField(max_length=64)
    detail = models.JSONField(default=dict)
    created = models.DateTimeField(default=timezone.now)
