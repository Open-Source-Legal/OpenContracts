from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("annotations", "0089_authorityfrontier_deferred_cap_state"),
    ]

    operations = [
        migrations.AddField(
            model_name="corpusreference",
            name="is_provisional",
            # Schema-only: default False means every existing row is finalized.
            field=models.BooleanField(db_index=True, default=False),
        ),
    ]
