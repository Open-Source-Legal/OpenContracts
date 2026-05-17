"""Shared base for OpenContracts vector stores.

Centralises the four pieces every vector store duplicated:

- Embedder/dim resolution from ``corpus_id`` or explicit ``embedder_path``.
- User lookup with "user not found" treated as deny-by-empty-result.
- IDOR check on ``document_id`` / ``corpus_id`` against
  ``visible_to_user`` (same pattern, same warning, same return contract).
- Sync + async query-embedding generation.

Subclasses only have to call these helpers and decide which model's
``.none()`` to return on deny; the IDOR contract stays uniform.
"""

from __future__ import annotations

import logging
from typing import Any

from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model

from opencontractserver.constants.search import VALID_EMBEDDING_DIMS
from opencontractserver.utils.embeddings import (
    agenerate_embeddings_from_text,
    generate_embeddings_from_text,
    get_embedder,
)

User = get_user_model()
_logger = logging.getLogger(__name__)


class BaseVectorStore:
    """Permissioning + embedder plumbing shared across vector stores."""

    def __init__(
        self,
        *,
        user_id: str | int | None = None,
        corpus_id: str | int | None = None,
        document_id: str | int | None = None,
        embedder_path: str | None = None,
        embed_dim: int = 384,
    ) -> None:
        if embedder_path is None and corpus_id is None:
            raise ValueError(
                f"{type(self).__name__} requires either 'corpus_id' to "
                "derive an embedder or an explicit 'embedder_path' override."
            )
        self.user_id = user_id
        self.corpus_id = corpus_id
        self.document_id = document_id
        self.embed_dim = embed_dim

        if embedder_path is not None:
            embedder_class, detected_embedder_path = get_embedder(
                embedder_path=embedder_path,
            )
        else:
            embedder_class, detected_embedder_path = get_embedder(
                corpus_id=corpus_id,
            )
        if detected_embedder_path is None:
            raise ValueError(
                f"get_embedder() resolved no embedder_path for "
                f"{type(self).__name__}; check corpus.preferred_embedder or "
                "the global default."
            )
        self.embedder_path: str = detected_embedder_path

        if self.embed_dim not in VALID_EMBEDDING_DIMS:
            self.embed_dim = getattr(embedder_class, "vector_size", 768)

    # ------------------------------------------------------------------ #
    # User resolution
    # ------------------------------------------------------------------ #
    def _resolve_user_sync(self) -> tuple[Any | None, bool]:
        """Return (user, user_invalid). ``user_invalid`` ⇒ caller denies."""
        if not self.user_id:
            return None, False
        try:
            return User.objects.get(id=self.user_id), False
        except User.DoesNotExist:
            _logger.warning("User ID %s not found", self.user_id)
            return None, True

    async def _aresolve_user(self) -> tuple[Any | None, bool]:
        if not self.user_id:
            return None, False
        try:
            user = await sync_to_async(User.objects.get)(id=self.user_id)
            return user, False
        except User.DoesNotExist:
            _logger.warning("User ID %s not found", self.user_id)
            return None, True

    # ------------------------------------------------------------------ #
    # IDOR checks
    # ------------------------------------------------------------------ #
    # Same "empty result for both missing-and-denied" contract everywhere
    # — prevents enumeration via differing error messages (see
    # docs/permissioning/consolidated_permissioning_guide.md).
    def _check_idor_sync(self, user: Any | None) -> bool:
        """Return True iff configured document/corpus is missing or denied."""
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.documents.models import Document

        if self.document_id is not None and not (
            Document.objects.visible_to_user(user).filter(id=self.document_id).exists()
        ):
            _logger.warning(
                "User %s denied access to document %s in vector search "
                "(not found or no permission)",
                self.user_id,
                self.document_id,
            )
            return True
        if self.corpus_id is not None and not (
            Corpus.objects.visible_to_user(user).filter(id=self.corpus_id).exists()
        ):
            _logger.warning(
                "User %s denied access to corpus %s in vector search "
                "(not found or no permission)",
                self.user_id,
                self.corpus_id,
            )
            return True
        return False

    async def _acheck_idor(self, user: Any | None) -> bool:
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.documents.models import Document

        if self.document_id is not None:

            def _doc_visible() -> bool:
                return (
                    Document.objects.visible_to_user(user)
                    .filter(id=self.document_id)
                    .exists()
                )

            if not await sync_to_async(_doc_visible)():
                _logger.warning(
                    "User %s denied access to document %s in vector search "
                    "(not found or no permission)",
                    self.user_id,
                    self.document_id,
                )
                return True
        if self.corpus_id is not None:

            def _corpus_visible() -> bool:
                return (
                    Corpus.objects.visible_to_user(user)
                    .filter(id=self.corpus_id)
                    .exists()
                )

            if not await sync_to_async(_corpus_visible)():
                _logger.warning(
                    "User %s denied access to corpus %s in vector search "
                    "(not found or no permission)",
                    self.user_id,
                    self.corpus_id,
                )
                return True
        return False

    # ------------------------------------------------------------------ #
    # Query embedding generation
    # ------------------------------------------------------------------ #
    def _generate_query_embedding(self, query_text: str) -> list[float] | None:
        _, vector = generate_embeddings_from_text(
            query_text, embedder_path=self.embedder_path
        )
        if vector is None:
            _logger.warning(
                "Failed to generate query embedding (embedder=%s, query='%s...')",
                self.embedder_path,
                query_text[:50],
            )
        return vector

    async def _agenerate_query_embedding(self, query_text: str) -> list[float] | None:
        _, vector = await agenerate_embeddings_from_text(
            query_text, embedder_path=self.embedder_path
        )
        if vector is None:
            _logger.warning(
                "Failed to generate async query embedding (embedder=%s, "
                "query='%s...')",
                self.embedder_path,
                query_text[:50],
            )
        return vector


__all__ = ["BaseVectorStore"]
