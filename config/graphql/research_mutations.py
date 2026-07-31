"""Generated strawberry GraphQL module (graphene migration).

Shape-generated from the graphene schema; stub functions marked PORT(...)
carry the ported business logic. See config/graphql_new/manifest.json.
"""

# mypy: disable-error-code="name-defined, valid-type, arg-type"
#   Code-generation artifacts of the strawberry schema bindings that
#   mypy's static pass cannot resolve, NOT real typing defects:
#     name-defined / valid-type — ``Annotated["XType", strawberry.lazy(...)]``
#       forward-reference strings + the runtime-generated ``*Connection``
#       types (``make_connection_types``).
#     arg-type — resolvers construct result types with ``to_global_id()``
#       (``str``) for ``strawberry.ID`` fields and return Django MODEL
#       instances where the field annotation names the strawberry type
#       (the graphene-django resolver contract). Both are correct at
#       runtime. Hand-written config/graphql/core/* stays fully checked.
# flake8: noqa: E501, F821 — generated strawberry schema module.
# E501: long GraphQL field/argument ``description=`` strings and the
# single-line generated resolver signatures (black cannot split string
# literals). F821: ``Annotated["XType", strawberry.lazy(...)]`` /
# ``cast("QuerySet", ...)`` forward-reference STRINGS that pyflakes
# resolves as names — the whole point of strawberry.lazy is to avoid the
# import (which would then be F401). Both are code-generation artifacts,
# not defects; hand-written modules (config/graphql/core/*, security.py,
# testing.py, filters.py, …) stay fully linted.

from __future__ import annotations

import logging
from typing import Annotated

import strawberry
from graphql_relay import from_global_id

from config.graphql._util import strip_unset
from config.graphql.core.auth import PermissionDenied
from config.graphql.core.relay import (
    register_type,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.research.constants import MAX_RESEARCH_PROMPT_CHARS
from opencontractserver.research.models import ResearchReport
from opencontractserver.research.services.research_reports import (
    ConcurrentResearchInProgress,
    ResearchReportService,
)
from opencontractserver.shared.services.base import BaseService

logger = logging.getLogger(__name__)


def _decode_global_pk(global_id: str) -> int | None:
    """Decode a relay global id to its integer pk, or ``None`` if malformed."""
    try:
        return int(from_global_id(global_id)[1])
    except (ValueError, TypeError, UnicodeDecodeError, IndexError):
        return None


@strawberry.type(
    name="StartResearchReport",
    description="Kick off a deep-research job over a corpus (explicit, non-chat path).",
)
class StartResearchReport:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[ResearchReportType, strawberry.lazy("config.graphql.research_types")]
    ) = strawberry.field(name="obj", default=None)


register_type("StartResearchReport", StartResearchReport, model=None)


@strawberry.type(
    name="CancelResearchReport",
    description="Request cooperative cancellation of an in-flight research job.",
)
class CancelResearchReport:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[ResearchReportType, strawberry.lazy("config.graphql.research_types")]
    ) = strawberry.field(name="obj", default=None)


register_type("CancelResearchReport", CancelResearchReport, model=None)


def _mutate_StartResearchReport(
    payload_cls,
    root,
    info,
    corpus_id,
    prompt,
    title=None,
    max_steps=None,
    corpus_group_id=None,
):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:43

    Port of StartResearchReport.mutate
    """
    # @login_required (graphql_jwt) — inlined because mutate stubs take
    # ``payload_cls`` as their first positional argument, which does not
    # match core.auth's ``(root, info, ...)`` calling convention.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    corpus_pk = _decode_global_pk(corpus_id)
    if corpus_pk is None:
        return payload_cls(
            ok=False, message="Corpus not found or not visible.", obj=None
        )
    if prompt is None or len(prompt) > MAX_RESEARCH_PROMPT_CHARS:
        return payload_cls(
            ok=False,
            message=(f"Prompt must be 1–{MAX_RESEARCH_PROMPT_CHARS} characters."),
            obj=None,
        )
    corpus = BaseService.get_or_none(
        Corpus, corpus_pk, info.context.user, request=info.context
    )
    if corpus is None:
        return payload_cls(
            ok=False, message="Corpus not found or not visible.", obj=None
        )

    # An optional group widens retrieval past the anchor corpus. Resolved and
    # permission-gated here rather than passed as an id, so a group the caller
    # cannot see is REFUSED — silently ignoring it would start a run that reads
    # only the anchor corpus and reports as though it had read the group.
    corpus_group = None
    if corpus_group_id:
        from opencontractserver.corpuses.services import CorpusGroupService

        group_pk = _decode_global_pk(corpus_group_id)
        corpus_group = (
            CorpusGroupService.get_group_by_id(
                info.context.user, group_pk, request=info.context
            )
            if group_pk is not None
            else None
        )
        if corpus_group is None:
            return payload_cls(
                ok=False, message="Corpus group not found or not visible.", obj=None
            )

    try:
        report = ResearchReportService.start(
            user=info.context.user,
            corpus=corpus,
            prompt=prompt,
            title=title,
            max_steps=max_steps,
            corpus_group=corpus_group,
            request=info.context,
        )
    except ConcurrentResearchInProgress as exc:
        return payload_cls(ok=False, message=str(exc), obj=None)
    except PermissionError as exc:
        return payload_cls(ok=False, message=str(exc), obj=None)
    except Exception:
        logger.exception("Failed to start research report")
        return payload_cls(
            ok=False, message="Failed to start research report.", obj=None
        )
    return payload_cls(ok=True, message="Started.", obj=report)


def m_start_research_report(
    info: strawberry.Info,
    corpus_id: Annotated[
        strawberry.ID, strawberry.argument(name="corpusId")
    ] = strawberry.UNSET,
    corpus_group_id: Annotated[
        strawberry.ID | None, strawberry.argument(name="corpusGroupId")
    ] = strawberry.UNSET,
    max_steps: Annotated[
        int | None, strawberry.argument(name="maxSteps")
    ] = strawberry.UNSET,
    prompt: Annotated[str, strawberry.argument(name="prompt")] = strawberry.UNSET,
    title: Annotated[str | None, strawberry.argument(name="title")] = strawberry.UNSET,
) -> StartResearchReport | None:
    kwargs = strip_unset(
        {
            "corpus_id": corpus_id,
            "corpus_group_id": corpus_group_id,
            "max_steps": max_steps,
            "prompt": prompt,
            "title": title,
        }
    )
    return _mutate_StartResearchReport(StartResearchReport, None, info, **kwargs)


def _mutate_CancelResearchReport(payload_cls, root, info, id):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:96

    Port of CancelResearchReport.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_StartResearchReport.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    pk = _decode_global_pk(id)
    if pk is None:
        return payload_cls(ok=False, message="Research report not found.", obj=None)
    report = BaseService.get_or_none(
        ResearchReport, pk, info.context.user, request=info.context
    )
    if report is None:
        return payload_cls(ok=False, message="Research report not found.", obj=None)
    try:
        ResearchReportService.request_cancel(info.context.user, report)
    except PermissionError as exc:
        return payload_cls(ok=False, message=str(exc), obj=report)
    return payload_cls(ok=True, message="Cancel requested.", obj=report)


def m_cancel_research_report(
    info: strawberry.Info,
    id: Annotated[strawberry.ID, strawberry.argument(name="id")] = strawberry.UNSET,
) -> CancelResearchReport | None:
    kwargs = strip_unset({"id": id})
    return _mutate_CancelResearchReport(CancelResearchReport, None, info, **kwargs)


MUTATION_FIELDS = {
    "start_research_report": strawberry.field(
        resolver=m_start_research_report,
        name="startResearchReport",
        description="Kick off a deep-research job over a corpus (explicit, non-chat path).",
    ),
    "cancel_research_report": strawberry.field(
        resolver=m_cancel_research_report,
        name="cancelResearchReport",
        description="Request cooperative cancellation of an in-flight research job.",
    ),
}
