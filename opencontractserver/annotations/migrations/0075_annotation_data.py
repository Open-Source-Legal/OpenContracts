"""Add ``Annotation.data`` JSONField — structured metadata sidecar.

Distinct from ``Annotation.json`` (positional bounds / span offsets), the
``data`` column stores label-specific state that downstream consumers query
directly. First consumer is the geocoding pipeline (issue #1819): rows
labelled ``OC_COUNTRY`` / ``OC_STATE`` / ``OC_CITY`` cache the resolved
``{canonical_name, lat, lng, admin_codes, geocoded}`` here so the map
aggregation service (issues #1820 / #1821) can group pins without rerunning
the geocoder.

Nullable so existing annotations need no backfill — the geocoding consumer
writes a dict on creation, every other label leaves the column ``NULL``.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("annotations", "0074_annotation_raw_text_trigram_index"),
    ]

    operations = [
        migrations.AddField(
            model_name="annotation",
            name="data",
            field=models.JSONField(
                blank=True,
                help_text=(
                    "Structured metadata sidecar for label-specific state "
                    "(e.g. geocoded place coordinates for "
                    "OC_COUNTRY/OC_STATE/OC_CITY)."
                ),
                null=True,
            ),
        ),
    ]
