import logging
from typing import Optional

from django.contrib.auth import get_user_model
from django.utils import timezone

from config import celery_app
from opencontractserver.analyzer.models import Analysis, GremlinEngine
from opencontractserver.analyzer.utils import get_gremlin_manifests
from opencontractserver.types.dicts import (
    AnalyzerManifest,
    OpenContractsGeneratedCorpusPythonType,
)

# Excellent django logging guidance here: https://docs.python.org/3/howto/logging-cookbook.html
from opencontractserver.utils.analyzer import (
    import_annotations_from_analysis,
    install_analyzers,
    run_analysis,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

User = get_user_model()


@celery_app.task()
def import_analysis(
    creator_id: int | str,
    analysis_id: int | str,
    analysis_results: OpenContractsGeneratedCorpusPythonType,
) -> bool:
    logger.info(f"import_analysis - creator_id: {creator_id}")
    logger.info(f"import_analysis - analysis_id: {analysis_id}")

    return import_annotations_from_analysis(
        analysis_id=analysis_id,
        creator_id=creator_id,
        analysis_results=analysis_results,
    )


@celery_app.task()
def start_analysis(
    analysis_id: str,
    doc_ids: Optional[list[int | str]] = None,
) -> bool:

    run_analysis(analysis_id=analysis_id, doc_ids=doc_ids)

    return True


@celery_app.task()
def request_gremlin_manifest(gremlin_id: str | int) -> list[AnalyzerManifest]:
    logger.info("request_gremlin_manifest() - Start...")

    gremlin = GremlinEngine.objects.get(id=gremlin_id)

    gremlin.install_started = timezone.now()
    gremlin.save()

    analyzer_manifests = get_gremlin_manifests(gremlin_id)
    # logger.info(
    #     f"request_gremlin_manifest() - analyzer_manifests: {analyzer_manifests}"
    # )
    logger.info("request_gremlin_manifest() - End.")

    return analyzer_manifests


@celery_app.task()
def install_analyzer_task(
    analyzer_manifests: list[AnalyzerManifest],
    gremlin_id: int,
) -> list[str]:
    # logger.info(f"install_analyzer_task() - analyzer_manifests: {analyzer_manifests}")

    gremlin = GremlinEngine.objects.get(id=gremlin_id)

    install_response = install_analyzers(
        gremlin_id=gremlin_id,
        analyzer_manifests=analyzer_manifests,
    )

    gremlin.install_completed = timezone.now()
    gremlin.save()

    return install_response


@celery_app.task()
def mark_analysis_complete(analysis_id: str | int, doc_ids: list[int | str]) -> None:
    from opencontractserver.corpuses.models import CorpusActionExecution

    analysis = Analysis.objects.get(pk=analysis_id)
    analysis.analysis_completed = timezone.now()
    analysis.analyzed_documents.add(*doc_ids)
    analysis.save()

    # Mark any related CorpusActionExecutions as completed
    # These were set to RUNNING when the analysis was queued
    updated_count = CorpusActionExecution.objects.filter(
        analysis_id=analysis_id, status=CorpusActionExecution.Status.RUNNING
    ).update(status=CorpusActionExecution.Status.COMPLETED, completed_at=timezone.now())

    if updated_count:
        logger.info(
            f"Analysis {analysis_id} marked complete, "
            f"updated {updated_count} CorpusActionExecution(s)"
        )
