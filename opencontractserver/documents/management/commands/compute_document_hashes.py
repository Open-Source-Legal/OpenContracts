"""
Django management command to compute and store SHA-256 hashes for all existing PDF files
"""

import hashlib
import logging

from django.core.management.base import BaseCommand

from opencontractserver.documents.models import Document

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Compute and store SHA-256 hashes for all existing PDF files"

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="Number of documents to process in each batch (default: 100)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run without actually saving changes to the database",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Recompute hashes even for documents that already have them",
        )

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        dry_run = options["dry_run"]
        force = options["force"]

        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN MODE - No changes will be saved")
            )

        # Get documents that need hash computation
        if force:
            documents = Document.objects.filter(pdf_file__isnull=False)
            self.stdout.write(
                f"Processing all {documents.count()} documents with PDF files"
            )
        else:
            documents = Document.objects.filter(
                pdf_file__isnull=False, pdf_file_hash__isnull=True
            )
            self.stdout.write(
                f"Processing {documents.count()} documents without hashes"
            )

        processed = 0
        updated = 0
        errors = 0

        # Process in batches to avoid memory issues
        for document in documents.iterator(chunk_size=batch_size):
            try:
                if not document.pdf_file:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Document {document.id} has no PDF file, skipping"
                        )
                    )
                    continue

                # Check if file exists
                if not document.pdf_file.storage.exists(document.pdf_file.name):
                    self.stdout.write(
                        self.style.ERROR(
                            f"PDF file missing for document {document.id}: {document.pdf_file.name}"
                        )
                    )
                    errors += 1
                    continue

                # Compute hash
                old_hash = document.pdf_file_hash
                new_hash = self.compute_file_hash(document.pdf_file)

                if old_hash != new_hash:
                    if not dry_run:
                        document.pdf_file_hash = new_hash
                        document.save(update_fields=["pdf_file_hash"])

                    if old_hash:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"Updated hash for document {document.id}: {old_hash[:8]}... → {new_hash[:8]}..."
                            )
                        )
                    else:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"Computed hash for document {document.id}: {new_hash[:8]}..."
                            )
                        )
                    updated += 1
                else:
                    self.stdout.write(
                        f"Document {document.id} already has correct hash: {old_hash[:8]}..."
                    )

                processed += 1

                # Progress update every 10 documents
                if processed % 10 == 0:
                    self.stdout.write(
                        f"Progress: {processed}/{documents.count()} documents processed"
                    )

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f"Error processing document {document.id}: {str(e)}"
                    )
                )
                logger.exception(f"Error processing document {document.id}")
                errors += 1

        # Final summary
        self.stdout.write(self.style.SUCCESS("\n" + "=" * 50))
        self.stdout.write(self.style.SUCCESS("Hash computation complete!"))
        self.stdout.write(f"Total documents processed: {processed}")
        self.stdout.write(f"Hashes updated: {updated}")
        self.stdout.write(f"Errors encountered: {errors}")

        if dry_run:
            self.stdout.write(
                self.style.WARNING("\nDRY RUN - No changes were saved to the database")
            )

    def compute_file_hash(self, file_field):
        """
        Compute SHA-256 hash of a file field
        """
        sha256_hash = hashlib.sha256()

        # Open the file and read in chunks
        with file_field.open("rb") as f:
            # Read file in 64KB chunks to handle large files efficiently
            for chunk in iter(lambda: f.read(65536), b""):
                sha256_hash.update(chunk)

        return sha256_hash.hexdigest()
