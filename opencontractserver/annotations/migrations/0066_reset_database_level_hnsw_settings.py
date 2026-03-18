"""
Reset database-level hnsw.iterative_scan and hnsw.ef_search settings.

Migration 0063 and init.sql used ALTER DATABASE SET to configure these GUCs.
This causes PostgreSQL 15 "invalid configuration parameter name" warnings
because the docker-entrypoint-initdb.d phase runs in a temporary postgres
instance without shared_preload_libraries=vector, so the hnsw.* GUCs aren't
registered when the database-level defaults are applied.

These settings are now applied via postgres command-line args (-c flags) in
the docker-compose files, which are processed after shared_preload_libraries
loads the vector library (guaranteeing GUC registration).

This migration cleans up the stale pg_db_role_setting entries from existing
databases. On fresh databases that never ran migration 0063, ALTER DATABASE
RESET on an unset parameter is a no-op (no exception raised). The exception
handler covers the case where pgvector is not loaded and the GUC names are
not registered.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("annotations", "0065_add_corpus_action_index"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                DO $$
                BEGIN
                    EXECUTE 'ALTER DATABASE '
                        || current_database()
                        || ' RESET hnsw.iterative_scan';
                    EXECUTE 'ALTER DATABASE '
                        || current_database()
                        || ' RESET hnsw.ef_search';
                EXCEPTION
                    WHEN undefined_object THEN NULL;
                    WHEN invalid_parameter_value THEN NULL;
                END $$;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
