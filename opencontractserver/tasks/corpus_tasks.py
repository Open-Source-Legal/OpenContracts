import logging
from datetime import timedelta

from celery import chord, group, shared_task
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from opencontractserver.analyzer.models import Analysis, Analyzer
from opencontractserver.conversations.models import (
    ChatMessage,
    Conversation,
    ConversationTypeChoices,
    MessageVote,
    VoteType,
)
from opencontractserver.corpuses.models import (
    Corpus,
    CorpusAction,
    CorpusEngagementMetrics,
)
from opencontractserver.documents.models import DocumentAnalysisRow
from opencontractserver.extracts.models import Datacell, Extract
from opencontractserver.tasks.analyzer_tasks import (
    mark_analysis_complete,
    start_analysis,
)
from opencontractserver.tasks.extract_orchestrator_tasks import mark_extract_complete
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.analysis import create_and_setup_analysis
from opencontractserver.utils.celery_tasks import (
    get_doc_analyzer_task_by_name,
    get_task_by_name,
)
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

logger = logging.getLogger(__name__)


@shared_task
def run_task_name_analyzer(
    analysis_id: int | str,
    document_ids: list[str | int] | None = None,
    analysis_input_data: dict | None = None,
):
    """
    Invokes a task-based analyzer by analysis_id. Pass any input data
    that the analyzer might require.
    """
    # Retrieve the analysis
    analysis = Analysis.objects.get(id=analysis_id)
    analyzer = analysis.analyzer

    task_name = analyzer.task_name
    task_func = get_doc_analyzer_task_by_name(task_name)

    if task_func is None:
        msg = f"Task {task_name} for analysis {analysis_id} failed as task could not be found..."
        logger.error(msg)
        raise ValueError(msg)

    if document_ids is None:
        if analysis.analyzed_corpus is None:
            raise ValueError(
                "If Analysis is not linked to a corpus, it must be linked to docs at "
                "run_task_name_analyzer() runtime..."
            )

        document_ids = list(
            analysis.analyzed_corpus.get_documents().values_list("id", flat=True)
        )

    logger.info(f"Added task {task_name} to queue: {task_func}")

    transaction.on_commit(
        lambda: chord(
            group(
                [
                    task_func.s(
                        doc_id=doc_id,
                        analysis_id=analysis.id,
                        corpus_id=(
                            analysis.analyzed_corpus.id
                            if analysis.analyzed_corpus
                            else None
                        ),
                        **(analysis_input_data if analysis_input_data else {}),
                    )
                    for doc_id in document_ids
                ]
            )
        )(mark_analysis_complete.si(analysis_id=analysis.id, doc_ids=document_ids))
    )


def process_analyzer(
    user_id: int | str,
    analyzer: Analyzer | None,
    corpus_id: str | int | None = None,
    document_ids: list[str | int] | None = None,
    corpus_action: CorpusAction | None = None,
    analysis_input_data: dict | None = None,
) -> Analysis:

    logger.info(
        f"process_analyzer called - user_id: {user_id}, analyzer: {analyzer.id if analyzer else None}"
    )
    logger.info(f"corpus_id: {corpus_id}, document_ids: {document_ids}")
    logger.info(f"analysis_input_data: {analysis_input_data}")

    analysis = create_and_setup_analysis(
        analyzer,
        user_id,
        corpus_id=corpus_id,
        doc_ids=document_ids,
        corpus_action=corpus_action,
    )

    logger.info(
        f"Analysis object created: {analysis.id}, analyzer: {analysis.analyzer.id if analysis.analyzer else None}"
    )

    if analyzer.task_name:
        logger.info(f"Using task_name analyzer: {analyzer.task_name}")

        transaction.on_commit(
            lambda: run_task_name_analyzer.si(
                analysis_id=analysis.id,
                document_ids=document_ids,
                analysis_input_data=analysis_input_data,
            ).apply_async()
        )

    else:
        logger.info(f"Using standard analyzer - retrieved analysis: {analysis}")
        transaction.on_commit(
            lambda: start_analysis.s(
                analysis_id=analysis.id, doc_ids=document_ids
            ).apply_async()
        )

    return analysis


@shared_task
def process_corpus_action(
    corpus_id: str | int, document_ids: list[str | int], user_id: str | int
):

    logger.info("process_corpus_action()...")

    actions = CorpusAction.objects.filter(
        Q(corpus_id=corpus_id, disabled=False)
        | Q(run_on_all_corpuses=True, disabled=False)
    )

    for action in actions:

        if action.fieldset:

            tasks = []

            with transaction.atomic():
                extract, created = Extract.objects.get_or_create(
                    corpus=action.corpus,
                    name=f"Action {action.name} for {action.corpus.title}",
                    fieldset=action.fieldset,
                    creator_id=user_id,
                    corpus_action=action,
                )
                extract.started = timezone.now()

                if created:
                    extract.finished = None

                extract.save()

            fieldset = action.fieldset

            for document_id in document_ids:

                with transaction.atomic():
                    row_results = DocumentAnalysisRow(
                        document_id=document_id,
                        extract_id=extract.id,
                        creator=extract.creator,
                    )
                    row_results.save()

                for column in fieldset.columns.all():
                    with transaction.atomic():
                        cell = Datacell.objects.create(
                            extract=extract,
                            column=column,
                            data_definition=column.output_type,
                            creator_id=user_id,
                            document_id=document_id,
                        )
                        set_permissions_for_obj_to_user(
                            user_id, cell, [PermissionTypes.CRUD]
                        )

                        # Add data cell to tracking
                        row_results.data.add(cell)

                        # Get the task function dynamically based on the column's task_name
                        task_func = get_task_by_name(column.task_name)
                        if task_func is None:
                            logger.error(
                                f"Task {column.task_name} not found for column {column.id}"
                            )
                            continue

                        # Add the task to the group
                        tasks.append(task_func.si(cell.pk))

            transaction.on_commit(
                lambda: chord(group(*tasks))(mark_extract_complete.si(extract.id))
            )

        elif action.analyzer:

            process_analyzer(
                user_id=user_id,
                analyzer=action.analyzer,
                corpus_id=corpus_id,
                document_ids=document_ids,
                corpus_action=action,
            )

        else:
            raise ValueError(
                "Unexpected action configuration... no analyzer or fieldset."
            )

    return True


# --------------------------------------------------------------------------- #
# Engagement Metrics Tasks (Epic #565)
# --------------------------------------------------------------------------- #


@shared_task
def update_corpus_engagement_metrics(corpus_id: int | str):
    """
    Calculate and update engagement metrics for a specific corpus.

    This task aggregates statistics about thread participation, message activity,
    and voting patterns to populate the CorpusEngagementMetrics model.

    Args:
        corpus_id: The ID of the corpus to update metrics for

    Returns:
        dict: Summary of updated metrics

    Raises:
        Corpus.DoesNotExist: If corpus_id is invalid

    Epic: #565 - Corpus Engagement Metrics & Analytics
    Issue: #567 - Create Celery periodic task for updating engagement metrics
    """
    try:
        corpus = Corpus.objects.get(id=corpus_id)
        logger.info(
            f"Updating engagement metrics for corpus {corpus_id}: {corpus.title}"
        )

        now = timezone.now()
        seven_days_ago = now - timedelta(days=7)
        thirty_days_ago = now - timedelta(days=30)

        # Get all threads for this corpus (excluding soft-deleted)
        threads = Conversation.objects.filter(
            chat_with_corpus=corpus,
            conversation_type=ConversationTypeChoices.THREAD,
            deleted_at__isnull=True,
        )

        # Calculate thread counts
        total_threads = threads.count()
        active_threads = threads.filter(is_locked=False).count()

        # Get all messages in corpus threads (excluding soft-deleted messages and messages in soft-deleted threads)
        messages = ChatMessage.objects.filter(
            conversation__chat_with_corpus=corpus,
            conversation__conversation_type=ConversationTypeChoices.THREAD,
            deleted_at__isnull=True,
            conversation__deleted_at__isnull=True,  # Also exclude messages in deleted threads
        )

        # Calculate message counts
        total_messages = messages.count()
        messages_last_7_days = messages.filter(created_at__gte=seven_days_ago).count()
        messages_last_30_days = messages.filter(created_at__gte=thirty_days_ago).count()

        # Calculate contributor counts
        unique_contributors = messages.values("creator").distinct().count()
        active_contributors_30_days = (
            messages.filter(created_at__gte=thirty_days_ago)
            .values("creator")
            .distinct()
            .count()
        )

        # Calculate total upvotes
        total_upvotes = MessageVote.objects.filter(
            message__conversation__chat_with_corpus=corpus,
            message__conversation__conversation_type=ConversationTypeChoices.THREAD,
            vote_type=VoteType.UPVOTE,
        ).count()

        # Calculate average messages per thread
        avg_messages_per_thread = (
            float(total_messages) / float(total_threads) if total_threads > 0 else 0.0
        )

        # Get or create metrics record
        metrics, created = CorpusEngagementMetrics.objects.get_or_create(corpus=corpus)

        # Update all metrics
        metrics.total_threads = total_threads
        metrics.active_threads = active_threads
        metrics.total_messages = total_messages
        metrics.messages_last_7_days = messages_last_7_days
        metrics.messages_last_30_days = messages_last_30_days
        metrics.unique_contributors = unique_contributors
        metrics.active_contributors_30_days = active_contributors_30_days
        metrics.total_upvotes = total_upvotes
        metrics.avg_messages_per_thread = avg_messages_per_thread
        metrics.save()

        result = {
            "corpus_id": corpus_id,
            "corpus_title": corpus.title,
            "created": created,
            "metrics": {
                "total_threads": total_threads,
                "active_threads": active_threads,
                "total_messages": total_messages,
                "messages_last_7_days": messages_last_7_days,
                "messages_last_30_days": messages_last_30_days,
                "unique_contributors": unique_contributors,
                "active_contributors_30_days": active_contributors_30_days,
                "total_upvotes": total_upvotes,
                "avg_messages_per_thread": round(avg_messages_per_thread, 2),
            },
        }

        logger.info(
            f"Successfully updated metrics for corpus {corpus_id}: "
            f"{total_threads} threads, {total_messages} messages, "
            f"{unique_contributors} contributors"
        )

        return result

    except Corpus.DoesNotExist:
        logger.error(f"Corpus {corpus_id} not found, cannot update metrics")
        raise
    except Exception as e:
        logger.error(
            f"Error updating engagement metrics for corpus {corpus_id}: {str(e)}",
            exc_info=True,
        )
        raise


@shared_task
def update_all_corpus_engagement_metrics():
    """
    Update engagement metrics for all corpuses.

    This task iterates through all corpuses and queues individual
    update_corpus_engagement_metrics tasks for each one.

    Returns:
        dict: Summary of queued updates

    Epic: #565 - Corpus Engagement Metrics & Analytics
    Issue: #567 - Create Celery periodic task for updating engagement metrics
    """
    logger.info("Starting batch update of all corpus engagement metrics")

    # Get all corpus IDs
    corpus_ids = list(Corpus.objects.values_list("id", flat=True))

    logger.info(f"Queueing metrics updates for {len(corpus_ids)} corpuses")

    # Queue individual update tasks
    for corpus_id in corpus_ids:
        transaction.on_commit(
            lambda cid=corpus_id: update_corpus_engagement_metrics.apply_async(
                args=[cid]
            )
        )

    return {
        "queued_updates": len(corpus_ids),
        "corpus_ids": corpus_ids,
    }
