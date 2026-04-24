from django.db import migrations, models

import opencontractserver.users.validators


class Migration(migrations.Migration):
    """
    Declare the OpenContracts-specific ``UserUnicodeUsernameValidator`` on the
    ``User.username`` field at the model layer.

    Previously the replacement was performed inside ``User.__init__`` by
    mutating ``self._meta.get_field("username").validators[0]``. That mutated a
    shared field-level list on every instantiation and was fragile against any
    third-party code that added its own validator to the same list (see issue
    #1358).
    """

    dependencies = [
        ("users", "0025_alter_userexport_format_add_v2"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="username",
            field=models.CharField(
                error_messages={
                    "unique": "A user with that username already exists."
                },
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
