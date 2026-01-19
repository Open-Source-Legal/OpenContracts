"""
Management command to migrate orphaned documents (documents without any corpus) to
per-user system corpuses.

This command is part of the "documents must always belong to a corpus" constraint.
It creates "My Documents" corpuses for document creators and users with edit permissions,
and "Shared With Me" corpuses for users with read-only permissions.

Usage:
    python manage.py migrate_orphaned_documents [--dry-run] [--user-id ID] [--verbose]
"""

import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import (
    Document,
    DocumentPath,
    DocumentUserObjectPermission,
)
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

logger = logging.getLogger(__name__)
User = get_user_model()

# Permission codenames that grant edit access
EDIT_PERMISSION_CODENAMES = {
    "change_document",
    "update_document",
    "remove_document",
    "delete_document",
}

# Permission codenames that grant read-only access
READ_PERMISSION_CODENAMES = {
    "view_document",
    "read_document",
}


class Command(BaseCommand):
    """
    Migrate orphaned documents to per-user system corpuses.

    This command:
    1. Identifies documents with no active DocumentPath records (orphaned)
    2. For each orphan, determines who has access via creator and guardian permissions
    3. Creates "My Documents" corpus for users with edit access
    4. Creates "Shared With Me" corpus for users with read-only access
    5. Creates DocumentPath records linking documents to appropriate corpuses
    6. Drops non-default embeddings (they'll be regenerated with corpus embedder)
    """

    help = "Migrate orphaned documents to per-user system corpuses"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run in dry-run mode (no database changes)",
        )
        parser.add_argument(
            "--user-id",
            type=int,
            help="Process only orphaned documents for a specific user by ID",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="Number of documents to process in each batch (default: 100)",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Show detailed progress information",
        )
        parser.add_argument(
            "--skip-embedding-cleanup",
            action="store_true",
            help="Skip deletion of non-default embeddings",
        )

    def handle(self, *args, **options):
        """Execute the migration command."""
        dry_run = options["dry_run"]
        user_id = options.get("user_id")
        batch_size = options["batch_size"]
        verbose = options["verbose"]
        skip_embedding_cleanup = options["skip_embedding_cleanup"]

        if dry_run:
            self.stdout.write(
                self.style.WARNING("Running in DRY-RUN mode - no changes will be made")
            )

        # Find all orphaned documents
        orphaned_docs = self._find_orphaned_documents(user_id)
        total_orphans = orphaned_docs.count()

        if total_orphans == 0:
            self.stdout.write(
                self.style.SUCCESS("No orphaned documents found. Nothing to migrate.")
            )
            return

        self.stdout.write(f"Found {total_orphans} orphaned document(s) to process\n")

        # Track statistics
        stats = {
            "documents_processed": 0,
            "my_documents_corpuses_created": 0,
            "shared_with_me_corpuses_created": 0,
            "document_paths_created": 0,
            "embeddings_deleted": 0,
            "errors": [],
        }

        # Process documents in batches
        processed = 0
        for doc in orphaned_docs.iterator():
            try:
                doc_stats = self._process_orphaned_document(
                    document=doc,
                    dry_run=dry_run,
                    verbose=verbose,
                    skip_embedding_cleanup=skip_embedding_cleanup,
                )

                stats["documents_processed"] += 1
                stats["my_documents_corpuses_created"] += doc_stats[
                    "my_documents_created"
                ]
                stats["shared_with_me_corpuses_created"] += doc_stats[
                    "shared_with_me_created"
                ]
                stats["document_paths_created"] += doc_stats["paths_created"]
                stats["embeddings_deleted"] += doc_stats["embeddings_deleted"]

                processed += 1
                if processed % batch_size == 0:
                    self.stdout.write(f"  Processed {processed}/{total_orphans}...")

            except Exception as e:
                error_msg = f"Error processing document {doc.pk}: {e}"
                stats["errors"].append(error_msg)
                self.stdout.write(self.style.ERROR(error_msg))
                if verbose:
                    import traceback

                    self.stdout.write(traceback.format_exc())

        # Print summary
        self._print_summary(stats, dry_run)

    def _find_orphaned_documents(self, user_id=None):
        """Find documents with no active DocumentPath records."""
        # Get IDs of documents that have active paths
        docs_with_paths = DocumentPath.objects.filter(
            is_current=True, is_deleted=False
        ).values_list("document_id", flat=True)

        # Find documents NOT in that set
        orphaned = Document.objects.exclude(id__in=docs_with_paths)

        if user_id:
            orphaned = orphaned.filter(creator_id=user_id)

        return orphaned.order_by("id")

    def _process_orphaned_document(
        self, document, dry_run, verbose, skip_embedding_cleanup
    ):
        """Process a single orphaned document."""
        stats = {
            "my_documents_created": 0,
            "shared_with_me_created": 0,
            "paths_created": 0,
            "embeddings_deleted": 0,
        }

        if verbose:
            self.stdout.write(
                f"\nProcessing document {document.pk}: {document.title or '(untitled)'}"
            )

        # Determine who has access to this document
        users_with_edit = set()
        users_with_read_only = set()

        # Creator always has edit access
        if document.creator:
            users_with_edit.add(document.creator)

        # Check guardian permissions
        perms = DocumentUserObjectPermission.objects.filter(
            content_object=document
        ).select_related("user", "permission")

        for perm in perms:
            user = perm.user
            if user == document.creator:
                continue  # Already handled

            codename = perm.permission.codename
            if codename in EDIT_PERMISSION_CODENAMES:
                users_with_edit.add(user)
                # Remove from read-only if they have edit
                users_with_read_only.discard(user)
            elif codename in READ_PERMISSION_CODENAMES:
                # Only add to read-only if they don't have edit
                if user not in users_with_edit:
                    users_with_read_only.add(user)

        if verbose:
            self.stdout.write(
                f"  Users with edit access: {[u.username for u in users_with_edit]}"
            )
            self.stdout.write(
                f"  Users with read-only access: {[u.username for u in users_with_read_only]}"
            )

        # Create corpus assignments for users with edit access
        for user in users_with_edit:
            corpus, created = self._get_or_create_my_documents_corpus(user, dry_run)
            if created:
                stats["my_documents_created"] += 1

            if self._create_document_path(document, corpus, user, dry_run, verbose):
                stats["paths_created"] += 1

        # Create corpus assignments for users with read-only access
        for user in users_with_read_only:
            corpus, created = self._get_or_create_shared_with_me_corpus(user, dry_run)
            if created:
                stats["shared_with_me_created"] += 1

            if self._create_document_path(document, corpus, user, dry_run, verbose):
                stats["paths_created"] += 1

        # Clean up non-default embeddings
        if not skip_embedding_cleanup:
            deleted_count = self._cleanup_embeddings(document, dry_run, verbose)
            stats["embeddings_deleted"] = deleted_count

        return stats

    def _get_or_create_my_documents_corpus(self, user, dry_run):
        """Get or create user's editable 'My Documents' corpus."""
        try:
            corpus = Corpus.objects.get(
                creator=user, title="My Documents", is_system_corpus=True
            )
            return corpus, False
        except Corpus.DoesNotExist:
            if dry_run:
                # Return a fake corpus for dry run
                return None, True

            with transaction.atomic():
                corpus = Corpus.objects.create(
                    creator=user,
                    title="My Documents",
                    description="Auto-created corpus for your documents",
                    is_public=False,
                    is_system_corpus=True,
                )
                set_permissions_for_obj_to_user(user, corpus, [PermissionTypes.CRUD])
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  Created 'My Documents' corpus for user {user.username}"
                    )
                )
                return corpus, True

    def _get_or_create_shared_with_me_corpus(self, user, dry_run):
        """Get or create user's read-only 'Shared With Me' corpus."""
        try:
            corpus = Corpus.objects.get(
                creator=user, title="Shared With Me", is_system_corpus=True
            )
            return corpus, False
        except Corpus.DoesNotExist:
            if dry_run:
                # Return a fake corpus for dry run
                return None, True

            with transaction.atomic():
                corpus = Corpus.objects.create(
                    creator=user,
                    title="Shared With Me",
                    description="Documents shared with you (read-only)",
                    is_public=False,
                    is_system_corpus=True,
                )
                # User only gets read permission on this corpus
                set_permissions_for_obj_to_user(user, corpus, [PermissionTypes.READ])
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  Created 'Shared With Me' corpus for user {user.username}"
                    )
                )
                return corpus, True

    def _create_document_path(self, document, corpus, user, dry_run, verbose):
        """Create DocumentPath linking document to corpus."""
        if dry_run:
            if verbose:
                corpus_title = corpus.title if corpus else "(new corpus)"
                self.stdout.write(
                    f"    Would create DocumentPath: {document.title} -> {corpus_title}"
                )
            return True

        # Check if path already exists (shouldn't happen but be safe)
        existing = DocumentPath.objects.filter(
            document=document, corpus=corpus, is_current=True, is_deleted=False
        ).exists()

        if existing:
            if verbose:
                self.stdout.write(
                    f"    DocumentPath already exists for document {document.pk} in corpus {corpus.pk}"
                )
            return False

        # Generate unique path
        base_path = self._generate_path(document)
        path = base_path
        counter = 1

        while DocumentPath.objects.filter(
            corpus=corpus, path=path, is_current=True, is_deleted=False
        ).exists():
            path = f"{base_path}_{counter}"
            counter += 1

        with transaction.atomic():
            DocumentPath.objects.create(
                document=document,
                corpus=corpus,
                folder=None,
                path=path,
                version_number=1,
                parent=None,
                is_current=True,
                is_deleted=False,
                creator=user,
            )

        if verbose:
            self.stdout.write(
                self.style.SUCCESS(
                    f"    Created DocumentPath: {path} in corpus '{corpus.title}'"
                )
            )

        return True

    def _generate_path(self, document):
        """Generate a filesystem path for a document."""
        if document.title:
            safe_title = "".join(
                c if c.isalnum() or c in "-_." else "_" for c in document.title[:100]
            ).strip("_")
            if safe_title:
                return f"/migrated/{safe_title}"

        return f"/migrated/document_{document.pk}"

    def _cleanup_embeddings(self, document, dry_run, verbose):
        """Delete non-default embeddings for the document."""
        from opencontractserver.annotations.models import Embedding

        default_embedder = getattr(settings, "DEFAULT_EMBEDDER", None)

        if not default_embedder:
            if verbose:
                self.stdout.write(
                    "    Skipping embedding cleanup - DEFAULT_EMBEDDER not configured"
                )
            return 0

        # Find embeddings to delete (non-default)
        embeddings_to_delete = Embedding.objects.filter(document=document).exclude(
            embedder_path=default_embedder
        )

        count = embeddings_to_delete.count()

        if count == 0:
            return 0

        if dry_run:
            if verbose:
                self.stdout.write(
                    f"    Would delete {count} non-default embedding(s)"
                )
            return count

        embeddings_to_delete.delete()

        if verbose:
            self.stdout.write(
                self.style.SUCCESS(f"    Deleted {count} non-default embedding(s)")
            )

        return count

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

        self.stdout.write(f"Documents processed: {stats['documents_processed']}")
        self.stdout.write(
            f"'My Documents' corpuses created: {stats['my_documents_corpuses_created']}"
        )
        self.stdout.write(
            f"'Shared With Me' corpuses created: {stats['shared_with_me_corpuses_created']}"
        )
        self.stdout.write(f"DocumentPaths created: {stats['document_paths_created']}")
        self.stdout.write(f"Embeddings deleted: {stats['embeddings_deleted']}")

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
                    f"\nSuccessfully migrated {stats['documents_processed']} orphaned document(s)"
                )
            )
        elif dry_run and stats["documents_processed"] > 0:
            self.stdout.write(
                self.style.WARNING(
                    f"\nWould migrate {stats['documents_processed']} orphaned document(s)"
                )
            )
            self.stdout.write("  Run without --dry-run to apply changes")
