import django.contrib.postgres.indexes
import django.contrib.postgres.search
from django.db import migrations


class Migration(migrations.Migration):
    """Add full-text search to ``Note`` (mirrors Annotation migration 0063).

    Notes previously had no ``search_vector`` column, so Discover note search
    could only use ``LIKE '%…%'`` (no stemming, no index, sequential scan).
    This adds a trigger-maintained ``tsvector`` built from ``title`` + ``content``
    plus a GIN index, enabling the same hybrid FTS path the annotation search
    already uses.
    """

    atomic = False

    dependencies = [
        ("annotations", "0075_annotation_data"),
    ]

    operations = [
        # =================================================================
        # Phase 1: Add the SearchVectorField column
        # =================================================================
        migrations.AddField(
            model_name="note",
            name="search_vector",
            field=django.contrib.postgres.search.SearchVectorField(null=True),
        ),
        # =================================================================
        # Phase 2: GIN index for fast full-text search (CONCURRENTLY so the
        # build does not hold a write lock on annotations_note)
        # =================================================================
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddIndex(
                    model_name="note",
                    index=django.contrib.postgres.indexes.GinIndex(
                        fields=["search_vector"],
                        name="note_search_vector_gin",
                    ),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
                        "note_search_vector_gin "
                        "ON annotations_note USING gin (search_vector);"
                    ),
                    reverse_sql=(
                        "DROP INDEX CONCURRENTLY IF EXISTS note_search_vector_gin;"
                    ),
                ),
            ],
        ),
        # =================================================================
        # Phase 3: Trigger to auto-populate search_vector from title + content
        # =================================================================
        # NOTE(deferred): FTS config hardcodes 'english', matching the
        # annotation trigger. Multilingual corpora will need per-corpus or
        # per-document text search configuration.
        migrations.RunSQL(
            sql="""
                CREATE OR REPLACE FUNCTION note_search_vector_update()
                RETURNS trigger AS $$
                BEGIN
                    NEW.search_vector :=
                        to_tsvector(
                            'english',
                            COALESCE(NEW.title, '') || ' ' || COALESCE(NEW.content, '')
                        );
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;

                CREATE TRIGGER note_search_vector_trigger
                    BEFORE INSERT OR UPDATE OF title, content
                    ON annotations_note
                    FOR EACH ROW
                    EXECUTE FUNCTION note_search_vector_update();
            """,
            reverse_sql="""
                DROP TRIGGER IF EXISTS note_search_vector_trigger
                    ON annotations_note;
                DROP FUNCTION IF EXISTS note_search_vector_update();
            """,
        ),
        # =================================================================
        # Phase 4: Backfill search_vector for existing notes
        # =================================================================
        # !! LARGE-TABLE WARNING !!
        # Single unbounded UPDATE across all NULL rows. Note volumes are far
        # smaller than annotations, but for very large deployments chunk this
        # manually during a maintenance window (see migration 0063 notes).
        migrations.RunSQL(
            sql="""
                DO $$
                DECLARE
                    row_count BIGINT;
                BEGIN
                    UPDATE annotations_note
                    SET search_vector = to_tsvector(
                        'english',
                        COALESCE(title, '') || ' ' || COALESCE(content, '')
                    )
                    WHERE search_vector IS NULL;

                    GET DIAGNOSTICS row_count = ROW_COUNT;
                    RAISE NOTICE 'Note search_vector backfill: % rows updated',
                        row_count;
                END $$;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
