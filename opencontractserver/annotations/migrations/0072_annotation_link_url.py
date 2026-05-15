from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("annotations", "0071_grounding_annotation_unique_constraints"),
    ]

    operations = [
        migrations.AddField(
            model_name="annotation",
            name="link_url",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Target URL opened when the annotation is clicked. "
                    "Only meaningful for annotations labelled OC_URL."
                ),
                max_length=2048,
                null=True,
            ),
        ),
    ]
