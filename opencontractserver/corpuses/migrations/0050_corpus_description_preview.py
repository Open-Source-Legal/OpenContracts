"""Add ``description_preview`` to Corpus and backfill from existing values.

``description_preview`` is an auto-maintained short summary derived from
``description``. It exists so card layouts and hero subtitles never spill
into a wall of raw text. The model's ``save()`` recomputes it on every
write, so this migration's only responsibility is creating the column and
populating it for existing rows.
"""

import re

from django.db import migrations, models


# Frozen snapshot of ``MAX_CORPUS_DESCRIPTION_PREVIEW_LENGTH`` at the time this
# migration was written. Migrations are historical snapshots, so the preview
# derivation is inlined here rather than imported from the live
# ``description_cache`` service — a future rename/signature change to that
# module must not break this historical migration on fresh installs.
_PREVIEW_MAX_LENGTH = 280


def _summarize_for_preview(plain_text: str) -> str:
    """Migration-local copy of ``description_cache.summarize_for_preview``.

    Pure string manipulation, no ORM access — safe to call from a data
    migration and self-contained against future service-module changes.
    """
    if not plain_text:
        return ""
    first_paragraph = plain_text.split("\n\n", 1)[0].strip()
    first_paragraph = re.sub(r"\s+", " ", first_paragraph)
    if len(first_paragraph) <= _PREVIEW_MAX_LENGTH:
        return first_paragraph
    cut = first_paragraph[:_PREVIEW_MAX_LENGTH]
    last_space = cut.rfind(" ")
    if last_space > _PREVIEW_MAX_LENGTH // 2:
        cut = cut[:last_space]
    return cut.rstrip() + "…"


def backfill_description_preview(apps, schema_editor):
    """Populate ``description_preview`` for every existing Corpus row.

    The previewing helper used to live as ``Corpus._summarize_for_preview``
    and was relocated to ``opencontractserver.corpuses.services.description_cache``
    during the Canonical-CAML refactor. To keep this historical migration
    self-contained (per Django's migration-snapshot guidance), the derivation
    is inlined above as ``_summarize_for_preview`` rather than imported from
    the live service module.
    """
    Corpus = apps.get_model("corpuses", "Corpus")
    # Chunked bulk_update so the migration scales to corpora counts in the
    # thousands without issuing one UPDATE per row.
    batch_size = 500
    batch: list = []
    for corpus in Corpus.objects.only("id", "description").iterator():
        corpus.description_preview = _summarize_for_preview(corpus.description or "")
        batch.append(corpus)
        if len(batch) >= batch_size:
            Corpus.objects.bulk_update(batch, ["description_preview"])
            batch.clear()
    if batch:
        Corpus.objects.bulk_update(batch, ["description_preview"])


def noop_reverse(apps, schema_editor):
    """No-op on reverse — the column is dropped by the AddField rollback."""
    return None


class Migration(migrations.Migration):

    dependencies = [
        ("corpuses", "0049_corpusvote_corpus_upvote_count_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="corpus",
            name="description_preview",
            field=models.TextField(
                blank=True,
                default="",
                editable=False,
                help_text=(
                    "Auto-generated truncated plain-text preview derived from "
                    "``description``. Used by card layouts, list snippets, "
                    "and hero subtitles so users never see a wall of raw "
                    "text. Capped at "
                    "``MAX_CORPUS_DESCRIPTION_PREVIEW_LENGTH`` characters."
                ),
            ),
        ),
        migrations.RunPython(backfill_description_preview, noop_reverse),
    ]
