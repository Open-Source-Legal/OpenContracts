"""
Add a pg_trgm GIN index on Annotation.raw_text for substring search.

The @-mention / discover annotation search matches ``raw_text`` with
``icontains`` (ILIKE '%term%') so users can find annotations by typing
word fragments and prefixes as they go — something the full-text
``search_vector`` column cannot do (FTS only matches whole, stemmed
lexemes). Without an index that ILIKE degrades to a sequential scan as
the annotation table grows.

This migration:
1. Enables the pg_trgm extension (CREATE EXTENSION IF NOT EXISTS) — but
   ONLY when the server has it available. The single-user desktop build
   runs the embedded ``pgserver`` Postgres, whose binaries bundle just
   ``plpgsql`` + ``vector`` (no contrib), so an unconditional
   ``TrigramExtension()`` hard-fails every desktop install mid-migrate.
   The queries this index accelerates are plain ``icontains`` — they run
   fine (as a sequential scan) without it, which is an acceptable trade
   on a personal-size desktop database.
2. Creates a GIN trigram index on raw_text so ILIKE substring queries
   stay index-backed wherever the extension exists (every compose /
   production deployment).

Uses SeparateDatabaseAndState so Django's migration state tracks the
GinIndex (matching the model Meta) while the database side runs
conditionally via RunPython, using CREATE INDEX CONCURRENTLY to avoid
locking annotations_annotation on large deployments. Requires
atomic = False for CONCURRENTLY.

INVARIANT for future changes to ``Annotation.raw_text``: migration state
always claims ``annotation_raw_text_trgm_gin`` exists, but on databases
without pg_trgm (the embedded desktop build) it does NOT exist in the DB.
Any future schema operation Django derives from state that drops or
recreates this index must stay tolerant of its absence (IF EXISTS /
conditional RunPython like below), or it will crash desktop upgrades.

Reversal note: the reverse drops only the index and deliberately leaves
pg_trgm installed. (The previous ``TrigramExtension().reverse`` ran
``DROP EXTENSION pg_trgm`` unconditionally, which raises ``cannot drop
extension pg_trgm because other objects depend on it`` whenever any
other object still uses ``gin_trgm_ops`` and leaves migration state
inconsistent.)
"""

import django.contrib.postgres.indexes
from django.db import migrations


def _pg_trgm_available(schema_editor) -> bool:
    if schema_editor.connection.vendor != "postgresql":
        return False
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_available_extensions WHERE name = 'pg_trgm';")
        return cursor.fetchone() is not None


def _add_trigram_index(apps, schema_editor):
    if not _pg_trgm_available(schema_editor):
        print(
            "\n  pg_trgm is not available on this PostgreSQL server "
            "(e.g. the embedded desktop build); skipping the "
            "annotation_raw_text_trgm_gin index. Substring search still "
            "works, unindexed."
        )
        return
    schema_editor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
    schema_editor.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
        "annotation_raw_text_trgm_gin "
        "ON annotations_annotation "
        "USING gin (raw_text gin_trgm_ops);"
    )


def _drop_trigram_index(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        "DROP INDEX CONCURRENTLY IF EXISTS annotation_raw_text_trgm_gin;"
    )


class Migration(migrations.Migration):
    atomic = False  # Required for CREATE INDEX CONCURRENTLY

    dependencies = [
        ("annotations", "0073_embedding_relationship"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddIndex(
                    model_name="annotation",
                    index=django.contrib.postgres.indexes.GinIndex(
                        fields=["raw_text"],
                        name="annotation_raw_text_trgm_gin",
                        opclasses=["gin_trgm_ops"],
                    ),
                ),
            ],
            database_operations=[
                migrations.RunPython(
                    _add_trigram_index,
                    _drop_trigram_index,
                    # Inherit the migration's atomic=False: CONCURRENTLY
                    # cannot run inside a transaction block.
                ),
            ],
        ),
    ]
