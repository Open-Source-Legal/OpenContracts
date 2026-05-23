"""
Add a pg_trgm GIN index on Annotation.raw_text for substring search.

The @-mention / discover annotation search matches ``raw_text`` with
``icontains`` (ILIKE '%term%') so users can find annotations by typing
word fragments and prefixes as they go — something the full-text
``search_vector`` column cannot do (FTS only matches whole, stemmed
lexemes). Without an index that ILIKE degrades to a sequential scan as
the annotation table grows.

This migration:
1. Enables the pg_trgm extension (a trusted extension; CREATE EXTENSION
   IF NOT EXISTS via TrigramExtension).
2. Creates a GIN trigram index on raw_text so ILIKE substring queries
   stay index-backed.

Uses SeparateDatabaseAndState so Django's migration state tracks the
GinIndex (matching the model Meta) while the database operation uses
CREATE INDEX CONCURRENTLY to avoid locking annotations_annotation on
large deployments. Requires atomic = False for CONCURRENTLY.
"""

import django.contrib.postgres.indexes
from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations


class Migration(migrations.Migration):
    atomic = False  # Required for CREATE INDEX CONCURRENTLY

    dependencies = [
        ("annotations", "0073_embedding_relationship"),
    ]

    operations = [
        # pg_trgm provides the gin_trgm_ops operator class used by the
        # index below. Must run before the index is created.
        #
        # Reversal hazard: TrigramExtension.reverse runs ``DROP EXTENSION
        # pg_trgm`` unconditionally. Rolling 0074 backwards in a database
        # where any *other* object still uses ``gin_trgm_ops`` (a different
        # trigram index, a pre-existing external use, or a partial-forward
        # state) will raise ``cannot drop extension pg_trgm because other
        # objects depend on it`` and leave the migration state inconsistent.
        # Forward path is safe (IF NOT EXISTS is idempotent); reversal must
        # only be attempted on databases known to have no other pg_trgm
        # dependencies.
        TrigramExtension(),
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
                migrations.RunSQL(
                    sql=(
                        "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
                        "annotation_raw_text_trgm_gin "
                        "ON annotations_annotation "
                        "USING gin (raw_text gin_trgm_ops);"
                    ),
                    reverse_sql=(
                        "DROP INDEX CONCURRENTLY IF EXISTS "
                        "annotation_raw_text_trgm_gin;"
                    ),
                ),
            ],
        ),
    ]
