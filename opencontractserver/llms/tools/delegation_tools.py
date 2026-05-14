"""Per-turn delegation tool factory for the rich-mention agent system.

Spec: ``docs/architecture/rich_mentions.md``

This module provides scope-aware filtering of ``AgentConfiguration`` rows for
chat delegation, and (in later tasks) the per-turn tool factory used by the
consumer to expose available sub-agents to the orchestrator LLM.
"""

from __future__ import annotations

from django.db.models import Q, QuerySet

from opencontractserver.agents.models import AgentConfiguration
from opencontractserver.documents.models import DocumentPath


def filter_by_scope(
    qs: QuerySet[AgentConfiguration],
    *,
    corpus_id: int | None,
    document_id: int | None,
) -> QuerySet[AgentConfiguration]:
    """Restrict an agent queryset to those usable in the current chat scope.

    Rules (matching the spec's scope matrix):
      - standalone doc chat (no corpus, no doc, OR a doc with no current
        corpus membership): GLOBAL agents only.
      - corpus chat: GLOBAL agents plus agents owned by that corpus.
      - doc-in-corpus chat: GLOBAL agents plus agents owned by the doc's
        active corpus.

    The Document <-> Corpus relation in this codebase is mediated by
    ``DocumentPath`` (no direct FK/M2M on ``Document``). We resolve the
    document's *current, non-deleted* path to determine its corpus.

    Args:
        qs: Base queryset of ``AgentConfiguration`` rows (typically already
            permission-filtered via ``visible_to_user``).
        corpus_id: Active corpus id for the chat, or ``None``.
        document_id: Active document id for the chat, or ``None``.

    Returns:
        A queryset filtered to the agents valid for the given chat scope.
    """
    if not corpus_id and not document_id:
        return qs.filter(scope="GLOBAL")

    if corpus_id:
        return qs.filter(Q(scope="GLOBAL") | Q(corpus_id=corpus_id))

    # document_id only — resolve its current corpus via DocumentPath.
    # The outer guard ensures ``document_id`` is non-None here; assert for
    # the type checker so the FK lookup receives ``int`` (not ``int | None``).
    assert document_id is not None
    doc_corpus_id = (
        DocumentPath.objects.filter(
            document_id=document_id,
            is_current=True,
            is_deleted=False,
        )
        .values_list("corpus_id", flat=True)
        .first()
    )
    if doc_corpus_id:
        return qs.filter(Q(scope="GLOBAL") | Q(corpus_id=doc_corpus_id))
    return qs.filter(scope="GLOBAL")
