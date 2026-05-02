"""Delete StructuralAnnotationSet rows that no Document references.

Use this to reclaim space and keep retrieval honest after bulk
deletes that pre-date the orphan-GC signal handlers added in
``opencontractserver.documents.signals``. Idempotent and safe to run
periodically.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db.models import Count

from opencontractserver.annotations.models import StructuralAnnotationSet


class Command(BaseCommand):
    help = (
        "Delete StructuralAnnotationSet rows with zero Document references. "
        "Cascades to their annotations and structural relationships."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be deleted but don't delete anything.",
        )

    def handle(self, *args, **options):
        dry_run: bool = options["dry_run"]

        orphans = StructuralAnnotationSet.objects.annotate(
            doc_count=Count("documents"),
        ).filter(doc_count=0)
        orphan_count = orphans.count()
        if orphan_count == 0:
            self.stdout.write(self.style.SUCCESS("No orphan structural sets."))
            return

        # Per-set annotation counts for visibility
        ann_total = sum(s.annotation_count for s in orphans)
        rel_total = sum(s.relationship_count for s in orphans)

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"[dry-run] would delete {orphan_count} orphan structural "
                    f"sets, freeing {ann_total} annotations + {rel_total} "
                    f"structural relationships"
                )
            )
            return

        deleted, _ = orphans.delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {orphan_count} orphan structural sets "
                f"({ann_total} annotations, {rel_total} structural "
                f"relationships freed; {deleted} total rows touched)"
            )
        )
