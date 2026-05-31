"""Remove md_description column and CorpusDescriptionRevision table.

Forward-only. By the time this migration runs, 0054
(canonical_caml_backfill) has migrated all md_description content into
Readme.CAML Documents and replayed every CorpusDescriptionRevision row as
a version-tree sibling (after 0053 added the readme_caml_document FK). The
data is durable in those Documents; this migration cleans up the now-empty
legacy storage.

Spec: docs/superpowers/specs/2026-05-27-canonical-caml-description-refactor-design.md §4.9
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("corpuses", "0054_canonical_caml_backfill"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="corpusdescriptionrevision",
            unique_together=None,
        ),
        migrations.RemoveField(
            model_name="corpusdescriptionrevision",
            name="author",
        ),
        migrations.RemoveField(
            model_name="corpusdescriptionrevision",
            name="corpus",
        ),
        migrations.RemoveField(
            model_name="corpus",
            name="md_description",
        ),
        migrations.DeleteModel(
            name="CorpusDescriptionRevision",
        ),
    ]
