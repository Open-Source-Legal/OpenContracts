"""Extract read-service — visibility and permission queries for ``Extract``.

Relocated from the former ``annotations/query_optimizer.py`` (where the
``ExtractQueryOptimizer`` class was misfiled — ``Extract`` is an
``extracts`` concern, not an ``annotations`` one) into its correct app as
Phase 3 of the service-layer centralization roadmap — see
``docs/refactor_plans/2026-05-19-service-layer-centralization-design.md``.

Behaviour is preserved exactly — this is a relocation, not a rewrite.
"""

from typing import TYPE_CHECKING, Any, Optional

from django.db.models import Exists, OuterRef, Q, QuerySet

from opencontractserver.shared.services import BaseService

if TYPE_CHECKING:
    from opencontractserver.extracts.models import Extract


class ExtractService(BaseService):
    """
    Optimized queries for Extract model with hybrid permission model.

    Permission model:
    - Extract has its own permissions (can be shared independently)
    - BUT visibility requires corpus permissions too
    - Datacells within are filtered by document permissions
    """

    @classmethod
    def check_extract_permission(
        cls, user, extract_id: int, context: Optional[Any] = None
    ) -> tuple[bool, Optional["Extract"]]:
        """
        Check if user can access an extract.
        Returns (has_permission, extract_object)

        Args:
            user: The requesting user
            extract_id: The extract ID to check
            context: Optional GraphQL context (``info.context``) threaded into
                ``user_can`` so Tier-2 request-scoped permission caching applies.
        """
        from opencontractserver.extracts.models import Extract
        from opencontractserver.types.enums import PermissionTypes

        # Superuser can see everything
        if user.is_superuser:
            try:
                extract = Extract.objects.get(id=extract_id)
                return True, extract
            except Extract.DoesNotExist:
                return False, None

        try:
            extract = Extract.objects.get(id=extract_id)

            # Check extract-level permission
            has_extract_perm = extract.creator_id == user.id or extract.user_can(
                user, PermissionTypes.READ, request=context
            )

            if not has_extract_perm:
                return False, None

            # Check corpus permission if extract has a corpus
            if extract.corpus:
                has_corpus_perm = (
                    extract.corpus.is_public
                    or extract.corpus.creator_id == user.id
                    or extract.corpus.user_can(
                        user, PermissionTypes.READ, request=context
                    )
                )
                if not has_corpus_perm:
                    return False, None

            return True, extract

        except Extract.DoesNotExist:
            return False, None

    @classmethod
    def get_visible_extracts(
        cls,
        user,
        corpus_id: Optional[int] = None,
        context: Optional[Any] = None,
    ) -> QuerySet:
        """
        Get extracts visible to user based on:
        1. User has permission on extract object
        2. User has READ permission on corpus

        Args:
            user: The requesting user
            corpus_id: Optional corpus ID to scope the query
            context: Optional GraphQL context (``info.context``) threaded into
                ``user_can`` so Tier-2 request-scoped permission caching applies.
        """
        from opencontractserver.corpuses.models import (
            Corpus,
            CorpusUserObjectPermission,
        )
        from opencontractserver.extracts.models import Extract
        from opencontractserver.types.enums import PermissionTypes

        if user.is_superuser:
            qs = Extract.objects.all()
        elif user.is_anonymous:
            # Anonymous users can only see public extracts in public corpuses
            qs = Extract.objects.filter(
                Q(is_public=True) & (Q(corpus__isnull=True) | Q(corpus__is_public=True))
            )
        else:
            # Import permission model
            from opencontractserver.extracts.models import ExtractUserObjectPermission

            # Get extracts where:
            # 1. User has permission on the extract (via creator, is_public, or guardian) AND
            # 2. User has permission on the corpus (required for both anonymous and authenticated)
            # Note: is_public=True grants extract-level access, but corpus access is still checked below
            qs = Extract.objects.filter(
                # User must have extract permission (one of: creator, public, or guardian)
                Q(creator=user)
                | Q(is_public=True)
                | Exists(
                    ExtractUserObjectPermission.objects.filter(
                        user=user, content_object_id=OuterRef("id")
                    )
                )
            ).filter(
                # AND user must have corpus permission
                Q(corpus__isnull=True)  # No corpus needed
                | Q(corpus__creator=user)
                | Q(corpus__is_public=True)
                | Exists(
                    CorpusUserObjectPermission.objects.filter(
                        user=user,
                        content_object_id=OuterRef("corpus_id"),
                        permission__codename__contains="read",
                    )
                )
            )

        # Filter by corpus if specified
        if corpus_id:
            # Check corpus permission
            try:
                corpus = Corpus.objects.get(id=corpus_id)
                # Anonymous users can only access public corpuses
                if user.is_anonymous:
                    if not corpus.is_public:
                        return Extract.objects.none()
                elif not user.is_superuser and not corpus.user_can(
                    user, PermissionTypes.READ, request=context
                ):
                    return Extract.objects.none()
            except Corpus.DoesNotExist:
                return Extract.objects.none()

            qs = qs.filter(corpus_id=corpus_id)

        # Optimize query
        qs = (
            qs.select_related("fieldset", "corpus", "creator", "corpus_action")
            .prefetch_related("documents", "fieldset__columns")
            .distinct()
        )

        return qs

    @classmethod
    def get_extract_datacells(
        cls, extract: "Extract", user, document_id: Optional[int] = None
    ) -> QuerySet:
        """
        Get datacells from an extract, filtered by document permissions.
        """
        from opencontractserver.documents.models import Document
        from opencontractserver.extracts.models import Datacell
        from opencontractserver.types.enums import PermissionTypes

        # Start with all datacells in the extract
        qs = Datacell.objects.filter(extract=extract)

        if document_id:
            # Filter to specific document if requested
            qs = qs.filter(document_id=document_id)

            # Check document permission
            if not user.is_superuser:
                try:
                    doc = Document.objects.get(id=document_id)
                    if not doc.user_can(user, PermissionTypes.READ):
                        return Datacell.objects.none()
                except Document.DoesNotExist:
                    return Datacell.objects.none()
        else:
            # Filter to only documents user can read
            if not user.is_superuser:
                readable_doc_ids = list(
                    Document.objects.visible_to_user(user)
                    .filter(id__in=extract.documents.values("id"))
                    .values_list("id", flat=True)
                )

                if not readable_doc_ids:
                    return Datacell.objects.none()

                qs = qs.filter(document_id__in=readable_doc_ids)

        # Optimize query
        qs = (
            qs.select_related(
                "column", "column__fieldset", "document", "approved_by", "rejected_by"
            )
            .prefetch_related("sources")
            .distinct()
        )

        return qs
