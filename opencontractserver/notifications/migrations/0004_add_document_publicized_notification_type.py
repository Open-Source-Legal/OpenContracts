"""Add DOCUMENT_PUBLICIZED notification type for I-1 corpus public-flip cascade."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0003_alter_notification_notification_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notification",
            name="notification_type",
            field=models.CharField(
                choices=[
                    ("REPLY", "Reply to Message"),
                    ("VOTE", "Vote on Message"),
                    ("BADGE", "Badge Awarded"),
                    ("MENTION", "Mentioned in Message"),
                    ("ACCEPTED", "Answer Accepted"),
                    ("THREAD_LOCKED", "Thread Locked"),
                    ("THREAD_UNLOCKED", "Thread Unlocked"),
                    ("THREAD_PINNED", "Thread Pinned"),
                    ("THREAD_UNPINNED", "Thread Unpinned"),
                    ("MESSAGE_DELETED", "Message Deleted"),
                    ("THREAD_DELETED", "Thread Deleted"),
                    ("MESSAGE_RESTORED", "Message Restored"),
                    ("THREAD_RESTORED", "Thread Restored"),
                    ("THREAD_REPLY", "Reply in Thread You're Participating In"),
                    ("DOCUMENT_PROCESSED", "Document Processing Complete"),
                    ("DOCUMENT_PROCESSING_FAILED", "Document Processing Failed"),
                    ("EXTRACT_COMPLETE", "Extract Complete"),
                    ("ANALYSIS_COMPLETE", "Analysis Complete"),
                    ("ANALYSIS_FAILED", "Analysis Failed"),
                    ("EXPORT_COMPLETE", "Export Complete"),
                    ("DOCUMENT_PUBLICIZED", "Document Made Public via Corpus"),
                ],
                help_text="Type of notification",
                max_length=30,
            ),
        ),
    ]
