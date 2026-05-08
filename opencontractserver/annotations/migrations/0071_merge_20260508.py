"""Merge migration: reconcile the two leaf nodes that landed on main.

``0069_grounding_annotation_unique_constraints`` (PR #1418, branched off
``0068_enforce_embedder_path_not_null``) and ``0070_seed_default_labelset``
(branched off ``0069_labelset_is_default_and_seed_default``, also off
``0068_*``) ended up as parallel leaves in the ``annotations`` migration
graph — Django refuses to migrate when ``makemigrations --check`` sees
multiple leaves. This empty merge node reunifies them; no schema change.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("annotations", "0069_grounding_annotation_unique_constraints"),
        ("annotations", "0070_seed_default_labelset"),
    ]

    operations: list = []
