"""GraphQL mutations for deep-research reports."""

import logging

import graphene
from graphql_jwt.decorators import login_required
from graphql_relay import from_global_id

from config.graphql.research_types import ResearchReportType
from opencontractserver.corpuses.models import Corpus
from opencontractserver.research.constants import MAX_RESEARCH_PROMPT_CHARS
from opencontractserver.research.models import ResearchReport
from opencontractserver.research.services.research_reports import (
    ConcurrentResearchInProgress,
    ResearchReportService,
)
from opencontractserver.shared.services.base import BaseService

logger = logging.getLogger(__name__)


def _decode_global_pk(global_id: str) -> int | None:
    """Decode a relay global id to its integer pk, or ``None`` if malformed."""
    try:
        return int(from_global_id(global_id)[1])
    except (ValueError, TypeError, UnicodeDecodeError, IndexError):
        return None


class StartResearchReport(graphene.Mutation):
    """Kick off a deep-research job over a corpus (explicit, non-chat path)."""

    class Arguments:
        corpus_id = graphene.ID(required=True)
        prompt = graphene.String(required=True)
        title = graphene.String(required=False)
        max_steps = graphene.Int(required=False)

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(ResearchReportType)

    @login_required
    def mutate(
        root, info, corpus_id, prompt, title=None, max_steps=None
    ) -> "StartResearchReport":
        corpus_pk = _decode_global_pk(corpus_id)
        if corpus_pk is None:
            return StartResearchReport(
                ok=False, message="Corpus not found or not visible.", obj=None
            )
        if prompt is None or len(prompt) > MAX_RESEARCH_PROMPT_CHARS:
            return StartResearchReport(
                ok=False,
                message=(f"Prompt must be 1–{MAX_RESEARCH_PROMPT_CHARS} characters."),
                obj=None,
            )
        corpus = BaseService.get_or_none(
            Corpus, corpus_pk, info.context.user, request=info.context
        )
        if corpus is None:
            return StartResearchReport(
                ok=False, message="Corpus not found or not visible.", obj=None
            )
        try:
            report = ResearchReportService.start(
                user=info.context.user,
                corpus=corpus,
                prompt=prompt,
                title=title,
                max_steps=max_steps,
                request=info.context,
            )
        except ConcurrentResearchInProgress as exc:
            return StartResearchReport(ok=False, message=str(exc), obj=None)
        except PermissionError as exc:
            return StartResearchReport(ok=False, message=str(exc), obj=None)
        except Exception:
            logger.exception("Failed to start research report")
            return StartResearchReport(
                ok=False, message="Failed to start research report.", obj=None
            )
        return StartResearchReport(ok=True, message="Started.", obj=report)


class CancelResearchReport(graphene.Mutation):
    """Request cooperative cancellation of an in-flight research job."""

    class Arguments:
        id = graphene.ID(required=True)

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(ResearchReportType)

    @login_required
    def mutate(root, info, id) -> "CancelResearchReport":
        pk = _decode_global_pk(id)
        if pk is None:
            return CancelResearchReport(
                ok=False, message="Research report not found.", obj=None
            )
        report = BaseService.get_or_none(
            ResearchReport, pk, info.context.user, request=info.context
        )
        if report is None:
            return CancelResearchReport(
                ok=False, message="Research report not found.", obj=None
            )
        try:
            ResearchReportService.request_cancel(info.context.user, report)
        except PermissionError as exc:
            return CancelResearchReport(ok=False, message=str(exc), obj=report)
        return CancelResearchReport(ok=True, message="Cancel requested.", obj=report)
