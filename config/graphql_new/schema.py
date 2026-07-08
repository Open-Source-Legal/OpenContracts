"""Strawberry schema composition (generated)."""
import strawberry

from config.graphql_new import action_queries as _action_queries
from config.graphql_new import agent_mutations as _agent_mutations
from config.graphql_new import agent_types as _agent_types
from config.graphql_new import analysis_mutations as _analysis_mutations
from config.graphql_new import annotation_mutations as _annotation_mutations
from config.graphql_new import annotation_queries as _annotation_queries
from config.graphql_new import annotation_types as _annotation_types
from config.graphql_new import authority_frontier_mutations as _authority_frontier_mutations
from config.graphql_new import authority_mapping_mutations as _authority_mapping_mutations
from config.graphql_new import authority_namespace_mutations as _authority_namespace_mutations
from config.graphql_new import badge_mutations as _badge_mutations
from config.graphql_new import base_types as _base_types
from config.graphql_new import conversation_mutations as _conversation_mutations
from config.graphql_new import conversation_queries as _conversation_queries
from config.graphql_new import conversation_types as _conversation_types
from config.graphql_new import corpus_category_mutations as _corpus_category_mutations
from config.graphql_new import corpus_folder_mutations as _corpus_folder_mutations
from config.graphql_new import corpus_mutations as _corpus_mutations
from config.graphql_new import corpus_queries as _corpus_queries
from config.graphql_new import corpus_types as _corpus_types
from config.graphql_new import discover_queries as _discover_queries
from config.graphql_new import document_mutations as _document_mutations
from config.graphql_new import document_queries as _document_queries
from config.graphql_new import document_relationship_mutations as _document_relationship_mutations
from config.graphql_new import document_types as _document_types
from config.graphql_new import enrichment_mutations as _enrichment_mutations
from config.graphql_new import extract_mutations as _extract_mutations
from config.graphql_new import extract_queries as _extract_queries
from config.graphql_new import extract_types as _extract_types
from config.graphql_new import ingestion_admin_queries as _ingestion_admin_queries
from config.graphql_new import ingestion_admin_types as _ingestion_admin_types
from config.graphql_new import ingestion_source_mutations as _ingestion_source_mutations
from config.graphql_new import jwt_auth as _jwt_auth
from config.graphql_new import label_mutations as _label_mutations
from config.graphql_new import moderation_mutations as _moderation_mutations
from config.graphql_new import notification_mutations as _notification_mutations
from config.graphql_new import og_metadata_queries as _og_metadata_queries
from config.graphql_new import og_metadata_types as _og_metadata_types
from config.graphql_new import pipeline_queries as _pipeline_queries
from config.graphql_new import pipeline_settings_mutations as _pipeline_settings_mutations
from config.graphql_new import pipeline_types as _pipeline_types
from config.graphql_new import research_mutations as _research_mutations
from config.graphql_new import research_queries as _research_queries
from config.graphql_new import research_types as _research_types
from config.graphql_new import search_queries as _search_queries
from config.graphql_new import slug_queries as _slug_queries
from config.graphql_new import smart_label_mutations as _smart_label_mutations
from config.graphql_new import social_queries as _social_queries
from config.graphql_new import social_types as _social_types
from config.graphql_new import stats_queries as _stats_queries
from config.graphql_new import user_mutations as _user_mutations
from config.graphql_new import user_queries as _user_queries
from config.graphql_new import user_types as _user_types
from config.graphql_new import voting_mutations as _voting_mutations
from config.graphql_new import worker_mutations as _worker_mutations
from config.graphql_new import worker_queries as _worker_queries
from config.graphql_new import worker_types as _worker_types

_query_ns = {}
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
_mutation_ns = {}
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
_extra_types = []
_extra_types += [v for v in vars(_agent_mutations).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_agent_types).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_analysis_mutations).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_annotation_mutations).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_annotation_queries).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_annotation_types).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_authority_frontier_mutations).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_authority_mapping_mutations).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_authority_namespace_mutations).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_badge_mutations).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_base_types).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_conversation_mutations).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_conversation_types).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_corpus_category_mutations).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_corpus_folder_mutations).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_corpus_mutations).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_corpus_types).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_document_mutations).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_document_relationship_mutations).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_document_types).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_enrichment_mutations).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_extract_mutations).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_extract_queries).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_extract_types).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_ingestion_admin_types).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_ingestion_source_mutations).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_jwt_auth).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_label_mutations).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_moderation_mutations).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_notification_mutations).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_og_metadata_types).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_pipeline_settings_mutations).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_pipeline_types).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_research_mutations).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_research_types).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_smart_label_mutations).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_social_types).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_stats_queries).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_user_mutations).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_user_types).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_voting_mutations).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_worker_mutations).values() if hasattr(v, '__strawberry_definition__')]
_extra_types += [v for v in vars(_worker_types).values() if hasattr(v, '__strawberry_definition__')]
schema = strawberry.Schema(query=Query, mutation=Mutation, types=_extra_types)
