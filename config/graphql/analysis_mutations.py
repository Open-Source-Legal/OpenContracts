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
from typing import Annotated

import strawberry
from django.conf import settings
from graphql_relay import from_global_id

from config.graphql._util import strip_unset
from config.graphql.core.auth import PermissionDenied, user_passes_test
from config.graphql.core.relay import (
    register_type,
)
from config.graphql.core.scalars import GenericScalar
from config.graphql.ratelimits import RateLimits, graphql_ratelimit
from config.telemetry import record_event
from opencontractserver.analyzer.services import AnalysisLifecycleService

logger = logging.getLogger(__name__)


@strawberry.type(name="StartDocumentAnalysisMutation")
class StartDocumentAnalysisMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[AnalysisType, strawberry.lazy("config.graphql.extract_types")]
    ) = strawberry.field(name="obj", default=None)


register_type(
    "StartDocumentAnalysisMutation", StartDocumentAnalysisMutation, model=None
)


@strawberry.type(name="DeleteAnalysisMutation")
class DeleteAnalysisMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("DeleteAnalysisMutation", DeleteAnalysisMutation, model=None)


@strawberry.type(name="MakeAnalysisPublic")
class MakeAnalysisPublic:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[AnalysisType, strawberry.lazy("config.graphql.extract_types")]
    ) = strawberry.field(name="obj", default=None)


register_type("MakeAnalysisPublic", MakeAnalysisPublic, model=None)


def _mutate_StartDocumentAnalysisMutation(
    payload_cls,
    root,
    info,
    analyzer_id,
    document_id=None,
    corpus_id=None,
    analysis_input_data=None,
):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:79

    Port of StartDocumentAnalysisMutation.mutate

    Starts a document or corpus analysis using the specified analyzer.
    Accepts optional analysis_input_data for analyzers that need
    user-provided parameters.
    """
    # @login_required (graphql_jwt) — inlined because mutate stubs take
    # ``payload_cls`` as their first positional argument, which does not
    # match core.auth's ``(root, info, ...)`` calling convention.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

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
        return payload_cls(ok=False, message=f"Error: {str(e)}")

    if not result.ok:
        return payload_cls(ok=False, message=result.error, obj=None)

    record_event(
        "analysis_started",
        {
            "env": settings.MODE,
            "user_id": info.context.user.id,
        },
    )

    return payload_cls(ok=True, message="SUCCESS", obj=result.value)


def m_start_analysis_on_doc(
    info: strawberry.Info,
    analysis_input_data: Annotated[
        GenericScalar | None,
        strawberry.argument(
            name="analysisInputData",
            description="Optional arguments to be passed to the analyzer.",
        ),
    ] = strawberry.UNSET,
    analyzer_id: Annotated[
        strawberry.ID,
        strawberry.argument(
            name="analyzerId", description="Id of the analyzer to use."
        ),
    ] = strawberry.UNSET,
    corpus_id: Annotated[
        strawberry.ID | None,
        strawberry.argument(
            name="corpusId",
            description="Optional Id of the corpus to associate with the analysis.",
        ),
    ] = strawberry.UNSET,
    document_id: Annotated[
        strawberry.ID | None,
        strawberry.argument(
            name="documentId", description="Id of the document to be analyzed."
        ),
    ] = strawberry.UNSET,
) -> StartDocumentAnalysisMutation | None:
    kwargs = strip_unset(
        {
            "analysis_input_data": analysis_input_data,
            "analyzer_id": analyzer_id,
            "corpus_id": corpus_id,
            "document_id": document_id,
        }
    )
    return _mutate_StartDocumentAnalysisMutation(
        StartDocumentAnalysisMutation, None, info, **kwargs
    )


def _mutate_DeleteAnalysisMutation(payload_cls, root, info, id):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:145

    Port of DeleteAnalysisMutation.mutate
    """
    # @login_required (graphql_jwt) — inlined; see
    # _mutate_StartDocumentAnalysisMutation.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    # Unified message blocks IDOR enumeration. Bad global-id, missing
    # analysis, and "exists but forbidden" all surface the same string.
    not_found_msg = "Analysis not found or you don't have permission to delete it."

    try:
        analysis_pk = from_global_id(id)[1]
    except Exception:
        return payload_cls(ok=False, message=not_found_msg)

    result = AnalysisLifecycleService.delete_analysis(
        info.context.user, analysis_pk, request=info.context
    )
    if not result.ok:
        return payload_cls(ok=False, message=result.error)
    return payload_cls(ok=True, message="SUCCESS")


def m_delete_analysis(
    info: strawberry.Info,
    id: Annotated[str, strawberry.argument(name="id")] = strawberry.UNSET,
) -> DeleteAnalysisMutation | None:
    kwargs = strip_unset({"id": id})
    return _mutate_DeleteAnalysisMutation(DeleteAnalysisMutation, None, info, **kwargs)


def _mutate_MakeAnalysisPublic(payload_cls, root, info, analysis_id):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:35

    Port of MakeAnalysisPublic.mutate
    """

    # The graphene decorator stack is applied to an inner ``mutate`` (the
    # stub itself takes ``payload_cls`` first, which does not match the
    # decorators' ``(root, info, ...)`` calling convention). Naming the
    # inner function ``mutate`` also keeps the rate limiter's default
    # cache group ("mutate", the decorated function's name) identical to
    # the graphene deployment.
    @user_passes_test(lambda user: user.is_superuser)
    @graphql_ratelimit(rate=RateLimits.ADMIN_OPERATION)
    def mutate(root, info, analysis_id):

        try:
            analysis_pk = from_global_id(analysis_id)[1]
            result = AnalysisLifecycleService.make_public(
                info.context.user, analysis_pk, request=info.context
            )
            return payload_cls(
                ok=result.ok,
                message=result.value if result.ok else result.error,
            )

        except Exception as e:
            return payload_cls(
                ok=False,
                message=(
                    f"ERROR - Could not make analysis public due to unexpected error: {e}"
                ),
            )

    return mutate(root, info, analysis_id=analysis_id)


def m_make_analysis_public(
    info: strawberry.Info,
    analysis_id: Annotated[
        str,
        strawberry.argument(
            name="analysisId", description="Analysis id to make public (superuser only)"
        ),
    ] = strawberry.UNSET,
) -> MakeAnalysisPublic | None:
    kwargs = strip_unset({"analysis_id": analysis_id})
    return _mutate_MakeAnalysisPublic(MakeAnalysisPublic, None, info, **kwargs)


MUTATION_FIELDS = {
    "start_analysis_on_doc": strawberry.field(
        resolver=m_start_analysis_on_doc, name="startAnalysisOnDoc"
    ),
    "delete_analysis": strawberry.field(
        resolver=m_delete_analysis, name="deleteAnalysis"
    ),
    "make_analysis_public": strawberry.field(
        resolver=m_make_analysis_public, name="makeAnalysisPublic"
    ),
}
