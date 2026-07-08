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


def _mutate_StartResearchReport(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:43

    Port of StartResearchReport.mutate
    """
    raise NotImplementedError("_mutate_StartResearchReport not yet ported — see manifest")


def m_start_research_report(info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId")] = strawberry.UNSET, max_steps: Annotated[Optional[int], strawberry.argument(name="maxSteps")] = strawberry.UNSET, prompt: Annotated[str, strawberry.argument(name="prompt")] = strawberry.UNSET, title: Annotated[Optional[str], strawberry.argument(name="title")] = strawberry.UNSET) -> Optional["StartResearchReport"]:
    kwargs = strip_unset({"corpus_id": corpus_id, "max_steps": max_steps, "prompt": prompt, "title": title})
    return _mutate_StartResearchReport(StartResearchReport, None, info, **kwargs)


def _mutate_CancelResearchReport(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:96

    Port of CancelResearchReport.mutate
    """
    raise NotImplementedError("_mutate_CancelResearchReport not yet ported — see manifest")


def m_cancel_research_report(info: strawberry.Info, id: Annotated[strawberry.ID, strawberry.argument(name="id")] = strawberry.UNSET) -> Optional["CancelResearchReport"]:
    kwargs = strip_unset({"id": id})
    return _mutate_CancelResearchReport(CancelResearchReport, None, info, **kwargs)



MUTATION_FIELDS = {
    "start_research_report": strawberry.field(resolver=m_start_research_report, name="startResearchReport", description='Kick off a deep-research job over a corpus (explicit, non-chat path).'),
    "cancel_research_report": strawberry.field(resolver=m_cancel_research_report, name="cancelResearchReport", description='Request cooperative cancellation of an in-flight research job.'),
}
