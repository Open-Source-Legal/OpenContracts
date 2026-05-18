"""
GraphQL mutations for analysis-related operations.
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
from opencontractserver.analyzer.models import Analysis, Analyzer
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.tasks import delete_analysis_and_annotations_task
from opencontractserver.tasks.corpus_tasks import process_analyzer
from opencontractserver.tasks.permissioning_tasks import make_analysis_public_task
from opencontractserver.types.enums import PermissionTypes

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
            make_analysis_public_task.si(analysis_id=analysis_pk).apply_async()

            message = (
                "Starting an OpenContracts worker to make your analysis public! Underlying corpus must be made "
                "public too!"
            )
            ok = True

        except Exception as e:
            ok = False
            message = (
                f"ERROR - Could not make analysis public due to unexpected error: {e}"
            )

        return MakeAnalysisPublic(ok=ok, message=message)


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
            f"Parsed IDs - document_pk: {document_pk}, analyzer_pk: {analyzer_pk}, corpus_pk: {corpus_pk}"
        )
        logger.info(f"Analysis input data: {analysis_input_data}")

        if document_pk is None and corpus_pk is None:
            raise ValueError("One of document_pk and corpus_pk must be provided")

        not_found_msg = "Resource not found or you do not have permission."

        try:
            # Check permissions for document using visible_to_user()
            if document_pk:
                if (
                    not Document.objects.visible_to_user(user)
                    .filter(pk=document_pk)
                    .exists()
                ):
                    return StartDocumentAnalysisMutation(
                        ok=False, message=not_found_msg, obj=None
                    )

            # Check permissions for corpus using visible_to_user()
            if corpus_pk:
                if (
                    not Corpus.objects.visible_to_user(user)
                    .filter(pk=corpus_pk)
                    .exists()
                ):
                    return StartDocumentAnalysisMutation(
                        ok=False, message=not_found_msg, obj=None
                    )

            analyzer = Analyzer.objects.get(pk=analyzer_pk)
            logger.info(
                f"Found analyzer: {analyzer.id} with task_name: {analyzer.task_name}"
            )

            analysis = process_analyzer(
                user_id=user.id,
                analyzer=analyzer,
                corpus_id=corpus_pk,
                document_ids=[document_pk] if document_pk else None,
                corpus_action=None,
                analysis_input_data=analysis_input_data,
            )

            logger.info(
                f"Analysis created with ID: {analysis.id if analysis else 'None'}"
            )

            record_event(
                "analysis_started",
                {
                    "env": settings.MODE,
                    "user_id": info.context.user.id,
                },
            )

            return StartDocumentAnalysisMutation(
                ok=True, message="SUCCESS", obj=analysis
            )
        except Exception as e:
            logger.error(f"StartDocumentAnalysisMutation error: {e}", exc_info=True)
            return StartDocumentAnalysisMutation(ok=False, message=f"Error: {str(e)}")


class DeleteAnalysisMutation(graphene.Mutation):
    ok = graphene.Boolean()
    message = graphene.String()

    class Arguments:
        id = graphene.String(required=True)

    @login_required
    def mutate(root, info, id) -> "DeleteAnalysisMutation":

        # ok = False
        # message = "Could not complete"

        analysis_pk = from_global_id(id)[1]
        analysis = Analysis.objects.visible_to_user(info.context.user).get(
            id=analysis_pk
        )

        # Check the object isn't locked by another user
        if analysis.user_lock is not None:
            if info.context.user.id != analysis.user_lock_id:
                raise PermissionError(
                    "Specified object is locked by another user. Cannot be " "deleted."
                )

        # We ARE OK with deleting something that's been locked by the backend, however, as sh@t happens, and we want
        # frontend users to be able to delete things that are hanging or taking too long and start over / abandon them.

        if not analysis.user_can(
            info.context.user, PermissionTypes.DELETE, request=info.context
        ):
            raise PermissionError("You don't have permission to delete this analysis.")

        # Kick off an async task to delete the analysis (as it can be very large)
        delete_analysis_and_annotations_task.si(analysis_pk=analysis_pk).apply_async()

        return DeleteAnalysisMutation(ok=True, message="SUCCESS")
