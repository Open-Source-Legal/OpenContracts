import inspect
import logging
from functools import lru_cache
from typing import Optional

from celery import chord, group, shared_task
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from opencontractserver.documents.models import DocumentAnalysisRow
from opencontractserver.extracts.models import Datacell, Extract
from opencontractserver.notifications.models import (
    Notification,
    NotificationTypeChoices,
)
from opencontractserver.notifications.signals import (
    broadcast_notification_via_websocket,
)
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.celery_tasks import get_task_by_name
from opencontractserver.utils.permissioning import (
    set_permissions_for_obj_to_user,
    user_has_permission_for_obj,
)

logger = logging.getLogger(__name__)


@lru_cache(maxsize=64)
def _task_accepts_kwarg(task_func, kwarg_name: str) -> bool:
    """Return True if ``task_func.run`` declares ``kwarg_name`` (or **kwargs).

    Cached so we only inspect once per (task, kwarg) pair across the worker.
    """
    target = getattr(task_func, "run", task_func)
    try:
        sig = inspect.signature(target)
    except (TypeError, ValueError):
        return False
    for param in sig.parameters.values():
        if param.name == kwarg_name:
            return True
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            return True
    return False


@shared_task
def mark_extract_complete(extract_id):
    """Mark extract as complete and update any related CorpusActionExecutions."""
    from opencontractserver.corpuses.models import CorpusActionExecution

    extract = Extract.objects.get(pk=extract_id)
    extract.finished = timezone.now()
    extract.save()

    # Mark any related CorpusActionExecutions as completed
    # These were set to RUNNING when the extract tasks were queued
    updated_count = CorpusActionExecution.objects.filter(
        extract_id=extract_id, status=CorpusActionExecution.Status.RUNNING
    ).update(status=CorpusActionExecution.Status.COMPLETED, completed_at=timezone.now())

    if updated_count:
        logger.info(
            f"Extract {extract_id} marked complete, "
            f"updated {updated_count} CorpusActionExecution(s)"
        )
    else:
        logger.info(f"Extract {extract_id} marked complete")

    # Create extract completion notification (Issue #624)
    try:
        if extract.creator:
            notification = Notification.objects.create(
                recipient=extract.creator,
                notification_type=NotificationTypeChoices.EXTRACT_COMPLETE,
                data={
                    "extract_id": extract.id,
                    "extract_name": extract.name,
                    "document_count": extract.documents.count(),
                    "fieldset_name": (
                        extract.fieldset.name if extract.fieldset else None
                    ),
                },
            )
            broadcast_notification_via_websocket(notification)
            logger.debug(
                f"Created EXTRACT_COMPLETE notification for {extract.creator.username}"
            )
    except Exception as e:
        logger.warning(f"Failed to create extract completion notification: {e}")


@shared_task
def run_extract(extract_id: Optional[str | int], user_id: str | int):
    logger.info(f"Run extract for extract {extract_id}")

    if extract_id is None:
        logger.error("run_extract called without an extract_id — aborting")
        return

    logger.info(f"Fetching extract with ID: {extract_id}")
    extract = Extract.objects.get(pk=extract_id)
    logger.info(f"Found extract: {extract.name} (ID: {extract.id})")

    # Re-validate permissions at task execution time (defense-in-depth).
    User = get_user_model()
    try:
        requesting_user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        logger.error(f"User {user_id} not found — aborting extract {extract_id}")
        return

    if not user_has_permission_for_obj(
        requesting_user, extract, PermissionTypes.UPDATE, include_group_permissions=True
    ):
        logger.error(
            f"User {user_id} lacks permission for extract {extract_id} — aborting"
        )
        return

    logger.info(f"Setting started timestamp for extract {extract.id}")
    with transaction.atomic():
        extract.started = timezone.now()
        extract.save()
        logger.info(f"Extract {extract.id} marked as started at {extract.started}")

    fieldset = extract.fieldset
    logger.info(f"Using fieldset: {fieldset.name} (ID: {fieldset.id})")

    logger.info(f"Retrieving document IDs for extract {extract.id}")
    document_ids = extract.documents.all().values_list("id", flat=True)
    logger.info(f"Found {len(document_ids)} documents to process: {list(document_ids)}")

    # Pull the iteration's captured model from extract.model_config so it can
    # be forwarded to each column task as ``model_override``. ``None`` means
    # "use the column/system default", preserving prior behaviour.
    model_config = extract.model_config or {}
    extract_model_override = model_config.get("model") or None

    tasks = []
    logger.info(f"Beginning document processing loop for extract {extract.id}")

    for document_id in document_ids:
        logger.info(f"Processing document ID: {document_id} for extract {extract.id}")

        row_results = DocumentAnalysisRow(
            document_id=document_id, extract_id=extract_id, creator=extract.creator
        )
        row_results.save()

        for column in fieldset.columns.all():

            with transaction.atomic():
                cell = Datacell.objects.create(
                    extract=extract,
                    column=column,
                    data_definition=column.output_type,
                    creator_id=user_id,
                    document_id=document_id,
                )

                set_permissions_for_obj_to_user(user_id, cell, [PermissionTypes.CRUD])

                # Add data cell to tracking
                row_results.data.add(cell)

                # Get the task function dynamically based on the column's task_name
                task_func = get_task_by_name(column.task_name)
                if task_func is None:
                    logger.error(
                        f"Task {column.task_name} not found for column {column.id}"
                    )
                    continue

                logger.info(
                    f"  Created datacell {cell.pk} for column '{column.name}' with task '{column.task_name}'"
                )

                # Add the task to the group. When the iteration captured a
                # specific model in ``extract.model_config``, forward it via
                # the ``model_override`` kwarg the column task already
                # accepts (introduced for the benchmark runner). Only the
                # canonical ``doc_extract_query_task`` accepts this kwarg
                # today, so we gate on the actual task signature to avoid
                # breaking custom column tasks.
                task_kwargs: dict = {}
                if extract_model_override and _task_accepts_kwarg(
                    task_func, "model_override"
                ):
                    task_kwargs["model_override"] = extract_model_override

                tasks.append(task_func.si(cell.pk, **task_kwargs))  # type: ignore[attr-defined]

    # Execute the tasks
    if tasks:
        # Check if we're in eager mode (test/synchronous execution)
        from celery import current_app

        if current_app.conf.task_always_eager:
            # In eager mode, chord doesn't work properly, so execute tasks manually
            logger.info(
                f"EAGER MODE: Running {len(tasks)} extraction tasks synchronously"
            )
            for i, task in enumerate(tasks, 1):
                logger.info(f"  Executing task {i}/{len(tasks)}...")
                try:
                    result = task.apply()
                    logger.info(f"    Task {i} completed successfully: {result}")
                except Exception as e:
                    logger.error(f"    Task {i} failed with error: {e}", exc_info=True)
            # Then mark complete
            logger.info("All tasks executed, marking extract as complete")
            mark_extract_complete(extract_id)
        else:
            # Normal async execution with chord
            chord(group(*tasks))(mark_extract_complete.si(extract_id))
            logger.info(
                f"ASYNC MODE: Queued {len(tasks)} extraction tasks for background execution"
            )
    else:
        logger.warning(f"No extraction tasks to run for extract {extract.id}")
        mark_extract_complete(extract_id)

    logger.info(f"Extract processing initiated for extract {extract.id}")
