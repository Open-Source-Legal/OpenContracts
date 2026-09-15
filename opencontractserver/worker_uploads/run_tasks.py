"""Durable reservation delivery. STARTED work is never automatically replayed."""

from celery import shared_task

from opencontractserver.constants.ingestion_runs import OPERATION_DRAIN_BATCH_SIZE


@shared_task(queue="worker_uploads", acks_late=True)
def process_ingestion_operation(reservation_id):
    from opencontractserver.worker_uploads.run_services import execute_reservation

    execute_reservation(reservation_id)


@shared_task(queue="worker_uploads")
def process_pending_ingestion_operations():
    from opencontractserver.worker_uploads.run_models import (
        IngestionReservation,
        IngestionRun,
    )

    ids = list(
        IngestionReservation.objects.filter(
            status=IngestionReservation.Status.RESERVED,
            operation__run__status__in=[
                IngestionRun.Status.ACTIVE,
                IngestionRun.Status.BUDGET_EXHAUSTED,
            ],
        )
        .order_by("created")
        .values_list("pk", flat=True)[:OPERATION_DRAIN_BATCH_SIZE]
    )
    for reservation_id in ids:
        process_ingestion_operation.delay(str(reservation_id))
    return len(ids)
