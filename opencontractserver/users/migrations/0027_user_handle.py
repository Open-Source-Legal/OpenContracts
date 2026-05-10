# Schema migration adding the auto-assigned display handle.
#
# Backfill is performed in the follow-on migration ``0028_backfill_user_handles``
# so the schema change is observable on its own and the data migration can be
# re-run via the ``regenerate_user_handles`` management command without
# touching the schema.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0026_alter_user_username_validator"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="handle",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Auto-assigned Reddit-style handle (e.g. 'cleverFox', "
                    "'cleverFox42'). Used by the displayName resolver when "
                    "Auth0 name claims are absent. User-facing editing is out "
                    "of scope for the initial rollout."
                ),
                max_length=64,
                null=True,
                unique=True,
                verbose_name="Display Handle",
            ),
        ),
    ]
