from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("annotations", "0083_backfill_corpusreference_classification"),
    ]

    operations = [
        migrations.AddField(
            model_name="corpusreference",
            name="detection_tier",
            field=models.CharField(db_index=True, default="registry", max_length=16),
        ),
        migrations.AddField(
            model_name="corpusreference",
            name="detection_confidence",
            field=models.FloatField(default=1.0),
        ),
    ]
