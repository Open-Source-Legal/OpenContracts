"""
GraphQL mutations for analysis-related operations.

Permission and lifecycle logic lives in
:class:`opencontractserver.analyzer.services.AnalysisLifecycleService`;
the mutations decode global IDs and forward to the service.
"""

import logging

import graphene
from django.conf import settings
from graphene.types.generic import GenericScalar
from graphql_jwt.decorators import login_required, user_passes_test
from graphql_relay import from_global_id

from config.graphql.graphene_types import AnalysisType
from config.graphql.ratelimits import RateLimits, graphql_ratelimit
from config.telemetry import record_event
from opencontractserver.analyzer.services import AnalysisLifecycleService

logger = logging.getLogger(__name__)


class MakeAnalysisPublic(graphene.Mutation):
    class Arguments:
        analysis_id = graphene.String(
            required=True, description="Analysis id to make public (superuser only)"
        )

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(AnalysisType)

    @user_passes_test(lambda user: user.is_superuser)
    @graphql_ratelimit(rate=RateLimits.ADMIN_OPERATION)
    def mutate(root, info, analysis_id) -> "MakeAnalysisPublic":

        try:
            analysis_pk = from_global_id(analysis_id)[1]
            result = AnalysisLifecycleService.make_public(
                info.context.user, analysis_pk, request=info.context
            )
            return MakeAnalysisPublic(
                ok=result.ok,
                message=result.value if result.ok else result.error,
            )

        except Exception as e:
            return MakeAnalysisPublic(
                ok=False,
                message=(
                    f"ERROR - Could not make analysis public due to unexpected error: {e}"
                ),
            )


class StartDocumentAnalysisMutation(graphene.Mutation):
    class Arguments:
        document_id = graphene.ID(
            required=False, description="Id of the document to be analyzed."
        )
        analyzer_id = graphene.ID(
            required=True, description="Id of the analyzer to use."
        )
        corpus_id = graphene.ID(
            required=False,
            description="Optional Id of the corpus to associate with the analysis.",
        )
        analysis_input_data = GenericScalar(
            required=False,
            description="Optional arguments to be passed to the analyzer.",
        )

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(AnalysisType)

    @login_required
    def mutate(
        root,
        info,
        analyzer_id,
        document_id=None,
        corpus_id=None,
        analysis_input_data=None,
    ) -> "StartDocumentAnalysisMutation":
        """
        Starts a document or corpus analysis using the specified analyzer.
        Accepts optional analysis_input_data for analyzers that need
        user-provided parameters.
        """

        user = info.context.user
        logger.info(f"StartDocumentAnalysisMutation called by user {user.id}")

        document_pk = from_global_id(document_id)[1] if document_id else None
        analyzer_pk = from_global_id(analyzer_id)[1]
        corpus_pk = from_global_id(corpus_id)[1] if corpus_id else None

        logger.info(
            f"Parsed IDs - document_pk: {document_pk}, analyzer_pk: {analyzer_pk}, "
            f"corpus_pk: {corpus_pk}"
        )
        logger.info(f"Analysis input data: {analysis_input_data}")

        try:
            result = AnalysisLifecycleService.start_document_analysis(
                user,
                analyzer_pk=analyzer_pk,
                document_pk=document_pk,
                corpus_pk=corpus_pk,
                analysis_input_data=analysis_input_data,
                request=info.context,
            )
        except Exception as e:
            logger.error(f"StartDocumentAnalysisMutation error: {e}", exc_info=True)
            return StartDocumentAnalysisMutation(ok=False, message=f"Error: {str(e)}")

        if not result.ok:
            return StartDocumentAnalysisMutation(
                ok=False, message=result.error, obj=None
            )

        record_event(
            "analysis_started",
            {
                "env": settings.MODE,
                "user_id": info.context.user.id,
            },
        )

        return StartDocumentAnalysisMutation(
            ok=True, message="SUCCESS", obj=result.value
        )


class DeleteAnalysisMutation(graphene.Mutation):
    ok = graphene.Boolean()
    message = graphene.String()

    class Arguments:
        id = graphene.String(required=True)

    @login_required
    def mutate(root, info, id) -> "DeleteAnalysisMutation":

        # Unified message blocks IDOR enumeration. Bad global-id, missing
        # analysis, and "exists but forbidden" all surface the same string.
        not_found_msg = "Analysis not found or you don't have permission to delete it."

        try:
            analysis_pk = from_global_id(id)[1]
        except Exception:
            return DeleteAnalysisMutation(ok=False, message=not_found_msg)

        result = AnalysisLifecycleService.delete_analysis(
            info.context.user, analysis_pk, request=info.context
        )
        if not result.ok:
            return DeleteAnalysisMutation(ok=False, message=result.error)
        return DeleteAnalysisMutation(ok=True, message="SUCCESS")
