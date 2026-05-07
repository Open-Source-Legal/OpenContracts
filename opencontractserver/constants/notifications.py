"""Constants for notification creation and delivery."""

# Cap for ``Notification.objects.bulk_create`` batches when fanning out
# notifications across thousands of cross-owner documents (e.g., corpus
# public-flip cascades). Bounded to avoid a single oversized SQL statement.
NOTIFICATION_BULK_CREATE_BATCH_SIZE: int = 500
