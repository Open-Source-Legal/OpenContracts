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


_BACKFILL_CHUNK = 500


def backfill_token_hashes(apps, schema_editor):
    """Hash existing plaintext callback_tokens via ``bulk_update`` batches.

    SHA-256 can't be expressed in a single portable SQL expression, so the
    hashing has to happen in Python. We accumulate `_BACKFILL_CHUNK` rows
    of historical-model instances and flush them with ``bulk_update`` to
    keep round-trips to ``ceil(N / _BACKFILL_CHUNK)`` instead of N.
    """
    Analysis = apps.get_model("analyzer", "Analysis")
    queryset = Analysis.objects.exclude(callback_token__isnull=True)
    batch: list = []
    for analysis in queryset.iterator(chunk_size=_BACKFILL_CHUNK):
        analysis.callback_token_hash = hashlib.sha256(
            str(analysis.callback_token).encode("utf-8")
        ).hexdigest()
        batch.append(analysis)
        if len(batch) >= _BACKFILL_CHUNK:
            Analysis.objects.bulk_update(batch, ["callback_token_hash"])
            batch.clear()
    if batch:
        Analysis.objects.bulk_update(batch, ["callback_token_hash"])


def restore_plaintext_tokens(apps, schema_editor):
    """Reverse migration is best-effort and intentionally lossy.

    The original UUIDs cannot be recovered from their SHA-256 hashes; this
    function exists so ``manage.py migrate analyzer 0020`` does not error.
    Each row receives a freshly-generated UUID so the column still has a
    valid value, but any in-flight analyzers will fail to authenticate.

    Batches with ``bulk_update`` to keep round-trips bounded — reverse
    migrations are rarely run, but a downgrade against a large table
    shouldn't degenerate into N individual UPDATEs.
    """
    import uuid

    Analysis = apps.get_model("analyzer", "Analysis")
    batch: list = []
    for analysis in Analysis.objects.iterator(chunk_size=_BACKFILL_CHUNK):
        analysis.callback_token = uuid.uuid4()
        batch.append(analysis)
        if len(batch) >= _BACKFILL_CHUNK:
            Analysis.objects.bulk_update(batch, ["callback_token"])
            batch.clear()
    if batch:
        Analysis.objects.bulk_update(batch, ["callback_token"])


class Migration(migrations.Migration):
    """Atomic by design.

    Add/backfill/drop must be one transaction so a partial run cannot leave
    the column lacking a hash for live rows. The bulk_update path keeps the
    transaction short by minimising round-trips. For very large
    ``Analysis`` tables (10k+ rows), expect this migration to take a few
    seconds of write lock; schedule accordingly.
    """

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
