"""
Data migration to convert annotation JSON from legacy verbose format
to compact format for storage efficiency.

Legacy format per page:
  {"bounds": {"top": 10, "bottom": 20, "left": 5, "right": 50},
   "tokensJsons": [{"pageIndex": 0, "tokenIndex": 3}],
   "rawText": "hello"}

Compact format per page:
  {"b": [5, 10, 50, 20], "t": [3], "r": "hello"}

This migration is reversible.
"""

from django.db import migrations


def compact_annotation_json_forward(annotation_json):
    """Convert legacy annotation JSON to compact format."""
    if not annotation_json or not isinstance(annotation_json, dict):
        return annotation_json

    # Skip if already compact (check first page entry)
    for page_data in annotation_json.values():
        if isinstance(page_data, dict):
            if "b" in page_data and "bounds" not in page_data:
                return annotation_json  # Already compact
            break

    result = {}
    for page_key, page_data in annotation_json.items():
        if not isinstance(page_data, dict):
            result[str(page_key)] = page_data
            continue

        bounds = page_data.get("bounds", {})
        tokens = page_data.get("tokensJsons", [])

        result[str(page_key)] = {
            "b": [
                bounds.get("left", 0),
                bounds.get("top", 0),
                bounds.get("right", 0),
                bounds.get("bottom", 0),
            ],
            "t": [t.get("tokenIndex", 0) for t in tokens if isinstance(t, dict)],
            "r": page_data.get("rawText", ""),
        }

    return result


def compact_annotation_json_reverse(annotation_json):
    """Convert compact annotation JSON back to legacy format."""
    if not annotation_json or not isinstance(annotation_json, dict):
        return annotation_json

    # Skip if already legacy (check first page entry)
    for page_data in annotation_json.values():
        if isinstance(page_data, dict):
            if "bounds" in page_data and "b" not in page_data:
                return annotation_json  # Already legacy
            break

    result = {}
    for page_key, page_data in annotation_json.items():
        if not isinstance(page_data, dict):
            result[str(page_key)] = page_data
            continue

        b = page_data.get("b", [0, 0, 0, 0])
        page_idx = int(page_key)

        result[str(page_key)] = {
            "bounds": {
                "left": b[0] if len(b) > 0 else 0,
                "top": b[1] if len(b) > 1 else 0,
                "right": b[2] if len(b) > 2 else 0,
                "bottom": b[3] if len(b) > 3 else 0,
            },
            "tokensJsons": [
                {"pageIndex": page_idx, "tokenIndex": idx}
                for idx in page_data.get("t", [])
            ],
            "rawText": page_data.get("r", ""),
        }

    return result


def forwards(apps, schema_editor):
    """Convert all annotation JSON fields to compact format in batches."""
    Annotation = apps.get_model("annotations", "Annotation")

    batch_size = 1000
    updated_count = 0

    # Process in batches to avoid memory issues
    last_pk = 0
    while True:
        batch = list(
            Annotation.objects.filter(pk__gt=last_pk)
            .exclude(json={})
            .exclude(json__isnull=True)
            .order_by("pk")
            .values_list("pk", "json")[:batch_size]
        )

        if not batch:
            break

        to_update = []
        for pk, json_data in batch:
            last_pk = pk
            if not json_data or not isinstance(json_data, dict):
                continue

            compacted = compact_annotation_json_forward(json_data)
            if compacted != json_data:
                to_update.append((pk, compacted))

        if to_update:
            for pk, compacted in to_update:
                Annotation.objects.filter(pk=pk).update(json=compacted)
            updated_count += len(to_update)

    if updated_count:
        print(f"\n  Compacted annotation JSON for {updated_count} annotations")


def backwards(apps, schema_editor):
    """Convert all annotation JSON fields back to legacy format in batches."""
    Annotation = apps.get_model("annotations", "Annotation")

    batch_size = 1000
    updated_count = 0

    last_pk = 0
    while True:
        batch = list(
            Annotation.objects.filter(pk__gt=last_pk)
            .exclude(json={})
            .exclude(json__isnull=True)
            .order_by("pk")
            .values_list("pk", "json")[:batch_size]
        )

        if not batch:
            break

        to_update = []
        for pk, json_data in batch:
            last_pk = pk
            if not json_data or not isinstance(json_data, dict):
                continue

            expanded = compact_annotation_json_reverse(json_data)
            if expanded != json_data:
                to_update.append((pk, expanded))

        if to_update:
            for pk, expanded in to_update:
                Annotation.objects.filter(pk=pk).update(json=expanded)
            updated_count += len(to_update)

    if updated_count:
        print(f"\n  Expanded annotation JSON for {updated_count} annotations")


class Migration(migrations.Migration):

    dependencies = [
        ("annotations", "0065_add_corpus_action_index"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
