"""Metadata (Datacell) read-service — permission-filtered metadata queries.

Relocated verbatim from the former ``extracts/query_optimizer.py``
``MetadataQueryOptimizer`` class as Phase 3 of the service-layer
centralization roadmap — see
``docs/refactor_plans/2026-05-19-service-layer-centralization-design.md``.

Behaviour is preserved exactly — this is a relocation, not a rewrite.
Permission model (same as annotations): effective permission =
``MIN(document_permission, corpus_permission)``.
"""

from __future__ import annotations

from collections import defaultdict

from django.db.models import QuerySet

from opencontractserver.extracts.models import Column, Datacell
from opencontractserver.shared.services import BaseService


class MetadataService(BaseService):
    """
    Optimized metadata (Datacell) queries with permission filtering.

    Permission model (same as annotations):
    - Document permissions are primary (most restrictive)
    - Corpus permissions are secondary
    - Effective permission = MIN(document_permission, corpus_permission)

    Use this optimizer for:
    - Fetching metadata for single documents
    - Batch fetching metadata for multiple documents (N+1 fix)
    - Any query that needs permission-aware metadata access
    """

    @classmethod
    def _compute_effective_permissions(
        cls, user, document_id: int, corpus_id: int
    ) -> tuple[bool, bool, bool, bool]:
        """
        Compute effective permissions based on document and corpus.

        Returns: (can_read, can_create, can_update, can_delete).

        Issue #1690: collapses 8 sequential ``user_can`` calls (one per
        permission-type per object) into at most two
        ``get_users_permissions_for_obj`` calls plus set-membership tests.
        Tier-2 batching that shares a granted-set cache across the document
        and corpus is deferred to issue #1691, which threads ``request``
        into this code path.
        """
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.documents.models import Document
        from opencontractserver.utils.permissioning import (
            get_users_permissions_for_obj,
        )

        # scoped admin access, 2026-05: admins computed like a normal user
        # Anonymous users only have read access to public documents/corpuses
        if user.is_anonymous:
            try:
                document = Document.objects.get(id=document_id)
                corpus = Corpus.objects.get(id=corpus_id)
                if document.is_public and corpus.is_public:
                    return True, False, False, False
            except (Document.DoesNotExist, Corpus.DoesNotExist):
                pass
            return False, False, False, False

        def _crud_from_granted(
            granted: set[str], model_name: str
        ) -> tuple[bool, bool, bool, bool]:
            return (
                f"read_{model_name}" in granted,
                f"create_{model_name}" in granted,
                f"update_{model_name}" in granted,
                f"remove_{model_name}" in granted,
            )

        # Check document permissions (primary)
        try:
            document = Document.objects.get(id=document_id)
        except Document.DoesNotExist:
            return False, False, False, False

        # Creator short-circuit mirrors ``_default_user_can`` in
        # ``utils/permissioning.py`` so behavior matches the legacy
        # per-permission ``user_can`` chain even when explicit guardian
        # rows aren't present on the instance. Skipping the guardian
        # fetch for creators avoids ~6 queries per object on the owner
        # hot path.
        if document.creator_id == user.id:
            doc_read, doc_create, doc_update, doc_delete = True, True, True, True
        else:
            doc_granted = get_users_permissions_for_obj(user=user, instance=document)
            doc_read, doc_create, doc_update, doc_delete = _crud_from_granted(
                doc_granted, "document"
            )

        # If no document read permission, no access
        if not doc_read:
            return False, False, False, False

        # Check corpus permissions (secondary) and apply most restrictive
        try:
            corpus = Corpus.objects.get(id=corpus_id)
        except Corpus.DoesNotExist:
            return False, False, False, False

        if corpus.creator_id == user.id:
            corpus_read, corpus_create, corpus_update, corpus_delete = (
                True,
                True,
                True,
                True,
            )
        else:
            corpus_granted = get_users_permissions_for_obj(user=user, instance=corpus)
            corpus_read, corpus_create, corpus_update, corpus_delete = (
                _crud_from_granted(corpus_granted, "corpus")
            )

        # Apply MIN logic: effective = MIN(doc_perm, corpus_perm)
        return (
            doc_read and corpus_read,
            doc_create and corpus_create,
            doc_update and corpus_update,
            doc_delete and corpus_delete,
        )

    @classmethod
    def _get_readable_document_ids_bulk(
        cls, user, document_ids: list[int], documents_queryset
    ) -> set[int]:
        """
        Bulk check which documents the user can read.

        This method avoids O(n) individual permission checks by querying
        guardian permission tables directly.

        Returns: Set of document IDs the user has read access to
        """
        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType
        from django.db.models import Q

        from opencontractserver.documents.models import (
            DocumentGroupObjectPermission,
            DocumentUserObjectPermission,
        )

        # Get the read_document permission ID
        content_type = ContentType.objects.get(app_label="documents", model="document")
        read_perm = Permission.objects.filter(
            codename="read_document", content_type=content_type
        ).first()

        if not read_perm:
            # Fallback to empty if permission doesn't exist
            return set()

        # Bulk query: documents the user has direct read permission on
        user_permitted_ids = set(
            DocumentUserObjectPermission.objects.filter(
                permission_id=read_perm.id,
                user_id=user.id,
                content_object_id__in=document_ids,
            ).values_list("content_object_id", flat=True)
        )

        # Bulk query: documents the user has read permission on via groups
        user_group_ids = list(user.groups.values_list("id", flat=True))
        if user_group_ids:
            group_permitted_ids = set(
                DocumentGroupObjectPermission.objects.filter(
                    permission_id=read_perm.id,
                    group_id__in=user_group_ids,
                    content_object_id__in=document_ids,
                ).values_list("content_object_id", flat=True)
            )
        else:
            group_permitted_ids = set()

        # Documents where user is creator or document is public
        creator_public_ids = set(
            documents_queryset.filter(
                Q(creator_id=user.id) | Q(is_public=True)
            ).values_list("id", flat=True)
        )

        # Union all sources of read permission
        return user_permitted_ids | group_permitted_ids | creator_public_ids

    @classmethod
    def get_corpus_metadata_columns(
        cls, user, corpus_id: int, manual_only: bool = True
    ) -> QuerySet:
        """
        Get metadata columns for a corpus with permission check.

        Args:
            user: The requesting user
            corpus_id: The corpus ID (local, not global)
            manual_only: If True, only return manual entry columns (default)

        Returns:
            QuerySet of Column objects ordered by display_order
        """
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.types.enums import PermissionTypes

        try:
            corpus = Corpus.objects.get(pk=corpus_id)

            # Check corpus read permission
            # scoped admin access, 2026-05: admins computed like a normal user
            if user.is_anonymous:
                if not corpus.is_public:
                    return Column.objects.none()
            elif not corpus.user_can(user, PermissionTypes.READ):
                return Column.objects.none()

            # Get metadata fieldset
            if not hasattr(corpus, "metadata_schema") or not corpus.metadata_schema:
                return Column.objects.none()

            qs = corpus.metadata_schema.columns.all()
            if manual_only:
                qs = qs.filter(is_manual_entry=True)

            return qs.order_by("display_order")

        except Corpus.DoesNotExist:
            return Column.objects.none()

    @classmethod
    def get_document_metadata(
        cls,
        user,
        document_id: int,
        corpus_id: int,
        manual_only: bool = True,
    ) -> QuerySet:
        """
        Get metadata datacells for a single document with permission filtering.

        Args:
            user: The requesting user
            document_id: The document ID (local, not global)
            corpus_id: The corpus ID (local, not global)
            manual_only: If True, only return manual entry datacells (default)

        Returns:
            QuerySet of Datacell objects with related column data
        """
        from opencontractserver.corpuses.models import Corpus

        # Check permissions
        can_read, _, _, _ = cls._compute_effective_permissions(
            user, document_id, corpus_id
        )
        if not can_read:
            return Datacell.objects.none()

        # Get corpus metadata schema
        try:
            corpus = Corpus.objects.get(pk=corpus_id)
            if not hasattr(corpus, "metadata_schema") or not corpus.metadata_schema:
                return Datacell.objects.none()

            qs = Datacell.objects.filter(
                document_id=document_id,
                column__fieldset=corpus.metadata_schema,
            )

            if manual_only:
                qs = qs.filter(column__is_manual_entry=True)

            return qs.select_related("column", "creator")

        except Corpus.DoesNotExist:
            return Datacell.objects.none()

    @classmethod
    def get_documents_metadata_batch(
        cls,
        user,
        document_ids: list[int],
        corpus_id: int,
        manual_only: bool = True,
        context=None,
    ) -> dict[int, list[Datacell]]:
        """
        Get metadata datacells for multiple documents in a single optimized query.

        This method solves the N+1 problem when loading metadata for a grid view.
        Instead of fetching metadata for each document individually, this fetches
        all metadata for all requested documents in one database query.

        Permission model:
        - Each document is checked against document + corpus permissions (MIN logic)
        - Only datacells for documents the user can read are returned

        Args:
            user: The requesting user
            document_ids: List of document IDs (local, not global)
            corpus_id: The corpus ID (local, not global)
            manual_only: If True, only return manual entry datacells (default)
            context: Optional GraphQL context for request-level caching

        Returns:
            Dict mapping document_id -> list of Datacell objects
        """
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.documents.models import Document
        from opencontractserver.types.enums import PermissionTypes

        result: dict[int, list[Datacell]] = defaultdict(list)

        if not document_ids:
            return result

        # Check corpus permission first (applies to all documents)
        try:
            corpus = Corpus.objects.get(pk=corpus_id)
        except Corpus.DoesNotExist:
            return result

        # scoped admin access, 2026-05: admins computed like a normal user
        # Anonymous user corpus check
        if user.is_anonymous:
            if not corpus.is_public:
                return result
        # Authenticated user corpus check
        elif not corpus.user_can(user, PermissionTypes.READ, request=context):
            return result

        # Check if corpus has metadata schema
        if not hasattr(corpus, "metadata_schema") or not corpus.metadata_schema:
            return result

        # Get all documents and check permissions using bulk queries
        documents = Document.objects.filter(pk__in=document_ids)

        # scoped admin access, 2026-05: admins computed like a normal user
        if user.is_anonymous:
            # Anonymous users can only read public documents
            readable_doc_ids = set(
                documents.filter(is_public=True).values_list("id", flat=True)
            )
        else:
            # Bulk permission check using guardian tables directly
            # This avoids O(n) individual permission checks for large document lists
            readable_doc_ids = cls._get_readable_document_ids_bulk(
                user, document_ids, documents
            )

        if not readable_doc_ids:
            return result

        # Initialize result with empty lists for all readable documents
        # This ensures documents with no datacells are still included in the result
        for doc_id in readable_doc_ids:
            result[doc_id] = []

        # Single query for all datacells with related data
        qs = Datacell.objects.filter(
            document_id__in=readable_doc_ids,
            column__fieldset=corpus.metadata_schema,
        )

        if manual_only:
            qs = qs.filter(column__is_manual_entry=True)

        # Optimize with select_related for efficient joins
        datacells = qs.select_related("column", "document", "creator")

        # Group by document
        for datacell in datacells:
            result[datacell.document_id].append(datacell)

        return result

    @classmethod
    def get_metadata_completion_status(
        cls,
        user,
        document_id: int,
        corpus_id: int,
    ) -> dict | None:
        """
        Get metadata completion status for a document.

        Returns:
            Dict with total_fields, filled_fields, missing_fields, percentage, missing_required
            or None if user doesn't have permission
        """
        from opencontractserver.corpuses.models import Corpus

        # Check permissions
        can_read, _, _, _ = cls._compute_effective_permissions(
            user, document_id, corpus_id
        )
        if not can_read:
            return None

        try:
            corpus = Corpus.objects.get(pk=corpus_id)
        except Corpus.DoesNotExist:
            return None

        # Check if corpus has metadata schema
        if not hasattr(corpus, "metadata_schema") or not corpus.metadata_schema:
            return {
                "total_fields": 0,
                "filled_fields": 0,
                "missing_fields": 0,
                "percentage": 100.0,
                "missing_required": [],
            }

        # Force evaluation once to avoid multiple queries
        columns = list(corpus.metadata_schema.columns.filter(is_manual_entry=True))
        total_fields = len(columns)

        if total_fields == 0:
            return {
                "total_fields": 0,
                "filled_fields": 0,
                "missing_fields": 0,
                "percentage": 100.0,
                "missing_required": [],
            }

        # Get column IDs for filtering
        column_ids = [c.id for c in columns]

        # Get filled datacells - use column_ids to avoid passing queryset
        filled_datacells = Datacell.objects.filter(
            document_id=document_id, column_id__in=column_ids
        ).exclude(data__value__isnull=True)

        filled_count = filled_datacells.count()
        filled_column_ids = set(filled_datacells.values_list("column_id", flat=True))

        # Find missing required fields (no additional queries - columns already evaluated)
        missing_required = []
        for column in columns:
            if column.id not in filled_column_ids:
                config = column.validation_config or {}
                if config.get("required", False):
                    missing_required.append(column.name)

        percentage = (filled_count / total_fields * 100) if total_fields > 0 else 0

        return {
            "total_fields": total_fields,
            "filled_fields": filled_count,
            "missing_fields": total_fields - filled_count,
            "percentage": percentage,
            "missing_required": missing_required,
        }

    @classmethod
    def check_metadata_mutation_permission(
        cls,
        user,
        document_id: int,
        corpus_id: int,
        permission_type: str = "UPDATE",
    ) -> tuple[bool, str]:
        """
        Check if user has permission to mutate metadata on a document.

        Permission model for metadata (different from annotations):
        - Metadata is a CORPUS-LEVEL feature (columns defined at corpus level)
        - Requires: Corpus UPDATE/DELETE permission + Document READ permission
        - This allows corpus owners/editors to manage metadata for any document
          they can see in their corpus, without needing explicit document permissions

        This differs from the annotation model (MIN of doc + corpus) because:
        - Metadata schemas are owned by the corpus, not the document
        - Corpus editors should be able to fill in metadata without explicit
          document UPDATE permissions (which aren't always assigned for
          corpus-scoped documents for performance reasons)

        Args:
            user: The requesting user
            document_id: The document ID (local, not global)
            corpus_id: The corpus ID (local, not global)
            permission_type: "UPDATE" or "DELETE" (default: "UPDATE")

        Returns:
            Tuple of (has_permission: bool, error_message: str)
            If has_permission is True, error_message will be empty.
        """
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.documents.models import Document
        from opencontractserver.types.enums import PermissionTypes

        # Anonymous users cannot mutate
        if user.is_anonymous:
            return False, "Authentication required"

        # scoped admin access, 2026-05: admins computed like a normal user

        # Check corpus exists first (needed for document visibility check)
        try:
            corpus = Corpus.objects.get(id=corpus_id)
        except Corpus.DoesNotExist:
            return False, "Corpus not found"

        # Check document visibility using the query resolver pattern.
        # IMPORTANT: We use visible_to_user() instead of the per-object user_can()
        # check because corpus-scoped documents may not have explicit guardian
        # permissions. visible_to_user() handles: creator access, is_public,
        # guardian permissions, and corpus membership — the full visibility model.
        doc_visible = (
            Document.objects.visible_to_user(user).filter(id=document_id).exists()
        )
        if not doc_visible:
            return False, "Document not found or not accessible"

        # Check corpus permission (UPDATE or DELETE based on operation).
        # For corpus, we use the per-object user_can() check because corpus
        # permissions are always explicit (not inherited from a parent context).
        corpus_perm_type = (
            PermissionTypes.DELETE
            if permission_type == "DELETE"
            else PermissionTypes.UPDATE
        )
        if not corpus.user_can(user, corpus_perm_type):
            return False, f"You don't have {permission_type} permission on this corpus"

        return True, ""

    @classmethod
    def validate_metadata_column(
        cls,
        column_id: int,
        corpus_id: int,
    ) -> tuple[bool, str, Column | None]:
        """
        Validate that a column belongs to the corpus's metadata schema and is manual entry.

        Args:
            column_id: The column ID (local, not global)
            corpus_id: The corpus ID (local, not global)

        Returns:
            Tuple of (is_valid: bool, error_message: str, column: Column | None)
        """
        from opencontractserver.corpuses.models import Corpus

        try:
            column = Column.objects.get(pk=column_id)
        except Column.DoesNotExist:
            return False, "Column not found", None

        try:
            corpus = Corpus.objects.get(pk=corpus_id)
        except Corpus.DoesNotExist:
            return False, "Corpus not found", None

        # Check column belongs to corpus metadata schema
        if not (
            column.fieldset
            and hasattr(column.fieldset, "corpus")
            and column.fieldset.corpus_id == corpus.id
        ):
            return False, "Column does not belong to corpus metadata schema", None

        # Check it's a manual entry column
        if not column.is_manual_entry:
            return False, "Only manual entry columns can be modified", None

        return True, "", column
