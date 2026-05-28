"""Add ``MANUAL_BATCH`` to ``CorpusActionExecution.trigger`` choices only."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("corpuses", "0050_corpus_description_preview"),
    ]

    operations = [
        migrations.AlterField(
            model_name="corpusactionexecution",
            name="trigger",
            field=models.CharField(
                choices=[
                    ("add_document", "Add Document"),
                    ("edit_document", "Edit Document"),
                    ("new_thread", "New Thread Created"),
                    ("new_message", "New Message Posted"),
                    ("manual_batch", "Manual Batch Run"),
                ],
                help_text="What triggered this execution",
                max_length=128,
            ),
        ),
    ]
