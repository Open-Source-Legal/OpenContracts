"""
Management command to migrate structural annotations to shared StructuralAnnotationSet objects.

This command is part of the v3.0.0.b3 migration for storage efficiency. It moves
structural annotations from individual documents to shared StructuralAnnotationSet
objects, keyed by content hash.

Usage:
    python manage.py migrate_structural_annotations [options]

Options:
    --dry-run          Preview changes without modifying database
    --document-id ID   Migrate a specific document only
    --corpus-id ID     Migrate all documents in a corpus
    --batch-size N     Process N documents per batch (default: 100)
    --verbose          Show detailed progress
    --force            Proceed even if document lacks pdf_file_hash
    --system-user-id   User ID for audit trail (default: 1)
"""

import logging
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from opencontractserver.annotations.models import (
    Annotation,
    Relationship,
    StructuralAnnotationSet,
)
from opencontractserver.documents.models import Document, DocumentPath

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    """
    Migrate structural annotations to shared StructuralAnnotationSet objects.

    This command:
    1. Finds documents with structural annotations that aren't in a structural set
    2. Creates or retrieves StructuralAnnotationSet by content hash
    3. Moves structural annotations from document to structural_set
    4. Links document to the structural_annotation_set
    """

    help = (
        "Migrate structural annotations to shared StructuralAnnotationSet "
        "objects for storage efficiency"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run in dry-run mode (no database changes)",
        )
        parser.add_argument(
            "--document-id",
            type=int,
            help="Process only a specific document by ID",
        )
        parser.add_argument(
            "--corpus-id",
            type=int,
            help="Process only documents in a specific corpus",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="Number of documents to process per batch (default: 100)",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Show detailed progress information",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Process documents without pdf_file_hash (uses document ID as hash)",
        )
        parser.add_argument(
            "--system-user-id",
            type=int,
            default=1,
            help="User ID for audit trail on created StructuralAnnotationSet (default: 1)",
        )

    def handle(self, *args, **options):
        """Execute the migration command."""
        dry_run = options["dry_run"]
        document_id = options.get("document_id")
        corpus_id = options.get("corpus_id")
        batch_size = options["batch_size"]
        verbose = options["verbose"]
        force = options["force"]
        system_user_id = options["system_user_id"]

        # Get system user for audit trail
        try:
            system_user = User.objects.get(pk=system_user_id)
        except User.DoesNotExist:
            raise CommandError(f"User with ID {system_user_id} not found")

        if dry_run:
            self.stdout.write(
                self.style.WARNING("Running in DRY-RUN mode - no changes will be made")
            )

        # Build queryset for documents to process
        documents = self._get_documents_to_process(document_id, corpus_id, force)

        total = documents.count()
        self.stdout.write(f"Found {total} document(s) eligible for migration\n")

        if total == 0:
            self.stdout.write(
                self.style.SUCCESS("No documents need migration. All done!")
            )
            return

        # Track statistics. Mixed value types (counters and an error list) so
        # we widen to ``Any`` so mypy treats the dict as heterogeneous.
        stats: dict[str, Any] = {
            "documents_processed": 0,
            "documents_skipped": 0,
            "structural_sets_created": 0,
            "structural_sets_reused": 0,
            "annotations_migrated": 0,
            "relationships_migrated": 0,
            "errors": [],
        }

        # Process in batches
        processed = 0
        for start in range(0, total, batch_size):
            batch = documents[start : start + batch_size]

            for doc in batch:
                try:
                    result = self._process_document(
                        doc=doc,
                        system_user=system_user,
                        dry_run=dry_run,
                        verbose=verbose,
                        force=force,
                    )

                    stats["documents_processed"] += 1
                    stats["structural_sets_created"] += result.get("set_created", 0)
                    stats["structural_sets_reused"] += result.get("set_reused", 0)
                    stats["annotations_migrated"] += result.get("annotations", 0)
                    stats["relationships_migrated"] += result.get("relationships", 0)

                except Exception as e:
                    error_msg = f"Error processing document {doc.pk}: {e}"
                    stats["errors"].append(error_msg)
                    self.stdout.write(self.style.ERROR(f"  {error_msg}"))
                    if verbose:
                        import traceback

                        self.stdout.write(traceback.format_exc())

                processed += 1
                if processed % 50 == 0:
                    self.stdout.write(f"  Progress: {processed}/{total}")

        # Print summary
        self._print_summary(stats, dry_run)

    def _get_documents_to_process(self, document_id, corpus_id, force):
        """Build queryset of documents eligible for migration."""
        # Base filter: documents with structural annotations but no structural_annotation_set
        queryset = Document.objects.filter(
            doc_annotation__structural=True, structural_annotation_set__isnull=True
        ).distinct()

        # Filter by specific document ID
        if document_id:
            queryset = queryset.filter(pk=document_id)

        # Filter by corpus
        if corpus_id:
            # Documents must have a DocumentPath in this corpus
            corpus_doc_ids = DocumentPath.objects.filter(
                corpus_id=corpus_id, is_current=True, is_deleted=False
            ).values_list("document_id", flat=True)
            queryset = queryset.filter(pk__in=corpus_doc_ids)

        # Exclude documents without hash unless force is set
        if not force:
            queryset = queryset.exclude(pdf_file_hash__isnull=True).exclude(
                pdf_file_hash=""
            )

        return queryset.order_by("id")

    def _process_document(self, doc, system_user, dry_run, verbose, force):
        """Process a single document's structural annotations."""
        result = {
            "set_created": 0,
            "set_reused": 0,
            "annotations": 0,
            "relationships": 0,
        }

        # Determine content hash
        content_hash = doc.pdf_file_hash
        if not content_hash:
            if force:
                # Use document ID as fallback hash
                content_hash = f"doc-{doc.pk}"
            else:
                return result  # Skip - shouldn't happen due to queryset filter

        if verbose:
            self.stdout.write(
                f"  Processing document {doc.pk}: {doc.title} (hash: {content_hash[:16]}...)"
            )

        # Count structural annotations/relationships before migration
        annot_count = Annotation.objects.filter(document=doc, structural=True).count()
        rel_count = Relationship.objects.filter(document=doc, structural=True).count()

        if verbose:
            self.stdout.write(
                f"    Found {annot_count} structural annotations, "
                f"{rel_count} structural relationships"
            )

        if dry_run:
            # Just report what would happen
            result["annotations"] = annot_count
            result["relationships"] = rel_count
            # Check if structural set exists
            if StructuralAnnotationSet.objects.filter(
                content_hash=content_hash
            ).exists():
                result["set_reused"] = 1
            else:
                result["set_created"] = 1
            return result

        # Actual migration
        with transaction.atomic():
            # Get or create StructuralAnnotationSet
            struct_set, created = StructuralAnnotationSet.objects.get_or_create(
                content_hash=content_hash,
                defaults={
                    "creator": system_user,
                    "parser_name": None,  # Will be filled if parsing data available
                    "parser_version": None,
                    "page_count": doc.page_count,
                    # Share file references (not duplicated)
                    "pawls_parse_file": (
                        doc.pawls_parse_file.name if doc.pawls_parse_file else None
                    ),
                    "txt_extract_file": (
                        doc.txt_extract_file.name if doc.txt_extract_file else None
                    ),
                },
            )

            if created:
                result["set_created"] = 1
                if verbose:
                    self.stdout.write(
                        f"    Created StructuralAnnotationSet {struct_set.pk}"
                    )
            else:
                result["set_reused"] = 1
                if verbose:
                    self.stdout.write(
                        f"    Reusing existing StructuralAnnotationSet {struct_set.pk}"
                    )

            # Move structural annotations
            migrated_annots = Annotation.objects.filter(
                document=doc, structural=True
            ).update(structural_set=struct_set, document=None)
            result["annotations"] = migrated_annots

            # Move structural relationships
            migrated_rels = Relationship.objects.filter(
                document=doc, structural=True
            ).update(structural_set=struct_set, document=None)
            result["relationships"] = migrated_rels

            # Link document to structural set
            doc.structural_annotation_set = struct_set
            doc.save(update_fields=["structural_annotation_set"])

            if verbose:
                self.stdout.write(
                    f"    Migrated {migrated_annots} annotations, "
                    f"{migrated_rels} relationships"
                )

        return result

    def _print_summary(self, stats, dry_run):
        """Print command execution summary."""
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(
            self.style.SUCCESS("MIGRATION SUMMARY")
            if not stats["errors"]
            else self.style.WARNING("MIGRATION SUMMARY (WITH ERRORS)")
        )
        self.stdout.write("=" * 60)

        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY-RUN MODE - No changes were made\n")
            )

        self.stdout.write(f"Documents processed: {stats['documents_processed']}")
        self.stdout.write(
            f"StructuralAnnotationSets created: {stats['structural_sets_created']}"
        )
        self.stdout.write(
            f"StructuralAnnotationSets reused: {stats['structural_sets_reused']}"
        )
        self.stdout.write(f"Annotations migrated: {stats['annotations_migrated']}")
        self.stdout.write(f"Relationships migrated: {stats['relationships_migrated']}")

        if stats["errors"]:
            self.stdout.write(
                "\n" + self.style.ERROR(f"Errors ({len(stats['errors'])}):")
            )
            for error in stats["errors"]:
                self.stdout.write(f"  - {error}")

        self.stdout.write("=" * 60)

        if not dry_run and stats["documents_processed"] > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\nSuccessfully migrated {stats['annotations_migrated']} annotations "
                    f"from {stats['documents_processed']} documents"
                )
            )
        elif dry_run and stats["documents_processed"] > 0:
            self.stdout.write(
                self.style.WARNING(
                    f"\nWould migrate {stats['annotations_migrated']} annotations "
                    f"from {stats['documents_processed']} documents"
                )
            )
            self.stdout.write("  Run without --dry-run to apply changes")
