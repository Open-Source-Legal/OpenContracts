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

from opencontractserver.agents.models import AgentActionResult
from opencontractserver.corpuses.models import CorpusAction
from opencontractserver.corpuses.models import CorpusActionExecution
from opencontractserver.corpuses.models import CorpusActionTemplate


def _resolve_Query_corpus_action_templates(root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:37

    Port of ActionQueryMixin.resolve_corpus_action_templates
    """
    raise NotImplementedError("_resolve_Query_corpus_action_templates not yet ported — see manifest")


def q_corpus_action_templates(info: strawberry.Info, is_active: Annotated[Optional[bool], strawberry.argument(name="isActive")] = strawberry.UNSET, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Optional[Annotated["CorpusActionTemplateTypeConnection", strawberry.lazy("config.graphql.agent_types")]]:
    kwargs = strip_unset({"is_active": is_active, "offset": offset, "before": before, "after": after, "first": first, "last": last})
    resolved = _resolve_Query_corpus_action_templates(None, info, **kwargs)
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="CorpusActionTemplateType", default_manager=CorpusActionTemplate._default_manager, )


def _resolve_Query_corpus_actions(root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:62

    Port of ActionQueryMixin.resolve_corpus_actions
    """
    raise NotImplementedError("_resolve_Query_corpus_actions not yet ported — see manifest")


def q_corpus_actions(info: strawberry.Info, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId")] = strawberry.UNSET, trigger: Annotated[Optional[str], strawberry.argument(name="trigger")] = strawberry.UNSET, disabled: Annotated[Optional[bool], strawberry.argument(name="disabled")] = strawberry.UNSET, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Optional[Annotated["CorpusActionTypeConnection", strawberry.lazy("config.graphql.agent_types")]]:
    kwargs = strip_unset({"corpus_id": corpus_id, "trigger": trigger, "disabled": disabled, "offset": offset, "before": before, "after": after, "first": first, "last": last})
    resolved = _resolve_Query_corpus_actions(None, info, **kwargs)
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="CorpusActionType", default_manager=CorpusAction._default_manager, )


def _resolve_Query_agent_action_results(root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:97

    Port of ActionQueryMixin.resolve_agent_action_results
    """
    raise NotImplementedError("_resolve_Query_agent_action_results not yet ported — see manifest")


def q_agent_action_results(info: strawberry.Info, corpus_action_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusActionId")] = strawberry.UNSET, document_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="documentId")] = strawberry.UNSET, status: Annotated[Optional[str], strawberry.argument(name="status")] = strawberry.UNSET, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Optional[Annotated["AgentActionResultTypeConnection", strawberry.lazy("config.graphql.agent_types")]]:
    kwargs = strip_unset({"corpus_action_id": corpus_action_id, "document_id": document_id, "status": status, "offset": offset, "before": before, "after": after, "first": first, "last": last})
    resolved = _resolve_Query_agent_action_results(None, info, **kwargs)
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="AgentActionResultType", default_manager=AgentActionResult._default_manager, )


def _resolve_Query_corpus_action_executions(root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:134

    Port of ActionQueryMixin.resolve_corpus_action_executions
    """
    raise NotImplementedError("_resolve_Query_corpus_action_executions not yet ported — see manifest")


def q_corpus_action_executions(info: strawberry.Info, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId")] = strawberry.UNSET, document_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="documentId")] = strawberry.UNSET, corpus_action_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusActionId")] = strawberry.UNSET, status: Annotated[Optional[str], strawberry.argument(name="status")] = strawberry.UNSET, action_type: Annotated[Optional[str], strawberry.argument(name="actionType")] = strawberry.UNSET, since: Annotated[Optional[datetime.datetime], strawberry.argument(name="since")] = strawberry.UNSET, offset: Annotated[Optional[int], strawberry.argument(name="offset")] = strawberry.UNSET, before: Annotated[Optional[str], strawberry.argument(name="before")] = strawberry.UNSET, after: Annotated[Optional[str], strawberry.argument(name="after")] = strawberry.UNSET, first: Annotated[Optional[int], strawberry.argument(name="first")] = strawberry.UNSET, last: Annotated[Optional[int], strawberry.argument(name="last")] = strawberry.UNSET) -> Optional[Annotated["CorpusActionExecutionTypeConnection", strawberry.lazy("config.graphql.agent_types")]]:
    kwargs = strip_unset({"corpus_id": corpus_id, "document_id": document_id, "corpus_action_id": corpus_action_id, "status": status, "action_type": action_type, "since": since, "offset": offset, "before": before, "after": after, "first": first, "last": last})
    resolved = _resolve_Query_corpus_action_executions(None, info, **kwargs)
    return resolve_django_connection(resolved=resolved, info=info, args=kwargs, node_type_name="CorpusActionExecutionType", default_manager=CorpusActionExecution._default_manager, )


def _resolve_Query_corpus_action_trail_stats(root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:218

    Port of ActionQueryMixin.resolve_corpus_action_trail_stats
    """
    raise NotImplementedError("_resolve_Query_corpus_action_trail_stats not yet ported — see manifest")


def q_corpus_action_trail_stats(info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId")] = strawberry.UNSET, since: Annotated[Optional[datetime.datetime], strawberry.argument(name="since")] = strawberry.UNSET) -> Optional[Annotated["CorpusActionTrailStatsType", strawberry.lazy("config.graphql.agent_types")]]:
    kwargs = strip_unset({"corpus_id": corpus_id, "since": since})
    return _resolve_Query_corpus_action_trail_stats(None, info, **kwargs)


def _resolve_Query_document_corpus_actions(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/action_queries.py:296

    Port of ActionQueryMixin.resolve_document_corpus_actions
    """
    raise NotImplementedError("_resolve_Query_document_corpus_actions not yet ported — see manifest")


def q_document_corpus_actions(info: strawberry.Info, document_id: Annotated[strawberry.ID, strawberry.argument(name="documentId")] = strawberry.UNSET, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId")] = strawberry.UNSET) -> Optional[Annotated["DocumentCorpusActionsType", strawberry.lazy("config.graphql.document_types")]]:
    kwargs = strip_unset({"document_id": document_id, "corpus_id": corpus_id})
    return _resolve_Query_document_corpus_actions(None, info, **kwargs)



QUERY_FIELDS = {
    "corpus_action_templates": strawberry.field(resolver=q_corpus_action_templates, name="corpusActionTemplates"),
    "corpus_actions": strawberry.field(resolver=q_corpus_actions, name="corpusActions"),
    "agent_action_results": strawberry.field(resolver=q_agent_action_results, name="agentActionResults"),
    "corpus_action_executions": strawberry.field(resolver=q_corpus_action_executions, name="corpusActionExecutions"),
    "corpus_action_trail_stats": strawberry.field(resolver=q_corpus_action_trail_stats, name="corpusActionTrailStats"),
    "document_corpus_actions": strawberry.field(resolver=q_document_corpus_actions, name="documentCorpusActions"),
}
