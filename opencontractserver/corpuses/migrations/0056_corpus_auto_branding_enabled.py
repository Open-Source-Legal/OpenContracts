from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("corpuses", "0055_drop_legacy_description_storage"),
    ]

    operations = [
        migrations.AddField(
            model_name="corpus",
            name="auto_branding_enabled",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "When True, auto-generate a logo and Readme.CAML article on "
                    "creation if no icon was uploaded. Set False to opt this corpus "
                    "out of auto-branding."
                ),
            ),
        ),
    ]
