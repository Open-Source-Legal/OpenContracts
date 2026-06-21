"""Add a partial unique constraint backing analysis-status notification idempotency.

The analysis-status signal (``notifications/signals.py``) previously guarded
against duplicate notifications with a check-then-create pair. Two concurrent
``Analysis.post_save`` signals could both pass the ``exists()`` check before
either ``create()`` committed, leaking duplicate rows. The signal now uses
``get_or_create``; this migration adds the partial unique constraint that makes
that atomic (the losing writer trips the constraint and re-reads the winner's
row), after first cleaning up any duplicates that predate the constraint.
"""

import logging

from django.db import migrations, models
from django.db.models import Count

logger = logging.getLogger(__name__)


def cleanup_duplicate_analysis_notifications(apps, schema_editor):
    """Collapse duplicate (analysis, notification_type) rows before the constraint.

    Keeps the earliest (lowest id) notification in each duplicate group and
    deletes the rest. Only notifications with a non-null ``analysis`` are
    considered — every other notification type is unaffected.
    """
    Notification = apps.get_model("notifications", "Notification")

    duplicate_groups = (
        Notification.objects.filter(analysis__isnull=False)
        .values("analysis_id", "notification_type")
        .annotate(count=Count("id"))
        .filter(count__gt=1)
    )

    total_deleted = 0
    for group in duplicate_groups:
        ids = list(
            Notification.objects.filter(
                analysis_id=group["analysis_id"],
                notification_type=group["notification_type"],
            )
            .order_by("id")
            .values_list("id", flat=True)
        )
        # Keep the first (earliest), delete the remainder.
        delete_ids = ids[1:]
        if delete_ids:
            deleted = Notification.objects.filter(id__in=delete_ids).delete()[0]
            total_deleted += deleted

    if total_deleted:
        logger.warning(
            "Deleted %s duplicate analysis notification(s) before adding the "
            "uniqueness constraint.",
            total_deleted,
        )
    else:
        logger.info("No duplicate analysis notifications found.")


def reverse_cleanup(apps, schema_editor):
    """No-op reverse for the dedup step.

    Reversing this migration drops the unique constraint/index automatically
    (Django reverses ``AddConstraint`` with ``RemoveConstraint``); only the
    one-time duplicate cleanup is irreversible — the deleted rows were invalid
    duplicates and cannot be restored.
    """
    pass


class Migration(migrations.Migration):
    # Non-atomic: the RunPython cleanup must commit before AddConstraint,
    # otherwise PostgreSQL raises "cannot CREATE INDEX ... pending trigger
    # events" when the constraint's partial index is built in the same
    # transaction as the deletes.
    atomic = False

    dependencies = [
        ("notifications", "0006_notification_analysis_and_more"),
    ]

    operations = [
        migrations.RunPython(cleanup_duplicate_analysis_notifications, reverse_cleanup),
        migrations.AddConstraint(
            model_name="notification",
            constraint=models.UniqueConstraint(
                fields=["analysis", "notification_type"],
                condition=models.Q(analysis__isnull=False),
                name="uniq_notification_per_analysis_type",
            ),
        ),
    ]
