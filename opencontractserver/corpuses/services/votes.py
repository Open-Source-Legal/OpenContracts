"""Corpus vote casting / removal service.

Routes through ``BaseService`` so the GraphQL voting mutations satisfy the
Tier-0 service-layer invariant (see CLAUDE.md rule 7) — corpus row access
and permission checks are gated here, not composed inline in
``config/graphql/voting_mutations.py``.

Two voter shapes are supported:

* **Authenticated users** — voter identity is pinned to ``user.pk``
  (the ``creator`` FK on :class:`CorpusVote`). The corpus READ check
  runs through :meth:`BaseService.get_or_none` so the unified IDOR-safe
  "not found or no permission" message is emitted on every failure mode.

* **Anonymous users** — voter identity is pinned to the Django session
  key. Anonymous voting is only enabled when the corpus is public; the
  ``visible_to_user`` queryset already filters non-public corpora out
  of an anonymous user's visible set, so we can rely on the same READ
  gate (``BaseService.get_or_none``) for both branches. ``ip_hash`` is
  stored as a best-effort audit signal but is intentionally not used
  for deduplication.

Self-vote is blocked in both branches: a corpus creator cannot inflate
their own corpus score. Anonymous voters by definition aren't the
creator, so the check only fires on the authenticated branch.
"""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db import transaction

from opencontractserver.shared.services.base import BaseService
from opencontractserver.shared.services.conventions import ServiceResult
from opencontractserver.utils.auth import is_authenticated_user

if TYPE_CHECKING:
    from opencontractserver.corpuses.models import Corpus, CorpusVote

logger = logging.getLogger(__name__)


# Unified IDOR-safe denial string — same text whether the corpus does not
# exist, the requester cannot READ it, or the global ID was malformed.
_CORPUS_NOT_FOUND_MSG = "Corpus not found or you do not have permission to vote on it"


def _normalize_vote_type(raw: str) -> str | None:
    """Lower-case and validate the vote_type string.

    Returns ``"upvote"`` / ``"downvote"`` on success, ``None`` on invalid
    input. Callers are expected to translate ``None`` into the unified
    "Invalid vote_type" GraphQL error.
    """
    value = (raw or "").strip().lower()
    if value not in ("upvote", "downvote"):
        return None
    return value


def _hash_ip(ip: str | None) -> str | None:
    """Salted SHA-256 of ``ip`` for the audit ``ip_hash`` column.

    Salt is the project ``SECRET_KEY`` (already a long secret); using
    SHA-256 over (salt + ip) means even leaking the column doesn't
    surface raw client IPs by brute force unless the attacker also has
    ``SECRET_KEY``. Returns ``None`` when no IP was provided so the
    column stays null rather than hashing an empty string.
    """
    if not ip:
        return None
    salt = (getattr(settings, "SECRET_KEY", "") or "").encode("utf-8")
    return hashlib.sha256(salt + ip.encode("utf-8")).hexdigest()


class CorpusVoteService(BaseService):
    """Corpus upvote / downvote / remove-vote operations."""

    @classmethod
    @transaction.atomic
    def cast_vote(
        cls,
        user: Any,
        corpus_pk: Any,
        vote_type: str,
        *,
        session_key: str | None = None,
        ip_address: str | None = None,
        request: Any = None,
    ) -> ServiceResult[CorpusVote]:
        """Create or update ``user``'s vote on the given corpus.

        ``user`` may be either an authenticated ``User`` or an
        ``AnonymousUser``; the latter requires ``session_key`` to identify
        the voter (the GraphQL mutation forces the session into existence
        before calling). ``ip_address`` is recorded as a salted hash for
        audit purposes only.

        Returns ``ServiceResult.success(vote_row)`` on success. The success
        value is the resulting :class:`CorpusVote` so the caller can return
        the corpus's refreshed score in the same response cycle.
        """
        from opencontractserver.corpuses.models import Corpus, CorpusVote

        normalized = _normalize_vote_type(vote_type)
        if normalized is None:
            return ServiceResult.failure(
                "Invalid vote_type. Must be 'upvote' or 'downvote'"
            )

        # IDOR-safe READ gate — same denial text whether the corpus
        # doesn't exist, the user can't see it, or the pk is malformed.
        corpus = cls.get_or_none(Corpus, corpus_pk, user, request=request)
        if corpus is None:
            return ServiceResult.failure(_CORPUS_NOT_FOUND_MSG)

        is_authenticated = is_authenticated_user(user)

        # Authenticated branch — block self-vote.  This MUST stay aligned
        # with the equivalent rule on MessageVote / ConversationVote so the
        # social-scoring contract is uniform across the platform.
        if is_authenticated and corpus.creator_id == getattr(user, "id", None):
            return ServiceResult.failure("You cannot vote on your own corpus")

        # Anonymous branch — must have a session_key to dedupe against.
        if not is_authenticated and not session_key:
            return ServiceResult.failure(
                "Anonymous voting requires a session.  Reload the page and try again."
            )

        ip_hash = _hash_ip(ip_address)

        # Look up an existing vote in the correct branch.  We deliberately
        # do not use ``get_or_create`` because the lookup-by-creator and
        # lookup-by-session conditions are mutually exclusive — mixing
        # them would let a logged-in user "take over" an anonymous vote.
        if is_authenticated:
            existing = CorpusVote.objects.filter(corpus=corpus, creator=user).first()
        else:
            existing = CorpusVote.objects.filter(
                corpus=corpus,
                creator__isnull=True,
                session_key=session_key,
            ).first()

        if existing is not None:
            # Update if the vote_type changed; otherwise no-op (idempotent
            # double-clicks should not error). ``ip_hash`` is refreshed on
            # every cast so the audit column reflects the latest known IP.
            update_fields: list[str] = []
            if existing.vote_type != normalized:
                existing.vote_type = normalized
                update_fields.append("vote_type")
            if ip_hash and existing.ip_hash != ip_hash:
                existing.ip_hash = ip_hash
                update_fields.append("ip_hash")
            if update_fields:
                existing.save(update_fields=update_fields)
                cls.log_action(f"Re-voted ({normalized}) on", corpus, user)
            return ServiceResult.success(existing)

        # New vote — populate the appropriate branch's identity columns.
        vote = CorpusVote.objects.create(
            corpus=corpus,
            vote_type=normalized,
            creator=user if is_authenticated else None,
            session_key=None if is_authenticated else session_key,
            ip_hash=ip_hash,
        )
        cls.log_action(f"Voted ({normalized}) on", corpus, user)
        return ServiceResult.success(vote)

    @classmethod
    @transaction.atomic
    def remove_vote(
        cls,
        user: Any,
        corpus_pk: Any,
        *,
        session_key: str | None = None,
        request: Any = None,
    ) -> ServiceResult[bool]:
        """Remove the caller's vote on a corpus (if any).

        Returns ``ServiceResult.success(True)`` when a vote was removed,
        ``ServiceResult.success(False)`` when there was no vote to remove
        — both are non-error outcomes from the user's perspective
        (idempotent un-vote). A non-empty error is returned only when the
        corpus is not visible / does not exist, mirroring ``cast_vote``.
        """
        from opencontractserver.corpuses.models import Corpus, CorpusVote

        corpus = cls.get_or_none(Corpus, corpus_pk, user, request=request)
        if corpus is None:
            return ServiceResult.failure(_CORPUS_NOT_FOUND_MSG)

        is_authenticated = is_authenticated_user(user)

        if is_authenticated:
            qs = CorpusVote.objects.filter(corpus=corpus, creator=user)
        elif session_key:
            qs = CorpusVote.objects.filter(
                corpus=corpus,
                creator__isnull=True,
                session_key=session_key,
            )
        else:
            # No session means no vote could have been recorded — same
            # idempotent "nothing removed" outcome as if the user simply
            # hadn't voted.  Not an error.
            return ServiceResult.success(False)

        # ``QuerySet.delete()`` returns ``(rows_deleted, {model: count})``
        # — read that directly rather than running a separate ``count()``
        # first.  Removes the small race window where a concurrent
        # double-click could delete the row between ``count()`` and
        # ``delete()`` and have us return a stale ``True``.
        deleted, _ = qs.delete()
        if not deleted:
            return ServiceResult.success(False)
        cls.log_action("Removed vote on", corpus, user)
        return ServiceResult.success(True)

    @classmethod
    def get_user_vote_type(
        cls,
        user: Any,
        corpus: Corpus,
        *,
        session_key: str | None = None,
    ) -> str | None:
        """Return ``"upvote"``/``"downvote"``/``None`` for the caller's vote.

        Used by the ``CorpusType.my_vote`` GraphQL field resolver so the
        UI can render the correct active-state on the vote arrows.

        SECURITY: this method takes a ``Corpus`` instance directly and
        does NOT run a READ visibility check — the caller is responsible
        for ensuring ``user`` is permitted to see ``corpus`` before
        calling. All in-tree call sites today reach the corpus through
        ``CorpusType.get_queryset`` (which already gates via
        ``BaseService.filter_visible_qs``), so the contract is satisfied.
        Future internal callers that pass an arbitrary corpus object MUST
        gate visibility themselves (e.g. via
        ``BaseService.get_or_none``) or this leaks the viewer's vote
        identity for corpora they shouldn't see.
        """
        from opencontractserver.corpuses.models import CorpusVote

        is_authenticated = is_authenticated_user(user)

        if is_authenticated:
            vote = (
                CorpusVote.objects.filter(corpus=corpus, creator=user)
                .only("vote_type")
                .first()
            )
        elif session_key:
            vote = (
                CorpusVote.objects.filter(
                    corpus=corpus,
                    creator__isnull=True,
                    session_key=session_key,
                )
                .only("vote_type")
                .first()
            )
        else:
            vote = None

        return vote.vote_type if vote else None
