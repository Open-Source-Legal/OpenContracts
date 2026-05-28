"""Add ``description_preview`` to Corpus and backfill from existing values.

``description_preview`` is an auto-maintained short summary derived from
``description``. It exists so card layouts and hero subtitles never spill
into a wall of raw text. The model's ``save()`` recomputes it on every
write, so this migration's only responsibility is creating the column and
populating it for existing rows.
"""

from django.db import migrations, models


def backfill_description_preview(apps, schema_editor):
    """Populate ``description_preview`` for every existing Corpus row.

    We can't call ``Corpus._summarize_for_preview`` on the historical model
    apps registry directly (it's a staticmethod on the *current* model, not
    historical), so we import the helper from the live model module. The
    helper is pure-string-manipulation with no ORM access, so calling it
    from a data migration is safe.
    """
    from opencontractserver.corpuses.models import Corpus as LiveCorpus

    Corpus = apps.get_model("corpuses", "Corpus")
    # Chunked bulk_update so the migration scales to corpora counts in the
    # thousands without issuing one UPDATE per row.
    batch_size = 500
    batch: list = []
    for corpus in Corpus.objects.only("id", "description").iterator():
        corpus.description_preview = LiveCorpus._summarize_for_preview(
            corpus.description or ""
        )
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
