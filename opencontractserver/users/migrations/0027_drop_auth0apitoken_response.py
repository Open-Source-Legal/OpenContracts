from django.db import migrations


class Migration(migrations.Migration):
    """Drop the unused ``Auth0APIToken.auth0_Response`` text column.

    The column duplicated the access token already stored in ``token`` along
    with other fields from the upstream response that were never read back.
    Removing it shrinks the row and avoids retaining unnecessary data.
    """

    dependencies = [
        ("users", "0026_alter_user_username_validator"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="auth0apitoken",
            name="auth0_Response",
        ),
    ]
