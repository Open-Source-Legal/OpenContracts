"""Corpus-row CRUD for the corpus service layer.

``CorpusService`` owns operations on the :class:`Corpus` row itself —
deletion, visibility changes, markdown-description versioning, the
create-time creator-permission grant, and the update-time embedder guard.
This closes the design-doc §3 Problem 3 gap: corpus *contents* had a service
(:mod:`opencontractserver.corpuses.services.corpus_documents` and siblings)
but the corpus *row* had none, so its business logic lived inline in
``config/graphql/corpus_mutations.py``.

The generic create/update mechanics (DRF serializer validation + save) stay
in the shared ``DRFMutation`` infrastructure; only the corpus-specific logic
is centralised here.

Part of issue #1716, service-layer centralization Phase 2B — see
``docs/refactor_plans/2026-05-22-service-layer-phase2bc-corpus-service-and-caller-migration.md``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.db import transaction

from opencontractserver.shared.services.base import BaseService
from opencontractserver.shared.services.conventions import ServiceResult
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

if TYPE_CHECKING:
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.documents.models import Document
    from opencontractserver.users.models import User

logger = logging.getLogger(__name__)


class CorpusService(BaseService):
    """Corpus-row CRUD and corpus-level permission operations.

    Read access to corpora stays on the Tier-0 manager
    (``Corpus.objects.visible_to_user`` / ``get_for_user_or_none``); this
    service owns the *write* surface of the corpus row.
    """

    @classmethod
    def update_description(
        cls,
        user: User,
        corpus: Corpus,
        new_content: str,
    ) -> ServiceResult[Document | None]:
        """Update a corpus's markdown description by writing a Readme.CAML doc.

        Routes through
        :func:`opencontractserver.documents.versioning.import_document` —
        the canonical dual-tree workhorse — so the editor write path uses
        the same versioning mechanics as every other CAML write (V2 import
        shim, migration backfill, agent edit tool). First call creates the
        Readme.CAML Document and its root ``DocumentPath``; subsequent
        calls create new version-tree siblings, atomically flipping the
        old Document's and DocumentPath's ``is_current`` flags. The
        Document ``post_save`` signal cascades the cache refresh onto
        ``Corpus.description`` / ``.description_preview`` /
        ``.readme_caml_document_id``.

        Creator-only by design: even collaborators with a guardian UPDATE
        grant cannot edit the description, so revision history stays
        attributable to a single author. Callers MUST have already gated
        corpus READ (the GraphQL wrapper does so via ``get_for_user_or_none``).

        Returns ``ServiceResult.success`` whose value is the new Readme.CAML
        :class:`Document` head, or ``None`` when ``new_content`` is
        byte-identical to the current Readme.CAML body (no new version
        created).

        Spec:
            ``docs/superpowers/specs/2026-05-27-canonical-caml-description-refactor-design.md``
            §4.6.
        """
        from opencontractserver.constants.document_processing import (
            CAML_ARTICLE_TITLE,
            MARKDOWN_MIME_TYPE,
        )
        from opencontractserver.corpuses.services.corpus_documents import (
            CorpusDocumentService,
        )
        from opencontractserver.corpuses.services.description_cache import (
            read_caml_body,
        )
        from opencontractserver.documents.versioning import import_document

        if corpus.creator_id != getattr(user, "id", None):
            return ServiceResult.failure(
                "Corpus not found or you do not have permission to update it."
            )

        # No-op when the candidate body is byte-identical to the current
        # CAML head. ``import_document`` does not deduplicate on content
        # (see its docstring: "No content-based deduplication is
        # performed"), so we filter the no-op here to match the
        # pre-refactor contract (``update_description`` returned ``None``
        # for unchanged content).
        candidate_body = new_content or ""
        existing = CorpusDocumentService.get_corpus_caml_articles(user, corpus).first()
        if existing is not None:
            current_body = read_caml_body(existing)
            if current_body == candidate_body:
                return ServiceResult.success(None)
        elif candidate_body == "":
            # No CAML doc yet and the new body is empty — nothing to do.
            return ServiceResult.success(None)

        doc, _status, _path = import_document(
            corpus=corpus,
            path=CAML_ARTICLE_TITLE,
            content=candidate_body.encode("utf-8"),
            user=user,
            file_type=MARKDOWN_MIME_TYPE,
            title=CAML_ARTICLE_TITLE,
        )
        cls.log_action("Updated description for", corpus, user)
        return ServiceResult.success(doc)

    @classmethod
    def update_icon(
        cls,
        user: User,
        corpus: Corpus,
        *,
        image_bytes: bytes,
        extension: str,
    ) -> ServiceResult[None]:
        """Persist a logo image to ``corpus.icon`` (creator-only).

        Mirrors :meth:`update_description`'s creator-only contract so an
        auto-generated (or agent-generated) logo carries the same write
        authority as the rest of the corpus row — even a collaborator with a
        guardian UPDATE grant cannot replace the icon. Callers MUST have
        already gated corpus READ.

        The bytes are written through the configured storage backend
        (LOCAL / S3 / GCP) via ``ContentFile``; ``FieldFile.save`` persists the
        corpus row so the new ``icon`` path is durable. Returns an empty
        success result, or a permission failure.
        """
        if corpus.creator_id != getattr(user, "id", None):
            return ServiceResult.failure(
                "Corpus not found or you do not have permission to update it."
            )

        import uuid

        from django.core.files.base import ContentFile

        ext = (extension or "png").lstrip(".")
        # Short UUID segment so a Celery retry writes a distinct object rather
        # than overwriting (S3) or accumulating storage-suffixed orphans (local).
        filename = f"corpus_logo_{corpus.pk}_{uuid.uuid4().hex[:8]}.{ext}"
        corpus.icon.save(filename, ContentFile(image_bytes), save=True)
        cls.log_action("Updated icon for", corpus, user)
        return ServiceResult.success(None)

    @classmethod
    def delete_corpus(
        cls,
        user: User,
        corpus: Corpus,
        *,
        request: Any = None,
    ) -> ServiceResult[None]:
        """Delete a corpus after the personal / lock / permission checks.

        Callers MUST have already gated corpus READ. The checks run in the
        same order as the former inline mutation logic: personal-corpus
        guard, then the user-lock guard, then the DELETE permission gate.
        """
        if corpus.is_personal:
            return ServiceResult.failure(
                "Cannot delete your personal 'My Documents' corpus. "
                "This corpus is automatically managed and stores your "
                "uploaded documents."
            )

        # User-lock check: the lock holder (or a superuser, via the
        # ``require_permission`` gate below) may proceed even on a
        # backend-held lock so users can abandon stalled corpora.
        if corpus.user_lock is not None and getattr(user, "id", None) != (
            corpus.user_lock_id
        ):
            return ServiceResult.failure(
                "Specified object is locked by another user. Cannot be deleted."
            )

        error = cls.require_permission(
            corpus,
            user,
            PermissionTypes.DELETE,
            request=request,
            error_message=(
                "Corpus not found or you don't have permission to delete it."
            ),
        )
        if error:
            return ServiceResult.failure(error)

        cls.log_action("Deleted", corpus, user)
        corpus.delete()
        return ServiceResult.success(None)

    @classmethod
    def set_visibility(
        cls,
        user: User,
        corpus: Corpus,
        is_public: bool,
        *,
        request: Any = None,
    ) -> ServiceResult[str]:
        """Change a corpus's public/private visibility.

        Requires PERMISSION on the corpus (changing visibility escalates
        access, so it is gated more strictly than UPDATE). Callers MUST have
        already gated corpus READ. The success value is the user-facing
        status message.
        """
        error = cls.require_permission(
            corpus,
            user,
            PermissionTypes.PERMISSION,
            request=request,
            error_message="Corpus not found or you don't have permission",
        )
        if error:
            return ServiceResult.failure(error)

        if corpus.is_public == is_public:
            status = "public" if is_public else "private"
            return ServiceResult.success(f"Corpus is already {status}")

        if is_public:
            # Cascade public visibility to all child objects (documents,
            # annotations, analyses, ...) via the existing async task.
            # Imported locally to avoid a circular import: the tasks module
            # imports from the corpuses package at module load time.
            from opencontractserver.tasks.permissioning_tasks import (
                make_corpus_public_task,
            )

            # Defer dispatch to commit: under ``ATOMIC_REQUESTS`` an
            # unwrapped ``apply_async`` would race the worker against
            # uncommitted state (and fire against rolled-back state on
            # error). Capture ``corpus.pk`` in a local so the closure
            # doesn't depend on ``corpus`` still being attached at commit.
            corpus_pk = corpus.pk
            transaction.on_commit(
                lambda: make_corpus_public_task.si(corpus_id=corpus_pk).apply_async()
            )
            cls.log_action("Made public", corpus, user)
            return ServiceResult.success(
                "Making corpus public. This may take a moment for large corpuses."
            )

        # Make private — only the corpus flag changes. Child objects stay
        # public if they were made public, to avoid breaking existing links.
        corpus.is_public = False
        corpus.save(update_fields=["is_public"])
        cls.log_action("Made private", corpus, user)
        return ServiceResult.success("Corpus is now private")

    @classmethod
    def assert_embedder_change_allowed(
        cls,
        corpus: Corpus,
        new_embedder: str,
    ) -> str:
        """Return ``""`` when changing ``preferred_embedder`` is allowed.

        Issue #437: the preferred embedder cannot change once documents exist,
        as that would create inconsistent embeddings within the corpus — the
        ``reEmbedCorpus`` mutation is the controlled migration path. Returns a
        human-readable error string when the change is disallowed.

        Deliberately returns a plain ``str`` rather than ``ServiceResult``:
        this is a pre-save guard whose only output is an optional error
        message, so the ``ServiceResult`` success/value channel would be
        dead weight. Do not "normalise" it to ``ServiceResult``.
        """
        if new_embedder != corpus.preferred_embedder and corpus.has_documents():
            return (
                "Cannot change preferred_embedder after documents "
                "have been added to this corpus. Changing the "
                "embedder would create inconsistent embeddings. "
                "Use the reEmbedCorpus mutation to migrate to a "
                "different embedder."
            )
        return ""

    @classmethod
    def grant_creator_permissions(
        cls,
        user: User,
        corpus: Corpus,
        *,
        request: Any = None,
    ) -> None:
        """Grant the creator full management rights over a new corpus.

        CRUD + PUBLISH + PERMISSION — PERMISSION is required so the creator
        can manage who else may access the corpus.
        """
        set_permissions_for_obj_to_user(
            user,
            corpus,
            [
                PermissionTypes.CRUD,
                PermissionTypes.PUBLISH,
                PermissionTypes.PERMISSION,
            ],
            request=request,
        )
        cls.log_action("Granted creator permissions on", corpus, user)
