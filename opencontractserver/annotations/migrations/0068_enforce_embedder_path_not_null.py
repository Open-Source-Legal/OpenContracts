"""
Backfill any legacy Embedding rows with NULL ``embedder_path`` and then
tighten the column to ``NOT NULL``.

Context (issue #1357): ``Embedding.embedder_path`` was declared
``null=True, blank=True`` on the Django field while its Python annotation
claimed ``str``. The partial unique constraints added in migration 0059
reference ``embedder_path`` with ``condition=Q(<parent>__isnull=False)``,
meaning any row where ``embedder_path`` is NULL silently bypasses duplicate
prevention. Every production creation path (store_embedding, add_embedding,
worker_uploads) already supplies a concrete value, so we enforce the
invariant at the DB level to match.

Backfill strategy:
  1. For each NULL-embedder_path row, set ``embedder_path`` to
     ``settings.DEFAULT_EMBEDDER``.
  2. If that assignment would collide with an existing (embedder_path,
     parent) row under a partial unique constraint, delete the NULL row
     instead — it cannot be matched by any query (all call sites filter
     on a concrete ``embedder_path``) so it was effectively dead data.
"""

import logging

from django.conf import settings
from django.db import IntegrityError, migrations, models, transaction

logger = logging.getLogger(__name__)


def backfill_null_embedder_paths(apps, schema_editor):
    Embedding = apps.get_model("annotations", "Embedding")

    total = Embedding.objects.filter(embedder_path__isnull=True).count()
    if total == 0:
        logger.info("No Embedding rows with NULL embedder_path — nothing to backfill.")
        return

    # Refuse to run if there's no default to backfill with — silently deleting
    # embedding rows because of a misconfigured env var would be irreversible.
    default_embedder_path = getattr(settings, "DEFAULT_EMBEDDER", "") or ""
    if not default_embedder_path:
        raise ValueError(
            f"settings.DEFAULT_EMBEDDER is empty but {total} Embedding row(s) "
            "have NULL embedder_path. Set DEFAULT_EMBEDDER (or manually clean "
            "up the NULL rows) before running this migration."
        )

    backfilled = 0
    deleted = 0

    # Keyset pagination: re-query each chunk for rows that still match the
    # NULL predicate AND have pk > the previous batch's max. Using
    # `.iterator(chunk_size=N)` here would be unsafe because we mutate or
    # delete every row we visit, and OFFSET-based chunking against a
    # shrinking result set would silently skip rows.
    chunk_size = 500
    last_pk = 0
    while True:
        batch = list(
            Embedding.objects.filter(
                embedder_path__isnull=True, pk__gt=last_pk
            ).order_by("pk")[:chunk_size]
        )
        if not batch:
            break
        for emb in batch:
            emb.embedder_path = default_embedder_path
            try:
                with transaction.atomic():
                    emb.save(update_fields=["embedder_path"])
                backfilled += 1
            except IntegrityError:
                # A (default_embedder_path, parent) row already exists and is
                # covered by the partial unique constraint. The legacy NULL row
                # cannot be queried (no call site filters on NULL), so dropping
                # it is a lossless cleanup.
                logger.info(
                    "Dropping NULL-embedder_path Embedding id=%s: backfill to %r "
                    "would duplicate an existing row under the partial unique "
                    "constraint.",
                    emb.pk,
                    default_embedder_path,
                )
                emb.delete()
                deleted += 1
        last_pk = batch[-1].pk

    if backfilled + deleted != total:
        logger.warning(
            "Embedding.embedder_path backfill: processed %s != initial NULL count %s "
            "(backfilled=%s, deleted=%s). Some rows may have been added/removed by "
            "concurrent traffic during the migration.",
            backfilled + deleted,
            total,
            backfilled,
            deleted,
        )
    logger.info(
        "Embedding.embedder_path backfill complete: backfilled=%s, deleted=%s, "
        "initial_null_count=%s.",
        backfilled,
        deleted,
        total,
    )


def reverse_backfill(apps, schema_editor):
    """No-op: we cannot restore rows that were deleted, and re-nulling
    backfilled rows would be indistinguishable from values that have always
    been ``settings.DEFAULT_EMBEDDER``."""


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("annotations", "0067_merge_20260316_0312"),
    ]

    operations = [
        migrations.RunPython(backfill_null_embedder_paths, reverse_backfill),
        migrations.AlterField(
            model_name="embedding",
            name="embedder_path",
            field=models.CharField(
                help_text=(
                    "Identifier for the embedding model or pipeline used "
                    "(e.g. 'openai/text-embedding-ada-002')."
                ),
                max_length=256,
            ),
        ),
    ]
