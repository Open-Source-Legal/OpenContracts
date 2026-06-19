from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("annotations", "0090_corpusreference_is_provisional"),
    ]

    operations = [
        migrations.AlterField(
            model_name="authoritykeyequivalence",
            name="source",
            field=models.CharField(
                choices=[
                    ("uslm", "OLRC USLM sourceCredit"),
                    ("popular_name", "USC popular-name table"),
                    ("baseline", "Shipped baseline (loader-managed)"),
                    ("manual", "Hand-curated (runtime override)"),
                ],
                default="uslm",
                max_length=32,
            ),
        ),
    ]
