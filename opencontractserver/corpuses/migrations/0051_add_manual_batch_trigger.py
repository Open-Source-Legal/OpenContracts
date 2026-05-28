"""Add ``MANUAL_BATCH`` to ``CorpusActionTrigger`` choices.

Choice-only schema change — no column type or constraint change. The new
trigger value is used by ``CorpusActionExecution`` rows produced by the
``StartCorpusActionBatchRun`` GraphQL mutation so manual-batch runs are
distinguishable from auto-fired ``ADD_DOCUMENT`` / ``EDIT_DOCUMENT``
executions in the audit trail.

Three fields share ``CorpusActionTrigger.choices`` and are re-altered here
for completeness, even though the choices argument is enforced at the
Python level (Django emits ``AlterField`` regardless when ``choices``
changes).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("corpuses", "0050_corpus_description_preview"),
    ]

    operations = [
        migrations.AlterField(
            model_name="corpusaction",
            name="trigger",
            field=models.CharField(
                choices=[
                    ("add_document", "Add Document"),
                    ("edit_document", "Edit Document"),
                    ("new_thread", "New Thread Created"),
                    ("new_message", "New Message Posted"),
                    ("manual_batch", "Manual Batch Run"),
                ],
                max_length=256,
            ),
        ),
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
        migrations.AlterField(
            model_name="corpusactiontemplate",
            name="trigger",
            field=models.CharField(
                choices=[
                    ("add_document", "Add Document"),
                    ("edit_document", "Edit Document"),
                    ("new_thread", "New Thread Created"),
                    ("new_message", "New Message Posted"),
                    ("manual_batch", "Manual Batch Run"),
                ],
                max_length=256,
            ),
        ),
    ]
