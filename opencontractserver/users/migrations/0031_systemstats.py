import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0030_user_profile_about_markdown_user_profile_headline_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="SystemStats",
            fields=[
                (
                    "id",
                    models.PositiveSmallIntegerField(
                        default=1,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("user_count", models.PositiveBigIntegerField(default=0)),
                ("document_count", models.PositiveBigIntegerField(default=0)),
                ("corpus_count", models.PositiveBigIntegerField(default=0)),
                (
                    "annotation_count",
                    models.PositiveBigIntegerField(
                        default=0,
                        help_text="Non-structural annotations (matches telemetry).",
                    ),
                ),
                ("conversation_count", models.PositiveBigIntegerField(default=0)),
                ("message_count", models.PositiveBigIntegerField(default=0)),
                (
                    "computed_at",
                    models.DateTimeField(
                        blank=True,
                        help_text=(
                            "When the snapshot was last recomputed; null until "
                            "first run."
                        ),
                        null=True,
                    ),
                ),
                (
                    "created",
                    models.DateTimeField(
                        default=django.utils.timezone.now, editable=False
                    ),
                ),
                ("modified", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "System Stats",
                "verbose_name_plural": "System Stats",
            },
        ),
    ]
