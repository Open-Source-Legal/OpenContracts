# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("corpuses", "0036_alter_corpusquerygroupobjectpermission_unique_together_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="corpus",
            name="is_system_corpus",
            field=models.BooleanField(
                default=False,
                help_text="System-managed corpus (e.g., 'My Documents'). Cannot be deleted by users.",
            ),
        ),
    ]
