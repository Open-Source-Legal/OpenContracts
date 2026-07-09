"""GraphQL mutations for Legal AI review workflows."""

from __future__ import annotations

import logging
from typing import Literal

import graphene
from asgiref.sync import async_to_sync
from graphene.types.generic import GenericScalar
from graphql_jwt.decorators import login_required
from graphql_relay import from_global_id
from pydantic import BaseModel, Field

from config.graphql.ratelimits import RateLimits, graphql_ratelimit
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.llms.api import AgentAPI
from opencontractserver.shared.services.base import BaseService
from opencontractserver.types.enums import PermissionTypes

logger = logging.getLogger(__name__)


class LegalReviewFinding(BaseModel):
    """Structured single finding returned by the legal review agent."""

    risk_level: Literal["low", "medium", "high", "critical"] = Field(
        description="Risk severity for this finding."
    )
    clause_type: str = Field(description="Short clause or issue category.")
    issue: str = Field(description="What is problematic or worth review.")
    recommendation: str = Field(description="Practical next step for counsel.")
    quote: str | None = Field(
        default=None,
        description="Short supporting quote from the document, if available.",
    )


class LegalReviewResult(BaseModel):
    """Top-level structured contract review result."""

    summary: str = Field(description="Brief overall legal review summary.")
    findings: list[LegalReviewFinding] = Field(
        default_factory=list,
        description="Prioritized legal review findings.",
    )


def _decode_global_id(value: str) -> str | None:
    try:
        return from_global_id(value)[1]
    except Exception:
        return None


def _model_to_dict(model: BaseModel) -> dict:
    dump = getattr(model, "model_dump", None)
    if callable(dump):
        return dump()
    return model.dict()


class RunLegalReview(graphene.Mutation):
    """Run a first-pass legal review for one document inside a corpus."""

    class Arguments:
        document_id = graphene.ID(required=True)
        corpus_id = graphene.ID(required=True)

    ok = graphene.Boolean()
    message = graphene.String()
    summary = graphene.String()
    findings = GenericScalar()
    source_annotation_ids = graphene.List(graphene.Int)

    @login_required
    @graphql_ratelimit(rate=RateLimits.AI_ANALYSIS)
    def mutate(root, info, document_id: str, corpus_id: str) -> "RunLegalReview":
        user = info.context.user

        document_pk = _decode_global_id(document_id)
        corpus_pk = _decode_global_id(corpus_id)
        if not document_pk or not corpus_pk:
            return RunLegalReview(
                ok=False,
                message="Dokument oder Akte konnte nicht gefunden werden.",
                summary="",
                findings=[],
                source_annotation_ids=[],
            )

        document = BaseService.get_or_none(
            Document, document_pk, user, request=info.context
        )
        corpus = BaseService.get_or_none(Corpus, corpus_pk, user, request=info.context)

        if document is None or corpus is None:
            return RunLegalReview(
                ok=False,
                message="Dokument oder Akte konnte nicht gefunden werden.",
                summary="",
                findings=[],
                source_annotation_ids=[],
            )

        if BaseService.require_permission(
            document, user, PermissionTypes.READ, request=info.context
        ) or BaseService.require_permission(
            corpus, user, PermissionTypes.READ, request=info.context
        ):
            return RunLegalReview(
                ok=False,
                message="Keine Berechtigung für diese Vertragsprüfung.",
                summary="",
                findings=[],
                source_annotation_ids=[],
            )

        in_corpus = DocumentPath.objects.filter(
            document=document,
            corpus=corpus,
            is_current=True,
            is_deleted=False,
        ).exists()
        if not in_corpus:
            return RunLegalReview(
                ok=False,
                message="Das Dokument ist nicht Teil dieser Akte.",
                summary="",
                findings=[],
                source_annotation_ids=[],
            )

        prompt = (
            "Prüfe dieses Dokument aus Sicht einer anwaltlichen Vertragsprüfung. "
            "Fokussiere dich auf Haftung, Laufzeit, Kündigung, Vertragsstrafen, "
            "Zahlungspflichten, unklare Pflichten und ungewöhnliche Risiken. "
            "Gib maximal fünf priorisierte Findings zurück. Formuliere knapp, "
            "praktisch und mit einer konkreten Empfehlung pro Finding."
        )

        try:
            result, source_ids = async_to_sync(
                AgentAPI.get_structured_response_and_sources_from_document
            )(
                document=document,
                corpus=corpus,
                prompt=prompt,
                target_type=LegalReviewResult,
                user_id=user.id,
                temperature=0.1,
                max_tokens=2500,
                tools=[
                    "load_document_summary",
                    "get_document_text_length",
                    "load_document_text",
                    "search_exact_text",
                ],
            )
        except Exception:
            logger.exception("Legal review LLM call failed")
            return RunLegalReview(
                ok=False,
                message=(
                    "Die KI-Prüfung konnte nicht ausgeführt werden. "
                    "Bitte LLM-Konfiguration und Dokumentverarbeitung prüfen."
                ),
                summary="",
                findings=[],
                source_annotation_ids=[],
            )

        if result is None:
            return RunLegalReview(
                ok=False,
                message="Die KI-Prüfung hat kein auswertbares Ergebnis geliefert.",
                summary="",
                findings=[],
                source_annotation_ids=source_ids,
            )

        payload = _model_to_dict(result)
        findings = [
            {
                "riskLevel": finding.get("risk_level", "medium"),
                "clauseType": finding.get("clause_type", ""),
                "issue": finding.get("issue", ""),
                "recommendation": finding.get("recommendation", ""),
                "quote": finding.get("quote"),
            }
            for finding in payload.get("findings", [])
            if isinstance(finding, dict)
        ]

        return RunLegalReview(
            ok=True,
            message="Vertragsprüfung abgeschlossen.",
            summary=payload.get("summary", ""),
            findings=findings,
            source_annotation_ids=source_ids,
        )
