from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bulk_ingestion", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="bulkingestionitem",
            name="claimed_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When this item was claimed by a workstation for processing",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="bulkingestionitem",
            name="claimed_by",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Identifier of the workstation that claimed this item",
                max_length=255,
            ),
        ),
    ]
