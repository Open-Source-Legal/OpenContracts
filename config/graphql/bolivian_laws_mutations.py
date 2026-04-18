"""GraphQL mutation for the Bolivian Laws RAG service.

Single mutation: ``askBolivianLaw(question, areas?)``.

- If ``areas`` is empty / null: routes through the orchestrator agent
  which decides which specialist(s) to consult.
- If ``areas`` is given: skips orchestration and consults the listed
  specialists directly in parallel (cheaper, deterministic).
"""

from __future__ import annotations

import logging

import graphene
from asgiref.sync import async_to_sync
from graphql_jwt.decorators import login_required

from opencontractserver.bolivian_laws.constants import LegalArea
from opencontractserver.bolivian_laws.services.agents import (
    ask_orchestrator,
    ask_specialists,
)

logger = logging.getLogger(__name__)


class BolivianLawSourceType(graphene.ObjectType):
    """Source citation returned by the orchestrator/specialists."""

    area = graphene.String(required=True)
    document_id = graphene.Int(required=False)
    snippet = graphene.String(required=True)
    similarity_score = graphene.Float(required=True)


class AskBolivianLawMutation(graphene.Mutation):
    """Query the Bolivian Laws RAG service.

    Returns a synthesised answer plus per-source citations tagged by
    legal area.
    """

    class Arguments:
        question = graphene.String(
            required=True,
            description="Pregunta del usuario en lenguaje natural.",
        )
        areas = graphene.List(
            graphene.String,
            required=False,
            description=(
                "Lista opcional de áreas (constitucional, penal, civil, "
                "administrativo, laboral, tributario, familia, comercial, "
                "agrario, ambiental, otros). Si se provee, se omite el "
                "orquestador y se consultan en paralelo."
            ),
        )
        conversation_id = graphene.Int(
            required=False,
            description="ID de conversación a continuar (opcional).",
        )

    ok = graphene.Boolean()
    message = graphene.String()
    answer = graphene.String()
    consulted_areas = graphene.List(graphene.String)
    sources = graphene.List(BolivianLawSourceType)
    conversation_id = graphene.Int()

    @staticmethod
    @login_required
    def mutate(root, info, question, areas=None, conversation_id=None):
        question = (question or "").strip()
        if not question:
            return AskBolivianLawMutation(
                ok=False,
                message="Question must be non-empty.",
                answer="",
                consulted_areas=[],
                sources=[],
            )

        valid_areas = {a.value for a in LegalArea}
        if areas:
            cleaned: list[str] = []
            for a in areas:
                a_norm = (a or "").strip().lower()
                if a_norm not in valid_areas:
                    return AskBolivianLawMutation(
                        ok=False,
                        message=f"Unknown area: {a!r}",
                        answer="",
                        consulted_areas=[],
                        sources=[],
                    )
                cleaned.append(a_norm)
            areas = cleaned

        user_id = info.context.user.pk if info.context.user else None

        try:
            if areas:
                response = async_to_sync(ask_specialists)(
                    areas, question, user_id=user_id
                )
            else:
                response = async_to_sync(ask_orchestrator)(
                    question,
                    user_id=user_id,
                    conversation_id=conversation_id,
                )
        except Exception as exc:
            logger.exception("askBolivianLaw failed")
            return AskBolivianLawMutation(
                ok=False,
                message=f"Internal error: {exc}",
                answer="",
                consulted_areas=[],
                sources=[],
            )

        return AskBolivianLawMutation(
            ok=True,
            message="ok",
            answer=response.answer,
            consulted_areas=response.consulted_areas,
            conversation_id=response.conversation_id,
            sources=[
                BolivianLawSourceType(
                    area=s.area,
                    document_id=s.document_id,
                    snippet=s.snippet,
                    similarity_score=s.similarity_score,
                )
                for s in response.sources
            ],
        )
