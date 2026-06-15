import django.db.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("annotations", "0079_corpusreference_uniq_corpusref_source_type_nullkey"),
    ]

    operations = [
        migrations.AddField(
            model_name="corpusreference",
            name="jurisdiction",
            field=models.CharField(
                blank=True, db_index=True, max_length=64, null=True
            ),
        ),
        migrations.AddField(
            model_name="corpusreference",
            name="authority_type",
            field=models.CharField(
                blank=True, db_index=True, max_length=32, null=True
            ),
        ),
    ]
