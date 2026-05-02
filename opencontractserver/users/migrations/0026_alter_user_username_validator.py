from django.db import migrations, models

import opencontractserver.users.validators


class Migration(migrations.Migration):
    """Declare ``UserUnicodeUsernameValidator`` on ``User.username`` at the model layer."""

    dependencies = [
        ("users", "0025_alter_userexport_format_add_v2"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="username",
            field=models.CharField(
                error_messages={"unique": "A user with that username already exists."},
                help_text=(
                    "Required. 150 characters or fewer. Letters, digits and "
                    "@/./+/-/_/|/*/\\ only."
                ),
                max_length=150,
                unique=True,
                validators=[
                    opencontractserver.users.validators.UserUnicodeUsernameValidator()
                ],
                verbose_name="username",
            ),
        ),
    ]
