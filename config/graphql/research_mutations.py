"""Generated strawberry GraphQL module (graphene migration).

Shape-generated from the graphene schema; stub functions marked PORT(...)
carry the ported business logic. See config/graphql_new/manifest.json.
"""
from __future__ import annotations

import datetime
import decimal
import uuid
from typing import Annotated, Any, Optional

import strawberry

from config.graphql.core import permissions as core_permissions
from config.graphql.core.filtering import filterset_factory, setup_filterset
from config.graphql.core.mutations import drf_deletion, drf_mutation
from config.graphql.core.relay import (
    Node,
    get_node_from_global_id,
    make_connection_types,
    register_type,
    resolve_django_connection,
    resolve_django_list,
)
from config.graphql.core.scalars import BigInt, GenericScalar, JSONString
from config.graphql._util import coerce_enum, coerce_str, strip_unset
from config.graphql import enums

import logging

from graphql_relay import from_global_id

from config.graphql.core.auth import PermissionDenied
from opencontractserver.corpuses.models import Corpus
from opencontractserver.research.constants import MAX_RESEARCH_PROMPT_CHARS
from opencontractserver.research.models import ResearchReport
from opencontractserver.research.services.research_reports import (
    ConcurrentResearchInProgress,
    ResearchReportService,
)
from opencontractserver.shared.services.base import BaseService

logger = logging.getLogger(__name__)


def _decode_global_pk(global_id: str) -> "int | None":
    """Decode a relay global id to its integer pk, or ``None`` if malformed."""
    try:
        return int(from_global_id(global_id)[1])
    except (ValueError, TypeError, UnicodeDecodeError, IndexError):
        return None


@strawberry.type(name="StartResearchReport", description='Kick off a deep-research job over a corpus (explicit, non-chat path).')
class StartResearchReport:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    message: Optional[str] = strawberry.field(name="message", default=None)
    obj: Optional[Annotated["ResearchReportType", strawberry.lazy("config.graphql.research_types")]] = strawberry.field(name="obj", default=None)


register_type("StartResearchReport", StartResearchReport, model=None)


@strawberry.type(name="CancelResearchReport", description='Request cooperative cancellation of an in-flight research job.')
class CancelResearchReport:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    message: Optional[str] = strawberry.field(name="message", default=None)
    obj: Optional[Annotated["ResearchReportType", strawberry.lazy("config.graphql.research_types")]] = strawberry.field(name="obj", default=None)


register_type("CancelResearchReport", CancelResearchReport, model=None)


def _mutate_StartResearchReport(
    payload_cls, root, info, corpus_id, prompt, title=None, max_steps=None
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
    try:
        report = ResearchReportService.start(
            user=info.context.user,
            corpus=corpus,
            prompt=prompt,
            title=title,
            max_steps=max_steps,
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


def m_start_research_report(info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId")] = strawberry.UNSET, max_steps: Annotated[Optional[int], strawberry.argument(name="maxSteps")] = strawberry.UNSET, prompt: Annotated[str, strawberry.argument(name="prompt")] = strawberry.UNSET, title: Annotated[Optional[str], strawberry.argument(name="title")] = strawberry.UNSET) -> Optional["StartResearchReport"]:
    kwargs = strip_unset({"corpus_id": corpus_id, "max_steps": max_steps, "prompt": prompt, "title": title})
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
        return payload_cls(
            ok=False, message="Research report not found.", obj=None
        )
    report = BaseService.get_or_none(
        ResearchReport, pk, info.context.user, request=info.context
    )
    if report is None:
        return payload_cls(
            ok=False, message="Research report not found.", obj=None
        )
    try:
        ResearchReportService.request_cancel(info.context.user, report)
    except PermissionError as exc:
        return payload_cls(ok=False, message=str(exc), obj=report)
    return payload_cls(ok=True, message="Cancel requested.", obj=report)


def m_cancel_research_report(info: strawberry.Info, id: Annotated[strawberry.ID, strawberry.argument(name="id")] = strawberry.UNSET) -> Optional["CancelResearchReport"]:
    kwargs = strip_unset({"id": id})
    return _mutate_CancelResearchReport(CancelResearchReport, None, info, **kwargs)



MUTATION_FIELDS = {
    "start_research_report": strawberry.field(resolver=m_start_research_report, name="startResearchReport", description='Kick off a deep-research job over a corpus (explicit, non-chat path).'),
    "cancel_research_report": strawberry.field(resolver=m_cancel_research_report, name="cancelResearchReport", description='Request cooperative cancellation of an in-flight research job.'),
}
