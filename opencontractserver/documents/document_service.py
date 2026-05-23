"""
DocumentService - Source of truth for document-level operations and permissioning.

Use this service for any operation where the *document* is the noun and corpus
context is incidental: creation, quota, validation, permissions, standalone
lookup. Operations that require corpus context (lifecycle within a corpus —
soft delete / restore / permanently delete, corpus-scoped lookup, folder
management, etc.) live on the segmented services in
:mod:`opencontractserver.corpuses.services`.

Key Design Principles
---------------------
1. DRY Permissions: Document-level permission checks live here once.
2. Transaction Safety: All mutations wrapped in transactions.
3. IDOR Protection: Consistent error semantics for not-found vs permission-denied.
4. Single Responsibility: Pure document operations; no corpus knowledge.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db import transaction

from opencontractserver.pipeline.registry import get_allowed_mime_types
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

if TYPE_CHECKING:
    from opencontractserver.documents.models import Document
    from opencontractserver.users.models import User

logger = logging.getLogger(__name__)


class DocumentService:
    """
    Centralized service for document-level operations and permissioning.

    Use this service for any operation where the *document* is the noun and
    corpus context is incidental: creation, quota, validation, permissions,
    standalone lookup. For corpus-scoped operations (give me documents in
    corpus X for user Y, lifecycle within a corpus, folder management),
    use the segmented services in :mod:`opencontractserver.corpuses.services`.

    Follows the QueryOptimizer pattern with static classmethod-based API.

    Usage::

        # Document creation
        doc, error = DocumentService.create_document(
            user, file_bytes, filename, title,
        )

        # Document lookup
        doc = DocumentService.get_document_by_id(user, document_id)

        # Permission management
        ok, error = DocumentService.set_document_permissions(
            user, document, target_user, [PermissionTypes.READ],
        )
    """

    # =========================================================================
    # DOCUMENT CREATION
    # =========================================================================

    @classmethod
    def check_user_upload_quota(
        cls,
        user: User,
    ) -> tuple[bool, str]:
        """
        Check if user can create more documents based on usage caps.

        Args:
            user: User to check quota for

        Returns:
            (can_upload, error_message) - True if user can upload, error if not
        """
        if not user.is_usage_capped:
            return True, ""

        from opencontractserver.documents.models import Document

        current_count = Document.objects.filter(creator=user).count()
        cap = getattr(settings, "USAGE_CAPPED_USER_DOC_CAP_COUNT", 10)

        if current_count >= cap:
            return False, (
                f"Your usage is capped at {cap} documents. "
                f"Try deleting an existing document first or contact the admin "
                f"for a higher limit."
            )

        return True, ""

    @classmethod
    def validate_file_type(
        cls,
        file_bytes: bytes,
    ) -> tuple[str | None, str]:
        """
        Validate and detect file MIME type.

        Args:
            file_bytes: Raw file bytes to analyze

        Returns:
            (mime_type, error_message) - mime_type is None if validation fails
        """
        import filetype

        from opencontractserver.utils.files import is_plaintext_content

        kind = filetype.guess(file_bytes)
        if kind is None:
            if is_plaintext_content(file_bytes):
                mime_type = "text/plain"
            else:
                return None, "Unable to determine file type"
        else:
            mime_type = kind.mime

        if mime_type not in get_allowed_mime_types():
            return None, f"Unallowed filetype: {mime_type}"

        return mime_type, ""

    @classmethod
    def create_document(
        cls,
        user: User,
        file_bytes: bytes,
        filename: str,
        title: str,
        description: str = "",
        custom_meta: dict | None = None,
        is_public: bool = False,
        slug: str | None = None,
        *,
        request: Any = None,
    ) -> tuple[Document | None, str]:
        """
        Create a standalone document (not attached to any corpus).

        This is the single entry point for creating documents outside of corpus context.
        Handles file type validation, usage quota checks, and permission setup.

        Args:
            user: Creating user
            file_bytes: Raw file bytes
            filename: Original filename
            title: Document title
            description: Document description
            custom_meta: Optional custom metadata dict
            is_public: Whether document should be public
            slug: Optional URL slug

        Returns:
            (document, error_message) - document is None if creation fails

        Note:
            For corpus imports with deduplication, use
            ``CorpusDocumentService.upload_document_to_corpus()`` instead.
        """
        from django.core.files.base import ContentFile

        from opencontractserver.documents.models import Document

        # Check quota
        can_upload, quota_error = cls.check_user_upload_quota(user)
        if not can_upload:
            return None, quota_error

        # Validate file type
        mime_type, type_error = cls.validate_file_type(file_bytes)
        if not mime_type:
            return None, type_error

        try:
            with transaction.atomic():
                # Create document based on file type
                if mime_type in [
                    "application/pdf",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ]:
                    pdf_file = ContentFile(file_bytes, name=filename)
                    document = Document.objects.create(
                        creator=user,
                        title=title,
                        description=description,
                        custom_meta=custom_meta or {},
                        pdf_file=pdf_file,
                        backend_lock=True,
                        is_public=is_public,
                        file_type=mime_type,
                        slug=slug,
                    )
                elif mime_type in ["text/plain", "application/txt"]:
                    txt_file = ContentFile(file_bytes, name=filename)
                    document = Document.objects.create(
                        creator=user,
                        title=title,
                        description=description,
                        custom_meta=custom_meta or {},
                        txt_extract_file=txt_file,
                        backend_lock=True,
                        is_public=is_public,
                        file_type=mime_type,
                        slug=slug,
                    )
                else:
                    return None, f"Unsupported file type: {mime_type}"

                # Set permissions for creator
                set_permissions_for_obj_to_user(
                    user,
                    document,
                    [PermissionTypes.CRUD],
                    request=request,
                )

                logger.info(
                    f"Created standalone document {document.id} "
                    f"(type={mime_type}) by user {user.id}"
                )

                return document, ""

        except Exception as e:
            logger.exception(f"Error creating document: {e}")
            return None, f"Error creating document: {e}"

    # =========================================================================
    # DOCUMENT LOOKUP
    # =========================================================================

    @classmethod
    def get_document_by_id(
        cls,
        user: User,
        document_id: int,
        *,
        request: Any = None,
    ) -> Document | None:
        """
        Get a document by ID if user has access.

        Args:
            user: Requesting user
            document_id: Document ID

        Returns:
            Document if found and accessible, None otherwise

        Note:
            Returns same error (None) whether document doesn't exist or
            user doesn't have access (IDOR protection).
        """
        from opencontractserver.documents.models import Document

        try:
            document = Document.objects.get(pk=document_id)
        except Document.DoesNotExist:
            return None

        # Single centralised READ check — encapsulates superuser / creator /
        # is_public / guardian rules and participates in the request-scoped
        # permission cache when ``request`` is supplied.
        if document.user_can(user, PermissionTypes.READ, request=request):
            return document

        return None

    # =========================================================================
    # DOCUMENT PERMISSIONS
    # =========================================================================

    @classmethod
    def set_document_permissions(
        cls,
        user: User,
        document: Document,
        target_user: User,
        permissions: list[PermissionTypes],
        *,
        request: Any = None,
    ) -> tuple[bool, str]:
        """
        Set permissions for a document.

        Args:
            user: User setting permissions (must be owner or have permission control)
            document: Document to set permissions on
            target_user: User to grant permissions to
            permissions: List of PermissionTypes to grant

        Returns:
            (success, error_message)

        Permissions:
            Requires document ownership or PERMISSION permission
        """
        # Single centralised PERMISSION check — encapsulates superuser / creator /
        # guardian rules and participates in the request-scoped permission cache.
        if not document.user_can(user, PermissionTypes.PERMISSION, request=request):
            return (
                False,
                "Permission denied: Cannot modify permissions for this document",
            )

        try:
            set_permissions_for_obj_to_user(
                target_user,
                document,
                permissions,
                request=request,
            )
            logger.info(
                f"Set permissions {permissions} on document {document.id} "
                f"for user {target_user.id} by user {user.id}"
            )
            return True, ""
        except Exception as e:
            logger.exception(f"Error setting document permissions: {e}")
            return False, f"Error setting permissions: {e}"
