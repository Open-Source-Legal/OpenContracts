"""Replace plaintext Analysis.callback_token with a SHA-256 hash column.

The callback token is the only credential the analyzer worker presents
when posting results back to OpenContracts. Storing it in plaintext means
a database read alone lets an attacker forge results for any in-flight
analysis. This migration:

1. Adds the new ``callback_token_hash`` column (CharField).
2. Backfills it by hashing the existing UUID ``callback_token`` value so
   in-flight analyzers (which still hold the original plaintext) keep
   working — the verification path will hash incoming candidates and
   compare against this column.
3. Drops the original ``callback_token`` column.
"""

from __future__ import annotations

import hashlib

from django.db import migrations, models


def backfill_token_hashes(apps, schema_editor):
    Analysis = apps.get_model("analyzer", "Analysis")
    for pk, raw_token in Analysis.objects.values_list("id", "callback_token"):
        if raw_token is None:
            continue
        digest = hashlib.sha256(str(raw_token).encode("utf-8")).hexdigest()
        Analysis.objects.filter(pk=pk).update(callback_token_hash=digest)


def restore_plaintext_tokens(apps, schema_editor):
    """Reverse migration is best-effort and intentionally lossy.

    The original UUIDs cannot be recovered from their SHA-256 hashes; this
    function exists so ``manage.py migrate analyzer 0020`` does not error.
    Each row receives a freshly-generated UUID so the column still has a
    valid value, but any in-flight analyzers will fail to authenticate.
    """
    import uuid

    Analysis = apps.get_model("analyzer", "Analysis")
    for analysis in Analysis.objects.all():
        analysis.callback_token = uuid.uuid4()
        analysis.save(update_fields=["callback_token"])


class Migration(migrations.Migration):

    dependencies = [
        ("analyzer", "0020_update_checkconstraint_check_to_condition"),
    ]

    operations = [
        migrations.AddField(
            model_name="analysis",
            name="callback_token_hash",
            field=models.CharField(
                blank=True, default="", editable=False, max_length=64
            ),
        ),
        migrations.RunPython(
            backfill_token_hashes, reverse_code=restore_plaintext_tokens
        ),
        migrations.RemoveField(
            model_name="analysis",
            name="callback_token",
        ),
    ]
