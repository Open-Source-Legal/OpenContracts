"""
Management command to validate v3.0.0.b3 migration for OpenContracts.

This command performs pre-flight and post-migration validation checks to ensure
the dual-tree versioning migration is complete.

Usage:
    python manage.py validate_v3_migration [--verbose]
"""

import logging

from django.core.management.base import BaseCommand

from opencontractserver.annotations.models import Annotation, Relationship
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Validate v3.0.0.b3 migration status.

    Checks:
    1. All documents have version_tree_id (not NULL)
    2. All documents have is_current=True (initially)
    3. All corpus-document M2M relationships have corresponding DocumentPath
    4. All annotations have a document (no orphaned annotations)
    5. All relationships have a document (no orphaned relationships)
    """

    help = "Validate v3.0.0.b3 migration status for dual-tree versioning"

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

        # Check 3: DocumentPath records for M2M relationships
        results["document_paths"] = self._check_document_paths(verbose)
        if not results["document_paths"]["passed"]:
            all_passed = False

        # Check 4: Annotations have documents
        results["annotation_doc"] = self._check_annotation_documents(verbose)
        if not results["annotation_doc"]["passed"]:
            all_passed = False

        # Check 5: Relationships have documents
        results["relationship_doc"] = self._check_relationship_documents(verbose)
        if not results["relationship_doc"]["passed"]:
            all_passed = False

        # Print summary
        self._print_summary(results, all_passed)

        if all_passed:
            return
        else:
            raise SystemExit(1)

    def _check_version_tree_id(self, verbose, fix):
        """Check that all documents have version_tree_id."""
        self.stdout.write("\n[1/5] Checking Document.version_tree_id...")

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
        self.stdout.write("\n[2/5] Checking Document.is_current...")

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

    def _check_document_paths(self, verbose):
        """Check that all corpus-document relationships have DocumentPath records."""
        self.stdout.write("\n[3/5] Checking DocumentPath records...")

        issues = []
        total_m2m = 0
        total_paths = 0

        for corpus in Corpus.objects.prefetch_related("documents").all():
            m2m_doc_ids = set(corpus.documents.values_list("id", flat=True))
            path_doc_ids = set(
                DocumentPath.objects.filter(
                    corpus=corpus, is_current=True, is_deleted=False
                ).values_list("document_id", flat=True)
            )

            total_m2m += len(m2m_doc_ids)
            total_paths += len(path_doc_ids)

            # Find M2M relationships without DocumentPath
            missing = m2m_doc_ids - path_doc_ids
            if missing:
                issues.append(
                    {
                        "corpus_id": corpus.pk,
                        "corpus_title": corpus.title,
                        "missing_count": len(missing),
                        "missing_ids": list(missing)[:5],
                    }
                )

        if not issues:
            self.stdout.write(
                self.style.SUCCESS(
                    f"  PASSED: All M2M relationships have DocumentPath records "
                    f"({total_paths} paths for {total_m2m} M2M relationships)"
                )
            )
            return {"passed": True, "total_m2m": total_m2m, "total_paths": total_paths}

        total_missing = sum(i["missing_count"] for i in issues)
        self.stdout.write(
            self.style.ERROR(
                f"  FAILED: {total_missing} M2M relationships missing DocumentPath"
            )
        )

        if verbose:
            for issue in issues[:5]:
                self.stdout.write(
                    f"    - Corpus {issue['corpus_id']} ({issue['corpus_title']}): "
                    f"{issue['missing_count']} missing"
                )
            if len(issues) > 5:
                self.stdout.write(f"    ... and {len(issues) - 5} more corpuses")

        return {"passed": False, "issues": issues, "total_missing": total_missing}

    def _check_annotation_documents(self, verbose):
        """Check that all annotations have a document."""
        self.stdout.write("\n[4/5] Checking Annotation documents...")

        # Check for NULL document (orphaned)
        orphaned = Annotation.objects.filter(document__isnull=True).count()

        total_annotations = Annotation.objects.count()

        if orphaned == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"  PASSED: All {total_annotations} annotations have a document"
                )
            )
            return {"passed": True, "total": total_annotations}

        self.stdout.write(
            self.style.ERROR(f"  FAILED: {orphaned} annotations have no document")
        )
        if verbose:
            orphaned_ids = list(
                Annotation.objects.filter(document__isnull=True).values_list(
                    "id", flat=True
                )[:10]
            )
            self.stdout.write(f"    IDs: {orphaned_ids}")

        return {"passed": False, "orphaned": orphaned}

    def _check_relationship_documents(self, verbose):
        """Check that all relationships have a document."""
        self.stdout.write("\n[5/5] Checking Relationship documents...")

        # Check for NULL document (orphaned)
        orphaned = Relationship.objects.filter(document__isnull=True).count()

        total_relationships = Relationship.objects.count()

        if orphaned == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"  PASSED: All {total_relationships} relationships have a document"
                )
            )
            return {"passed": True, "total": total_relationships}

        self.stdout.write(
            self.style.ERROR(f"  FAILED: {orphaned} relationships have no document")
        )

        return {"passed": False, "orphaned": orphaned}

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
            ("DocumentPath records", results["document_paths"]["passed"]),
            ("Annotation documents", results["annotation_doc"]["passed"]),
            ("Relationship documents", results["relationship_doc"]["passed"]),
        ]

        for check_name, passed in checks:
            status = self.style.SUCCESS("PASS") if passed else self.style.ERROR("FAIL")
            self.stdout.write(f"  {check_name}: {status}")

        self.stdout.write("=" * 70 + "\n")
