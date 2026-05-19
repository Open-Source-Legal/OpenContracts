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

import json
import logging
from typing import Any

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Prefetch, Q

from opencontractserver.analyzer.models import Analysis, Analyzer
from opencontractserver.constants.tools import (
    ANALYSIS_INPUT_DATA_RESERVED_KEYS,
    ANALYZER_INPUT_SCHEMA_MAX_INLINE_CHARS,
)
from opencontractserver.constants.tools import (
    EXTRACT_ANALYZER_TOOL_DEFAULT_LIST_LIMIT as DEFAULT_LIST_LIMIT,
)
from opencontractserver.constants.tools import (
    EXTRACT_ANALYZER_TOOL_DEFAULT_RECENT_LIMIT as DEFAULT_RECENT_LIMIT,
)
from opencontractserver.constants.tools import (
    EXTRACT_ANALYZER_TOOL_MAX_LIST_LIMIT as MAX_LIST_LIMIT,
)
from opencontractserver.constants.tools import (
    EXTRACT_STATUS_COMPLETED,
    EXTRACT_STATUS_FAILED,
    EXTRACT_STATUS_QUEUED,
    EXTRACT_STATUS_RUNNING,
)
from opencontractserver.corpuses.models import Corpus, CorpusAction
from opencontractserver.extracts.models import Column, Extract, Fieldset
from opencontractserver.tasks.corpus_tasks import process_analyzer
from opencontractserver.tasks.extract_orchestrator_tasks import run_extract
from opencontractserver.types.enums import JobStatus, PermissionTypes
from opencontractserver.utils.extract import create_and_setup_extract

from ._helpers import _db_sync_to_async

logger = logging.getLogger(__name__)

User = get_user_model()


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
    """Return the User row for ``user_id`` or ``None`` if missing / unauth.

    Return type is intentionally inferred — ``User`` here is the result of
    ``get_user_model()`` (a runtime variable, not a type alias) so a
    quoted annotation would still trip mypy's ``valid-type`` check.
    """
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

    Intersects with the corpus's active document set in SQL so the agent
    can never escape the corpus scope it was created in. The branches
    avoid materialising the full corpus document list into Python:

    - ``requested_ids`` supplied → ``Document`` filter scoped by the
      corpus + ``pk__in=requested_ids``. Cost is bounded by the
      requested list size, not corpus cardinality.
    - ``agent_document_id`` supplied (document-agent context) → a
      single membership check via ``exists()``.
    - Neither supplied (corpus-agent default scope) → returns the
      whole corpus document set, which is unavoidable but at least
      streamed via ``values_list(flat=True)`` rather than re-collected
      from a Python set.
    """

    # The agent has already passed corpus-level visibility/UPDATE checks
    # in the caller, so corpus-internal active-document filtering here
    # is the only scope still owed.
    corpus_doc_qs = corpus.get_documents()

    if requested_ids:
        normalized = {int(d) for d in requested_ids}
        if not normalized:
            return []
        filtered = corpus_doc_qs.filter(pk__in=normalized).values_list("id", flat=True)
        return sorted(filtered)

    if agent_document_id is not None:
        agent_doc_pk = int(agent_document_id)
        if corpus_doc_qs.filter(pk=agent_doc_pk).exists():
            return [agent_doc_pk]
        # Silent fallback to full corpus is dangerous: a document agent
        # wired to one doc would quietly become a corpus-wide dispatch.
        # Fail loudly so the LLM can surface the mismatch instead of
        # over-scoping (and over-billing).
        raise ValueError(
            f"Document {agent_document_id} is not part of corpus {corpus.id}; "
            "pass document_ids explicitly or omit them to use the full "
            "corpus scope."
        )
    return sorted(corpus_doc_qs.values_list("id", flat=True))


def _extract_status(extract: Extract) -> str:
    if extract.error:
        return EXTRACT_STATUS_FAILED
    if extract.finished:
        return EXTRACT_STATUS_COMPLETED
    if extract.started:
        return EXTRACT_STATUS_RUNNING
    return EXTRACT_STATUS_QUEUED


def _normalize_analysis_status(raw_status: str | None) -> str:
    """Normalise ``Analysis.status`` for the agent surface.

    Pre-fix, ``start_analysis`` returned ``"queued"`` (the Extract
    constant) while ``list_recent_analyses`` passed the raw model value
    (``JobStatus.QUEUED.value`` → ``"QUEUED"``). An LLM that
    polled the listing after dispatching saw the status apparently
    change without anything having happened.

    Resolution: agents always see lowercase status strings, mirroring
    the extract vocabulary (``queued`` / ``running`` / ``completed`` /
    ``failed``). The model still stores uppercase values via
    ``JobStatus`` — only the agent surface is normalised.

    ``raw_status`` is permissive: ``None`` and unknown values pass
    through (lower-cased if string) rather than raising, so a future
    addition to ``JobStatus`` does not crash the listing tool.
    """

    if raw_status is None:
        return ""
    return str(raw_status).lower()


# Default initial status agents see immediately after ``start_analysis``.
# Sourced from ``JobStatus.QUEUED`` and normalised so the value matches
# what ``list_recent_analyses`` would emit on a subsequent poll, closing
# the vocabulary mismatch flagged in PR review.
_ANALYSIS_STATUS_QUEUED = _normalize_analysis_status(JobStatus.QUEUED.value)


def _strip_reserved_input_keys(
    analysis_input_data: dict | None,
    *,
    tool_name: str,
) -> dict | None:
    """Return ``analysis_input_data`` with internal kwargs removed.

    ``run_task_name_analyzer`` spreads the payload into the analyzer
    task with ``**(analysis_input_data or {})``. An agent driven by
    adversarial prompt injection (e.g. via document content) could
    therefore override internal scoping kwargs the task expects.
    Strip the reserved set defined in
    :data:`ANALYSIS_INPUT_DATA_RESERVED_KEYS` and log a warning so the
    override attempt is observable in production traces. The task
    itself remains the canonical validation boundary — this is a
    defense-in-depth shave on the agent-facing edge.
    """

    if not analysis_input_data:
        return analysis_input_data

    stripped = {
        k: v
        for k, v in analysis_input_data.items()
        if k not in ANALYSIS_INPUT_DATA_RESERVED_KEYS
    }
    if len(stripped) != len(analysis_input_data):
        removed = sorted(set(analysis_input_data) - set(stripped))
        logger.warning(
            "%s stripped reserved keys from analysis_input_data: %s",
            tool_name,
            removed,
        )
    return stripped


def _summarise_input_schema(schema: Any) -> Any:
    """Truncate over-large ``Analyzer.input_schema`` payloads for listing.

    Analyzer authors can register arbitrarily large schemas in their
    decorator. Returning them verbatim from ``list_analyzers``
    inflates the LLM context window on every discovery call. When the
    JSON-serialised schema exceeds
    :data:`ANALYZER_INPUT_SCHEMA_MAX_INLINE_CHARS`, replace it with a
    placeholder pointer; ``start_analysis`` itself does not need the
    schema (the task validates the payload), and the agent can still
    discover the analyzer.
    """

    if schema is None:
        return None
    try:
        serialized = json.dumps(schema)
    except (TypeError, ValueError):
        # Non-serialisable schema is itself a bug, but don't break the
        # listing — surface a placeholder instead.
        return {
            "_truncated": True,
            "_reason": "input_schema is not JSON-serialisable",
        }
    if len(serialized) <= ANALYZER_INPUT_SCHEMA_MAX_INLINE_CHARS:
        return schema
    return {
        "_truncated": True,
        "_reason": (
            "input_schema exceeds "
            f"{ANALYZER_INPUT_SCHEMA_MAX_INLINE_CHARS} chars; call "
            "start_analysis with the analyzer_id to dispatch and let "
            "the task validate the payload server-side."
        ),
        "_size_chars": len(serialized),
    }


def _resolve_corpus_action(
    corpus_action_id: int | None,
    *,
    corpus_id: int,
    tool_name: str,
) -> CorpusAction | None:
    """Resolve a ``corpus_action_id`` while pinning it to ``corpus_id``.

    The parameter is normally framework-injected, but a direct caller of
    ``start_extract`` / ``start_analysis`` could pass any ID. Restricting
    the lookup to the action's parent corpus prevents cross-corpus
    lineage attribution.
    """
    if corpus_action_id is None:
        return None
    try:
        return CorpusAction.objects.get(pk=corpus_action_id, corpus_id=corpus_id)
    except CorpusAction.DoesNotExist:
        logger.warning(
            "%s called with corpus_action_id=%s not attached to corpus %s; "
            "proceeding without lineage link.",
            tool_name,
            corpus_action_id,
            corpus_id,
        )
        return None


def list_fieldsets(
    *,
    corpus_id: int,
    user_id: int | None = None,
    limit: int | None = None,
    include_columns: bool = False,
) -> list[dict[str, Any]]:
    """List Fieldsets visible to the user that can be applied to this corpus.

    By default returns one row per fieldset with just the name, description,
    and a list of column names — enough for the agent to decide which
    fieldset to dispatch. Pass ``include_columns=True`` to get the full
    column definitions (``query``, ``match_text``, ``output_type``,
    ``instructions``) inline; useful when the agent wants to verify a
    fieldset's schema before calling ``start_extract``. Fieldsets pinned as
    the metadata schema of another corpus (via ``Fieldset.corpus``) are
    excluded; fieldsets pinned to *this* corpus are included so the agent
    sees the same set ``start_extract`` accepts.
    """

    user = _get_user_or_none(user_id)
    # IDOR: same message whether the corpus is missing or hidden.
    if not Corpus.objects.visible_to_user(user).filter(pk=corpus_id).exists():
        raise ValueError(f"Corpus with id={corpus_id} does not exist.")

    capped_limit = _clamp_limit(limit, DEFAULT_LIST_LIMIT)

    queryset = (
        Fieldset.objects.visible_to_user(user)
        .filter(Q(corpus__isnull=True) | Q(corpus_id=corpus_id))
        .prefetch_related(
            Prefetch(
                "columns",
                queryset=Column.objects.filter(is_manual_entry=False),
                to_attr="auto_columns",
            )
        )
        # ``-created`` matches ``list_recent_extracts`` so the agent
        # sees a stable, time-ordered list across the two discovery
        # tools. Pre-fix this used ``-modified``, which silently
        # reshuffled positions whenever a fieldset was edited.
        .order_by("-created")[:capped_limit]
    )

    results: list[dict[str, Any]] = []
    for fieldset in queryset:
        auto_columns = list(fieldset.auto_columns)
        # Default to a slim summary so a corpus admin with 20 fieldsets
        # of 10 long-form columns each doesn't return a multi-page
        # payload on every discovery call. ``column_names`` keeps the
        # LLM able to decide which fieldset matches its intent.
        row: dict[str, Any] = {
            "id": fieldset.id,
            "name": fieldset.name,
            "description": fieldset.description,
            "column_count": len(auto_columns),
            # ``extractable=False`` signals the LLM that
            # ``start_extract`` will reject this fieldset (no
            # auto-extract columns — every column is manual-entry,
            # the fieldset is empty, etc.). Surfacing the flag in
            # the listing avoids the LLM optimistically dispatching
            # and discovering the constraint via a ``ValueError``.
            "extractable": len(auto_columns) > 0,
        }
        if include_columns:
            row["columns"] = [
                {
                    "id": column.id,
                    "name": column.name,
                    "query": column.query,
                    "match_text": column.match_text,
                    "output_type": column.output_type,
                    "instructions": column.instructions,
                    "extract_is_list": column.extract_is_list,
                }
                for column in auto_columns
            ]
        else:
            row["column_names"] = [column.name for column in auto_columns]
        results.append(row)

    return results


async def alist_fieldsets(
    *,
    corpus_id: int,
    user_id: int | None = None,
    limit: int | None = None,
    include_columns: bool = False,
) -> list[dict[str, Any]]:
    """Async variant of :func:`list_fieldsets`."""
    return await _db_sync_to_async(list_fieldsets)(
        corpus_id=corpus_id,
        user_id=user_id,
        limit=limit,
        include_columns=include_columns,
    )


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

    if user_id is None:
        raise PermissionError("start_extract requires an authenticated user.")
    user = _get_user_or_none(user_id)
    if user is None:
        raise PermissionError(f"User {user_id} not found.")

    corpus = Corpus.objects.visible_to_user(user).filter(pk=corpus_id).first()
    if corpus is None:
        raise PermissionError(f"User {user_id} cannot access corpus {corpus_id}.")

    if not corpus.user_can(user, PermissionTypes.UPDATE):
        raise PermissionError(
            f"User {user_id} lacks UPDATE permission on corpus {corpus_id}."
        )

    fieldset = Fieldset.objects.visible_to_user(user).filter(pk=fieldset_id).first()
    if fieldset is None:
        raise PermissionError(f"User {user_id} cannot access fieldset {fieldset_id}.")

    # Fieldsets pinned as another corpus's metadata schema are private to that corpus.
    if fieldset.corpus_id is not None and fieldset.corpus_id != corpus_id:
        raise PermissionError(
            f"Fieldset {fieldset_id} is the metadata schema for corpus "
            f"{fieldset.corpus_id} and cannot be applied to corpus {corpus_id}."
        )

    if not fieldset.columns.filter(is_manual_entry=False).exists():
        raise ValueError(
            f"Fieldset {fieldset_id} has no extractable columns "
            "(empty or all manual-entry)."
        )

    corpus_action = _resolve_corpus_action(
        corpus_action_id, corpus_id=corpus_id, tool_name="start_extract"
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

    # The CRUD grant and atomic boundary live inside
    # ``create_and_setup_extract`` so every caller (here, the GraphQL
    # mutations, and the CorpusAction pipeline) gets the same guarantee
    # without having to remember it.
    with transaction.atomic():
        extract = create_and_setup_extract(
            user.id,
            corpus=corpus,
            fieldset=fieldset,
            name=extract_name,
            document_ids=target_ids,
            corpus_action=corpus_action,
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
        "status": EXTRACT_STATUS_QUEUED,
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
        Analyzer.objects.visible_to_user(user).filter(disabled=False)
        # ``-created`` mirrors ``list_fieldsets`` so the discovery surface
        # is consistent. Previous ``order_by("id")`` was lexicographic
        # over CharField IDs like ``"gremlin.v2.analyzer"`` — deterministic
        # but unpredictable, and the position of any given analyzer would
        # shift whenever a new one with an ID earlier in the alphabet
        # was registered.
        .order_by("-created")[:capped_limit]
    )

    results: list[dict[str, Any]] = []
    for analyzer in queryset:
        results.append(
            {
                "id": analyzer.id,
                "description": analyzer.description,
                "host_gremlin_id": analyzer.host_gremlin_id,
                "task_name": analyzer.task_name,
                # Schemas larger than the inline cap are truncated to a
                # placeholder so a misbehaving analyzer can't blow up
                # every agent's context window on a discovery call.
                "input_schema": _summarise_input_schema(analyzer.input_schema),
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

    if user_id is None:
        raise PermissionError("start_analysis requires an authenticated user.")
    user = _get_user_or_none(user_id)
    if user is None:
        raise PermissionError(f"User {user_id} not found.")

    corpus = Corpus.objects.visible_to_user(user).filter(pk=corpus_id).first()
    if corpus is None:
        raise PermissionError(f"User {user_id} cannot access corpus {corpus_id}.")

    if not corpus.user_can(user, PermissionTypes.UPDATE):
        raise PermissionError(
            f"User {user_id} lacks UPDATE permission on corpus {corpus_id}."
        )

    analyzer = Analyzer.objects.visible_to_user(user).filter(pk=analyzer_id).first()
    if analyzer is None:
        raise PermissionError(f"User {user_id} cannot access analyzer {analyzer_id}.")

    if analyzer.disabled:
        raise ValueError(f"Analyzer {analyzer_id} is disabled.")

    corpus_action = _resolve_corpus_action(
        corpus_action_id, corpus_id=corpus_id, tool_name="start_analysis"
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

    # widened for process_analyzer's list[str | int] param (list[int] is invariant)
    widened_ids: list[str | int] = list(target_ids)
    # analysis_input_data is intentionally NOT validated here against
    # analyzer.input_schema. Validation is the per-analyzer task's
    # responsibility — the schema is a freeform JSON-Schema sourced from
    # the analyzer's Python decorator, and ``run_task_name_analyzer``
    # spreads the payload directly into the task function call as
    # ``**(analysis_input_data or {})``. The task function is therefore
    # the canonical validation boundary; a malformed payload fails at
    # task execution so the agent path stays bug-compatible with the
    # human GraphQL / CorpusAction path that also doesn't pre-validate.
    #
    # Defense in depth: ``_strip_reserved_input_keys`` removes a small
    # set of internal kwargs (``analysis_id``, scoping IDs, etc.) that
    # would otherwise shadow ``run_task_name_analyzer``'s own
    # arguments. The agent path is uniquely exposed to adversarial
    # prompt injection via document content, so closing this
    # privilege-escalation vector on the way in is cheap and observable.
    #
    # ``process_analyzer`` itself does NOT wrap its work in
    # ``transaction.atomic()`` — it creates the Analysis row then
    # registers a ``transaction.on_commit`` callback to dispatch Celery.
    # In Django autocommit mode (Celery workers, ``manage.py shell``),
    # ``on_commit`` fires immediately, so without an explicit outer
    # ``atomic()`` an error after the call would still kick off the
    # downstream task. Wrap in ``atomic()`` here for symmetry with
    # ``start_extract`` and to give callers a clean rollback boundary.
    safe_input_data = _strip_reserved_input_keys(
        analysis_input_data, tool_name="start_analysis"
    )
    with transaction.atomic():
        analysis = process_analyzer(
            user_id=user.id,
            analyzer=analyzer,
            corpus_id=corpus.id,
            document_ids=widened_ids,
            corpus_action=corpus_action,
            analysis_input_data=safe_input_data,
        )

    return {
        "analysis_id": analysis.id,
        "analyzer_id": analyzer.id,
        "analyzer_description": analyzer.description,
        "document_count": len(target_ids),
        "corpus_action_id": corpus_action.id if corpus_action else None,
        # Use the analysis-domain status constant (lowercase JobStatus
        # value) so the listing tool's normalisation produces the same
        # vocabulary on a subsequent poll. See ``_normalize_analysis_status``.
        "status": _ANALYSIS_STATUS_QUEUED,
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
                # Normalise the model-sourced ``JobStatus`` to the same
                # lowercase vocabulary ``start_analysis`` emits, so an
                # agent polling immediately after dispatch sees a stable
                # value rather than a case-shift mid-lifecycle.
                "status": _normalize_analysis_status(analysis.status),
                # ``created`` mirrors ``list_recent_extracts`` — an agent
                # polling immediately after ``start_analysis`` would
                # otherwise see ``analysis_started=null`` /
                # ``analysis_completed=null`` with no timestamp to
                # confirm the record exists.
                "created": (analysis.created.isoformat() if analysis.created else None),
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
