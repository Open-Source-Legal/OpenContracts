"""Add a ``(structural, modified)`` composite index to ``Annotation`` (issue #1906).

Tier 3 of #1908 rewrote ``AnnotationQuerySet.visible_to_user`` to express
document / corpus / structural-set visibility as correlated ``EXISTS``
subqueries rather than a ``structural_set__documents`` reverse-FK join, dropping
the trailing ``.distinct()``. With the de-joined predicate the un-scoped
"Browse annotations" page (``ORDER BY -modified``) and its structural-filtered
variants can finally ride an index instead of a full scan + dedup.

This adds the composite ``(structural, modified)`` index that backs the common
``structural=<bool>`` + ``ORDER BY -modified`` query shape used by the
anonymous / Discover browse and the ``structural`` filter on the annotations
connection. The unfiltered ``-modified`` page continues to use the existing
single-column ``modified`` index, so this index is purely additive.

Created with ``CREATE INDEX CONCURRENTLY`` (``atomic = False``) so building it
on a large ``annotations_annotation`` table does not take an
``ACCESS EXCLUSIVE`` lock that would block reads/writes for the duration.
"""

from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):

    # AddIndexConcurrently cannot run inside a transaction.
    atomic = False

    dependencies = [
        ("annotations", "0076_note_search_vector"),
    ]

    operations = [
        AddIndexConcurrently(
            model_name="annotation",
            index=models.Index(
                fields=["structural", "modified"],
                name="annot_structural_modified_idx",
            ),
        ),
    ]
