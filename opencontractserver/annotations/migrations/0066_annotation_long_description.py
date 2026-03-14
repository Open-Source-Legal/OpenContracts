from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("annotations", "0065_add_corpus_action_index"),
    ]

    operations = [
        migrations.AddField(
            model_name="annotation",
            name="long_description",
            field=models.TextField(
                blank=True,
                help_text=(
                    "Optional markdown description for this annotation, "
                    "e.g. a section summary in a document index."
                ),
                null=True,
            ),
        ),
    ]
