from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0042_pendingannotations_run_id_and_index"),
    ]

    operations = [
        migrations.AddField(
            model_name="pendingdocumentannotations",
            name="id_map",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
