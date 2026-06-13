from django.db import migrations


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("analyzer", "0022_alter_analysis_status"),
    ]

    operations = [
        migrations.RunSQL(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS anl_uop_perm_user_obj_idx
            ON analyzer_analysisuserobjectpermission
            (permission_id, user_id, content_object_id);
            """,
            reverse_sql=(
                "DROP INDEX CONCURRENTLY IF EXISTS anl_uop_perm_user_obj_idx;"
            ),
        ),
        migrations.RunSQL(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS anl_gop_perm_grp_obj_idx
            ON analyzer_analysisgroupobjectpermission
            (permission_id, group_id, content_object_id);
            """,
            reverse_sql=(
                "DROP INDEX CONCURRENTLY IF EXISTS anl_gop_perm_grp_obj_idx;"
            ),
        ),
    ]
