"""Agent tools for triggering Extracts and Analyses on a corpus.

These tools let an LLM agent discover the Fieldsets and Analyzers visible
to the calling user and dispatch them just like a human would — without
inventing schemas or analyzers from scratch.

Permissioning matches the existing GraphQL surface:

* Discovery tools (``list_*``) are read-only and filter via the model
  manager's ``visible_to_user`` (auth-aware; respects ``is_public``).
* Run tools (``start_extract`` / ``start_analysis``) are write,
  approval-gated, and require WRITE permission on the corpus. They
  re-use the same Celery dispatch path as the
  ``StartExtract`` / ``StartDocumentAnalysisMutation`` GraphQL mutations.

Document scoping convention (start_extract / start_analysis):

* If the LLM omits ``document_ids``:
    - Corpus-agent context (``document_id`` injected as ``None``):
      defaults to the full visible corpus document set.
    - Document-agent context (``document_id`` injected from agent
      deps): defaults to ``[document_id]`` — single-doc scope.
* Any ``document_ids`` the LLM passes are intersected with the corpus's
  active document set so the agent can never reach documents outside
  the corpus it's working in.

Parameter naming matches ``build_inject_params_for_context`` in
``opencontractserver.llms.tools.tool_factory`` — ``corpus_id``,
``user_id``, ``document_id``, and ``corpus_action_id`` are
auto-injected by the tool wrapper and hidden from the LLM's schema.
"""

from __future__ import annotations

import logging
from typing import Any

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q

from opencontractserver.analyzer.models import Analysis, Analyzer
from opencontractserver.constants.tools import (
    EXTRACT_ANALYZER_TOOL_DEFAULT_LIST_LIMIT as DEFAULT_LIST_LIMIT,
)
from opencontractserver.constants.tools import (
    EXTRACT_ANALYZER_TOOL_DEFAULT_RECENT_LIMIT as DEFAULT_RECENT_LIMIT,
)
from opencontractserver.constants.tools import (
    EXTRACT_ANALYZER_TOOL_MAX_LIST_LIMIT as MAX_LIST_LIMIT,
)
from opencontractserver.corpuses.models import Corpus, CorpusAction
from opencontractserver.extracts.models import Extract, Fieldset
from opencontractserver.tasks.extract_orchestrator_tasks import run_extract
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import (
    set_permissions_for_obj_to_user,
    user_has_permission_for_obj,
)

from ._helpers import _db_sync_to_async

logger = logging.getLogger(__name__)

User = get_user_model()


# --------------------------------------------------------------------------- #
# Internal helpers                                                            #
# --------------------------------------------------------------------------- #


def _clamp_limit(limit: int | None, default: int) -> int:
    if limit is None:
        return default
    try:
        value = int(limit)
    except (TypeError, ValueError):
        return default
    if value <= 0:
        return default
    return min(value, MAX_LIST_LIMIT)


def _get_user_or_none(user_id: int | None):
    if user_id is None:
        return None
    try:
        return User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return None


def _resolve_target_document_ids(
    corpus: Corpus,
    *,
    requested_ids: list[int] | None,
    agent_document_id: int | None,
) -> list[int]:
    """Resolve which document IDs an extract/analysis run should target.

    Intersects with ``corpus.get_documents()`` so the agent can never
    escape the corpus scope it was created in.
    """
    corpus_doc_ids = set(corpus.get_documents().values_list("id", flat=True))

    if requested_ids:
        normalized = {int(d) for d in requested_ids}
        filtered = sorted(normalized & corpus_doc_ids)
        return filtered

    # No explicit IDs from the LLM.
    if agent_document_id is not None:
        if int(agent_document_id) in corpus_doc_ids:
            return [int(agent_document_id)]
        # The document agent is somehow scoped outside the corpus —
        # fall through to corpus-wide scope rather than silently dropping
        # the call (this shouldn't normally happen).
        logger.warning(
            "Document agent document_id=%s not in corpus %s; defaulting to "
            "full corpus scope.",
            agent_document_id,
            corpus.id,
        )
    return sorted(corpus_doc_ids)


def _extract_status(extract: Extract) -> str:
    if extract.error:
        return "failed"
    if extract.finished:
        return "completed"
    if extract.started:
        return "running"
    return "queued"


# --------------------------------------------------------------------------- #
# Fieldset discovery                                                          #
# --------------------------------------------------------------------------- #


def list_fieldsets(
    *,
    corpus_id: int,
    user_id: int | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """List Fieldsets visible to the user that can be applied to this corpus.

    Returns each fieldset's name, description, and column definitions so the
    agent can pick one. Fieldsets pinned as the metadata schema of another
    corpus (via ``Fieldset.corpus``) are excluded; fieldsets pinned to *this*
    corpus are included so the agent sees the same set ``start_extract``
    accepts.
    """

    user = _get_user_or_none(user_id)
    # Use visible_to_user instead of bare ``get`` so we don't leak the
    # existence of private corpus IDs to callers (CLAUDE.md IDOR rule —
    # same message whether the corpus is missing or hidden).
    if not Corpus.objects.visible_to_user(user).filter(pk=corpus_id).exists():
        raise ValueError(f"Corpus with id={corpus_id} does not exist.")

    capped_limit = _clamp_limit(limit, DEFAULT_LIST_LIMIT)

    queryset = (
        Fieldset.objects.visible_to_user(user)
        .filter(Q(corpus__isnull=True) | Q(corpus_id=corpus_id))
        .prefetch_related("columns")
        .order_by("-modified")[:capped_limit]
    )

    results: list[dict[str, Any]] = []
    for fieldset in queryset:
        columns = []
        for column in fieldset.columns.all():
            if column.is_manual_entry:
                continue
            columns.append(
                {
                    "id": column.id,
                    "name": column.name,
                    "query": column.query,
                    "match_text": column.match_text,
                    "output_type": column.output_type,
                    "instructions": column.instructions,
                    "extract_is_list": column.extract_is_list,
                }
            )
        results.append(
            {
                "id": fieldset.id,
                "name": fieldset.name,
                "description": fieldset.description,
                "column_count": len(columns),
                "columns": columns,
            }
        )

    return results


async def alist_fieldsets(
    *,
    corpus_id: int,
    user_id: int | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Async variant of :func:`list_fieldsets`."""
    return await _db_sync_to_async(list_fieldsets)(
        corpus_id=corpus_id, user_id=user_id, limit=limit
    )


# --------------------------------------------------------------------------- #
# Extract dispatch                                                            #
# --------------------------------------------------------------------------- #


def start_extract(
    *,
    corpus_id: int,
    fieldset_id: int,
    user_id: int,
    name: str | None = None,
    document_ids: list[int] | None = None,
    corpus_action_id: int | None = None,
    document_id: int | None = None,
) -> dict[str, Any]:
    """Create a new Extract record and queue ``run_extract``.

    Validates fieldset visibility and corpus UPDATE permission, scopes the
    document set via ``_resolve_target_document_ids`` (respects the
    agent's ``document_id`` if it's a document agent), grants the user
    CRUD on the resulting Extract, and dispatches the Celery pipeline on
    transaction commit.
    """

    user = _get_user_or_none(user_id)
    if user is None:
        raise PermissionError("start_extract requires an authenticated user.")

    corpus = Corpus.objects.visible_to_user(user).filter(pk=corpus_id).first()
    if corpus is None:
        raise PermissionError(f"User {user_id} cannot access corpus {corpus_id}.")

    if not user_has_permission_for_obj(
        user, corpus, PermissionTypes.UPDATE, include_group_permissions=True
    ):
        raise PermissionError(
            f"User {user_id} lacks UPDATE permission on corpus {corpus_id}."
        )

    # Single-query visibility-and-fetch — the prior two-step ``exists()`` +
    # ``get()`` pattern was a needless round trip.
    fieldset = Fieldset.objects.visible_to_user(user).filter(pk=fieldset_id).first()
    if fieldset is None:
        raise PermissionError(f"User {user_id} cannot access fieldset {fieldset_id}.")

    # Block fieldsets that are pinned as another corpus's metadata schema —
    # they are private to that corpus by design.
    if fieldset.corpus_id is not None and fieldset.corpus_id != corpus_id:
        raise PermissionError(
            f"Fieldset {fieldset_id} is the metadata schema for corpus "
            f"{fieldset.corpus_id} and cannot be applied to corpus {corpus_id}."
        )

    if not fieldset.columns.exists():
        raise ValueError(f"Fieldset {fieldset_id} has no columns to extract.")

    corpus_action: CorpusAction | None = None
    if corpus_action_id is not None:
        try:
            corpus_action = CorpusAction.objects.get(pk=corpus_action_id)
        except CorpusAction.DoesNotExist:
            logger.warning(
                "start_extract called with unknown corpus_action_id=%s; "
                "proceeding without lineage link.",
                corpus_action_id,
            )

    target_ids = _resolve_target_document_ids(
        corpus,
        requested_ids=document_ids,
        agent_document_id=document_id,
    )

    if not target_ids:
        raise ValueError(
            f"No documents available to extract on corpus {corpus_id} "
            "(after permission and scope filtering)."
        )

    extract_name = name or (
        f"Agent extract: {fieldset.name} on {corpus.title or 'corpus'}"
    )

    with transaction.atomic():
        extract = Extract.objects.create(
            corpus=corpus,
            name=extract_name,
            fieldset=fieldset,
            creator=user,
            corpus_action=corpus_action,
        )
        extract.documents.add(*target_ids)
        set_permissions_for_obj_to_user(
            user, extract, [PermissionTypes.CRUD], is_new=True
        )

        extract_id = extract.id
        run_user_id = user.id

        def _dispatch() -> None:
            run_extract.s(extract_id, run_user_id).apply_async()

        transaction.on_commit(_dispatch)

    return {
        "extract_id": extract.id,
        "name": extract.name,
        "fieldset_id": fieldset.id,
        "fieldset_name": fieldset.name,
        "document_count": len(target_ids),
        "corpus_action_id": corpus_action.id if corpus_action else None,
        "status": "queued",
    }


async def astart_extract(
    *,
    corpus_id: int,
    fieldset_id: int,
    user_id: int,
    name: str | None = None,
    document_ids: list[int] | None = None,
    corpus_action_id: int | None = None,
    document_id: int | None = None,
) -> dict[str, Any]:
    """Async variant of :func:`start_extract`."""
    return await _db_sync_to_async(start_extract)(
        corpus_id=corpus_id,
        fieldset_id=fieldset_id,
        user_id=user_id,
        name=name,
        document_ids=document_ids,
        corpus_action_id=corpus_action_id,
        document_id=document_id,
    )


# --------------------------------------------------------------------------- #
# Recent extracts                                                             #
# --------------------------------------------------------------------------- #


def list_recent_extracts(
    *,
    corpus_id: int,
    user_id: int | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return the most recent Extracts on this corpus visible to the user."""

    user = _get_user_or_none(user_id)
    if not Corpus.objects.visible_to_user(user).filter(pk=corpus_id).exists():
        raise ValueError(f"Corpus with id={corpus_id} does not exist.")

    capped_limit = _clamp_limit(limit, DEFAULT_RECENT_LIMIT)

    # ``annotate(Count(...))`` folds the per-extract M2M count into the
    # single SELECT so the loop below is O(1) queries instead of O(N).
    queryset = (
        Extract.objects.visible_to_user(user)
        .filter(corpus_id=corpus_id)
        .select_related("fieldset")
        .annotate(document_count=Count("documents"))
        .order_by("-created")[:capped_limit]
    )

    results: list[dict[str, Any]] = []
    for extract in queryset:
        results.append(
            {
                "id": extract.id,
                "name": extract.name,
                "fieldset_id": extract.fieldset_id,
                "fieldset_name": (extract.fieldset.name if extract.fieldset else None),
                "created": extract.created.isoformat() if extract.created else None,
                "started": extract.started.isoformat() if extract.started else None,
                "finished": (
                    extract.finished.isoformat() if extract.finished else None
                ),
                "document_count": extract.document_count,
                "status": _extract_status(extract),
            }
        )

    return results


async def alist_recent_extracts(
    *,
    corpus_id: int,
    user_id: int | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Async variant of :func:`list_recent_extracts`."""
    return await _db_sync_to_async(list_recent_extracts)(
        corpus_id=corpus_id, user_id=user_id, limit=limit
    )


# --------------------------------------------------------------------------- #
# Analyzer discovery                                                          #
# --------------------------------------------------------------------------- #


def list_analyzers(
    *,
    corpus_id: int,
    user_id: int | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """List Analyzers visible to the user that can be applied to this corpus."""

    user = _get_user_or_none(user_id)
    if not Corpus.objects.visible_to_user(user).filter(pk=corpus_id).exists():
        raise ValueError(f"Corpus with id={corpus_id} does not exist.")

    capped_limit = _clamp_limit(limit, DEFAULT_LIST_LIMIT)

    queryset = (
        Analyzer.objects.visible_to_user(user)
        .filter(disabled=False)
        .order_by("id")[:capped_limit]
    )

    results: list[dict[str, Any]] = []
    for analyzer in queryset:
        results.append(
            {
                "id": analyzer.id,
                "description": analyzer.description,
                "host_gremlin_id": analyzer.host_gremlin_id,
                "task_name": analyzer.task_name,
                "input_schema": analyzer.input_schema,
                "is_public": analyzer.is_public,
            }
        )

    return results


async def alist_analyzers(
    *,
    corpus_id: int,
    user_id: int | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Async variant of :func:`list_analyzers`."""
    return await _db_sync_to_async(list_analyzers)(
        corpus_id=corpus_id, user_id=user_id, limit=limit
    )


# --------------------------------------------------------------------------- #
# Analysis dispatch                                                           #
# --------------------------------------------------------------------------- #


def start_analysis(
    *,
    corpus_id: int,
    analyzer_id: str,
    user_id: int,
    document_ids: list[int] | None = None,
    analysis_input_data: dict | None = None,
    corpus_action_id: int | None = None,
    document_id: int | None = None,
) -> dict[str, Any]:
    """Create an Analysis and dispatch the configured analyzer.

    Mirrors ``process_analyzer`` (the existing GraphQL/CorpusAction entry
    point) so the agent path and the human path produce identical
    Analysis records.
    """

    # Local import to keep this module importable even when the analyzer
    # task graph is being refactored.
    from opencontractserver.tasks.corpus_tasks import process_analyzer

    user = _get_user_or_none(user_id)
    if user is None:
        raise PermissionError("start_analysis requires an authenticated user.")

    corpus = Corpus.objects.visible_to_user(user).filter(pk=corpus_id).first()
    if corpus is None:
        raise PermissionError(f"User {user_id} cannot access corpus {corpus_id}.")

    if not user_has_permission_for_obj(
        user, corpus, PermissionTypes.UPDATE, include_group_permissions=True
    ):
        raise PermissionError(
            f"User {user_id} lacks UPDATE permission on corpus {corpus_id}."
        )

    # Single-query visibility-and-fetch — the prior two-step ``exists()`` +
    # ``get()`` pattern was a needless round trip.
    analyzer = Analyzer.objects.visible_to_user(user).filter(pk=analyzer_id).first()
    if analyzer is None:
        raise PermissionError(f"User {user_id} cannot access analyzer {analyzer_id}.")

    if analyzer.disabled:
        raise ValueError(f"Analyzer {analyzer_id} is disabled.")

    corpus_action: CorpusAction | None = None
    if corpus_action_id is not None:
        try:
            corpus_action = CorpusAction.objects.get(pk=corpus_action_id)
        except CorpusAction.DoesNotExist:
            logger.warning(
                "start_analysis called with unknown corpus_action_id=%s; "
                "proceeding without lineage link.",
                corpus_action_id,
            )

    target_ids = _resolve_target_document_ids(
        corpus,
        requested_ids=document_ids,
        agent_document_id=document_id,
    )

    if not target_ids:
        raise ValueError(
            f"No documents available to analyze on corpus {corpus_id} "
            "(after permission and scope filtering)."
        )

    # list[int] is invariant; ``process_analyzer`` declares the parameter
    # as ``list[str | int]`` so we widen explicitly to keep mypy happy.
    widened_ids: list[str | int] = list(target_ids)
    analysis = process_analyzer(
        user_id=user.id,
        analyzer=analyzer,
        corpus_id=corpus.id,
        document_ids=widened_ids,
        corpus_action=corpus_action,
        analysis_input_data=analysis_input_data,
    )

    return {
        "analysis_id": analysis.id,
        "analyzer_id": analyzer.id,
        "analyzer_description": analyzer.description,
        "document_count": len(target_ids),
        "corpus_action_id": corpus_action.id if corpus_action else None,
        "status": "queued",
    }


async def astart_analysis(
    *,
    corpus_id: int,
    analyzer_id: str,
    user_id: int,
    document_ids: list[int] | None = None,
    analysis_input_data: dict | None = None,
    corpus_action_id: int | None = None,
    document_id: int | None = None,
) -> dict[str, Any]:
    """Async variant of :func:`start_analysis`."""
    return await _db_sync_to_async(start_analysis)(
        corpus_id=corpus_id,
        analyzer_id=analyzer_id,
        user_id=user_id,
        document_ids=document_ids,
        analysis_input_data=analysis_input_data,
        corpus_action_id=corpus_action_id,
        document_id=document_id,
    )


# --------------------------------------------------------------------------- #
# Recent analyses                                                             #
# --------------------------------------------------------------------------- #


def list_recent_analyses(
    *,
    corpus_id: int,
    user_id: int | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return the most recent Analyses on this corpus visible to the user."""

    user = _get_user_or_none(user_id)
    if not Corpus.objects.visible_to_user(user).filter(pk=corpus_id).exists():
        raise ValueError(f"Corpus with id={corpus_id} does not exist.")

    capped_limit = _clamp_limit(limit, DEFAULT_RECENT_LIMIT)

    # ``annotate(Count(...))`` folds the per-analysis M2M count into the
    # single SELECT so the loop below is O(1) queries instead of O(N).
    queryset = (
        Analysis.objects.visible_to_user(user)
        .filter(analyzed_corpus_id=corpus_id)
        .select_related("analyzer")
        .annotate(document_count=Count("analyzed_documents"))
        .order_by("-created")[:capped_limit]
    )

    results: list[dict[str, Any]] = []
    for analysis in queryset:
        results.append(
            {
                "id": analysis.id,
                "analyzer_id": analysis.analyzer_id,
                "analyzer_description": (
                    analysis.analyzer.description if analysis.analyzer else None
                ),
                "status": analysis.status,
                "analysis_started": (
                    analysis.analysis_started.isoformat()
                    if analysis.analysis_started
                    else None
                ),
                "analysis_completed": (
                    analysis.analysis_completed.isoformat()
                    if analysis.analysis_completed
                    else None
                ),
                "document_count": analysis.document_count,
                "error_message": analysis.error_message,
            }
        )

    return results


async def alist_recent_analyses(
    *,
    corpus_id: int,
    user_id: int | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Async variant of :func:`list_recent_analyses`."""
    return await _db_sync_to_async(list_recent_analyses)(
        corpus_id=corpus_id, user_id=user_id, limit=limit
    )
