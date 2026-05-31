"""Document-in-corpus operations for the corpus service layer.

``CorpusDocumentService`` is the source of truth for corpus-scoped document
access: membership checks, corpus-scoped document reads, and document-in-corpus
writes (upload / add / remove).

Document read access exposes TWO deliberate, separately-named semantics
(issue #1682 — no hidden semantic flips):

* ``get_corpus_documents`` is **corpus-as-gate**: corpus READ unlocks every
  document with an active path in that corpus. The documented default for
  pipeline-facing callers (MCP, discovery, badge / analysis tasks).
* ``get_corpus_documents_visible_to_user`` enforces
  **MIN(document_permission, corpus_permission)**: a private document inside a
  public (or merely shared) corpus stays hidden from a user without
  document-level READ. User-facing surfaces use this variant.

Split out of the former ``corpus_objs_service.py`` monolith — see
``docs/refactor_plans/2026-05-21-service-layer-phase2-corpus-services-plan.md``
(issue #1716, service-layer centralization Phase 2).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.db.models import QuerySet

from opencontractserver.shared.services.base import BaseService
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

if TYPE_CHECKING:
    from opencontractserver.corpuses.models import Corpus, CorpusFolder
    from opencontractserver.documents.models import Document
    from opencontractserver.users.models import User
    from opencontractserver.users.types import UserOrAnonymous

logger = logging.getLogger(__name__)


class CorpusDocumentService(BaseService):
    """Corpus-scoped document access, membership, and document-in-corpus writes.

    All read methods enforce corpus READ as the gate; all write methods
    enforce corpus UPDATE. See the module docstring for the two deliberate
    ``get_corpus_documents`` / ``get_corpus_documents_visible_to_user``
    read semantics.
    """

    @classmethod
    def _check_document_in_corpus(
        cls,
        document: Document,
        corpus: Corpus,
    ) -> bool:
        """
        Verify that a document belongs to a corpus.

        **NO PERMISSION CHECK.** This method is a raw membership query
        against ``DocumentPath`` — it does NOT verify that the caller can
        see the corpus or the document. Callers MUST gate corpus READ
        (typically via ``CorpusDocumentService.get_corpus_documents(...)``,
        ``Corpus.objects.visible_to_user(...).get(pk=...)``, or an
        equivalent ``user_can(... READ)`` check) BEFORE calling this.

        Used as a low-level post-condition inside service methods that
        have already enforced READ. The leading underscore marks the
        method as service-internal — new resolvers should reach for
        ``get_corpus_document_by_id`` (which gates corpus READ for you)
        instead.

        Args:
            document: The document to check
            corpus: The corpus to check membership in

        Returns:
            True if document belongs to corpus, False otherwise
        """
        from opencontractserver.documents.models import DocumentPath

        # Check DocumentPath (source of truth for corpus membership)
        return DocumentPath.objects.filter(
            document=document,
            corpus=corpus,
        ).exists()

    @classmethod
    def _build_corpus_documents_queryset(
        cls,
        corpus: Corpus,
        *,
        include_deleted: bool = False,
        include_caml: bool = False,
    ) -> QuerySet[Document]:
        """Single source of truth for the corpus → document path query.

        Centralises the join across ``DocumentPath`` so the soft-delete
        and CAML toggles compose cleanly. The pre-fix split where
        ``include_deleted=True`` used a hand-written ``DocumentPath``
        filter and ``include_deleted=False`` delegated to
        ``Corpus._get_active_documents`` would have drifted the moment
        one branch added (e.g.) ``select_related`` or refined the CAML
        exclusion — and pre-fix, the True branch silently bypassed CAML
        filtering altogether.

        Reserved for use by service methods that have already checked
        corpus READ. No permission gate here — the caller owns that.
        """

        from opencontractserver.constants.document_processing import (
            MARKDOWN_MIME_TYPE,
        )
        from opencontractserver.documents.models import Document, DocumentPath

        path_qs = DocumentPath.objects.filter(corpus=corpus, is_current=True)
        if not include_deleted:
            path_qs = path_qs.filter(is_deleted=False)

        doc_ids = path_qs.values_list("document_id", flat=True)
        # ``.distinct()`` is defensive, not load-bearing. ``DocumentPath`` has
        # no DB constraint preventing multiple ``is_current=True`` rows for the
        # same ``(corpus, document)`` pair — only ``unique_active_path_per_corpus``
        # (``(corpus, path)`` where ``is_current=True AND is_deleted=False``).
        # That means an aliased / renamed current path *or* an
        # include_deleted=True query that picks up both a soft-deleted current
        # path and a non-deleted current path could surface the same
        # ``document_id`` twice. The distinct() collapses those defensively
        # so the downstream service contract ("one document per row") holds
        # regardless of whether the rare duplicate path arises. Cheap on PG
        # against the small per-corpus working set.
        qs = Document.objects.filter(pk__in=doc_ids).distinct()
        if not include_caml:
            qs = qs.exclude(file_type=MARKDOWN_MIME_TYPE)
        return qs

    @staticmethod
    def with_readme_caml_doc(qs: QuerySet[Corpus]) -> QuerySet[Corpus]:
        """Return ``qs`` with ``readme_caml_document`` prefetched.

        Apply on every queryset where ``mdDescription`` or
        ``readmeCamlDocument`` may be selected so the resolver does not
        issue a per-row Document fetch. See spec §4.5 at
        ``docs/superpowers/specs/2026-05-27-canonical-caml-description-refactor-design.md``.

        The GraphQL resolver layer wires this into the corpus list/single
        entry points; tasks 5–6 below add those call sites.
        """
        return qs.select_related("readme_caml_document")

    @classmethod
    def get_corpus_documents(
        cls,
        user: UserOrAnonymous,
        corpus: Corpus,
        include_deleted: bool = False,
        include_caml: bool = False,
        *,
        request: Any = None,
    ) -> QuerySet[Document]:
        """
        Get all documents in a corpus.

        Args:
            user: Requesting user
            corpus: Corpus to get documents from
            include_deleted: Whether to include soft-deleted documents
            include_caml: Whether to include CAML / markdown documents.
                Defaults to False so extractors, analyzers, and other
                downstream consumers skip CAML articles by default —
                mirroring ``Corpus._get_active_documents`` so the two
                surfaces stay aligned regardless of which branch the
                caller takes.

        Returns:
            QuerySet of documents (empty if no access)

        Permissions:
            Requires corpus READ permission (corpus-as-gate semantic: if the
            user has corpus READ, every document with an active path in that
            corpus is returned).

        See Also:
            :meth:`get_corpus_documents_visible_to_user` for the
            MIN-permission variant that additionally hides documents the
            user cannot see at the document level.
        """
        from opencontractserver.documents.models import Document

        if not corpus.user_can(user, PermissionTypes.READ, request=request):
            return Document.objects.none()

        return cls._build_corpus_documents_queryset(
            corpus,
            include_deleted=include_deleted,
            include_caml=include_caml,
        )

    @classmethod
    def get_corpus_documents_visible_to_user(
        cls,
        user: UserOrAnonymous,
        corpus: Corpus,
        include_deleted: bool = False,
        include_caml: bool = False,
        *,
        request: Any = None,
    ) -> QuerySet[Document]:
        """
        Get the documents in a corpus under the MIN-permission semantic.

        Unlike :meth:`get_corpus_documents` (corpus-as-gate: corpus READ
        unlocks every document in the corpus), this method additionally
        intersects the corpus document set with
        ``Document.objects.visible_to_user`` so a document is returned only
        when the user can see it at BOTH levels::

            Effective Permission = MIN(document_permission, corpus_permission)

        A private document inside a public — or merely shared — corpus is
        therefore hidden from a user who lacks document-level access,
        matching the permission model documented in
        ``docs/permissioning/consolidated_permissioning_guide.md`` and the
        ``CLAUDE.md`` Permission System section.

        Use this for user-facing surfaces that must not leak private
        documents through a corpus the user can merely read (e.g. the
        GraphQL ``CorpusType.documents`` field). Use
        :meth:`get_corpus_documents` for corpus-as-gate surfaces (MCP,
        discovery, badge / analysis pipelines) where corpus READ is the
        intended single gate.

        Args:
            user: Requesting user
            corpus: Corpus to get documents from
            include_deleted: Whether to include soft-deleted documents
            include_caml: Whether to include CAML / markdown documents
                (see :meth:`get_corpus_documents` for the default rationale)
            request: Optional request object for the per-request
                permission cache

        Returns:
            QuerySet of documents the user can see at both the corpus and
            the document level (empty if the user lacks corpus READ).

        Permissions:
            Requires corpus READ permission AND, per document, document-level
            READ (creator / ``is_public`` / guardian grant). IDOR-safe: a
            user without corpus READ gets an empty queryset, indistinguishable
            from an empty corpus.
        """
        from opencontractserver.documents.models import Document

        if not corpus.user_can(user, PermissionTypes.READ, request=request):
            return Document.objects.none()

        # Corpus READ confirmed (the corpus side of MIN). Now intersect with
        # the document-level visibility set (the document side of MIN) so
        # private documents do not leak through a readable corpus.
        corpus_doc_ids = cls._build_corpus_documents_queryset(
            corpus,
            include_deleted=include_deleted,
            include_caml=include_caml,
        ).values_list("pk", flat=True)

        return Document.objects.visible_to_user(user).filter(pk__in=corpus_doc_ids)

    @classmethod
    def get_corpus_document_by_slug(
        cls,
        user: UserOrAnonymous,
        corpus: Corpus,
        slug: str,
        include_deleted: bool = False,
        *,
        request: Any = None,
    ) -> Document:
        """
        Single corpus-scoped document lookup by slug.

        Args:
            user: Requesting user
            corpus: Corpus to look up in
            slug: Document slug
            include_deleted: Whether to consider soft-deleted documents

        Returns:
            The matching Document.

        Raises:
            Document.DoesNotExist: If the slug is not in the corpus, the
                user lacks corpus READ, or no document matches. The same
                exception fires for all three cases — IDOR-safe.
        """
        return cls.get_corpus_documents(
            user=user,
            corpus=corpus,
            include_deleted=include_deleted,
            request=request,
        ).get(slug=slug)

    @classmethod
    def get_corpus_document_by_id(
        cls,
        user: UserOrAnonymous,
        corpus: Corpus,
        document_id: int,
        include_deleted: bool = False,
        *,
        request: Any = None,
    ) -> Document:
        """
        Single corpus-scoped document lookup by primary key.

        Args:
            user: Requesting user
            corpus: Corpus to look up in
            document_id: Document primary key
            include_deleted: Whether to consider soft-deleted documents

        Returns:
            The matching Document.

        Raises:
            Document.DoesNotExist: If the document is not in the corpus,
                the user lacks corpus READ, or no document matches. The
                same exception fires for all three cases — IDOR-safe.
        """
        return cls.get_corpus_documents(
            user=user,
            corpus=corpus,
            include_deleted=include_deleted,
            request=request,
        ).get(pk=document_id)

    @classmethod
    def is_document_in_corpus(
        cls,
        user: UserOrAnonymous,
        corpus: Corpus,
        document_id: int,
        include_deleted: bool = False,
        *,
        request: Any = None,
    ) -> bool:
        """
        Corpus-membership check that also enforces corpus READ.

        Returns ``False`` when the user lacks READ — no information leak
        about whether the document exists.

        Args:
            user: Requesting user
            corpus: Corpus to check membership in
            document_id: Document primary key
            include_deleted: Whether to consider soft-deleted documents

        Returns:
            True if the document is in the corpus and the user has READ;
            False otherwise.
        """
        return (
            cls.get_corpus_documents(
                user=user,
                corpus=corpus,
                include_deleted=include_deleted,
                request=request,
            )
            .filter(pk=document_id)
            .exists()
        )

    @classmethod
    def get_corpus_caml_articles(
        cls,
        user: UserOrAnonymous,
        corpus: Corpus,
        *,
        request: Any = None,
    ) -> QuerySet[Document]:
        """
        Get the CAML article documents in a corpus (typically 0 or 1).

        A CAML article is a Markdown ``Document`` attached to the corpus
        whose ``title`` is ``"Readme.CAML"`` and whose ``file_type`` is
        ``"text/markdown"``. The plural return shape mirrors
        :meth:`get_corpus_documents` so future multi-article designs do
        not require a signature change; today the queryset is expected
        to contain at most one row.

        Reuses :meth:`_build_corpus_documents_queryset` so the
        ``DocumentPath`` join and CAML toggle stay consistent with the
        rest of the corpus-scoped read surface.

        Args:
            user: Requesting user.
            corpus: Corpus to look up CAML articles in.
            request: Optional request object for the per-request
                permission cache.

        Returns:
            QuerySet of ``Document`` rows matching the CAML article
            shape. Empty if the user lacks corpus READ or the corpus
            has no CAML article — IDOR-safe (no distinction between
            "no permission" and "no article").

        Permissions:
            Requires corpus READ permission. Mirrors
            :meth:`get_corpus_documents`' corpus-as-gate semantic.
        """
        from opencontractserver.constants.document_processing import (
            CAML_ARTICLE_TITLE,
            MARKDOWN_MIME_TYPE,
        )
        from opencontractserver.documents.models import Document

        if not corpus.user_can(user, PermissionTypes.READ, request=request):
            return Document.objects.none()

        return cls._build_corpus_documents_queryset(corpus, include_caml=True).filter(
            title=CAML_ARTICLE_TITLE, file_type=MARKDOWN_MIME_TYPE
        )

    @classmethod
    def upload_document_to_corpus(
        cls,
        user: User,
        corpus: Corpus,
        file_bytes: bytes,
        filename: str,
        title: str,
        description: str = "",
        folder: CorpusFolder | None = None,
        custom_meta: dict | None = None,
        is_public: bool = False,
        slug: str | None = None,
        *,
        request: Any = None,
    ) -> tuple[Document | None, str, str]:
        """
        Upload a document to a corpus.

        This method ensures consistent versioning behavior by:
        1. First creating a standalone document in the system
        2. Then adding that document to the corpus (creating a corpus-isolated copy)

        This approach ensures documents have identical versioning behavior regardless
        of whether they were uploaded directly to a corpus or added later.

        Args:
            user: Uploading user
            corpus: Target corpus
            file_bytes: Raw file bytes
            filename: Original filename
            title: Document title
            description: Document description
            folder: Optional folder to place document in
            custom_meta: Optional custom metadata dict
            is_public: Whether document should be public
            slug: Optional URL slug

        Returns:
            (corpus_document, status, error_message) where:
            - corpus_document: The corpus-isolated document
            - status: 'added' or 'already_exists'
            - error_message: Empty if successful

        Permissions:
            Requires corpus UPDATE permission
        """
        from opencontractserver.documents.document_service import DocumentService

        # Check corpus write permission first
        if not corpus.user_can(user, PermissionTypes.UPDATE, request=request):
            return (
                None,
                "",
                "Permission denied: You do not have write access to this corpus",
            )

        # Step 1: Create standalone document first
        standalone_doc, create_error = DocumentService.create_document(
            user=user,
            file_bytes=file_bytes,
            filename=filename,
            title=title,
            description=description,
            custom_meta=custom_meta,
            is_public=is_public,
            slug=slug,
            request=request,
        )

        if not standalone_doc:
            return None, "", create_error

        # Step 2: Add to corpus (creates isolated copy with proper versioning)
        corpus_doc, status, add_error = cls.add_document_to_corpus(
            user=user,
            document=standalone_doc,
            corpus=corpus,
            folder=folder,
            request=request,
        )

        if not corpus_doc:
            # If adding to corpus failed, we still have the standalone doc
            logger.warning(
                f"Document {standalone_doc.id} created but failed to add to corpus: {add_error}"
            )
            return None, "", add_error

        logger.info(
            f"Uploaded document to corpus {corpus.id} "
            f"(standalone={standalone_doc.id}, corpus_doc={corpus_doc.id}, "
            f"status={status}, folder={folder.id if folder else None}) by user {user.id}"
        )

        return corpus_doc, status, ""

    @classmethod
    def add_document_to_corpus(
        cls,
        user: User,
        document: Document,
        corpus: Corpus,
        folder: CorpusFolder | None = None,
        *,
        request: Any = None,
    ) -> tuple[Document | None, str, str]:
        """
        Add an existing document to a corpus, creating a corpus-isolated copy.

        This creates a NEW document in the corpus with:
        - Its own version_tree_id (independent version tree)
        - source_document pointing to original (provenance tracking)
        - DocumentPath linking to the corpus

        Use this when you have a document (perhaps from user's library) and want
        to add it to a corpus. The original document is unchanged.

        Args:
            user: User performing the operation
            document: Source document to copy into corpus
            corpus: Target corpus
            folder: Optional folder to place document in

        Returns:
            (corpus_document, status, error_message) where:
            - corpus_document: The NEW corpus-isolated document (not the original)
            - status: 'added' or 'already_exists'

        Permissions:
            Requires corpus UPDATE permission AND document READ permission
        """
        # Check corpus write permission
        if not corpus.user_can(user, PermissionTypes.UPDATE, request=request):
            return (
                None,
                "",
                "Permission denied: You do not have write access to this corpus",
            )

        # Single centralised READ check on the source document — encapsulates
        # superuser / creator / is_public / guardian rules and participates in
        # the request-scoped permission cache.
        if not document.user_can(user, PermissionTypes.READ, request=request):
            return (
                None,
                "",
                "Permission denied: You do not have access to this document",
            )

        try:
            # Use corpus.add_document for proper corpus isolation
            # The folder is passed through and stored in DocumentPath
            corpus_doc, status, path_record = corpus.add_document(
                document=document,
                user=user,
                folder=folder,
            )

            # Set permissions on the corpus-isolated copy
            set_permissions_for_obj_to_user(
                user,
                corpus_doc,
                [PermissionTypes.CRUD],
                request=request,
            )

            logger.info(
                f"Added document {document.id} to corpus {corpus.id} as {corpus_doc.id} "
                f"(status={status}) by user {user.id}"
            )

            return corpus_doc, status, ""

        except Exception as e:
            logger.exception(f"Error adding document to corpus: {e}")
            return None, "", f"Error adding document to corpus: {e}"

    @classmethod
    def add_documents_to_corpus(
        cls,
        user: User,
        document_ids: list[int],
        corpus: Corpus,
        folder: CorpusFolder | None = None,
        *,
        request: Any = None,
    ) -> tuple[int, list[int], str]:
        """
        Add multiple existing documents to a corpus.

        This is a bulk operation that creates corpus-isolated copies of each document.

        Args:
            user: User performing the operation
            document_ids: List of document IDs to add
            corpus: Target corpus
            folder: Optional folder to place documents in

        Returns:
            (added_count, added_doc_ids, error_message)

        Permissions:
            Requires corpus UPDATE permission
        """
        from opencontractserver.documents.models import Document

        # Check corpus write permission
        if not corpus.user_can(user, PermissionTypes.UPDATE, request=request):
            return (
                0,
                [],
                "Permission denied: You do not have write access to this corpus",
            )

        # Get accessible documents in a single query — ``visible_to_user``
        # encapsulates the creator / is_public / guardian-READ rules that the
        # singular ``add_document_to_corpus`` runs per-doc, but in one
        # ``Q(creator=user) | Q(is_public=True) | Q(id__in=permitted_ids)``
        # filter. Closes the N+1 the previous per-doc shim loop introduced.
        documents = list(
            Document.objects.visible_to_user(user).filter(pk__in=document_ids)
        )

        added_count = 0
        added_ids = []
        errors = []

        for doc in documents:
            corpus_doc, status, error = cls.add_document_to_corpus(
                user=user,
                document=doc,
                corpus=corpus,
                folder=folder,
                request=request,
            )
            if corpus_doc:
                added_count += 1
                added_ids.append(corpus_doc.id)
            elif error:
                errors.append(f"Doc {doc.id}: {error}")

        error_msg = "; ".join(errors) if errors else ""
        return added_count, added_ids, error_msg

    @classmethod
    def remove_document_from_corpus(
        cls,
        user: User,
        document: Document,
        corpus: Corpus,
        *,
        request: Any = None,
    ) -> tuple[bool, str]:
        """
        Remove a document from a corpus (soft delete).

        This creates a soft-delete DocumentPath record maintaining history.
        The document is not permanently deleted and can be restored.

        Args:
            user: User performing the operation
            document: Document to remove
            corpus: Corpus to remove from

        Returns:
            (success, error_message)

        Permissions:
            Requires corpus UPDATE permission
        """
        # Check corpus write permission
        if not corpus.user_can(user, PermissionTypes.UPDATE, request=request):
            return (
                False,
                "Permission denied: You do not have write access to this corpus",
            )

        try:
            deleted_paths = corpus.remove_document(document=document, user=user)

            if not deleted_paths:
                return False, "Document not found in corpus"

            logger.info(
                f"Removed document {document.id} from corpus {corpus.id} "
                f"({len(deleted_paths)} paths) by user {user.id}"
            )

            return True, ""

        except Exception as e:
            logger.exception(f"Error removing document from corpus: {e}")
            return False, f"Error removing document from corpus: {e}"

    @classmethod
    def remove_documents_from_corpus(
        cls,
        user: User,
        document_ids: list[int],
        corpus: Corpus,
        *,
        request: Any = None,
    ) -> tuple[int, str]:
        """
        Remove multiple documents from a corpus (soft delete).

        Args:
            user: User performing the operation
            document_ids: List of document IDs to remove
            corpus: Corpus to remove from

        Returns:
            (removed_count, error_message)

        Permissions:
            Requires corpus UPDATE permission
        """
        # Check corpus write permission
        if not corpus.user_can(user, PermissionTypes.UPDATE, request=request):
            return 0, "Permission denied: You do not have write access to this corpus"

        # Get documents that are actually in this corpus.
        # Uses ``_get_active_documents`` (internal, permission-free) because
        # the corpus UPDATE check is already done above and the service is
        # its own consumer; this avoids the DeprecationWarning emitted by
        # the user-context wrapper.
        corpus_docs = corpus._get_active_documents().filter(pk__in=document_ids)

        removed_count = 0
        errors = []

        for doc in corpus_docs:
            success, error = cls.remove_document_from_corpus(
                user=user,
                document=doc,
                corpus=corpus,
                request=request,
            )
            if success:
                removed_count += 1
            elif error:
                errors.append(f"Doc {doc.id}: {error}")

        error_msg = "; ".join(errors) if errors else ""
        return removed_count, error_msg
