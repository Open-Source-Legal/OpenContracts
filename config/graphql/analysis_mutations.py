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




@strawberry.type(name="StartDocumentAnalysisMutation")
class StartDocumentAnalysisMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    message: Optional[str] = strawberry.field(name="message", default=None)
    obj: Optional[Annotated["AnalysisType", strawberry.lazy("config.graphql.extract_types")]] = strawberry.field(name="obj", default=None)


register_type("StartDocumentAnalysisMutation", StartDocumentAnalysisMutation, model=None)


@strawberry.type(name="DeleteAnalysisMutation")
class DeleteAnalysisMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    message: Optional[str] = strawberry.field(name="message", default=None)


register_type("DeleteAnalysisMutation", DeleteAnalysisMutation, model=None)


@strawberry.type(name="MakeAnalysisPublic")
class MakeAnalysisPublic:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    message: Optional[str] = strawberry.field(name="message", default=None)
    obj: Optional[Annotated["AnalysisType", strawberry.lazy("config.graphql.extract_types")]] = strawberry.field(name="obj", default=None)


register_type("MakeAnalysisPublic", MakeAnalysisPublic, model=None)


def _mutate_StartDocumentAnalysisMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:79

    Port of StartDocumentAnalysisMutation.mutate
    """
    raise NotImplementedError("_mutate_StartDocumentAnalysisMutation not yet ported — see manifest")


def m_start_analysis_on_doc(info: strawberry.Info, analysis_input_data: Annotated[Optional[GenericScalar], strawberry.argument(name="analysisInputData", description='Optional arguments to be passed to the analyzer.')] = strawberry.UNSET, analyzer_id: Annotated[strawberry.ID, strawberry.argument(name="analyzerId", description='Id of the analyzer to use.')] = strawberry.UNSET, corpus_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="corpusId", description='Optional Id of the corpus to associate with the analysis.')] = strawberry.UNSET, document_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="documentId", description='Id of the document to be analyzed.')] = strawberry.UNSET) -> Optional["StartDocumentAnalysisMutation"]:
    kwargs = strip_unset({"analysis_input_data": analysis_input_data, "analyzer_id": analyzer_id, "corpus_id": corpus_id, "document_id": document_id})
    return _mutate_StartDocumentAnalysisMutation(StartDocumentAnalysisMutation, None, info, **kwargs)


def _mutate_DeleteAnalysisMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:145

    Port of DeleteAnalysisMutation.mutate
    """
    raise NotImplementedError("_mutate_DeleteAnalysisMutation not yet ported — see manifest")


def m_delete_analysis(info: strawberry.Info, id: Annotated[str, strawberry.argument(name="id")] = strawberry.UNSET) -> Optional["DeleteAnalysisMutation"]:
    kwargs = strip_unset({"id": id})
    return _mutate_DeleteAnalysisMutation(DeleteAnalysisMutation, None, info, **kwargs)


def _mutate_MakeAnalysisPublic(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:35

    Port of MakeAnalysisPublic.mutate
    """
    raise NotImplementedError("_mutate_MakeAnalysisPublic not yet ported — see manifest")


def m_make_analysis_public(info: strawberry.Info, analysis_id: Annotated[str, strawberry.argument(name="analysisId", description='Analysis id to make public (superuser only)')] = strawberry.UNSET) -> Optional["MakeAnalysisPublic"]:
    kwargs = strip_unset({"analysis_id": analysis_id})
    return _mutate_MakeAnalysisPublic(MakeAnalysisPublic, None, info, **kwargs)



MUTATION_FIELDS = {
    "start_analysis_on_doc": strawberry.field(resolver=m_start_analysis_on_doc, name="startAnalysisOnDoc"),
    "delete_analysis": strawberry.field(resolver=m_delete_analysis, name="deleteAnalysis"),
    "make_analysis_public": strawberry.field(resolver=m_make_analysis_public, name="makeAnalysisPublic"),
}
