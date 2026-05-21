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
from opencontractserver.utils.permissioning import get_for_user_or_none

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

        # Unified message blocks IDOR enumeration: same response whether the
        # analysis doesn't exist, the caller can't see it, or they can see
        # it but lack DELETE permission. Returned via the standard ok=False
        # envelope (matches every other mutation migrated in Phase D) — the
        # previous mix of Analysis.DoesNotExist + PermissionError surfaced
        # different GraphQL response shapes for each branch and leaked
        # object existence to anyone with a guessable pk.
        not_found_msg = "Analysis not found or you don't have permission to delete it."

        # ``from_global_id`` raises a bare ``Exception`` (via
        # ``binascii.Error``) on malformed base64 ids; route that through
        # the same unified IDOR envelope rather than letting it surface
        # as a GraphQL ``errors`` entry.
        try:
            analysis_pk = from_global_id(id)[1]
        except Exception:
            return DeleteAnalysisMutation(ok=False, message=not_found_msg)
        analysis = get_for_user_or_none(Analysis, analysis_pk, info.context.user)
        if analysis is None:
            return DeleteAnalysisMutation(ok=False, message=not_found_msg)

        # Lock check stays its own error path — the lock is observable state
        # to anyone who can READ the analysis (so it does NOT leak existence).
        # We ARE OK with deleting something locked by the backend itself —
        # processing can stall and users need to abandon hung analyses.
        if analysis.user_lock is not None:
            if info.context.user.id != analysis.user_lock_id:
                return DeleteAnalysisMutation(
                    ok=False,
                    message=(
                        "Specified object is locked by another user. "
                        "Cannot be deleted."
                    ),
                )

        if not analysis.user_can(
            info.context.user, PermissionTypes.DELETE, request=info.context
        ):
            return DeleteAnalysisMutation(ok=False, message=not_found_msg)

        # Kick off an async task to delete the analysis (as it can be very large)
        delete_analysis_and_annotations_task.si(analysis_pk=analysis_pk).apply_async()

        return DeleteAnalysisMutation(ok=True, message="SUCCESS")
