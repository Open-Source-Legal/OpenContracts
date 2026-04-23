"""
Management command to validate v3.0.0.b3 migration for OpenContracts.

This command performs pre-flight and post-migration validation checks to ensure
the dual-tree versioning and structural annotation set migrations are complete.

Usage:
    python manage.py validate_v3_migration [--verbose]
"""

import logging

from django.core.management.base import BaseCommand
from django.db.models import Count

from opencontractserver.annotations.models import (
    Annotation,
    Relationship,
    StructuralAnnotationSet,
)
from opencontractserver.documents.models import Document

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Validate v3.0.0.b3 migration status.

    Checks:
    1. All documents have version_tree_id (not NULL)
    2. All documents have is_current=True (initially)
    3. No annotations violate XOR constraint
    4. No orphaned annotations (both FKs NULL)
    5. StructuralAnnotationSet content_hash uniqueness
    6. Report documents eligible for structural migration
    """

    help = "Validate v3.0.0.b3 migration status for dual-tree versioning and structural annotations"

    def add_arguments(self, parser):
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Show detailed information about each check",
        )
        parser.add_argument(
            "--fix",
            action="store_true",
            help="Attempt to fix simple issues (like missing version_tree_id)",
        )

    def handle(self, *args, **options):
        """Execute the validation command."""
        verbose = options["verbose"]
        fix = options["fix"]

        self.stdout.write(self.style.NOTICE("\n" + "=" * 70))
        self.stdout.write(
            self.style.NOTICE("OpenContracts v3.0.0.b3 Migration Validation")
        )
        self.stdout.write(self.style.NOTICE("=" * 70 + "\n"))

        all_passed = True
        results = {}

        # Check 1: Documents have version_tree_id
        results["version_tree_id"] = self._check_version_tree_id(verbose, fix)
        if not results["version_tree_id"]["passed"]:
            all_passed = False

        # Check 2: Documents have is_current set
        results["is_current"] = self._check_is_current(verbose)
        if not results["is_current"]["passed"]:
            all_passed = False

        # Check 3: XOR constraint on Annotations
        results["annotation_xor"] = self._check_annotation_xor_constraint(verbose)
        if not results["annotation_xor"]["passed"]:
            all_passed = False

        # Check 4: XOR constraint on Relationships
        results["relationship_xor"] = self._check_relationship_xor_constraint(verbose)
        if not results["relationship_xor"]["passed"]:
            all_passed = False

        # Check 5: StructuralAnnotationSet uniqueness
        results["structural_set_hash"] = self._check_structural_set_uniqueness(verbose)
        if not results["structural_set_hash"]["passed"]:
            all_passed = False

        # Check 6: Structural migration candidates
        results["migration_candidates"] = self._check_structural_migration_candidates(
            verbose
        )

        # Print summary
        self._print_summary(results, all_passed)

        if all_passed:
            return
        else:
            raise SystemExit(1)

    def _check_version_tree_id(self, verbose, fix):
        """Check that all documents have version_tree_id."""
        self.stdout.write("\n[1/6] Checking Document.version_tree_id...")

        docs_without_tree_id = Document.objects.filter(version_tree_id__isnull=True)
        count = docs_without_tree_id.count()

        if count == 0:
            self.stdout.write(
                self.style.SUCCESS("  PASSED: All documents have version_tree_id")
            )
            return {"passed": True, "count": 0}

        if fix:
            import uuid

            fixed = 0
            for doc in docs_without_tree_id:
                doc.version_tree_id = uuid.uuid4()
                doc.save(update_fields=["version_tree_id"])
                fixed += 1
                if verbose:
                    self.stdout.write(f"    Fixed document {doc.pk}: {doc.title}")
            self.stdout.write(
                self.style.SUCCESS(f"  FIXED: Assigned version_tree_id to {fixed} docs")
            )
            return {"passed": True, "count": 0, "fixed": fixed}

        self.stdout.write(
            self.style.ERROR(f"  FAILED: {count} documents missing version_tree_id")
        )

        if verbose:
            for doc in docs_without_tree_id[:10]:
                self.stdout.write(f"    - Document {doc.pk}: {doc.title}")
            if count > 10:
                self.stdout.write(f"    ... and {count - 10} more")

        return {"passed": False, "count": count}

    def _check_is_current(self, verbose):
        """Check that documents have is_current set properly."""
        self.stdout.write("\n[2/6] Checking Document.is_current...")

        # For migration validation, we expect all docs to have is_current=True initially
        # unless they've been versioned (which creates new docs with is_current=True
        # and sets old ones to False)

        # Check for NULL is_current (shouldn't happen but be safe)
        docs_null_current = Document.objects.filter(is_current__isnull=True).count()
        if docs_null_current > 0:
            self.stdout.write(
                self.style.ERROR(
                    f"  FAILED: {docs_null_current} docs have NULL is_current"
                )
            )
            return {"passed": False, "count": docs_null_current}

        # Count current vs non-current
        current_count = Document.objects.filter(is_current=True).count()
        non_current_count = Document.objects.filter(is_current=False).count()

        self.stdout.write(
            self.style.SUCCESS(
                f"  PASSED: {current_count} current, {non_current_count} non-current (versioned)"
            )
        )

        if verbose and non_current_count > 0:
            self.stdout.write(
                f"    Note: {non_current_count} non-current documents are previous versions"
            )

        return {
            "passed": True,
            "current": current_count,
            "non_current": non_current_count,
        }

    def _check_annotation_xor_constraint(self, verbose):
        """Check that all annotations satisfy XOR constraint."""
        self.stdout.write("\n[3/6] Checking Annotation XOR constraint...")

        # Check for both being NULL (orphaned)
        orphaned = Annotation.objects.filter(
            document__isnull=True, structural_set__isnull=True
        ).count()

        # Check for both being set (constraint violation)
        both_set = Annotation.objects.filter(
            document__isnull=False, structural_set__isnull=False
        ).count()

        total_annotations = Annotation.objects.count()

        if orphaned == 0 and both_set == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"  PASSED: All {total_annotations} annotations satisfy XOR constraint"
                )
            )
            return {"passed": True, "total": total_annotations}

        if orphaned > 0:
            self.stdout.write(
                self.style.ERROR(
                    f"  FAILED: {orphaned} annotations have neither document nor structural_set"
                )
            )
            if verbose:
                orphaned_ids = list(
                    Annotation.objects.filter(
                        document__isnull=True, structural_set__isnull=True
                    ).values_list("id", flat=True)[:10]
                )
                self.stdout.write(f"    IDs: {orphaned_ids}")

        if both_set > 0:
            self.stdout.write(
                self.style.ERROR(
                    f"  FAILED: {both_set} annotations have BOTH document AND structural_set"
                )
            )

        return {"passed": False, "orphaned": orphaned, "both_set": both_set}

    def _check_relationship_xor_constraint(self, verbose):
        """Check that all relationships satisfy XOR constraint."""
        self.stdout.write("\n[4/6] Checking Relationship XOR constraint...")

        # Check for both being NULL (orphaned)
        orphaned = Relationship.objects.filter(
            document__isnull=True, structural_set__isnull=True
        ).count()

        # Check for both being set (constraint violation)
        both_set = Relationship.objects.filter(
            document__isnull=False, structural_set__isnull=False
        ).count()

        total_relationships = Relationship.objects.count()

        if orphaned == 0 and both_set == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"  PASSED: All {total_relationships} relationships satisfy XOR constraint"
                )
            )
            return {"passed": True, "total": total_relationships}

        if orphaned > 0:
            self.stdout.write(
                self.style.ERROR(
                    f"  FAILED: {orphaned} relationships have neither document nor structural_set"
                )
            )

        if both_set > 0:
            self.stdout.write(
                self.style.ERROR(
                    f"  FAILED: {both_set} relationships have BOTH document AND structural_set"
                )
            )

        return {"passed": False, "orphaned": orphaned, "both_set": both_set}

    def _check_structural_set_uniqueness(self, verbose):
        """Check StructuralAnnotationSet content_hash uniqueness."""
        self.stdout.write("\n[5/6] Checking StructuralAnnotationSet uniqueness...")

        total_sets = StructuralAnnotationSet.objects.count()

        # Find duplicate content_hash values
        duplicates = (
            StructuralAnnotationSet.objects.values("content_hash")
            .annotate(count=Count("id"))
            .filter(count__gt=1)
        )

        duplicate_count = duplicates.count()

        if duplicate_count == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"  PASSED: All {total_sets} structural sets have unique content_hash"
                )
            )
            return {"passed": True, "total": total_sets}

        self.stdout.write(
            self.style.ERROR(
                f"  FAILED: {duplicate_count} duplicate content_hash values"
            )
        )

        if verbose:
            for content_hash, count in duplicates.values_list(
                "content_hash", "count"
            )[:5]:
                self.stdout.write(
                    f"    - Hash {content_hash[:16]}...: {count} duplicates"
                )

        return {"passed": False, "duplicate_hashes": duplicate_count}

    def _check_structural_migration_candidates(self, verbose):
        """Report documents eligible for structural annotation migration."""
        self.stdout.write("\n[6/6] Checking structural migration candidates...")

        # Documents with structural annotations but no structural_annotation_set
        candidates = Document.objects.filter(
            doc_annotation__structural=True, structural_annotation_set__isnull=True
        ).distinct()

        candidate_count = candidates.count()

        # Count structural annotations that could be migrated
        structural_annotation_count = Annotation.objects.filter(
            structural=True, document__isnull=False
        ).count()

        structural_relationship_count = Relationship.objects.filter(
            structural=True, document__isnull=False
        ).count()

        # Documents already using structural sets
        already_migrated = Document.objects.filter(
            structural_annotation_set__isnull=False
        ).count()

        self.stdout.write(
            self.style.WARNING(
                f"  INFO: {candidate_count} documents eligible for structural migration"
            )
        )
        self.stdout.write(
            f"    - {structural_annotation_count} structural annotations on documents"
        )
        self.stdout.write(
            f"    - {structural_relationship_count} structural relationships on documents"
        )
        self.stdout.write(
            f"    - {already_migrated} documents already using StructuralAnnotationSet"
        )

        if candidate_count > 0:
            self.stdout.write(
                self.style.NOTICE(
                    "\n  To migrate, run: python manage.py migrate_structural_annotations"
                )
            )

        return {
            "passed": True,  # This is informational, not a pass/fail check
            "candidates": candidate_count,
            "structural_annotations": structural_annotation_count,
            "structural_relationships": structural_relationship_count,
            "already_migrated": already_migrated,
        }

    def _print_summary(self, results, all_passed):
        """Print validation summary."""
        self.stdout.write("\n" + "=" * 70)
        if all_passed:
            self.stdout.write(self.style.SUCCESS("VALIDATION PASSED"))
        else:
            self.stdout.write(self.style.ERROR("VALIDATION FAILED"))
        self.stdout.write("=" * 70)

        # Summary table
        checks = [
            ("Document.version_tree_id", results["version_tree_id"]["passed"]),
            ("Document.is_current", results["is_current"]["passed"]),
            ("Annotation XOR constraint", results["annotation_xor"]["passed"]),
            ("Relationship XOR constraint", results["relationship_xor"]["passed"]),
            (
                "StructuralAnnotationSet uniqueness",
                results["structural_set_hash"]["passed"],
            ),
        ]

        for check_name, passed in checks:
            status = self.style.SUCCESS("PASS") if passed else self.style.ERROR("FAIL")
            self.stdout.write(f"  {check_name}: {status}")

        # Structural migration info
        candidates = results["migration_candidates"]["candidates"]
        if candidates > 0:
            self.stdout.write(
                self.style.NOTICE(
                    f"\n  {candidates} documents can benefit from structural annotation migration"
                )
            )

        self.stdout.write("=" * 70 + "\n")
