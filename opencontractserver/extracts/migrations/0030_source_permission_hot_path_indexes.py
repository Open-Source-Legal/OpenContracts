from django.db import migrations


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("extracts", "0029_extract_iterations"),
    ]

    operations = [
        migrations.RunSQL(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ext_uop_perm_user_obj_idx
            ON extracts_extractuserobjectpermission
            (permission_id, user_id, content_object_id);
            """,
            reverse_sql=(
                "DROP INDEX CONCURRENTLY IF EXISTS ext_uop_perm_user_obj_idx;"
            ),
        ),
        migrations.RunSQL(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ext_gop_perm_grp_obj_idx
            ON extracts_extractgroupobjectpermission
            (permission_id, group_id, content_object_id);
            """,
            reverse_sql=(
                "DROP INDEX CONCURRENTLY IF EXISTS ext_gop_perm_grp_obj_idx;"
            ),
        ),
    ]
