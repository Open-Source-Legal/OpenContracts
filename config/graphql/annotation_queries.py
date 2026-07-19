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
import re
from typing import Annotated

import strawberry
from django.db.models import Q
from graphql import GraphQLError
from graphql_relay import from_global_id, to_global_id

from config.graphql import enums
from config.graphql._util import strip_unset
from config.graphql.annotation_types import (
    AuthorityDetailType,
    AuthorityFrontierStateCountType,
    AuthorityFrontierStatsType,
    AuthorityMappingSourceCountType,
    AuthorityMappingStatsType,
    AuthorityNamespaceFacetCountType,
    AuthorityNamespaceStatsType,
    AuthorityReferenceStatusCountType,
    AuthoritySourceProviderType,
    GovernanceGraphCorpusType,
    GovernanceGraphEdgeType,
    GovernanceGraphNodeType,
    GovernanceGraphType,
    WantedAuthorityKeyType,
    WantedAuthorityType,
)
from config.graphql.base_types import PageAwareAnnotationType, PdfPageInfoType
from config.graphql.core.auth import login_required
from config.graphql.core.filtering import setup_filterset
from config.graphql.core.relay import (
    get_node_from_global_id,
    register_type,
    resolve_django_connection,
)
from config.graphql.filters import LabelFilter, LabelsetFilter, RelationshipFilter
from config.graphql.ratelimits import get_user_tier_rate, graphql_ratelimit_dynamic
from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
    CorpusReference,
    LabelSet,
    Note,
    Relationship,
)
from opencontractserver.constants.annotations import (
    DOCUMENT_ANNOTATION_INDEX_LIMIT,
    MANUAL_ANNOTATION_SENTINEL,
)
from opencontractserver.constants.stats import GOVERNANCE_GRAPH_MAX_NODES
from opencontractserver.documents.models import Document
from opencontractserver.enrichment import constants as enrichment_constants
from opencontractserver.shared.services.base import BaseService

logger = logging.getLogger(__name__)


@strawberry.input(
    name="BBoxInputType",
    description="Map bounding-box input shared by both geographic queries.\n\nFields use standard map conventions: ``south <= north`` (degenerate\n``south > north`` boxes are rejected with a ``GraphQLError``); ``west``\nmay exceed ``east`` for boxes that cross the antimeridian (180°/-180°\nlongitude seam) and the resolver handles the wrap-around explicitly.",
)
class BBoxInputType:
    south: float = strawberry.field(name="south")
    west: float = strawberry.field(name="west")
    north: float = strawberry.field(name="north")
    east: float = strawberry.field(name="east")


def _resolve_GeographicAnnotationPinType_sample_document_ids(root, info):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_queries.py:1302

    Port of GeographicAnnotationPinType.resolve_sample_document_ids

    Wrap raw integer PKs as Relay global IDs.

    The service layer carries integer PKs for cheap lookup; the GraphQL
    contract is ``[ID]`` so we encode here. Done in the resolver
    rather than the service so the service stays decoupled from the
    Relay encoding scheme.
    """
    from graphql_relay import to_global_id

    return [to_global_id("DocumentType", pk) for pk in root.sample_document_ids]


@strawberry.type(
    name="GeographicAnnotationPinType",
    description='A single aggregated geographic pin returned to the map UI.\n\nMirrors :class:`GeographicPin` from the service layer one-to-one — the\nresolver projects the dataclass directly into this type via field\nresolvers below. ``label_type`` is a literal string ("country" /\n"state" / "city") rather than an enum so a future label-type expansion\ndoesn\'t break the schema.',
)
class GeographicAnnotationPinType:
    canonical_name: str = strawberry.field(name="canonicalName", default=None)
    label_type: str = strawberry.field(name="labelType", default=None)
    lat: float = strawberry.field(name="lat", default=None)
    lng: float = strawberry.field(name="lng", default=None)
    document_count: int = strawberry.field(name="documentCount", default=None)

    @strawberry.field(name="sampleDocumentIds")
    def sample_document_ids(
        self, info: strawberry.Info
    ) -> list[strawberry.ID | None] | None:
        kwargs = strip_unset({})
        return _resolve_GeographicAnnotationPinType_sample_document_ids(
            self, info, **kwargs
        )


register_type("GeographicAnnotationPinType", GeographicAnnotationPinType, model=None)


def _resolve_Query_corpus_references(root, info, corpus_id, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_queries.py:88

    Port of AnnotationQueryMixin.resolve_corpus_references

    List enrichment cross-references for a corpus the user can read.

    Visibility is enforced by ``CorpusReferenceService`` (corpus-derived);
    no inline Tier-0 permission fusion here.
    """
    from opencontractserver.annotations.models import CorpusReference
    from opencontractserver.documents.models import Document
    from opencontractserver.enrichment.services import CorpusReferenceService
    from opencontractserver.shared.services.base import BaseService

    pk_str = from_global_id(corpus_id)[1]
    if not str(pk_str).isdigit():
        return CorpusReference.objects.none()
    pk = int(pk_str)
    qs = CorpusReferenceService.for_corpus(info.context.user, pk)
    if kwargs.get("reference_type"):
        qs = qs.filter(reference_type=kwargs["reference_type"])
    if kwargs.get("canonical_key"):
        qs = qs.filter(canonical_key=kwargs["canonical_key"])
    if kwargs.get("document_id"):
        doc_pk_str = from_global_id(kwargs["document_id"])[1]
        if not str(doc_pk_str).isdigit():
            return CorpusReference.objects.none()
        doc_pk = int(doc_pk_str)
        # IDOR: validate the document is READ-visible to the caller before
        # filtering by it. Without this a corpus reader could probe whether
        # an arbitrary (possibly invisible) document has references in this
        # corpus. An invisible document yields the same empty result as one
        # with no references.
        if (
            not BaseService.filter_visible(
                Document, info.context.user, request=info.context
            )
            .filter(id=doc_pk)
            .exists()
        ):
            return CorpusReference.objects.none()
        qs = qs.filter(
            Q(source_annotation__document_id=doc_pk) | Q(target_document_id=doc_pk)
        )
    # Pull the FK targets the type resolves in one pass — without this each
    # CorpusReferenceType row fires a separate query per FK (N+1).
    return qs.select_related(
        "source_annotation",
        "corpus",
        "target_document",
        "target_annotation",
        "target_corpus",
    )


def q_corpus_references(
    info: strawberry.Info,
    corpus_id: Annotated[
        strawberry.ID, strawberry.argument(name="corpusId")
    ] = strawberry.UNSET,
    reference_type: Annotated[
        str | None, strawberry.argument(name="referenceType")
    ] = strawberry.UNSET,
    canonical_key: Annotated[
        str | None, strawberry.argument(name="canonicalKey")
    ] = strawberry.UNSET,
    document_id: Annotated[
        strawberry.ID | None,
        strawberry.argument(
            name="documentId",
            description="Restrict to references touching this document on EITHER side (source mention's document or resolved target document) — the single-fetch shape the document References panel needs.",
        ),
    ] = strawberry.UNSET,
    offset: Annotated[
        int | None, strawberry.argument(name="offset")
    ] = strawberry.UNSET,
    before: Annotated[
        str | None, strawberry.argument(name="before")
    ] = strawberry.UNSET,
    after: Annotated[str | None, strawberry.argument(name="after")] = strawberry.UNSET,
    first: Annotated[int | None, strawberry.argument(name="first")] = strawberry.UNSET,
    last: Annotated[int | None, strawberry.argument(name="last")] = strawberry.UNSET,
) -> None | (
    Annotated[
        CorpusReferenceTypeConnection,
        strawberry.lazy("config.graphql.annotation_types"),
    ]
):
    kwargs = strip_unset(
        {
            "corpus_id": corpus_id,
            "reference_type": reference_type,
            "canonical_key": canonical_key,
            "document_id": document_id,
            "offset": offset,
            "before": before,
            "after": after,
            "first": first,
            "last": last,
        }
    )
    resolved = _resolve_Query_corpus_references(None, info, **kwargs)
    return resolve_django_connection(
        resolved=resolved,
        info=info,
        args=kwargs,
        node_type_name="CorpusReferenceType",
        default_manager=CorpusReference._default_manager,
    )


@graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_MEDIUM"))
def _resolve_Query_governance_graph(root, info, corpus_id, limit=None):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_queries.py:152

    Port of AnnotationQueryMixin.resolve_governance_graph

    Build the governance graph through ``GovernanceGraphService``.

    All visibility decisions (corpus READ gate, per-document READ checks,
    ghost degradation for invisible targets) live in the service; this
    resolver only translates raw PKs / canonical keys into relay ids.
    """
    # Function-local service import (services import GraphQL types
    # transitively — module-level import would cycle).
    from opencontractserver.enrichment.services import GovernanceGraphService

    empty = GovernanceGraphType(
        corpora=[],
        nodes=[],
        edges=[],
        document_count=0,
        external_key_count=0,
        edge_count=0,
        mention_count=0,
        truncated=False,
    )

    corpus_pk = from_global_id(corpus_id)[1]
    # Malformed/empty global ids decode to a non-numeric pk; treat as
    # not-found (empty graph) rather than erroring.
    if not str(corpus_pk).isdigit():
        return empty

    node_cap = GOVERNANCE_GRAPH_MAX_NODES
    if limit is not None and 0 < limit < node_cap:
        node_cap = limit

    data = GovernanceGraphService.build(
        info.context.user, int(corpus_pk), node_cap, request=info.context
    )
    if data is None:
        return empty

    def _node_id(endpoint) -> str:
        kind, val = endpoint
        if kind == "doc":
            return to_global_id("DocumentType", val)
        return f"key:{val}"

    nodes = [
        GovernanceGraphNodeType(
            id=to_global_id("DocumentType", n["doc_pk"]),
            document_id=to_global_id("DocumentType", n["doc_pk"]),
            title=n["title"],
            kind=n["kind"],
            corpus_id=(
                to_global_id("CorpusType", n["corpus_pk"]) if n["corpus_pk"] else None
            ),
            authority=n["authority"],
            jurisdiction=n.get("jurisdiction"),
            authority_type=n.get("authority_type"),
            discovery_state=None,
            degree=n["degree"],
        )
        for n in data["doc_nodes"]
    ] + [
        GovernanceGraphNodeType(
            id=f"key:{g['key']}",
            document_id=None,
            title=g["key"],
            kind=enrichment_constants.GRAPH_NODE_EXTERNAL,
            corpus_id=None,
            authority=g["authority"],
            jurisdiction=g.get("jurisdiction"),
            authority_type=g.get("authority_type"),
            discovery_state=g.get("discovery_state"),
            degree=g["degree"],
        )
        for g in data["ghost_nodes"]
    ]

    return GovernanceGraphType(
        corpora=[
            GovernanceGraphCorpusType(
                id=to_global_id("CorpusType", c["corpus_pk"]),
                title=c["title"],
                kind=c["kind"],
            )
            for c in data["corpora"]
        ],
        nodes=nodes,
        edges=[
            GovernanceGraphEdgeType(
                source=_node_id(e["source"]),
                target=_node_id(e["target"]),
                edge_type=e["edge_type"],
                weight=e["weight"],
            )
            for e in data["edges"]
        ],
        document_count=data["document_count"],
        external_key_count=data["external_key_count"],
        edge_count=data["edge_count"],
        mention_count=data["mention_count"],
        truncated=data["truncated"],
    )


def q_governance_graph(
    info: strawberry.Info,
    corpus_id: Annotated[
        strawberry.ID, strawberry.argument(name="corpusId")
    ] = strawberry.UNSET,
    limit: Annotated[int | None, strawberry.argument(name="limit")] = strawberry.UNSET,
) -> None | (
    Annotated[GovernanceGraphType, strawberry.lazy("config.graphql.annotation_types")]
):
    kwargs = strip_unset({"corpus_id": corpus_id, "limit": limit})
    return _resolve_Query_governance_graph(None, info, **kwargs)


@graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_MEDIUM"))
def _resolve_Query_wanted_authorities(root, info, corpus_id=None):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_queries.py:271

    Port of AnnotationQueryMixin.resolve_wanted_authorities

    Aggregate through ``CorpusReferenceService`` (visibility-scoped). The
    service returns plain dicts; graphene's default resolver mapped them onto
    ``WantedAuthorityType`` fields automatically, but strawberry's default
    resolver is attribute-based (``getattr``), so we construct the payload
    types explicitly here.
    """
    from opencontractserver.enrichment.services import CorpusReferenceService

    pk: int | None = None
    if corpus_id:
        pk_str = from_global_id(corpus_id)[1]
        if not str(pk_str).isdigit():
            return []
        pk = int(pk_str)
    rows = CorpusReferenceService.wanted_authorities(info.context.user, corpus_id=pk)
    return [
        WantedAuthorityType(
            authority=row["authority"],
            mention_count=row["mention_count"],
            key_count=row["key_count"],
            corpus_count=row["corpus_count"],
            top_keys=[WantedAuthorityKeyType(**key) for key in row["top_keys"]],
        )
        for row in rows
    ]


def q_wanted_authorities(
    info: strawberry.Info,
    corpus_id: Annotated[
        strawberry.ID | None,
        strawberry.argument(
            name="corpusId",
            description="Restrict the backlog to one corpus; omit for all visible.",
        ),
    ] = strawberry.UNSET,
) -> list[
    Annotated[WantedAuthorityType, strawberry.lazy("config.graphql.annotation_types")]
]:
    kwargs = strip_unset({"corpus_id": corpus_id})
    return _resolve_Query_wanted_authorities(None, info, **kwargs)


@graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
def _resolve_Query_authority_frontier_stats(
    root,
    info,
    jurisdiction=None,
    authority_type=None,
    provider=None,
    authority=None,
    search=None,
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_queries.py:315

    Port of AnnotationQueryMixin.resolve_authority_frontier_stats

    Delegate the (superuser-gated) aggregation to the service. Graphene's
    default resolver mapped the returned dict onto ``AuthorityFrontierStatsType``;
    strawberry needs explicit construction (attribute-based default resolver).
    """
    from opencontractserver.enrichment.services import AuthorityFrontierService

    data = AuthorityFrontierService.admin_state_counts(
        info.context.user,
        jurisdiction=jurisdiction,
        authority_type=authority_type,
        provider=provider,
        authority=authority,
        search=search,
    )
    return AuthorityFrontierStatsType(
        total_count=data["total_count"],
        by_state=[AuthorityFrontierStateCountType(**row) for row in data["by_state"]],
    )


def q_authority_frontier_stats(
    info: strawberry.Info,
    jurisdiction: Annotated[
        str | None, strawberry.argument(name="jurisdiction")
    ] = strawberry.UNSET,
    authority_type: Annotated[
        str | None, strawberry.argument(name="authorityType")
    ] = strawberry.UNSET,
    provider: Annotated[
        str | None, strawberry.argument(name="provider")
    ] = strawberry.UNSET,
    authority: Annotated[
        str | None, strawberry.argument(name="authority")
    ] = strawberry.UNSET,
    search: Annotated[
        str | None, strawberry.argument(name="search")
    ] = strawberry.UNSET,
) -> Annotated[
    AuthorityFrontierStatsType, strawberry.lazy("config.graphql.annotation_types")
]:
    kwargs = strip_unset(
        {
            "jurisdiction": jurisdiction,
            "authority_type": authority_type,
            "provider": provider,
            "authority": authority,
            "search": search,
        }
    )
    return _resolve_Query_authority_frontier_stats(None, info, **kwargs)


@graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
def _resolve_Query_authority_mapping_stats(root, info, search=None):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_queries.py:361

    Port of AnnotationQueryMixin.resolve_authority_mapping_stats

    Delegate the (superuser-gated) aggregation to the service. Graphene's
    default resolver mapped the returned dict onto ``AuthorityMappingStatsType``;
    strawberry needs explicit construction (attribute-based default resolver).
    """
    from opencontractserver.enrichment.services import (
        AuthorityKeyEquivalenceService,
    )

    data = AuthorityKeyEquivalenceService.stats(info.context.user, search=search)
    return AuthorityMappingStatsType(
        total_count=data["total_count"],
        by_source=[AuthorityMappingSourceCountType(**row) for row in data["by_source"]],
    )


def q_authority_mapping_stats(
    info: strawberry.Info,
    search: Annotated[
        str | None, strawberry.argument(name="search")
    ] = strawberry.UNSET,
) -> Annotated[
    AuthorityMappingStatsType, strawberry.lazy("config.graphql.annotation_types")
]:
    kwargs = strip_unset({"search": search})
    return _resolve_Query_authority_mapping_stats(None, info, **kwargs)


@graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
def _resolve_Query_authority_namespace_stats(root, info, search=None):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_queries.py:405

    Port of AnnotationQueryMixin.resolve_authority_namespace_stats

    Service returns plain dicts (graphene auto-mapped them); strawberry needs
    explicit type construction.
    """
    from opencontractserver.enrichment.services import AuthorityNamespaceService

    data = AuthorityNamespaceService.stats(info.context.user, search=search)
    return AuthorityNamespaceStatsType(
        total_count=data["total_count"],
        by_jurisdiction=[
            AuthorityNamespaceFacetCountType(**row) for row in data["by_jurisdiction"]
        ],
        by_authority_type=[
            AuthorityNamespaceFacetCountType(**row) for row in data["by_authority_type"]
        ],
        by_scope=[AuthorityNamespaceFacetCountType(**row) for row in data["by_scope"]],
    )


def q_authority_namespace_stats(
    info: strawberry.Info,
    search: Annotated[
        str | None, strawberry.argument(name="search")
    ] = strawberry.UNSET,
) -> Annotated[
    AuthorityNamespaceStatsType, strawberry.lazy("config.graphql.annotation_types")
]:
    kwargs = strip_unset({"search": search})
    return _resolve_Query_authority_namespace_stats(None, info, **kwargs)


@graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_MEDIUM"))
def _resolve_Query_authority_namespace_detail(root, info, prefix):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_queries.py:411

    Port of AnnotationQueryMixin.resolve_authority_namespace_detail

    The service returns an ``AuthorityDetail`` dataclass (attribute access
    works for strawberry) except its two counts lists carry plain dicts, which
    graphene auto-mapped but strawberry must wrap explicitly.
    """
    from opencontractserver.enrichment.services import AuthorityNamespaceService

    detail = AuthorityNamespaceService.detail(info.context.user, prefix)
    if detail is None:
        return None
    return AuthorityDetailType(
        namespace=detail.namespace,
        equivalences_out=detail.equivalences_out,
        equivalences_in=detail.equivalences_in,
        frontier_rows=detail.frontier_rows,
        frontier_state_counts=[
            AuthorityFrontierStateCountType(**row)
            for row in detail.frontier_state_counts
        ],
        reference_total=detail.reference_total,
        reference_status_counts=[
            AuthorityReferenceStatusCountType(**row)
            for row in detail.reference_status_counts
        ],
        reference_sample=detail.reference_sample,
        effective_provider=detail.effective_provider,
    )


def q_authority_namespace_detail(
    info: strawberry.Info,
    prefix: Annotated[str, strawberry.argument(name="prefix")] = strawberry.UNSET,
) -> None | (
    Annotated[AuthorityDetailType, strawberry.lazy("config.graphql.annotation_types")]
):
    kwargs = strip_unset({"prefix": prefix})
    return _resolve_Query_authority_namespace_detail(None, info, **kwargs)


@graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
def _resolve_Query_authority_source_providers(root, info):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_queries.py:429

    Port of AnnotationQueryMixin.resolve_authority_source_providers

    Service returns plain dicts (graphene auto-mapped them); strawberry needs
    explicit type construction. Dict keys match the type's python field names
    one-to-one.
    """
    from opencontractserver.enrichment.services import (
        AuthoritySourceProviderService,
    )

    return [
        AuthoritySourceProviderType(**row)
        for row in AuthoritySourceProviderService.list_providers(info.context.user)
    ]


def q_authority_source_providers(
    info: strawberry.Info,
) -> list[
    Annotated[
        AuthoritySourceProviderType,
        strawberry.lazy("config.graphql.annotation_types"),
    ]
]:
    kwargs = strip_unset({})
    return _resolve_Query_authority_source_providers(None, info, **kwargs)


@graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_MEDIUM"))
def _resolve_Query_annotations(
    root,
    info,
    analysis_isnull=None,
    structural=None,
    corpus_action_isnull=None,
    agent_created=None,
    **kwargs,
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_queries.py:460

    Port of AnnotationQueryMixin.resolve_annotations
    """
    # Import the query optimizer
    from opencontractserver.annotations.services import AnnotationService

    document_id = kwargs.get("document_id")
    corpus_id = kwargs.get("corpus_id")

    # Decoded PKs of the requested context, used below to scope the
    # structural-set document prefetch so structural annotations
    # (document_id=NULL) resolve to the context-local document.
    doc_django_pk: int | None = None
    corpus_django_pk: int | None = None

    if document_id:
        # Use document-specific query optimizer
        doc_django_pk = int(from_global_id(document_id)[1])
        corpus_django_pk = int(from_global_id(corpus_id)[1]) if corpus_id else None

        # Use query optimizer which handles permissions properly
        queryset = AnnotationService.get_document_annotations(
            document_id=doc_django_pk,
            user=info.context.user,
            corpus_id=corpus_django_pk,
            analysis_id=None,  # Will be handled below if needed
            extract_id=None,
        )

    elif corpus_id:
        # Use corpus-wide query optimizer (handles structural annotations correctly)
        # This optimizer already applies structural, analysis_isnull, and corpus filters
        corpus_django_pk = int(from_global_id(corpus_id)[1])
        queryset = AnnotationService.get_corpus_annotations(
            corpus_id=corpus_django_pk,
            user=info.context.user,
            structural=structural,
            analysis_isnull=analysis_isnull,
            context=info.context,
        )
        # Mark filters already applied by optimizer to prevent double-filtering
        corpus_id = None
        structural = None
        analysis_isnull = None

    else:
        # Fallback to visible_to_user for queries without document or
        # corpus. This un-scoped "Browse annotations" path uses a cached
        # exact totalCount (scoped paths above keep live counts) — see
        # ``CachedCountQuerySetMixin`` / issue #1908.
        queryset = BaseService.filter_visible(
            Annotation, info.context.user, request=info.context
        ).with_cached_count()

    queryset = queryset.select_related(
        "annotation_label",
        "creator",
        "document",
        "document__creator",
        "corpus",
        "analysis",
        "analysis__analyzer",
        "corpus_action",
        "structural_set",
    ).prefetch_related(
        # Scope the structural-set documents to the requested corpus (or
        # document) so AnnotationType.resolve_document returns the
        # context-local copy rather than an arbitrary member of a
        # content-hash-shared StructuralAnnotationSet. See
        # AnnotationService.structural_document_prefetch.
        AnnotationService.structural_document_prefetch(
            user=info.context.user,
            corpus_id=corpus_django_pk,
            document_id=doc_django_pk,
        ),
    )

    # Filter by uses_label_from_labelset_id
    labelset_id = kwargs.get("uses_label_from_labelset_id")
    if labelset_id:
        django_pk = from_global_id(labelset_id)[1]
        queryset = queryset.filter(annotation_label__included_in_labelset=django_pk)

    # Filter by created_by_analysis_ids
    analysis_ids = kwargs.get("created_by_analysis_ids")
    if analysis_ids:
        analysis_id_list = analysis_ids.split(",")
        if MANUAL_ANNOTATION_SENTINEL in analysis_id_list:
            analysis_id_list = [
                id for id in analysis_id_list if id != MANUAL_ANNOTATION_SENTINEL
            ]
            analysis_pks = [int(from_global_id(value)[1]) for value in analysis_id_list]
            queryset = queryset.filter(
                Q(analysis__isnull=True) | Q(analysis_id__in=analysis_pks)
            )
        else:
            analysis_pks = [int(from_global_id(value)[1]) for value in analysis_id_list]
            queryset = queryset.filter(analysis_id__in=analysis_pks)

    # Filter by created_with_analyzer_id
    analyzer_ids = kwargs.get("created_with_analyzer_id")
    if analyzer_ids:
        analyzer_id_list = analyzer_ids.split(",")
        if MANUAL_ANNOTATION_SENTINEL in analyzer_id_list:
            analyzer_id_list = [
                id for id in analyzer_id_list if id != MANUAL_ANNOTATION_SENTINEL
            ]
            analyzer_pks = [
                int(from_global_id(id)[1])
                for id in analyzer_id_list
                if id != MANUAL_ANNOTATION_SENTINEL
            ]
            queryset = queryset.filter(
                Q(analysis__isnull=True) | Q(analysis__analyzer_id__in=analyzer_pks)
            )
        elif len(analyzer_id_list) > 0:
            analyzer_pks = [int(from_global_id(id)[1]) for id in analyzer_id_list]
            queryset = queryset.filter(analysis__analyzer_id__in=analyzer_pks)

    # Filter by raw_text
    raw_text = kwargs.get("raw_text_contains")
    if raw_text:
        queryset = queryset.filter(raw_text__contains=raw_text)

    # Filter by annotation_label_id
    annotation_label_id = kwargs.get("annotation_label_id")
    if annotation_label_id:
        django_pk = from_global_id(annotation_label_id)[1]
        queryset = queryset.filter(annotation_label_id=django_pk)

    # Filter by annotation_label__text
    label_text = kwargs.get("annotation_label__text")
    if label_text:
        queryset = queryset.filter(annotation_label__text=label_text)

    label_text_contains = kwargs.get("annotation_label__text_contains")
    if label_text_contains:
        queryset = queryset.filter(annotation_label__text__contains=label_text_contains)

    # Filter by annotation_label__description
    label_description = kwargs.get("annotation_label__description_contains")
    if label_description:
        queryset = queryset.filter(
            annotation_label__description__contains=label_description
        )

    # Filter by annotation_label__label_type
    label_type = kwargs.get("annotation_label__label_type")
    if label_type:
        queryset = queryset.filter(annotation_label__label_type=label_type)

    # Filter by analysis
    if analysis_isnull is not None:
        queryset = queryset.filter(analysis__isnull=analysis_isnull)

    # Filter by corpus_action
    if corpus_action_isnull is not None:
        queryset = queryset.filter(corpus_action__isnull=corpus_action_isnull)

    # Combined agent filter: annotations created by analysis OR corpus action
    if agent_created is not None:
        agent_q = Q(analysis__isnull=False) | Q(corpus_action__isnull=False)
        if agent_created:
            queryset = queryset.filter(agent_q)
        else:
            queryset = queryset.exclude(agent_q)

    # Skip document_id and corpus_id filtering if already handled by optimizer
    if not document_id:
        # Filter by document_id
        document_id = kwargs.get("document_id")
        if document_id:
            django_pk = from_global_id(document_id)[1]
            queryset = queryset.filter(document_id=django_pk)

        # Filter by corpus_id
        corpus_id = kwargs.get("corpus_id")
        if corpus_id:
            django_pk = from_global_id(corpus_id)[1]
            queryset = queryset.filter(corpus_id=django_pk)

    # Filter by structural
    if structural is not None:
        queryset = queryset.filter(structural=structural)

    # Ordering
    order_by = kwargs.get("order_by")
    if order_by:
        queryset = queryset.order_by(order_by)
    else:
        queryset = queryset.order_by("-modified")

    return queryset


def q_annotations(
    info: strawberry.Info,
    raw_text_contains: Annotated[
        str | None, strawberry.argument(name="rawTextContains")
    ] = strawberry.UNSET,
    annotation_label_id: Annotated[
        strawberry.ID | None, strawberry.argument(name="annotationLabelId")
    ] = strawberry.UNSET,
    annotation_label__text: Annotated[
        str | None, strawberry.argument(name="annotationLabel_Text")
    ] = strawberry.UNSET,
    annotation_label__text_contains: Annotated[
        str | None, strawberry.argument(name="annotationLabel_TextContains")
    ] = strawberry.UNSET,
    annotation_label__description_contains: Annotated[
        str | None, strawberry.argument(name="annotationLabel_DescriptionContains")
    ] = strawberry.UNSET,
    annotation_label__label_type: Annotated[
        str | None, strawberry.argument(name="annotationLabel_LabelType")
    ] = strawberry.UNSET,
    analysis_isnull: Annotated[
        bool | None, strawberry.argument(name="analysisIsnull")
    ] = strawberry.UNSET,
    corpus_action_isnull: Annotated[
        bool | None, strawberry.argument(name="corpusActionIsnull")
    ] = strawberry.UNSET,
    agent_created: Annotated[
        bool | None, strawberry.argument(name="agentCreated")
    ] = strawberry.UNSET,
    document_id: Annotated[
        strawberry.ID | None, strawberry.argument(name="documentId")
    ] = strawberry.UNSET,
    corpus_id: Annotated[
        strawberry.ID | None, strawberry.argument(name="corpusId")
    ] = strawberry.UNSET,
    structural: Annotated[
        bool | None, strawberry.argument(name="structural")
    ] = strawberry.UNSET,
    uses_label_from_labelset_id: Annotated[
        strawberry.ID | None, strawberry.argument(name="usesLabelFromLabelsetId")
    ] = strawberry.UNSET,
    created_by_analysis_ids: Annotated[
        str | None, strawberry.argument(name="createdByAnalysisIds")
    ] = strawberry.UNSET,
    created_with_analyzer_id: Annotated[
        str | None, strawberry.argument(name="createdWithAnalyzerId")
    ] = strawberry.UNSET,
    order_by: Annotated[
        str | None, strawberry.argument(name="orderBy")
    ] = strawberry.UNSET,
    offset: Annotated[
        int | None, strawberry.argument(name="offset")
    ] = strawberry.UNSET,
    before: Annotated[
        str | None, strawberry.argument(name="before")
    ] = strawberry.UNSET,
    after: Annotated[str | None, strawberry.argument(name="after")] = strawberry.UNSET,
    first: Annotated[int | None, strawberry.argument(name="first")] = strawberry.UNSET,
    last: Annotated[int | None, strawberry.argument(name="last")] = strawberry.UNSET,
) -> None | (
    Annotated[
        AnnotationTypeConnection, strawberry.lazy("config.graphql.annotation_types")
    ]
):
    kwargs = strip_unset(
        {
            "raw_text_contains": raw_text_contains,
            "annotation_label_id": annotation_label_id,
            "annotation_label__text": annotation_label__text,
            "annotation_label__text_contains": annotation_label__text_contains,
            "annotation_label__description_contains": annotation_label__description_contains,
            "annotation_label__label_type": annotation_label__label_type,
            "analysis_isnull": analysis_isnull,
            "corpus_action_isnull": corpus_action_isnull,
            "agent_created": agent_created,
            "document_id": document_id,
            "corpus_id": corpus_id,
            "structural": structural,
            "uses_label_from_labelset_id": uses_label_from_labelset_id,
            "created_by_analysis_ids": created_by_analysis_ids,
            "created_with_analyzer_id": created_with_analyzer_id,
            "order_by": order_by,
            "offset": offset,
            "before": before,
            "after": after,
            "first": first,
            "last": last,
        }
    )
    resolved = _resolve_Query_annotations(None, info, **kwargs)
    return resolve_django_connection(
        resolved=resolved,
        info=info,
        args=kwargs,
        node_type_name="AnnotationType",
        default_manager=Annotation._default_manager,
        # Higher limit for Document Annotation Index which needs full hierarchy
        # (graphene original: DjangoConnectionField(..., max_limit=DOCUMENT_ANNOTATION_INDEX_LIMIT)).
        max_limit=DOCUMENT_ANNOTATION_INDEX_LIMIT,
    )


def _resolve_Query_bulk_doc_relationships_in_corpus(root, info, corpus_id, document_id):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_queries.py:682

    Port of AnnotationQueryMixin.resolve_bulk_doc_relationships_in_corpus
    """
    # Get the base queryset using visible_to_user
    queryset = BaseService.filter_visible(
        Relationship, info.context.user, request=info.context
    )

    doc_django_pk = from_global_id(document_id)[1]
    corpus_django_pk = from_global_id(corpus_id)[1]

    queryset = queryset.filter(
        corpus_id=corpus_django_pk, document_id=doc_django_pk
    )  # Existing filter
    queryset = queryset.select_related(
        "relationship_label",
        "corpus",
        "document",
        "creator",
        "analyzer",  # If needed
        "analysis",  # If needed
    ).prefetch_related(
        "source_annotations",  # If RelationshipType shows source annotations
        "target_annotations",  # If RelationshipType shows target annotations
    )
    return queryset


def q_bulk_doc_relationships_in_corpus(
    info: strawberry.Info,
    corpus_id: Annotated[
        strawberry.ID, strawberry.argument(name="corpusId")
    ] = strawberry.UNSET,
    document_id: Annotated[
        strawberry.ID, strawberry.argument(name="documentId")
    ] = strawberry.UNSET,
) -> None | (
    list[
        None
        | (
            Annotated[
                RelationshipType, strawberry.lazy("config.graphql.annotation_types")
            ]
        )
    ]
):
    kwargs = strip_unset({"corpus_id": corpus_id, "document_id": document_id})
    return _resolve_Query_bulk_doc_relationships_in_corpus(None, info, **kwargs)


def _resolve_Query_bulk_doc_annotations_in_corpus(root, info, corpus_id, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_queries.py:717

    Port of AnnotationQueryMixin.resolve_bulk_doc_annotations_in_corpus
    """

    corpus_django_pk = from_global_id(corpus_id)[1]

    # Get the base queryset using visible_to_user
    queryset = BaseService.filter_visible(
        Annotation, info.context.user, request=info.context
    ).order_by("page")

    # Now build query to stuff they want to see (filter to annotations in this corpus or with NO corpus FK, which
    # travel with document.
    q_objects = Q(corpus_id=corpus_django_pk) | Q(corpus_id__isnull=True)

    # If for_analysis_ids is passed in, only show annotations from those analyses, otherwise only show human
    # annotations.
    for_analysis_ids = kwargs.get("for_analysis_ids", None)
    if for_analysis_ids is not None and len(for_analysis_ids) > 0:
        logger.info(
            f"resolve_bulk_doc_annotations - Split ids: {for_analysis_ids.split(',')}"
        )
        analysis_pks = [
            int(from_global_id(value)[1])
            for value in list(
                filter(lambda raw_id: len(raw_id) > 0, for_analysis_ids.split(","))
            )
        ]
        logger.info(f"resolve_bulk_doc_annotations - Analysis pks: {analysis_pks}")
        q_objects.add(Q(analysis_id__in=analysis_pks), Q.AND)
    # else:
    #     q_objects.add(Q(analysis__isnull=True), Q.AND)

    label_type = kwargs.get("label_type", None)
    if label_type is not None:
        q_objects.add(Q(annotation_label__label_type=label_type), Q.AND)

    document_id = kwargs.get("document_id", None)
    if document_id is not None:
        doc_pk = from_global_id(document_id)[1]
        q_objects.add(Q(document_id=doc_pk), Q.AND)

    logger.info(f"Filter queryset {queryset} bulk annotations: {q_objects}")

    final_queryset = queryset.filter(q_objects).order_by(
        "created", "page"
    )  # Existing filter/order
    final_queryset = final_queryset.select_related(
        "annotation_label",
        "creator",
        "document",
        "corpus",
        "analysis",
        "analysis__analyzer",
        # 'embeddings' # If needed
    )
    return final_queryset


def q_bulk_doc_annotations_in_corpus(
    info: strawberry.Info,
    corpus_id: Annotated[
        strawberry.ID, strawberry.argument(name="corpusId")
    ] = strawberry.UNSET,
    document_id: Annotated[
        strawberry.ID | None, strawberry.argument(name="documentId")
    ] = strawberry.UNSET,
    for_analysis_ids: Annotated[
        str | None, strawberry.argument(name="forAnalysisIds")
    ] = strawberry.UNSET,
    label_type: Annotated[
        enums.LabelType | None, strawberry.argument(name="labelType")
    ] = strawberry.UNSET,
) -> None | (
    list[
        None
        | (
            Annotated[
                AnnotationType, strawberry.lazy("config.graphql.annotation_types")
            ]
        )
    ]
):
    kwargs = strip_unset(
        {
            "corpus_id": corpus_id,
            "document_id": document_id,
            "for_analysis_ids": for_analysis_ids,
            "label_type": label_type,
        }
    )
    return _resolve_Query_bulk_doc_annotations_in_corpus(None, info, **kwargs)


@graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_MEDIUM"))
def _resolve_Query_page_annotations(root, info, document_id, corpus_id=None, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_queries.py:785

    Port of AnnotationQueryMixin.resolve_page_annotations
    """

    doc_django_pk = int(from_global_id(document_id)[1])

    # Fetch the document (consider select_related if creator/etc. are used elsewhere)
    # Using get_object_or_404 for better error handling if document not found/accessible
    # For simplicity, assuming simple get for now based on original code.
    try:
        # Add select_related if document creator/etc. needed later
        document = Document.objects.get(id=doc_django_pk)
    except Document.DoesNotExist:
        # Handle error appropriately, maybe return null or raise GraphQL error
        logger.error(f"Document with pk {doc_django_pk} not found.")
        return None  # Or raise appropriate GraphQL error

    # Get the base queryset using visible_to_user
    queryset = BaseService.filter_visible(
        Annotation, info.context.user, request=info.context
    )

    # Apply select_related EARLY to the base queryset
    queryset = queryset.select_related(
        "annotation_label",
        "creator",
        "document",  # Document already fetched, but good practice if base queryset reused
        "corpus",
        "analysis",
        "analysis__analyzer",
    )

    # Now build query filters
    q_objects = Q(document_id=doc_django_pk)
    if corpus_id is not None:
        corpus_pk = from_global_id(corpus_id)[
            1
        ]  # Get corpus_pk only if corpus_id is present
        q_objects.add(Q(corpus_id=corpus_pk), Q.AND)

    # If for_analysis_ids is passed in, only show annotations from those analyses
    for_analysis_ids = kwargs.get("for_analysis_ids", None)
    if for_analysis_ids is not None:
        analysis_pks = [
            int(from_global_id(value)[1])
            for value in list(
                filter(lambda raw_id: len(raw_id) > 0, for_analysis_ids.split(","))
            )
        ]
        if analysis_pks:  # Only add filter if there are valid PKs
            logger.info(
                f"resolve_page_annotations - Filtering by Analysis pks: {analysis_pks}"
            )
            q_objects.add(Q(analysis_id__in=analysis_pks), Q.AND)
        else:
            # Handle case maybe? Or assume UI prevents empty string if filter applied
            logger.warning(
                "resolve_page_annotations - for_analysis_ids provided but resulted in empty PK list."
            )
    else:
        logger.info(
            "resolve_page_annotations - for_analysis_ids is None, filtering for analysis__isnull=True"
        )
        q_objects.add(Q(analysis__isnull=True), Q.AND)

    label_type = kwargs.get("label_type", None)
    if label_type is not None:
        logger.info(f"resolve_page_annotations - Filtering by label_type: {label_type}")
        q_objects.add(Q(annotation_label__label_type=label_type), Q.AND)

    # Apply filters to the optimized base queryset
    # Order by page first for potential pagination logic, then created
    all_pages_annotations = queryset.filter(q_objects).order_by("page", "created")

    # --- Determine the current page ---
    page_containing_annotation_with_id = kwargs.get(
        "page_containing_annotation_with_id", None
    )
    page_number_list = kwargs.get("page_number_list", None)
    current_page = 1  # Default to page 1 (1-indexed)
    pages: list[int] = []  # Parsed page list from page_number_list (1-indexed)

    # Always parse page_number_list when provided so `pages` is available
    # for the filtering step below, regardless of which branch sets current_page.
    if page_number_list is not None:
        if re.search(r"^(?:\d+,)*\d+$", page_number_list):
            pages = [int(page) for page in page_number_list.split(",")]
        else:
            logger.warning(f"Invalid format for page_number_list: {page_number_list}")

    if kwargs.get("current_page", None) is not None:
        current_page = int(kwargs["current_page"])
        logger.info(
            f"resolve_page_annotations - Using provided current_page: {current_page}"
        )
    elif pages:
        current_page = pages[-1]
        logger.info(
            f"resolve_page_annotations - Using last page from page_number_list: {current_page}"
        )
    elif page_containing_annotation_with_id:
        try:
            annotation_pk = int(from_global_id(page_containing_annotation_with_id)[1])
            # Optimized fetch for just the page number
            annotation_page_zero_indexed = (
                Annotation.objects.filter(pk=annotation_pk)
                .values_list("page", flat=True)
                .first()
            )  # Use first() to avoid DoesNotExist

            if annotation_page_zero_indexed is not None:
                current_page = (
                    annotation_page_zero_indexed + 1
                )  # Convert 0-indexed DB value to 1-indexed page number
                logger.info(
                    f"resolve_page_annotations - Found page {current_page} for annotation pk {annotation_pk}"
                )
            else:
                logger.warning(
                    f"resolve_page_annotations - Annotation pk {annotation_pk} not found for page lookup."
                )
                # Keep default current_page = 1
        except (ValueError, TypeError) as e:
            logger.error(
                f"Error parsing annotation ID {page_containing_annotation_with_id}: {e}"
            )
            # Keep default current_page = 1

    # Convert 1-indexed current page to 0-indexed for DB filtering
    current_page_zero_indexed = max(0, current_page - 1)  # Ensure it's not negative

    # --- Filter annotations for the specific page(s) ---
    if page_number_list is not None and re.search(r"^(?:\d+,)*\d+$", page_number_list):
        # Use validated page list from earlier
        pages_zero_indexed = [max(0, page - 1) for page in pages]
        page_annotations = all_pages_annotations.filter(
            page__in=pages_zero_indexed
        )  # Order already applied
    else:
        page_annotations = all_pages_annotations.filter(
            page=current_page_zero_indexed
        )  # Order already applied

    logger.info(
        f"resolve_page_annotations - final page annotations count: {page_annotations.count()}"
    )  # Use .count() carefully if queryset is large

    pdf_page_info = PdfPageInfoType(
        page_count=document.page_count,
        current_page=current_page_zero_indexed,  # Return 0-indexed as per original logic
        has_next_page=current_page_zero_indexed < document.page_count - 1,
        has_previous_page=current_page_zero_indexed > 0,
        corpus_id=corpus_id,
        document_id=document_id,
        for_analysis_ids=for_analysis_ids,
        label_type=label_type,
    )

    return PageAwareAnnotationType(
        page_annotations=page_annotations, pdf_page_info=pdf_page_info
    )


def q_page_annotations(
    info: strawberry.Info,
    current_page: Annotated[
        int | None, strawberry.argument(name="currentPage")
    ] = strawberry.UNSET,
    page_number_list: Annotated[
        str | None, strawberry.argument(name="pageNumberList")
    ] = strawberry.UNSET,
    page_containing_annotation_with_id: Annotated[
        strawberry.ID | None,
        strawberry.argument(name="pageContainingAnnotationWithId"),
    ] = strawberry.UNSET,
    corpus_id: Annotated[
        strawberry.ID | None, strawberry.argument(name="corpusId")
    ] = strawberry.UNSET,
    document_id: Annotated[
        strawberry.ID, strawberry.argument(name="documentId")
    ] = strawberry.UNSET,
    for_analysis_ids: Annotated[
        str | None, strawberry.argument(name="forAnalysisIds")
    ] = strawberry.UNSET,
    label_type: Annotated[
        enums.LabelType | None, strawberry.argument(name="labelType")
    ] = strawberry.UNSET,
) -> None | (
    Annotated[PageAwareAnnotationType, strawberry.lazy("config.graphql.base_types")]
):
    kwargs = strip_unset(
        {
            "current_page": current_page,
            "page_number_list": page_number_list,
            "page_containing_annotation_with_id": page_containing_annotation_with_id,
            "corpus_id": corpus_id,
            "document_id": document_id,
            "for_analysis_ids": for_analysis_ids,
            "label_type": label_type,
        }
    )
    return _resolve_Query_page_annotations(None, info, **kwargs)


def q_annotation(
    info: strawberry.Info,
    id: Annotated[
        strawberry.ID,
        strawberry.argument(name="id", description="The ID of the object"),
    ] = strawberry.UNSET,
) -> None | (
    Annotated[AnnotationType, strawberry.lazy("config.graphql.annotation_types")]
):
    return get_node_from_global_id(info, id, only_type_name="AnnotationType")


def _resolve_Query_relationships(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_queries.py:977

    Port of AnnotationQueryMixin.resolve_relationships
    """
    queryset = BaseService.filter_visible(
        Relationship, info.context.user, request=info.context
    )
    queryset = queryset.select_related(
        "relationship_label",
        "corpus",
        "document",
        "creator",
        "analyzer",
        "analysis",
    ).prefetch_related("source_annotations", "target_annotations")
    return queryset


def q_relationships(
    info: strawberry.Info,
    offset: Annotated[
        int | None, strawberry.argument(name="offset")
    ] = strawberry.UNSET,
    before: Annotated[
        str | None, strawberry.argument(name="before")
    ] = strawberry.UNSET,
    after: Annotated[str | None, strawberry.argument(name="after")] = strawberry.UNSET,
    first: Annotated[int | None, strawberry.argument(name="first")] = strawberry.UNSET,
    last: Annotated[int | None, strawberry.argument(name="last")] = strawberry.UNSET,
    relationship_label: Annotated[
        strawberry.ID | None, strawberry.argument(name="relationshipLabel")
    ] = strawberry.UNSET,
    corpus_id: Annotated[
        strawberry.ID | None, strawberry.argument(name="corpusId")
    ] = strawberry.UNSET,
    document_id: Annotated[
        strawberry.ID | None, strawberry.argument(name="documentId")
    ] = strawberry.UNSET,
) -> None | (
    Annotated[
        RelationshipTypeConnection, strawberry.lazy("config.graphql.annotation_types")
    ]
):
    kwargs = strip_unset(
        {
            "offset": offset,
            "before": before,
            "after": after,
            "first": first,
            "last": last,
            "relationship_label": relationship_label,
            "corpus_id": corpus_id,
            "document_id": document_id,
        }
    )
    resolved = _resolve_Query_relationships(None, info, **kwargs)
    return resolve_django_connection(
        resolved=resolved,
        info=info,
        args=kwargs,
        node_type_name="RelationshipType",
        default_manager=Relationship._default_manager,
        filterset_class=setup_filterset(RelationshipFilter),
        filter_args={
            "relationship_label": "relationship_label",
            "corpus_id": "corpus_id",
            "document_id": "document_id",
        },
    )


def q_relationship(
    info: strawberry.Info,
    id: Annotated[
        strawberry.ID,
        strawberry.argument(name="id", description="The ID of the object"),
    ] = strawberry.UNSET,
) -> None | (
    Annotated[RelationshipType, strawberry.lazy("config.graphql.annotation_types")]
):
    return get_node_from_global_id(info, id, only_type_name="RelationshipType")


def _resolve_Query_annotation_labels(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_queries.py:1016

    Port of AnnotationQueryMixin.resolve_annotation_labels
    """
    return BaseService.filter_visible(
        AnnotationLabel, info.context.user, request=info.context
    )


def q_annotation_labels(
    info: strawberry.Info,
    offset: Annotated[
        int | None, strawberry.argument(name="offset")
    ] = strawberry.UNSET,
    before: Annotated[
        str | None, strawberry.argument(name="before")
    ] = strawberry.UNSET,
    after: Annotated[str | None, strawberry.argument(name="after")] = strawberry.UNSET,
    first: Annotated[int | None, strawberry.argument(name="first")] = strawberry.UNSET,
    last: Annotated[int | None, strawberry.argument(name="last")] = strawberry.UNSET,
    description__contains: Annotated[
        str | None, strawberry.argument(name="description_Contains")
    ] = strawberry.UNSET,
    text: Annotated[str | None, strawberry.argument(name="text")] = strawberry.UNSET,
    text__contains: Annotated[
        str | None, strawberry.argument(name="text_Contains")
    ] = strawberry.UNSET,
    label_type: Annotated[
        enums.AnnotationsAnnotationLabelLabelTypeChoices | None,
        strawberry.argument(name="labelType"),
    ] = strawberry.UNSET,
    used_in_labelset_id: Annotated[
        str | None, strawberry.argument(name="usedInLabelsetId")
    ] = strawberry.UNSET,
    used_in_labelset_for_corpus_id: Annotated[
        str | None, strawberry.argument(name="usedInLabelsetForCorpusId")
    ] = strawberry.UNSET,
    used_in_analysis_ids: Annotated[
        str | None, strawberry.argument(name="usedInAnalysisIds")
    ] = strawberry.UNSET,
) -> None | (
    Annotated[
        AnnotationLabelTypeConnection,
        strawberry.lazy("config.graphql.annotation_types"),
    ]
):
    kwargs = strip_unset(
        {
            "offset": offset,
            "before": before,
            "after": after,
            "first": first,
            "last": last,
            "description__contains": description__contains,
            "text": text,
            "text__contains": text__contains,
            "label_type": label_type,
            "used_in_labelset_id": used_in_labelset_id,
            "used_in_labelset_for_corpus_id": used_in_labelset_for_corpus_id,
            "used_in_analysis_ids": used_in_analysis_ids,
        }
    )
    resolved = _resolve_Query_annotation_labels(None, info, **kwargs)
    return resolve_django_connection(
        resolved=resolved,
        info=info,
        args=kwargs,
        node_type_name="AnnotationLabelType",
        default_manager=AnnotationLabel._default_manager,
        filterset_class=setup_filterset(LabelFilter),
        filter_args={
            "description__contains": "description__contains",
            "text": "text",
            "text__contains": "text__contains",
            "label_type": "label_type",
            "used_in_labelset_id": "used_in_labelset_id",
            "used_in_labelset_for_corpus_id": "used_in_labelset_for_corpus_id",
            "used_in_analysis_ids": "used_in_analysis_ids",
        },
    )


def q_annotation_label(
    info: strawberry.Info,
    id: Annotated[
        strawberry.ID,
        strawberry.argument(name="id", description="The ID of the object"),
    ] = strawberry.UNSET,
) -> None | (
    Annotated[AnnotationLabelType, strawberry.lazy("config.graphql.annotation_types")]
):
    return get_node_from_global_id(info, id, only_type_name="AnnotationLabelType")


@graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
def _resolve_Query_labelsets(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_queries.py:1036

    Port of AnnotationQueryMixin.resolve_labelsets
    """
    return BaseService.filter_visible(LabelSet, info.context.user, request=info.context)


def q_labelsets(
    info: strawberry.Info,
    offset: Annotated[
        int | None, strawberry.argument(name="offset")
    ] = strawberry.UNSET,
    before: Annotated[
        str | None, strawberry.argument(name="before")
    ] = strawberry.UNSET,
    after: Annotated[str | None, strawberry.argument(name="after")] = strawberry.UNSET,
    first: Annotated[int | None, strawberry.argument(name="first")] = strawberry.UNSET,
    last: Annotated[int | None, strawberry.argument(name="last")] = strawberry.UNSET,
    id: Annotated[
        strawberry.ID | None, strawberry.argument(name="id")
    ] = strawberry.UNSET,
    description__contains: Annotated[
        str | None, strawberry.argument(name="description_Contains")
    ] = strawberry.UNSET,
    title: Annotated[str | None, strawberry.argument(name="title")] = strawberry.UNSET,
    text_search: Annotated[
        str | None, strawberry.argument(name="textSearch")
    ] = strawberry.UNSET,
    title__contains: Annotated[
        str | None, strawberry.argument(name="title_Contains")
    ] = strawberry.UNSET,
    labelset_id: Annotated[
        str | None, strawberry.argument(name="labelsetId")
    ] = strawberry.UNSET,
) -> None | (
    Annotated[
        LabelSetTypeConnection, strawberry.lazy("config.graphql.annotation_types")
    ]
):
    kwargs = strip_unset(
        {
            "offset": offset,
            "before": before,
            "after": after,
            "first": first,
            "last": last,
            "id": id,
            "description__contains": description__contains,
            "title": title,
            "text_search": text_search,
            "title__contains": title__contains,
            "labelset_id": labelset_id,
        }
    )
    resolved = _resolve_Query_labelsets(None, info, **kwargs)
    return resolve_django_connection(
        resolved=resolved,
        info=info,
        args=kwargs,
        node_type_name="LabelSetType",
        default_manager=LabelSet._default_manager,
        filterset_class=setup_filterset(LabelsetFilter),
        filter_args={
            "id": "id",
            "description__contains": "description__contains",
            "title": "title",
            "text_search": "text_search",
            "title__contains": "title__contains",
            "labelset_id": "labelset_id",
        },
    )


def q_labelset(
    info: strawberry.Info,
    id: Annotated[
        strawberry.ID,
        strawberry.argument(name="id", description="The ID of the object"),
    ] = strawberry.UNSET,
) -> None | (
    Annotated[LabelSetType, strawberry.lazy("config.graphql.annotation_types")]
):
    return get_node_from_global_id(info, id, only_type_name="LabelSetType")


@login_required
def _resolve_Query_default_labelset(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_queries.py:1059

    Port of AnnotationQueryMixin.resolve_default_labelset
    """
    return (
        BaseService.filter_visible(LabelSet, info.context.user, request=info.context)
        .filter(is_default=True)
        .first()
    )


def q_default_labelset(
    info: strawberry.Info,
) -> None | (
    Annotated[LabelSetType, strawberry.lazy("config.graphql.annotation_types")]
):
    kwargs = strip_unset({})
    return _resolve_Query_default_labelset(None, info, **kwargs)


@login_required
def _resolve_Query_notes(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_queries.py:1079

    Port of AnnotationQueryMixin.resolve_notes
    """
    # Base filtering for user permissions
    queryset = BaseService.filter_visible(Note, info.context.user, request=info.context)

    # Filter by title
    title_contains = kwargs.get("title_contains")
    if title_contains:
        logger.info(f"Filtering by title containing: {title_contains}")
        queryset = queryset.filter(title__contains=title_contains)

    # Filter by content
    content_contains = kwargs.get("content_contains")
    if content_contains:
        logger.info(f"Filtering by content containing: {content_contains}")
        queryset = queryset.filter(content__contains=content_contains)

    # Filter by document_id
    document_id = kwargs.get("document_id")
    if document_id:
        logger.info(f"Filtering by document_id: {document_id}")
        django_pk = from_global_id(document_id)[1]
        queryset = queryset.filter(document_id=django_pk)

    # Filter by annotation_id
    annotation_id = kwargs.get("annotation_id")
    if annotation_id:
        logger.info(f"Filtering by annotation_id: {annotation_id}")
        django_pk = from_global_id(annotation_id)[1]
        queryset = queryset.filter(annotation_id=django_pk)

    # Ordering
    order_by = kwargs.get("order_by")
    if order_by:
        logger.info(f"Ordering by: {order_by}")
        queryset = queryset.order_by(order_by)
    else:
        logger.info("Ordering by default: -modified")
        queryset = queryset.order_by("-modified")

    logger.info(f"Final queryset: {queryset}")
    return queryset


def q_notes(
    info: strawberry.Info,
    title_contains: Annotated[
        str | None, strawberry.argument(name="titleContains")
    ] = strawberry.UNSET,
    content_contains: Annotated[
        str | None, strawberry.argument(name="contentContains")
    ] = strawberry.UNSET,
    document_id: Annotated[
        strawberry.ID | None, strawberry.argument(name="documentId")
    ] = strawberry.UNSET,
    annotation_id: Annotated[
        strawberry.ID | None, strawberry.argument(name="annotationId")
    ] = strawberry.UNSET,
    order_by: Annotated[
        str | None, strawberry.argument(name="orderBy")
    ] = strawberry.UNSET,
    offset: Annotated[
        int | None, strawberry.argument(name="offset")
    ] = strawberry.UNSET,
    before: Annotated[
        str | None, strawberry.argument(name="before")
    ] = strawberry.UNSET,
    after: Annotated[str | None, strawberry.argument(name="after")] = strawberry.UNSET,
    first: Annotated[int | None, strawberry.argument(name="first")] = strawberry.UNSET,
    last: Annotated[int | None, strawberry.argument(name="last")] = strawberry.UNSET,
) -> None | (
    Annotated[NoteTypeConnection, strawberry.lazy("config.graphql.annotation_types")]
):
    kwargs = strip_unset(
        {
            "title_contains": title_contains,
            "content_contains": content_contains,
            "document_id": document_id,
            "annotation_id": annotation_id,
            "order_by": order_by,
            "offset": offset,
            "before": before,
            "after": after,
            "first": first,
            "last": last,
        }
    )
    resolved = _resolve_Query_notes(None, info, **kwargs)
    return resolve_django_connection(
        resolved=resolved,
        info=info,
        args=kwargs,
        node_type_name="NoteType",
        default_manager=Note._default_manager,
    )


def q_note(
    info: strawberry.Info,
    id: Annotated[
        strawberry.ID,
        strawberry.argument(name="id", description="The ID of the object"),
    ] = strawberry.UNSET,
) -> None | (Annotated[NoteType, strawberry.lazy("config.graphql.annotation_types")]):
    return get_node_from_global_id(info, id, only_type_name="NoteType")


@graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_MEDIUM"))
def _resolve_Query_geographic_annotations_for_corpus(
    root, info, corpus_id, bbox=None, zoom=None, label_types=None
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_queries.py:1167

    Port of AnnotationQueryMixin.resolve_geographic_annotations_for_corpus

    Resolve corpus-scoped pins via :class:`GeographicAnnotationService`.

    ``zoom`` is accepted for forward compatibility with the map UI but
    is not consumed today; the server returns all label types and the
    frontend picks the right one for the current cluster threshold.
    """
    from opencontractserver.annotations.services import (
        BBox,
        GeographicAnnotationService,
    )
    from opencontractserver.corpuses.models import Corpus

    django_pk = from_global_id(corpus_id)[1]
    corpus = BaseService.get_or_none(
        Corpus, django_pk, info.context.user, request=info.context
    )
    # IDOR-safe: same empty response whether the corpus doesn't exist or
    # is invisible — never leaks existence.
    if corpus is None:
        return []

    # ``BBox`` raises ``ValueError`` on a degenerate ``south > north``
    # box, and ``aggregate_for_corpus`` raises on an unknown
    # ``label_types`` entry. Surface both as clean ``GraphQLError`` so
    # the client gets an actionable, sanitised message instead of an
    # unhandled-exception 500.
    try:
        bbox_obj = (
            BBox(
                south=bbox.south,
                west=bbox.west,
                north=bbox.north,
                east=bbox.east,
            )
            if bbox is not None
            else None
        )
        return GeographicAnnotationService.aggregate_for_corpus(
            user=info.context.user,
            corpus=corpus,
            bbox=bbox_obj,
            label_types=label_types,
            request=info.context,
        )
    except ValueError as exc:
        raise GraphQLError(str(exc)) from exc


def q_geographic_annotations_for_corpus(
    info: strawberry.Info,
    corpus_id: Annotated[
        strawberry.ID, strawberry.argument(name="corpusId")
    ] = strawberry.UNSET,
    bbox: Annotated[
        BBoxInputType | None, strawberry.argument(name="bbox")
    ] = strawberry.UNSET,
    zoom: Annotated[
        float | None,
        strawberry.argument(
            name="zoom",
            description="Optional map zoom level used by the consumer to pick a label type. Not currently consumed server-side — the resolver returns every label type and lets the client decide which to render at the current zoom. ``Float`` accommodates the fractional zoom levels (e.g. 12.5) that Mapbox / MapLibre use natively.",
        ),
    ] = strawberry.UNSET,
    label_types: Annotated[
        list[str | None] | None,
        strawberry.argument(
            name="labelTypes",
            description="Optional subset of label types to include: 'country', 'state', 'city'. Defaults to all three.",
        ),
    ] = strawberry.UNSET,
) -> list[GeographicAnnotationPinType | None] | None:
    kwargs = strip_unset(
        {"corpus_id": corpus_id, "bbox": bbox, "zoom": zoom, "label_types": label_types}
    )
    return _resolve_Query_geographic_annotations_for_corpus(None, info, **kwargs)


@graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_MEDIUM"))
def _resolve_Query_global_geographic_annotations(
    root, info, bbox=None, zoom=None, label_types=None
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_queries.py:1230

    Port of AnnotationQueryMixin.resolve_global_geographic_annotations

    Resolve global pins via :class:`GeographicAnnotationService`.

    No ``@login_required`` — the Discover page must work for anonymous
    visitors. ``Annotation.objects.visible_to_user`` enforces the
    anonymous-friendly visibility rules (public corpus + public
    document) inside the service.
    """
    from opencontractserver.annotations.services import (
        BBox,
        GeographicAnnotationService,
    )

    # Symmetric with ``resolve_geographic_annotations_for_corpus``:
    # convert ``ValueError`` from either ``BBox`` construction (degenerate
    # south > north box) or the service's label-type validation into a
    # ``GraphQLError`` rather than letting it escape as a generic 500.
    try:
        bbox_obj = (
            BBox(
                south=bbox.south,
                west=bbox.west,
                north=bbox.north,
                east=bbox.east,
            )
            if bbox is not None
            else None
        )
        return GeographicAnnotationService.aggregate_global(
            user=info.context.user,
            bbox=bbox_obj,
            label_types=label_types,
            request=info.context,
        )
    except ValueError as exc:
        raise GraphQLError(str(exc)) from exc


def q_global_geographic_annotations(
    info: strawberry.Info,
    bbox: Annotated[
        BBoxInputType | None, strawberry.argument(name="bbox")
    ] = strawberry.UNSET,
    zoom: Annotated[float | None, strawberry.argument(name="zoom")] = strawberry.UNSET,
    label_types: Annotated[
        list[str | None] | None, strawberry.argument(name="labelTypes")
    ] = strawberry.UNSET,
) -> list[GeographicAnnotationPinType | None] | None:
    kwargs = strip_unset({"bbox": bbox, "zoom": zoom, "label_types": label_types})
    return _resolve_Query_global_geographic_annotations(None, info, **kwargs)


QUERY_FIELDS = {
    "corpus_references": strawberry.field(
        resolver=q_corpus_references, name="corpusReferences"
    ),
    "governance_graph": strawberry.field(
        resolver=q_governance_graph,
        name="governanceGraph",
        description="The corpus-scoped reference web in node-link form: documents, statute sections, and external-citation ghost nodes, with mention-weighted LAW / LAW_EXTERNAL / DOCUMENT edges. Powers the Governance Graph panel on the Corpus Intelligence home.",
    ),
    "wanted_authorities": strawberry.field(
        resolver=q_wanted_authorities,
        name="wantedAuthorities",
        description="The missing-authority backlog: EXTERNAL law citations visible to the user, aggregated by authority prefix and ranked by mention volume — what to bootstrap next to resolve the most references.",
    ),
    "authority_frontier_stats": strawberry.field(
        resolver=q_authority_frontier_stats,
        name="authorityFrontierStats",
        description="Facet-aware per-discovery_state row counts for the authority-sources monitor's summary chips. Honours the non-state facets but not a state filter. SUPERUSER-ONLY (empty otherwise).",
    ),
    "authority_mapping_stats": strawberry.field(
        resolver=q_authority_mapping_stats,
        name="authorityMappingStats",
        description="Facet-aware per-source row counts for the authority-mappings panel's summary chips. Honours the search facet but not a source filter. SUPERUSER-ONLY (empty otherwise).",
    ),
    "authority_namespace_stats": strawberry.field(
        resolver=q_authority_namespace_stats,
        name="authorityNamespaceStats",
        description="Faceted per-jurisdiction / authority_type / scope row counts for the registry panel's summary chips. Honours the search facet but not the facet selects. SUPERUSER-ONLY (empty otherwise).",
    ),
    "authority_namespace_detail": strawberry.field(
        resolver=q_authority_namespace_detail,
        name="authorityNamespaceDetail",
        description="Everything about one body of law, string-joined across the authority models: the namespace + its aliases, in/out key-equivalences, discovery-queue rows, and reference demand. SUPERUSER-ONLY (null otherwise or for an unknown prefix).",
    ),
    "authority_source_providers": strawberry.field(
        resolver=q_authority_source_providers,
        name="authoritySourceProviders",
        description="The registered authority source providers (scrapers): US Code / eCFR / Federal Register / agentic web locator, with their supported prefixes, license, priority, enabled flag and whether the secrets vault holds credentials. SUPERUSER-ONLY (empty otherwise).",
    ),
    "annotations": strawberry.field(resolver=q_annotations, name="annotations"),
    "bulk_doc_relationships_in_corpus": strawberry.field(
        resolver=q_bulk_doc_relationships_in_corpus, name="bulkDocRelationshipsInCorpus"
    ),
    "bulk_doc_annotations_in_corpus": strawberry.field(
        resolver=q_bulk_doc_annotations_in_corpus, name="bulkDocAnnotationsInCorpus"
    ),
    "page_annotations": strawberry.field(
        resolver=q_page_annotations, name="pageAnnotations"
    ),
    "annotation": strawberry.field(resolver=q_annotation, name="annotation"),
    "relationships": strawberry.field(resolver=q_relationships, name="relationships"),
    "relationship": strawberry.field(resolver=q_relationship, name="relationship"),
    "annotation_labels": strawberry.field(
        resolver=q_annotation_labels, name="annotationLabels"
    ),
    "annotation_label": strawberry.field(
        resolver=q_annotation_label, name="annotationLabel"
    ),
    "labelsets": strawberry.field(resolver=q_labelsets, name="labelsets"),
    "labelset": strawberry.field(resolver=q_labelset, name="labelset"),
    "default_labelset": strawberry.field(
        resolver=q_default_labelset,
        name="defaultLabelset",
        description="The install-wide default LabelSet (is_default=True), or null if none has been seeded yet or the current user cannot see it. Used by the new-corpus modal to pre-fill the label set field.",
    ),
    "notes": strawberry.field(resolver=q_notes, name="notes"),
    "note": strawberry.field(resolver=q_note, name="note"),
    "geographic_annotations_for_corpus": strawberry.field(
        resolver=q_geographic_annotations_for_corpus,
        name="geographicAnnotationsForCorpus",
        description="Aggregated geographic pins for a single corpus. Pins are deduplicated by ``(label_type, canonical_name, lat, lng)`` and ship a bounded ``sample_document_ids`` preview rather than the full annotation row set. Document visibility uses MIN(document, corpus) so private documents inside a public corpus stay hidden.",
    ),
    "global_geographic_annotations": strawberry.field(
        resolver=q_global_geographic_annotations,
        name="globalGeographicAnnotations",
        description="Aggregated geographic pins across every annotation visible to the requesting user (the Discover map surface). Same shape as ``geographicAnnotationsForCorpus``.",
    ),
}
