"""GraphQL type definitions for extract and analysis types."""

import graphene
from graphene import relay
from graphene.types.generic import GenericScalar
from graphene_django import DjangoObjectType
from graphql_relay import from_global_id

from config.graphql.annotation_types import AnnotationLabelType, AnnotationType
from config.graphql.base import CountableConnection
from config.graphql.document_types import DocumentType
from config.graphql.permissioning.permission_annotator.mixins import (
    AnnotatePermissionsForReadMixin,
)
from opencontractserver.analyzer.models import Analysis, Analyzer, GremlinEngine
from opencontractserver.constants.annotations import MAX_DATACELL_FIRST
from opencontractserver.extracts.models import Column, Datacell, Extract, Fieldset


class ColumnType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    validation_config = GenericScalar()
    default_value = GenericScalar()

    class Meta:
        model = Column
        interfaces = [relay.Node]
        connection_class = CountableConnection


class FieldsetType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    in_use = graphene.Boolean(
        description="True if the fieldset is used in any extract that has started."
    )
    full_column_list = graphene.List(ColumnType)

    class Meta:
        model = Fieldset
        interfaces = [relay.Node]
        connection_class = CountableConnection

    def resolve_in_use(self, info) -> bool:
        """
        Returns True if the fieldset is used in any extract that has started.
        """
        return self.extracts.filter(started__isnull=False).exists()

    def resolve_full_column_list(self, info):
        return self.columns.all()


class DatacellType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    data = GenericScalar()
    corrected_data = GenericScalar()
    full_source_list = graphene.List(AnnotationType)

    def resolve_full_source_list(self, info):
        return self.sources.all()

    class Meta:
        model = Datacell
        interfaces = [relay.Node]
        connection_class = CountableConnection


class ExtractType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    full_datacell_list = graphene.List(
        DatacellType,
        first=graphene.Int(
            description=(
                "Optional cap on the number of datacells returned. When "
                "provided, the resolver slices the queryset after permission "
                "filtering so the payload stays bounded for large extracts."
            ),
        ),
    )
    full_document_list = graphene.List(DocumentType)

    @classmethod
    def get_node(cls, info, id):
        """
        Override the default node resolution to apply permission checks.
        """
        from opencontractserver.annotations.query_optimizer import ExtractQueryOptimizer

        has_perm, extract = ExtractQueryOptimizer.check_extract_permission(
            info.context.user, int(id)
        )
        return extract if has_perm else None

    class Meta:
        model = Extract
        interfaces = [relay.Node]
        connection_class = CountableConnection

    def resolve_full_datacell_list(self, info, first=None):
        from opencontractserver.annotations.query_optimizer import ExtractQueryOptimizer

        qs = ExtractQueryOptimizer.get_extract_datacells(
            self, info.context.user, document_id=None
        )
        # Bound the payload when `first` is supplied. Negative / zero values
        # are treated as "no cap" so misconfigured clients can't accidentally
        # blank the grid — the frontend's row guard still handles too-many-rows.
        if first is not None and first > 0:
            qs = qs[: min(first, MAX_DATACELL_FIRST)]
        return qs

    def resolve_full_document_list(self, info):
        from opencontractserver.types.enums import PermissionTypes
        from opencontractserver.utils.permissioning import user_has_permission_for_obj

        # Filter to only documents user can read
        if info.context.user.is_superuser:
            return self.documents.all()

        readable_docs = []
        for doc in self.documents.all():
            if user_has_permission_for_obj(
                info.context.user,
                doc,
                PermissionTypes.READ,
                include_group_permissions=True,
            ):
                readable_docs.append(doc)
        return readable_docs


class AnalyzerType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    analyzer_id = graphene.String()

    def resolve_analyzer_id(self, info):
        return self.id.__str__()

    input_schema = GenericScalar(
        description="JSONSchema describing the analyzer's expected input if provided."
    )

    manifest = GenericScalar()

    full_label_list = graphene.List(AnnotationLabelType)

    def resolve_full_label_list(self, info):
        return self.annotation_labels.all()

    def resolve_icon(self, info):
        return "" if not self.icon else info.context.build_absolute_uri(self.icon.url)

    class Meta:
        model = Analyzer
        interfaces = [relay.Node]
        connection_class = CountableConnection


class GremlinEngineType_READ(AnnotatePermissionsForReadMixin, DjangoObjectType):
    class Meta:
        model = GremlinEngine
        exclude = ("api_key",)
        interfaces = [relay.Node]
        connection_class = CountableConnection


class GremlinEngineType_WRITE(AnnotatePermissionsForReadMixin, DjangoObjectType):
    class Meta:
        model = GremlinEngine
        interfaces = [relay.Node]
        connection_class = CountableConnection


class AnalysisType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    full_annotation_list = graphene.List(
        AnnotationType,
        document_id=graphene.ID(),
    )

    def resolve_full_annotation_list(self, info, document_id=None):
        from opencontractserver.annotations.query_optimizer import (
            AnalysisQueryOptimizer,
        )

        if document_id is not None:
            document_pk = int(from_global_id(document_id)[1])
        else:
            document_pk = None

        return AnalysisQueryOptimizer.get_analysis_annotations(
            self, info.context.user, document_id=document_pk
        )

    @classmethod
    def get_node(cls, info, id):
        """
        Override the default node resolution to apply permission checks.
        """
        from opencontractserver.annotations.query_optimizer import (
            AnalysisQueryOptimizer,
        )

        has_perm, analysis = AnalysisQueryOptimizer.check_analysis_permission(
            info.context.user, int(id)
        )
        return analysis if has_perm else None

    class Meta:
        model = Analysis
        interfaces = [relay.Node]
        connection_class = CountableConnection
