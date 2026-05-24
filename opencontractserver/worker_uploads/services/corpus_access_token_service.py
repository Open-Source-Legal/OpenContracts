"""``CorpusAccessToken`` service — per-corpus token CRUD.

Tokens are scoped to a single corpus. Both the create and revoke flows are
**gated by ownership / superuser**: only the corpus creator (or a superuser)
may issue or revoke a token for a corpus. The list flow uses the same gate.

Phase 5 of the service-layer centralization roadmap — see
``docs/refactor_plans/2026-05-19-service-layer-centralization-design.md``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from opencontractserver.shared.services.base import BaseService
from opencontractserver.shared.services.conventions import ServiceResult

if TYPE_CHECKING:
    from datetime import datetime

    from django.db.models import QuerySet

    from opencontractserver.worker_uploads.models import CorpusAccessToken

logger = logging.getLogger(__name__)


class CorpusAccessTokenService(BaseService):
    """Per-corpus access-token CRUD (superuser-or-creator gated)."""

    @classmethod
    def list_for_corpus(
        cls,
        user: Any,
        corpus_id: Any,
        *,
        is_active: bool | None = None,
        request: Any = None,
    ) -> ServiceResult[QuerySet]:
        """Return the corpus's access tokens, annotated for the resolver.

        Superusers may list any corpus; non-superusers must be the corpus's
        creator. Returns ``ServiceResult.failure("Not found or permission
        denied.")`` for both not-found and not-permitted (IDOR rule). On
        success, the queryset is annotated with ``_pending`` / ``_completed`` /
        ``_failed`` upload counts.
        """
        from django.db.models import Count, Q

        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.worker_uploads.models import CorpusAccessToken

        qs = Corpus.objects.filter(id=corpus_id)
        if not getattr(user, "is_superuser", False):
            qs = qs.filter(creator=user)
        corpus = qs.first()
        if corpus is None:
            return ServiceResult.failure("Not found or permission denied.")

        token_qs = (
            CorpusAccessToken.objects.filter(corpus=corpus)
            .select_related("worker_account")
            .order_by("-created")
        )
        if is_active is not None:
            token_qs = token_qs.filter(is_active=is_active)

        token_qs = token_qs.annotate(
            _pending=Count("uploads", filter=Q(uploads__status="PENDING")),
            _completed=Count("uploads", filter=Q(uploads__status="COMPLETED")),
            _failed=Count("uploads", filter=Q(uploads__status="FAILED")),
        )
        return ServiceResult.success(token_qs)

    @classmethod
    def create_token(
        cls,
        user: Any,
        *,
        worker_account_id: Any,
        corpus_id: Any,
        expires_at: datetime | None = None,
        rate_limit_per_minute: int = 0,
        request: Any = None,
    ) -> ServiceResult[tuple[CorpusAccessToken, str]]:
        """Issue a new corpus-scoped access token.

        Authorisation: the caller must be a superuser OR the corpus's
        creator. The corpus gate is IDOR-safe — nonexistent ``corpus_id``
        and an existing-but-not-owned ``corpus_id`` both surface the unified
        "Not found or permission denied." message (matching ``list_for_corpus``
        / ``revoke_token``). The "Worker account not found." failure message
        is preserved verbatim from the pre-relocation mutation.

        Returns a tuple ``(token, plaintext_key)`` on success. The plaintext
        is shown only once — the stored row only retains the SHA-256 hash.
        """
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.worker_uploads.models import (
            CorpusAccessToken,
            WorkerAccount,
        )

        # Compose the owner-or-superuser gate into the queryset so a
        # nonexistent corpus_id and a corpus_id the caller doesn't own
        # collapse onto the same response. Matches ``list_for_corpus`` /
        # ``revoke_token`` IDOR-safe pattern.
        corpus_qs = Corpus.objects.filter(id=corpus_id)
        if not getattr(user, "is_superuser", False):
            corpus_qs = corpus_qs.filter(creator=user)
        corpus = corpus_qs.first()
        if corpus is None:
            return ServiceResult.failure("Not found or permission denied.")

        try:
            account = WorkerAccount.objects.get(id=worker_account_id)
        except WorkerAccount.DoesNotExist:
            return ServiceResult.failure("Worker account not found.")

        token, plaintext_key = CorpusAccessToken.create_token(
            worker_account=account,
            corpus=corpus,
            expires_at=expires_at,
            rate_limit_per_minute=rate_limit_per_minute,
        )
        cls.log_action("Created", token, user, corpus=corpus.id)
        return ServiceResult.success((token, plaintext_key))

    @classmethod
    def revoke_token(
        cls,
        user: Any,
        token_id: Any,
        *,
        request: Any = None,
    ) -> ServiceResult[None]:
        """Revoke (deactivate) a corpus access token.

        Returns the unified IDOR-safe "Not found or permission denied." for
        both not-found and not-permitted; the lookup composes the
        owner-or-superuser gate into the queryset so the two branches are
        indistinguishable.
        """
        from opencontractserver.worker_uploads.models import CorpusAccessToken

        qs = CorpusAccessToken.objects.select_related("corpus").filter(id=token_id)
        if not getattr(user, "is_superuser", False):
            qs = qs.filter(corpus__creator=user)
        token = qs.first()
        if token is None:
            return ServiceResult.failure("Not found or permission denied.")

        token.is_active = False
        token.save(update_fields=["is_active"])
        cls.log_action("Revoked", token, user)
        return ServiceResult.success(None)
