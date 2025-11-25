"""
Management command to sync existing M2M corpus.documents relationships to DocumentPath records.

This command is part of Issue #654: Resolving dual source of truth between
corpus.documents M2M field and the new DocumentPath model.

Usage:
    python manage.py sync_m2m_to_documentpath [--dry-run] [--corpus-id ID]
"""

import logging

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count

from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    """
    Sync existing M2M corpus.documents relationships to DocumentPath records.

    This command:
    1. Identifies corpuses using the legacy M2M relationship
    2. Creates DocumentPath records for documents without them
    3. Reports on migration status and any issues
    4. Can run in dry-run mode for safety
    """

    help = "Sync M2M corpus.documents relationships to DocumentPath records"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run in dry-run mode (no database changes)",
        )
        parser.add_argument(
            "--corpus-id",
            type=int,
            help="Process only a specific corpus by ID",
        )
        parser.add_argument(
            "--system-user-id",
            type=int,
            default=1,
            help="User ID to use for audit trail (default: 1)",
        )
        parser.add_argument(
            "--path-prefix",
            type=str,
            default="/migrated",
            help="Path prefix for migrated documents (default: /migrated)",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Show detailed progress information",
        )

    def handle(self, *args, **options):
        """Execute the sync command."""
        dry_run = options["dry_run"]
        corpus_id = options.get("corpus_id")
        system_user_id = options["system_user_id"]
        path_prefix = options["path_prefix"]
        verbose = options["verbose"]

        # Get system user for audit trail
        try:
            system_user = User.objects.get(pk=system_user_id)
        except User.DoesNotExist:
            raise CommandError(f"User with ID {system_user_id} not found")

        if dry_run:
            self.stdout.write(
                self.style.WARNING("Running in DRY-RUN mode - no changes will be made")
            )

        # Get corpuses to process
        if corpus_id:
            try:
                corpuses = Corpus.objects.filter(pk=corpus_id)
                if not corpuses.exists():
                    raise CommandError(f"Corpus with ID {corpus_id} not found")
            except Exception as e:
                raise CommandError(f"Error fetching corpus: {e}")
        else:
            # Get all corpuses with documents
            corpuses = Corpus.objects.annotate(doc_count=Count("documents")).filter(
                doc_count__gt=0
            )

        total_corpuses = corpuses.count()
        self.stdout.write(f"Found {total_corpuses} corpus(es) to process\n")

        # Track statistics
        stats = {
            "corpuses_processed": 0,
            "documents_processed": 0,
            "paths_created": 0,
            "paths_already_existed": 0,
            "errors": [],
        }

        # Process each corpus
        for corpus in corpuses:
            self.stdout.write(f"\nProcessing corpus: {corpus.title} (ID: {corpus.pk})")

            try:
                corpus_stats = self._process_corpus(
                    corpus=corpus,
                    system_user=system_user,
                    path_prefix=path_prefix,
                    dry_run=dry_run,
                    verbose=verbose,
                )

                stats["corpuses_processed"] += 1
                stats["documents_processed"] += corpus_stats["documents_processed"]
                stats["paths_created"] += corpus_stats["paths_created"]
                stats["paths_already_existed"] += corpus_stats["paths_already_existed"]

            except Exception as e:
                error_msg = f"Error processing corpus {corpus.pk}: {e}"
                stats["errors"].append(error_msg)
                self.stdout.write(self.style.ERROR(error_msg))
                if verbose:
                    import traceback

                    self.stdout.write(traceback.format_exc())

        # Print summary
        self._print_summary(stats, dry_run)

    def _process_corpus(self, corpus, system_user, path_prefix, dry_run, verbose):
        """Process a single corpus."""
        stats = {
            "documents_processed": 0,
            "paths_created": 0,
            "paths_already_existed": 0,
        }

        # Get documents via M2M relationship
        m2m_documents = corpus.documents.all()
        m2m_count = m2m_documents.count()

        # Get documents via DocumentPath
        path_doc_ids = (
            DocumentPath.objects.filter(
                corpus=corpus, is_current=True, is_deleted=False
            )
            .values_list("document_id", flat=True)
            .distinct()
        )

        documentpath_count = len(set(path_doc_ids))

        self.stdout.write(
            f"  M2M documents: {m2m_count}, "
            f"DocumentPath documents: {documentpath_count}"
        )

        # Find documents that need DocumentPath records
        missing_doc_ids = set(m2m_documents.values_list("id", flat=True)) - set(
            path_doc_ids
        )

        if not missing_doc_ids:
            self.stdout.write(
                self.style.SUCCESS("  All documents already have DocumentPath records")
            )
            stats["paths_already_existed"] = m2m_count
            return stats

        self.stdout.write(
            f"  Found {len(missing_doc_ids)} documents needing DocumentPath records"
        )

        # Process documents missing DocumentPath records
        for doc_id in missing_doc_ids:
            try:
                document = Document.objects.get(pk=doc_id)
                stats["documents_processed"] += 1

                # Check if document already has a path in this corpus (shouldn't happen but be safe)
                existing_path = DocumentPath.objects.filter(
                    corpus=corpus, document=document, is_current=True, is_deleted=False
                ).first()

                if existing_path:
                    if verbose:
                        self.stdout.write(
                            f"    Document {document.pk} already has path: {existing_path.path}"
                        )
                    stats["paths_already_existed"] += 1
                    continue

                # Generate path for document
                path = self._generate_path(document, path_prefix)

                if verbose:
                    self.stdout.write(
                        f"    Creating DocumentPath for document {document.pk}: {path}"
                    )

                if not dry_run:
                    # Create DocumentPath record
                    with transaction.atomic():
                        # Check if this path already exists (avoid conflicts)
                        path_counter = 0
                        original_path = path
                        while DocumentPath.objects.filter(
                            corpus=corpus, path=path, is_current=True, is_deleted=False
                        ).exists():
                            path_counter += 1
                            path = f"{original_path}_{path_counter}"

                        # Create the DocumentPath
                        DocumentPath.objects.create(
                            document=document,
                            corpus=corpus,
                            folder=None,  # No folder for migrated documents
                            path=path,
                            version_number=1,  # First version in this corpus
                            parent=None,  # Root of path tree for this document
                            is_current=True,
                            is_deleted=False,
                            creator=system_user,
                        )
                        stats["paths_created"] += 1

                        if verbose:
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"      Created DocumentPath: {path}"
                                )
                            )
                else:
                    stats["paths_created"] += 1  # Count what would be created

            except Document.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f"    Document {doc_id} not found - skipping")
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"    Error processing document {doc_id}: {e}")
                )
                if verbose:
                    import traceback

                    self.stdout.write(traceback.format_exc())

        return stats

    def _generate_path(self, document, path_prefix):
        """Generate a filesystem path for a document."""
        # Use document title if available, otherwise use ID
        if document.title:
            # Sanitize title for filesystem
            safe_title = "".join(
                c if c.isalnum() or c in "-_." else "_" for c in document.title[:100]
            ).strip("_")

            if safe_title:
                return f"{path_prefix}/{safe_title}"

        # Fallback to ID-based path
        return f"{path_prefix}/document_{document.pk}"

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
            self.stdout.write(self.style.WARNING("DRY-RUN MODE - No changes were made"))

        self.stdout.write(f"Corpuses processed: {stats['corpuses_processed']}")
        self.stdout.write(f"Documents processed: {stats['documents_processed']}")
        self.stdout.write(f"DocumentPaths created: {stats['paths_created']}")
        self.stdout.write(
            f"Documents already had paths: {stats['paths_already_existed']}"
        )

        if stats["errors"]:
            self.stdout.write(
                "\n" + self.style.ERROR(f"Errors ({len(stats['errors'])}):")
            )
            for error in stats["errors"]:
                self.stdout.write(f"  - {error}")

        self.stdout.write("=" * 60)

        if not dry_run and stats["paths_created"] > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\n✓ Successfully created {stats['paths_created']} DocumentPath records"
                )
            )
        elif dry_run and stats["paths_created"] > 0:
            self.stdout.write(
                self.style.WARNING(
                    f"\n→ Would create {stats['paths_created']} DocumentPath records"
                )
            )
            self.stdout.write("  Run without --dry-run to apply changes")
