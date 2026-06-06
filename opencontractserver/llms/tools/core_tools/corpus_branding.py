"""Agent tool for manually (re)generating a corpus's icon/logo.

The corpus auto-branding flow
(``opencontractserver/corpuses/services/branding.py``) generates a logo once,
at corpus-creation time, when no icon was uploaded. This tool exposes the
*same* generator to an agent so a user can trigger it on demand — e.g.
"regenerate the icon for this collection" or "give it a logo featuring a set of
scales" — at any point in a corpus conversation.

Permissioning mirrors the rest of the corpus-row write surface:

* The corpus must be visible to the calling user (IDOR-safe error otherwise).
* Writing the icon is **creator-only**, exactly like
  :meth:`CorpusService.update_icon` / ``update_corpus_description`` — even a
  collaborator with a guardian UPDATE grant cannot replace it. The creator gate
  is checked up front (so we never spend an image-generation round-trip on a
  request that cannot succeed) and is re-enforced by ``update_icon`` itself.

The tool is registered ``requires_approval=True`` so each regeneration surfaces
a confirmation prompt before it overwrites the existing icon.

``corpus_id`` and ``user_id`` are framework-injected (hidden from the LLM) by
``build_inject_params_for_context``; the only LLM-visible argument is the
optional ``additional_instructions`` styling hint.
"""

from __future__ import annotations

import logging
from typing import Any

from django.contrib.auth import get_user_model

from opencontractserver.corpuses.models import Corpus

from ._helpers import _db_sync_to_async

logger = logging.getLogger(__name__)

User = get_user_model()


def _authorize_icon_regeneration(
    corpus_id: int, user_id: int | None
) -> tuple[Corpus, Any]:
    """Resolve and authorize ``(corpus, user)`` for an icon regeneration.

    The user element of the return is typed ``Any``: ``User`` here is the
    ``get_user_model()`` runtime variable (not a type alias), so a quoted
    annotation would trip mypy's ``valid-type`` check (mirrors
    ``extracts_and_analyzers._get_user_or_none``).

    Raises ``PermissionError`` — a security exception the tool wrapper
    propagates rather than swallowing — when the user is anonymous, missing,
    cannot see the corpus, or is not the corpus creator. The "cannot access"
    branch returns the same opaque framing the other corpus tools use so the
    message cannot be used to enumerate corpora.
    """
    if user_id is None:
        raise PermissionError("regenerate_corpus_icon requires an authenticated user.")

    user = User.objects.filter(pk=user_id).first()
    if user is None:
        raise PermissionError(f"User {user_id} not found.")

    corpus = Corpus.objects.visible_to_user(user).filter(pk=corpus_id).first()
    if corpus is None:
        raise PermissionError(f"User {user_id} cannot access corpus {corpus_id}.")

    # Creator-only: mirror ``CorpusService.update_icon``'s authoritative gate so
    # we fail fast (before generating an image) on a request that cannot persist.
    if corpus.creator_id != user.id:
        raise PermissionError(
            f"Only the corpus creator can regenerate the icon for corpus {corpus_id}."
        )
    return corpus, user


async def aregenerate_corpus_icon(
    *,
    corpus_id: int,
    user_id: int | None = None,
    additional_instructions: str | None = None,
) -> dict[str, Any]:
    """Generate a fresh icon/logo for the corpus and save it.

    Re-runs the corpus logo generator (OpenAI Images with a deterministic PIL
    monogram fallback) and writes the result to the corpus's ``icon``,
    **replacing** any existing icon. Useful when the creator wants a new look,
    or wants to steer the style via ``additional_instructions``.

    Args:
        corpus_id: Corpus whose icon to regenerate (injected from context).
        user_id: User performing the regeneration (injected from context);
            must be the corpus creator.
        additional_instructions: Optional free-text styling hint folded into
            the image prompt (e.g. "use blue tones and a gavel motif"). Only
            affects AI generation; the deterministic monogram fallback (used
            when image generation is disabled or unconfigured) ignores it.
            Sanitised and length-capped before use.

    Returns:
        A small status dict describing the result.
    """
    corpus, user = await _db_sync_to_async(_authorize_icon_regeneration)(
        corpus_id, user_id
    )

    # Deferred import: the branding service imports from the corpuses package at
    # module load, so importing it at the top of a tool module that is itself
    # imported during tool-registry population risks a cycle.
    from opencontractserver.corpuses.services.branding import (
        aregenerate_corpus_logo,
        sanitize_logo_instruction_hint,
    )

    result = await aregenerate_corpus_logo(
        corpus, user, additional_instructions=additional_instructions
    )
    if not result.ok:
        # The up-front gate already screens the creator-only case, so reaching
        # here means the corpus/user state changed mid-flight (e.g. a hard
        # delete during the slow image generation). Surface it as an operational
        # error string so the agent can inform the user rather than crashing the
        # turn.
        raise ValueError(result.error or "Failed to save the regenerated corpus icon.")

    return {
        "corpus_id": corpus.id,
        "status": "updated",
        # Report from the *sanitised* hint (the same value the prompt builder
        # appends) so a hint that collapses to empty (e.g. only quotes) is not
        # falsely reported as applied.
        "additional_instructions_applied": bool(
            sanitize_logo_instruction_hint(additional_instructions)
        ),
        "detail": "A new corpus icon was generated and saved.",
    }
