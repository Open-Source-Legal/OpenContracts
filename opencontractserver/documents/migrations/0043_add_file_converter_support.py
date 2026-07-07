import functools

import django.db.models
from django.conf import settings as django_settings
from django.db import migrations, models

from opencontractserver.shared.utils import calc_oc_file_path


def seed_default_file_converter(apps, schema_editor):
    """Seed the singleton's ``default_file_converter`` from Django settings.

    Intentionally a no-op when ``DEFAULT_FILE_CONVERTER`` is not defined or
    empty, so existing deployments keep the pre-parse conversion step disabled
    until an operator opts in via the admin System Settings UI.

    One-shot semantics: re-running ``migrate`` after a value has already been
    persisted will NOT re-seed it (the existing value is preserved by the
    ``not instance.default_file_converter`` guard).
    """
    PipelineSettings = apps.get_model("documents", "PipelineSettings")
    initial = getattr(django_settings, "DEFAULT_FILE_CONVERTER", "")
    if not initial:
        return
    # PipelineSettings is a singleton, but query by lowest PK rather than a
    # hardcoded ``pk=1`` so the seed still finds the row if the singleton was
    # ever recreated with a different PK (matches ``get_instance()`` semantics).
    instance = PipelineSettings.objects.order_by("pk").first()
    if instance is None:
        return
    if not instance.default_file_converter:
        instance.default_file_converter = initial
        instance.save(update_fields=["default_file_converter"])


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0042_pendingcorpusimport"),
    ]

    operations = [
        migrations.AddField(
            model_name="pipelinesettings",
            name="default_file_converter",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "File converter class path used to convert non-native "
                    "upload formats to PDF before parsing. Empty string "
                    "disables the conversion step."
                ),
                max_length=512,
            ),
        ),
        migrations.AddField(
            model_name="document",
            name="original_file",
            field=django.db.models.FileField(
                blank=True,
                max_length=1024,
                null=True,
                upload_to=functools.partial(
                    calc_oc_file_path, sub_folder="original_files"
                ),
            ),
        ),
        migrations.AddField(
            model_name="document",
            name="original_file_type",
            field=models.CharField(
                blank=True,
                default="",
                help_text="MIME type of the original upload before PDF conversion",
                max_length=255,
            ),
        ),
        migrations.RunPython(
            seed_default_file_converter, migrations.RunPython.noop
        ),
    ]
