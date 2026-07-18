"""Strawberry GraphQL schema composition.

Aggregates the per-module ``QUERY_FIELDS`` / ``MUTATION_FIELDS`` namespaces
into the root ``Query`` / ``Mutation`` types and builds the strawberry
schema with the security validation rules (depth limiting always;
introspection disabled outside DEBUG).

Unlike graphene's ``validate(schema, document, rules)`` — which REPLACED
the spec rule set when custom rules were passed (see the old schema.py
comment / test_security_hardening) — strawberry's ``AddValidationRules``
extension APPENDS to graphql-core's full spec rule set, so every standard
validation stays active on the served endpoint. ``validation_rules`` keeps
the full effective list exported for tests/tooling.
"""

from typing import Any

import strawberry
from django.conf import settings
from graphql.validation import specified_rules
from strawberry.extensions import AddValidationRules

from config.graphql import action_queries as _action_queries
from config.graphql import agent_mutations as _agent_mutations
from config.graphql import agent_types as _agent_types
from config.graphql import analysis_mutations as _analysis_mutations
from config.graphql import annotation_mutations as _annotation_mutations
from config.graphql import annotation_queries as _annotation_queries
from config.graphql import annotation_types as _annotation_types
from config.graphql import authority_frontier_mutations as _authority_frontier_mutations
from config.graphql import authority_mapping_mutations as _authority_mapping_mutations
from config.graphql import (
    authority_namespace_mutations as _authority_namespace_mutations,
)
from config.graphql import badge_mutations as _badge_mutations
from config.graphql import base_types as _base_types
from config.graphql import conversation_mutations as _conversation_mutations
from config.graphql import conversation_queries as _conversation_queries
from config.graphql import conversation_types as _conversation_types
from config.graphql import corpus_category_mutations as _corpus_category_mutations
from config.graphql import corpus_folder_mutations as _corpus_folder_mutations
from config.graphql import corpus_group_mutations as _corpus_group_mutations
from config.graphql import corpus_mutations as _corpus_mutations
from config.graphql import corpus_queries as _corpus_queries
from config.graphql import corpus_types as _corpus_types
from config.graphql import discover_queries as _discover_queries
from config.graphql import document_mutations as _document_mutations
from config.graphql import document_queries as _document_queries
from config.graphql import (
    document_relationship_mutations as _document_relationship_mutations,
)
from config.graphql import document_types as _document_types
from config.graphql import enrichment_mutations as _enrichment_mutations
from config.graphql import extract_mutations as _extract_mutations
from config.graphql import extract_queries as _extract_queries
from config.graphql import extract_types as _extract_types
from config.graphql import ingestion_admin_queries as _ingestion_admin_queries
from config.graphql import ingestion_admin_types as _ingestion_admin_types
from config.graphql import ingestion_source_mutations as _ingestion_source_mutations
from config.graphql import jwt_auth as _jwt_auth
from config.graphql import label_mutations as _label_mutations
from config.graphql import moderation_mutations as _moderation_mutations
from config.graphql import notification_mutations as _notification_mutations
from config.graphql import og_metadata_queries as _og_metadata_queries
from config.graphql import og_metadata_types as _og_metadata_types
from config.graphql import pipeline_queries as _pipeline_queries
from config.graphql import pipeline_settings_mutations as _pipeline_settings_mutations
from config.graphql import pipeline_types as _pipeline_types
from config.graphql import research_mutations as _research_mutations
from config.graphql import research_queries as _research_queries
from config.graphql import research_types as _research_types
from config.graphql import search_queries as _search_queries
from config.graphql import slug_queries as _slug_queries
from config.graphql import smart_label_mutations as _smart_label_mutations
from config.graphql import social_queries as _social_queries
from config.graphql import social_types as _social_types
from config.graphql import stats_queries as _stats_queries
from config.graphql import user_mutations as _user_mutations
from config.graphql import user_queries as _user_queries
from config.graphql import user_types as _user_types
from config.graphql import voting_mutations as _voting_mutations
from config.graphql import worker_mutations as _worker_mutations
from config.graphql import worker_queries as _worker_queries
from config.graphql import worker_types as _worker_types
from config.graphql.security import DepthLimitValidationRule, DisableIntrospection

_query_ns: dict[str, Any] = {}
_query_ns.update(_action_queries.QUERY_FIELDS)
_query_ns.update(_annotation_queries.QUERY_FIELDS)
_query_ns.update(_annotation_types.QUERY_FIELDS)
_query_ns.update(_conversation_queries.QUERY_FIELDS)
_query_ns.update(_conversation_types.QUERY_FIELDS)
_query_ns.update(_corpus_queries.QUERY_FIELDS)
_query_ns.update(_corpus_types.QUERY_FIELDS)
_query_ns.update(_discover_queries.QUERY_FIELDS)
_query_ns.update(_document_queries.QUERY_FIELDS)
_query_ns.update(_extract_queries.QUERY_FIELDS)
_query_ns.update(_ingestion_admin_queries.QUERY_FIELDS)
_query_ns.update(_og_metadata_queries.QUERY_FIELDS)
_query_ns.update(_pipeline_queries.QUERY_FIELDS)
_query_ns.update(_research_queries.QUERY_FIELDS)
_query_ns.update(_search_queries.QUERY_FIELDS)
_query_ns.update(_slug_queries.QUERY_FIELDS)
_query_ns.update(_social_queries.QUERY_FIELDS)
_query_ns.update(_stats_queries.QUERY_FIELDS)
_query_ns.update(_user_queries.QUERY_FIELDS)
_query_ns.update(_worker_queries.QUERY_FIELDS)
_mutation_ns: dict[str, Any] = {}
_mutation_ns.update(_agent_mutations.MUTATION_FIELDS)
_mutation_ns.update(_analysis_mutations.MUTATION_FIELDS)
_mutation_ns.update(_annotation_mutations.MUTATION_FIELDS)
_mutation_ns.update(_authority_frontier_mutations.MUTATION_FIELDS)
_mutation_ns.update(_authority_mapping_mutations.MUTATION_FIELDS)
_mutation_ns.update(_authority_namespace_mutations.MUTATION_FIELDS)
_mutation_ns.update(_badge_mutations.MUTATION_FIELDS)
_mutation_ns.update(_conversation_mutations.MUTATION_FIELDS)
_mutation_ns.update(_corpus_category_mutations.MUTATION_FIELDS)
_mutation_ns.update(_corpus_folder_mutations.MUTATION_FIELDS)
_mutation_ns.update(_corpus_group_mutations.MUTATION_FIELDS)
_mutation_ns.update(_corpus_mutations.MUTATION_FIELDS)
_mutation_ns.update(_document_mutations.MUTATION_FIELDS)
_mutation_ns.update(_document_relationship_mutations.MUTATION_FIELDS)
_mutation_ns.update(_enrichment_mutations.MUTATION_FIELDS)
_mutation_ns.update(_extract_mutations.MUTATION_FIELDS)
_mutation_ns.update(_ingestion_source_mutations.MUTATION_FIELDS)
_mutation_ns.update(_jwt_auth.MUTATION_FIELDS)
_mutation_ns.update(_label_mutations.MUTATION_FIELDS)
_mutation_ns.update(_moderation_mutations.MUTATION_FIELDS)
_mutation_ns.update(_notification_mutations.MUTATION_FIELDS)
_mutation_ns.update(_pipeline_settings_mutations.MUTATION_FIELDS)
_mutation_ns.update(_research_mutations.MUTATION_FIELDS)
_mutation_ns.update(_smart_label_mutations.MUTATION_FIELDS)
_mutation_ns.update(_user_mutations.MUTATION_FIELDS)
_mutation_ns.update(_voting_mutations.MUTATION_FIELDS)
_mutation_ns.update(_worker_mutations.MUTATION_FIELDS)
Query = strawberry.type(type("Query", (), dict(_query_ns)), name="Query")
Mutation = strawberry.type(type("Mutation", (), dict(_mutation_ns)), name="Mutation")
# Every strawberry-defined type (query/mutation field return types, input
# types, etc.) declared in each ported module must be registered on the
# schema's ``types=`` so it's reachable even when no query/mutation field
# references it directly (e.g. a type only reached via a union/interface).
# One shared loop over the module list — not one hand-copied comprehension
# per module — so adding a module can't accidentally skip this step.
_extra_type_modules = [
    _agent_mutations,
    _agent_types,
    _analysis_mutations,
    _annotation_mutations,
    _annotation_queries,
    _annotation_types,
    _authority_frontier_mutations,
    _authority_mapping_mutations,
    _authority_namespace_mutations,
    _badge_mutations,
    _base_types,
    _conversation_mutations,
    _conversation_types,
    _corpus_category_mutations,
    _corpus_folder_mutations,
    _corpus_group_mutations,
    _corpus_mutations,
    _corpus_types,
    _document_mutations,
    _document_relationship_mutations,
    _document_types,
    _enrichment_mutations,
    _extract_mutations,
    _extract_queries,
    _extract_types,
    _ingestion_admin_types,
    _ingestion_source_mutations,
    _jwt_auth,
    _label_mutations,
    _moderation_mutations,
    _notification_mutations,
    _og_metadata_types,
    _pipeline_settings_mutations,
    _pipeline_types,
    _research_mutations,
    _research_types,
    _smart_label_mutations,
    _social_types,
    _stats_queries,
    _user_mutations,
    _user_types,
    _voting_mutations,
    _worker_mutations,
    _worker_types,
]
_extra_types: list[Any] = [
    v
    for _module in _extra_type_modules
    for v in vars(_module).values()
    if hasattr(v, "__strawberry_definition__")
]
_custom_rules: list = [DepthLimitValidationRule]
if not settings.DEBUG:
    _custom_rules.append(DisableIntrospection)

_extensions: list = [AddValidationRules(_custom_rules)]
if getattr(settings, "FILE_URL_SHARED_CACHE_TTL", 0):
    from config.graphql.file_url_prewarm import FileUrlPrewarmExtension

    _extensions.append(FileUrlPrewarmExtension)

# Full effective rule set served on the endpoint (spec rules + hardening).
validation_rules: list = [*specified_rules, *_custom_rules]

schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    types=_extra_types,
    extensions=_extensions,
)

# Backwards-compatibility accessor: graphene's ``Schema`` exposed the
# underlying graphql-core schema as ``.graphql_schema``. A few call sites
# (frontend-document validation in ``scripts/validate_frontend_graphql.py``
# and ``test_security_hardening``/``test_authority_mapping_loader``) reach
# for it directly. Strawberry stores it on the private ``_schema``; alias it
# so those references keep working across the migration without a rename.
schema.graphql_schema = schema._schema  # type: ignore[attr-defined]
