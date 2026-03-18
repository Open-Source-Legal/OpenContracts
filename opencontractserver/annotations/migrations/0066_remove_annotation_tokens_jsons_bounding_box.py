"""Remove dead fields tokens_jsons and bounding_box from Annotation model.

These fields were redundant with the ``json`` field which stores all
annotation positioning data (bounds, token references) in a structured
per-page format.  Neither field was read or populated by any code path
in production (parsers, export, import, GraphQL, frontend).

A ``RunPython`` step runs first to backfill ``json`` from the legacy
fields for any rows where ``json`` is empty but the legacy fields
contain data.  Rows that already have a non-empty ``json`` value are
intentionally skipped.  Backfilled rows are written in v1 format and
will be lazily compacted to v2 on the next ``Annotation.save()`` call.

NOTE: This migration is irreversible.
"""

from django.db import migrations, models


def backfill_json_from_legacy_fields(apps, schema_editor):
    """Copy tokens_jsons/bounding_box into json for rows where json is empty."""
    Annotation = apps.get_model("annotations", "Annotation")

    # Find annotations where json is empty/null but legacy fields have data.
    # Use explicit Q objects: json__in=[{}, None] may not match DB-level NULL
    # reliably across PostgreSQL versions, so we use json__isnull=True as well.
    qs = Annotation.objects.filter(
        models.Q(json__isnull=True) | models.Q(json={}),
    ).exclude(
        models.Q(tokens_jsons__isnull=True) | models.Q(tokens_jsons=[]),
    )

    updated = 0
    for annot in qs.iterator(chunk_size=1000):
        tokens_jsons = annot.tokens_jsons or []
        bounding_box = annot.bounding_box or {}

        if not tokens_jsons:
            continue

        # Rebuild a v1-style json payload from the legacy fields.
        # tokens_jsons is a flat list of {pageIndex, tokenIndex} dicts;
        # group them by page and attach the bounding_box to each page.
        #
        # NOTE: The legacy bounding_box field was a single annotation-level
        # dict, not per-page.  For multi-page annotations the same box is
        # assigned to every page entry.  This is acceptable because (a) the
        # legacy bounding_box was never page-specific in the old schema, and
        # (b) the authoritative bounds come from the json field (which we are
        # backfilling here only for rows that had no json at all).
        pages: dict[str, dict] = {}
        for tok in tokens_jsons:
            if not isinstance(tok, dict):
                continue
            page_key = str(tok.get("pageIndex", 0))
            if page_key not in pages:
                pages[page_key] = {
                    "bounds": bounding_box if isinstance(bounding_box, dict) else {},
                    "tokensJsons": [],
                    "rawText": annot.raw_text or "",
                }
            pages[page_key]["tokensJsons"].append(tok)

        if pages:
            Annotation.objects.filter(pk=annot.pk).update(json=pages)
            updated += 1

    if updated:
        print(f"  Backfilled json for {updated} annotation(s) from legacy fields.")


class Migration(migrations.Migration):

    dependencies = [
        ("annotations", "0065_add_corpus_action_index"),
    ]

    operations = [
        migrations.RunPython(
            backfill_json_from_legacy_fields,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.RemoveField(
            model_name="annotation",
            name="tokens_jsons",
        ),
        migrations.RemoveField(
            model_name="annotation",
            name="bounding_box",
        ),
    ]
