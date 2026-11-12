"""Delete contentless structural annotations stored before the parse-time filter.

Uses the parser's rule (``utils/contentless_annotations.py``): structural, no
letter or digit in any script, no image content, not a content-region label
(tables, formulas, figures, checkboxes), and a leaf once its contentless
children are gone. Nothing deleted has a kept child, so ``Annotation.parent``'s
cascade never removes content. Relationships left without a source or a
target are deleted. Idempotent.
"""

from __future__ import annotations

from collections import Counter

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count, Q

from opencontractserver.annotations.models import Annotation, Relationship
from opencontractserver.utils.contentless_annotations import (
    is_contentless,
    prunable_leaves,
)


class Command(BaseCommand):
    help = (
        "Delete structural leaf annotations whose text has no letters or digits "
        "(whitespace, fill-in lines, stray punctuation or symbol glyphs)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be deleted but don't delete anything.",
        )

    def handle(self, *args, **options):
        dry_run: bool = options["dry_run"]

        # ASCII prefilter is locale-independent and keeps the scan small; the
        # Unicode-aware check decides (it keeps non-Latin scripts).
        rows = (
            Annotation.objects.filter(structural=True)
            .exclude(raw_text__regex=r"[A-Za-z0-9]")
            .values_list(
                "pk", "raw_text", "annotation_label__text", "content_modalities"
            )
        )
        kind_of = {
            pk: (label, tuple(modalities or []))
            for pk, raw_text, label, modalities in rows.iterator()
            if is_contentless(raw_text, label, modalities)
        }
        children_of: dict = {}
        for parent_id, pk in Annotation.objects.filter(
            parent_id__in=list(kind_of)
        ).values_list("parent_id", "pk"):
            children_of.setdefault(parent_id, []).append(pk)
        doomed = prunable_leaves(kind_of, children_of)
        if not doomed:
            self.stdout.write(
                self.style.SUCCESS("No contentless structural annotations.")
            )
            return

        relationships = Relationship.objects.filter(
            Q(source_annotations__in=doomed) | Q(target_annotations__in=doomed)
        ).distinct()

        if dry_run:
            # Show what kinds match, so a parser whose meaningful regions fall
            # under this rule is noticed before anything is deleted.
            by_kind = Counter(kind_of[pk] for pk in doomed)
            for (label, modalities), count in by_kind.most_common():
                self.stdout.write(f"  {count:>8}  {label} {list(modalities)}")
            self.stdout.write(
                self.style.WARNING(
                    f"[dry-run] would delete {len(doomed)} contentless structural "
                    f"annotations and update {relationships.count()} relationships"
                )
            )
            return

        with transaction.atomic():
            relationship_ids = list(relationships.values_list("pk", flat=True))
            deleted, _ = Annotation.objects.filter(pk__in=doomed).delete()
            emptied, _ = (
                Relationship.objects.filter(pk__in=relationship_ids)
                .annotate(
                    n_sources=Count("source_annotations", distinct=True),
                    n_targets=Count("target_annotations", distinct=True),
                )
                .filter(Q(n_sources=0) | Q(n_targets=0))
                .delete()
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {len(doomed)} contentless structural annotations "
                f"({deleted} rows incl. embeddings), removed {emptied} emptied "
                f"relationship rows"
            )
        )
