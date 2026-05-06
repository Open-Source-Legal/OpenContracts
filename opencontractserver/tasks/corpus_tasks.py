import logging
from datetime import timedelta
from typing import Any

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
    CorpusActionExecution,
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
                    task_func.s(  # type: ignore[attr-defined]
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

    if analyzer is None:
        raise ValueError("process_analyzer requires a non-null analyzer")

    logger.info(
        f"process_analyzer called - user_id: {user_id}, analyzer: {analyzer.id}"
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
    corpus_id: str | int,
    document_ids: list[str | int],
    user_id: str | int,
    trigger: str | None = None,
) -> None:
    """
    Process corpus actions for given documents with execution tracking.

    Creates CorpusActionExecution records for each (action, document) pair
    to provide unified tracking across all action types.

    Args:
        corpus_id: The corpus ID
        document_ids: List of document IDs to process
        user_id: The user ID who triggered the action
        trigger: Optional trigger type to filter actions by (e.g., "add_document", "edit_document").
                 If None, all non-disabled actions for the corpus will run.
    """
    logger.info(
        f"process_corpus_action() - corpus_id={corpus_id}, "
        f"document_ids={document_ids}, trigger={trigger}"
    )

    # Build the base query for corpus actions
    base_query = Q(corpus_id=corpus_id, disabled=False) | Q(
        run_on_all_corpuses=True, disabled=False
    )

    # Filter by trigger type if specified
    if trigger:
        base_query &= Q(trigger=trigger)

    actions = CorpusAction.objects.filter(base_query)

    summary = {"actions_processed": 0, "executions_queued": 0}

    # Celery JSON serialisation may widen int → str.
    int_document_ids: list[int] = [int(d) for d in document_ids]
    int_user_id: int = int(user_id)

    for action in actions:
        # Create execution records for tracking
        # Use trigger or default to add_document for backwards compatibility
        execution_trigger = trigger or "add_document"

        # Queue execution records for all documents within a transaction
        # to ensure atomicity with subsequent processing
        with transaction.atomic():
            executions = CorpusActionExecution.bulk_queue(
                corpus_action=action,
                document_ids=int_document_ids,
                trigger=execution_trigger,
                user_id=int_user_id,
            )
        execution_map = {ex.document_id: ex for ex in executions}

        summary["actions_processed"] += 1
        summary["executions_queued"] += len(executions)

        if action.fieldset:

            tasks = []

            with transaction.atomic():
                extract, created = Extract.objects.get_or_create(
                    corpus=action.corpus,
                    name=f"Action {action.name} for {action.corpus.title}",
                    fieldset=action.fieldset,
                    creator_id=int_user_id,
                    corpus_action=action,
                )
                extract.started = timezone.now()

                if created:
                    extract.finished = None

                extract.save()

                # Link executions to extract and mark as running
                now = timezone.now()
                for doc_id, execution in execution_map.items():
                    execution.extract = extract
                    execution.status = CorpusActionExecution.Status.RUNNING
                    execution.started_at = now
                    execution.modified = now  # bulk_update doesn't auto-update
                    execution.add_affected_object("extract", extract.id)

                CorpusActionExecution.objects.bulk_update(
                    list(execution_map.values()),
                    ["extract", "status", "started_at", "affected_objects", "modified"],
                )

            fieldset = action.fieldset

            for document_id in int_document_ids:
                doc_execution = execution_map.get(document_id)

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
                            creator_id=int_user_id,
                            document_id=document_id,
                        )
                        set_permissions_for_obj_to_user(
                            int_user_id, cell, [PermissionTypes.CRUD]
                        )

                        # Add data cell to tracking
                        row_results.data.add(cell)

                        # Track affected datacell in execution record
                        if doc_execution:
                            doc_execution.add_affected_object(
                                "datacell", cell.id, column_name=column.name
                            )

                        # Get the task function dynamically based on the column's task_name
                        task_func = get_task_by_name(column.task_name)
                        if task_func is None:
                            logger.error(
                                f"Task {column.task_name} not found for column {column.id}"
                            )
                            continue

                        # Add the task to the group
                        tasks.append(task_func.si(cell.pk))  # type: ignore[attr-defined]

                # Save updated affected_objects for this execution
                if doc_execution:
                    doc_execution.save(update_fields=["affected_objects"])

            # Capture extract_id and execution_ids for the lambda closure
            extract_id_for_closure = extract.id
            execution_ids_for_closure = [ex.id for ex in executions]

            def on_commit_callback():
                chord(group(*tasks))(mark_extract_complete.si(extract_id_for_closure))
                # Mark executions as running - they will be marked completed
                # by mark_extract_complete when all tasks finish
                CorpusActionExecution.objects.filter(
                    id__in=execution_ids_for_closure
                ).update(
                    status=CorpusActionExecution.Status.RUNNING,
                    started_at=timezone.now(),
                )

            transaction.on_commit(on_commit_callback)

        elif action.analyzer:
            analysis = process_analyzer(
                user_id=user_id,
                analyzer=action.analyzer,
                corpus_id=corpus_id,
                document_ids=document_ids,
                corpus_action=action,
            )

            # Link executions to analysis and mark as running
            # They will be marked COMPLETED by mark_analysis_complete when
            # the analysis actually finishes
            if analysis:
                CorpusActionExecution.objects.filter(
                    id__in=[ex.id for ex in executions]
                ).update(
                    analysis=analysis,
                    status=CorpusActionExecution.Status.RUNNING,
                    started_at=timezone.now(),
                    affected_objects=[{"type": "analysis", "id": analysis.id}],
                )

        elif action.is_agent_action:
            # Agent-based corpus action (with or without agent_config)
            from opencontractserver.tasks.agent_tasks import run_agent_corpus_action

            logger.info(
                f"Triggering agent corpus action '{action.name}' "
                f"for {len(document_ids)} document(s)"
            )

            # Pass execution_id to agent task for tracking
            for document_id in int_document_ids:
                doc_execution = execution_map.get(document_id)
                run_agent_corpus_action.delay(
                    corpus_action_id=action.id,
                    document_id=document_id,
                    user_id=int_user_id,
                    execution_id=doc_execution.id if doc_execution else None,
                )

        else:
            raise ValueError(
                "Unexpected action configuration... no analyzer, fieldset, "
                "agent_config, or task_instructions."
            )

    logger.info(
        f"process_corpus_action() completed - {summary['actions_processed']} actions, "
        f"{summary['executions_queued']} executions queued"
    )


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
            lambda cid=corpus_id: update_corpus_engagement_metrics.apply_async(  # type: ignore[misc]
                args=[cid]
            )
        )

    return {
        "queued_updates": len(corpus_ids),
        "corpus_ids": corpus_ids,
    }


# --------------------------------------------------------------------------- #
# Thread/Message Corpus Action Tasks
# --------------------------------------------------------------------------- #


@shared_task
def process_thread_corpus_action(
    corpus_id: int | str,
    conversation_id: int | str,
    user_id: int | str,
    trigger: str = "new_thread",
) -> dict:
    """
    Process corpus actions triggered by thread creation.

    Similar to process_corpus_action but for thread context.
    Supports both corpus-specific and run_on_all_corpuses actions.
    Only processes agent-based actions (fieldset/analyzer don't apply to threads).

    Args:
        corpus_id: The corpus the thread belongs to
        conversation_id: The conversation (thread) that was created
        user_id: The user who created the thread
        trigger: The trigger type (default "new_thread")

    Returns:
        dict: Summary of actions processed
    """
    logger.info(
        f"process_thread_corpus_action() - corpus={corpus_id}, "
        f"conversation={conversation_id}, trigger={trigger}"
    )

    try:
        conversation = Conversation.objects.get(pk=conversation_id)
    except Conversation.DoesNotExist:
        logger.error(f"Conversation {conversation_id} not found")
        return {"error": "Conversation not found"}

    # Find matching corpus actions with this trigger
    base_query = Q(corpus_id=corpus_id, disabled=False, trigger=trigger) | Q(
        run_on_all_corpuses=True, disabled=False, trigger=trigger
    )

    actions = list(CorpusAction.objects.filter(base_query))

    logger.info(
        f"[ThreadTask] Found {len(actions)} corpus action(s) for corpus={corpus_id}, "
        f"trigger={trigger}"
    )

    summary = {"actions_processed": 0, "executions_queued": 0, "skipped_no_agent": 0}

    for action in actions:
        # Only agent-based actions support thread/message triggers
        if not action.agent_config:
            logger.info(
                f"[ThreadTask] Skipping action '{action.name}' (id={action.id}) - "
                f"no agent_config set"
            )
            summary["skipped_no_agent"] += 1
            continue

        # Create execution record
        with transaction.atomic():
            execution = CorpusActionExecution.objects.create(
                corpus_action=action,
                corpus_id=corpus_id,
                document=None,  # No document for thread-based actions
                conversation=conversation,
                action_type=CorpusActionExecution.ActionType.AGENT,
                trigger=trigger,
                queued_at=timezone.now(),
                status=CorpusActionExecution.Status.QUEUED,
                creator_id=user_id,
            )

        summary["actions_processed"] += 1
        summary["executions_queued"] += 1

        # Queue the agent task
        from opencontractserver.tasks.agent_tasks import run_agent_thread_action

        run_agent_thread_action.delay(
            corpus_action_id=action.id,
            conversation_id=conversation_id,
            message_id=None,  # No specific message for NEW_THREAD
            user_id=user_id,
            execution_id=execution.id,
        )

    logger.info(f"process_thread_corpus_action() completed - {summary}")
    return summary


@shared_task
def process_message_corpus_action(
    corpus_id: int | str,
    conversation_id: int | str,
    message_id: int | str,
    user_id: int | str,
    trigger: str = "new_message",
) -> dict:
    """
    Process corpus actions triggered by message creation.

    Similar to process_thread_corpus_action but with message context.
    Only processes agent-based actions.

    Args:
        corpus_id: The corpus the thread belongs to
        conversation_id: The conversation (thread) containing the message
        message_id: The message that was created
        user_id: The user who created the message
        trigger: The trigger type (default "new_message")

    Returns:
        dict: Summary of actions processed
    """
    logger.info(
        f"process_message_corpus_action() - corpus={corpus_id}, "
        f"conversation={conversation_id}, message={message_id}, trigger={trigger}"
    )

    try:
        conversation = Conversation.objects.get(pk=conversation_id)
        message = ChatMessage.objects.get(pk=message_id)
    except (Conversation.DoesNotExist, ChatMessage.DoesNotExist) as e:
        logger.error(f"Conversation or message not found: {e}")
        return {"error": str(e)}

    # Find matching corpus actions with this trigger
    base_query = Q(corpus_id=corpus_id, disabled=False, trigger=trigger) | Q(
        run_on_all_corpuses=True, disabled=False, trigger=trigger
    )

    actions = list(CorpusAction.objects.filter(base_query))

    logger.info(
        f"[MessageTask] Found {len(actions)} corpus action(s) for corpus={corpus_id}, "
        f"trigger={trigger}"
    )

    summary = {"actions_processed": 0, "executions_queued": 0, "skipped_no_agent": 0}

    for action in actions:
        # Only agent-based actions support thread/message triggers
        if not action.agent_config:
            logger.info(
                f"[MessageTask] Skipping action '{action.name}' (id={action.id}) - "
                f"no agent_config set"
            )
            summary["skipped_no_agent"] += 1
            continue

        # Create execution record
        with transaction.atomic():
            execution = CorpusActionExecution.objects.create(
                corpus_action=action,
                corpus_id=corpus_id,
                document=None,  # No document for message-based actions
                conversation=conversation,
                message=message,
                action_type=CorpusActionExecution.ActionType.AGENT,
                trigger=trigger,
                queued_at=timezone.now(),
                status=CorpusActionExecution.Status.QUEUED,
                creator_id=user_id,
            )

        summary["actions_processed"] += 1
        summary["executions_queued"] += 1

        # Queue the agent task
        from opencontractserver.tasks.agent_tasks import run_agent_thread_action

        run_agent_thread_action.delay(
            corpus_action_id=action.id,
            conversation_id=conversation_id,
            message_id=message_id,
            user_id=user_id,
            execution_id=execution.id,
        )

    logger.info(f"process_message_corpus_action() completed - {summary}")
    return summary


# --------------------------------------------------------------------------- #
# Embedding Tasks for Shared StructuralAnnotationSets
# --------------------------------------------------------------------------- #


@shared_task
def ensure_embeddings_for_corpus(
    structural_set_id: int | str,
    corpus_id: int | str,
) -> dict:
    """
    Ensure all annotations in a StructuralAnnotationSet have embeddings for the
    corpus's required embedders.

    When a document is added to a corpus and reuses a shared StructuralAnnotationSet,
    this task checks if embeddings exist for the corpus's embedder(s) and queues
    embedding generation only for missing ones.

    Required embedders:
    - Default embedder (from PipelineSettings) - always required for global search
    - corpus.preferred_embedder (if different from the default)

    Args:
        structural_set_id: ID of the StructuralAnnotationSet to check
        corpus_id: ID of the Corpus (to determine required embedders)

    Returns:
        dict: Summary of embedding tasks queued
    """
    from opencontractserver.annotations.models import (
        Embedding,
        StructuralAnnotationSet,
    )
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.pipeline.utils import get_default_embedder_path

    logger.info(
        f"ensure_embeddings_for_corpus() - structural_set={structural_set_id}, "
        f"corpus={corpus_id}"
    )

    result: dict[str, Any] = {
        "structural_set_id": structural_set_id,
        "corpus_id": corpus_id,
        "embedders_checked": [],
        "tasks_queued": 0,
        "annotations_already_embedded": 0,
        "errors": [],
    }

    try:
        # Get the structural annotation set
        try:
            structural_set = StructuralAnnotationSet.objects.get(pk=structural_set_id)
        except StructuralAnnotationSet.DoesNotExist:
            logger.warning(f"StructuralAnnotationSet {structural_set_id} not found")
            result["errors"].append("StructuralAnnotationSet not found")
            return result

        # Get the corpus
        try:
            corpus = Corpus.objects.get(pk=corpus_id)
        except Corpus.DoesNotExist:
            logger.warning(f"Corpus {corpus_id} not found")
            result["errors"].append("Corpus not found")
            return result

        # Determine required embedders
        default_embedder = get_default_embedder_path() or None
        corpus_embedder = corpus.preferred_embedder

        required_embedders = set()
        if default_embedder:
            required_embedders.add(default_embedder)
        if corpus_embedder and corpus_embedder != default_embedder:
            required_embedders.add(corpus_embedder)

        if not required_embedders:
            logger.warning(
                f"No embedders configured for corpus {corpus_id} "
                "(default embedder not set in PipelineSettings)"
            )
            result["errors"].append("No embedders configured")
            return result

        result["embedders_checked"] = list(required_embedders)
        logger.info(f"Required embedders: {required_embedders}")

        # Get all annotation IDs in this structural set
        annotation_ids = list(
            structural_set.structural_annotations.values_list("id", flat=True)
        )

        if not annotation_ids:
            logger.info(
                f"No annotations in structural set {structural_set_id}, nothing to embed"
            )
            return result

        logger.info(
            f"Checking embeddings for {len(annotation_ids)} annotations "
            f"across {len(required_embedders)} embedder(s)"
        )

        # For each required embedder, find missing embeddings and queue tasks
        for embedder_path in required_embedders:
            # Find which annotations already have embeddings for this embedder
            existing_annotation_ids = set(
                Embedding.objects.filter(
                    annotation_id__in=annotation_ids,
                    embedder_path=embedder_path,
                ).values_list("annotation_id", flat=True)
            )

            # Find annotations missing embeddings for this embedder
            missing_annotation_ids = set(annotation_ids) - existing_annotation_ids

            result["annotations_already_embedded"] += len(existing_annotation_ids)

            if not missing_annotation_ids:
                logger.info(
                    f"All {len(annotation_ids)} annotations already have embeddings "
                    f"for {embedder_path}"
                )
                continue

            logger.info(
                f"Queueing embedding tasks for {len(missing_annotation_ids)} annotations "
                f"missing embeddings for {embedder_path}"
            )

            # Queue embedding tasks in batches to prevent queue flooding
            # Import batch size constant
            from opencontractserver.constants.document_processing import (
                EMBEDDING_BATCH_SIZE,
            )
            from opencontractserver.tasks.embeddings_task import (
                calculate_embeddings_for_annotation_batch,
            )

            missing_ids_list = list(missing_annotation_ids)
            for i in range(0, len(missing_ids_list), EMBEDDING_BATCH_SIZE):
                batch = missing_ids_list[i : i + EMBEDDING_BATCH_SIZE]
                calculate_embeddings_for_annotation_batch.delay(
                    annotation_ids=batch,
                    corpus_id=corpus_id,
                    embedder_path=embedder_path,
                )
                result["tasks_queued"] += 1

        logger.info(
            f"ensure_embeddings_for_corpus() completed - "
            f"queued {result['tasks_queued']} tasks, "
            f"{result['annotations_already_embedded']} already embedded"
        )

        return result

    except Exception as e:
        logger.error(f"ensure_embeddings_for_corpus() failed: {e}")
        result["errors"].append(str(e))
        return result


# --------------------------------------------------------------------------- #
# Re-Embed Corpus Task (Issue #437)
# --------------------------------------------------------------------------- #


@shared_task
def reembed_corpus(
    corpus_id: int | str,
    new_embedder_path: str,
) -> dict:
    """
    Re-embed all annotations in a corpus with a new embedder.

    This is the controlled migration path for changing a corpus's embedder
    after documents have been added. It:
    1. Updates corpus.preferred_embedder to the new embedder
    2. Finds all annotations in the corpus (via DocumentPath + StructuralAnnotationSets)
    3. Queues batch embedding tasks for all annotations missing the new embedder
    4. Unlocks the corpus when complete

    The corpus should be locked (backend_lock=True) before calling this task.

    Args:
        corpus_id: ID of the corpus to re-embed
        new_embedder_path: Fully qualified path to the new embedder class

    Returns:
        dict: Summary of re-embedding tasks queued
    """
    from opencontractserver.annotations.models import Annotation, Embedding
    from opencontractserver.constants.document_processing import (
        EMBEDDING_BATCH_SIZE,
        MAX_REEMBED_TASKS_PER_RUN,
    )
    from opencontractserver.documents.models import DocumentPath
    from opencontractserver.tasks.embeddings_task import (
        calculate_embeddings_for_annotation_batch,
    )

    logger.info(
        f"reembed_corpus() - corpus={corpus_id}, new_embedder={new_embedder_path}"
    )

    result: dict[str, Any] = {
        "corpus_id": corpus_id,
        "new_embedder_path": new_embedder_path,
        "total_annotations": 0,
        "already_embedded": 0,
        "tasks_queued": 0,
        "capped": False,
        "errors": [],
    }

    corpus = None
    try:
        try:
            corpus = Corpus.objects.get(pk=corpus_id)
        except Corpus.DoesNotExist:
            result["errors"].append("Corpus not found")
            return result

        # Update the corpus's preferred_embedder
        old_embedder = corpus.preferred_embedder
        corpus.preferred_embedder = new_embedder_path
        # Use update_fields to avoid triggering the full save() logic
        corpus.save(update_fields=["preferred_embedder", "modified"])
        logger.info(
            f"Updated corpus {corpus_id} preferred_embedder: "
            f"{old_embedder} -> {new_embedder_path}"
        )

        # Get all document IDs in this corpus
        doc_ids = list(
            DocumentPath.objects.filter(
                corpus=corpus, is_current=True, is_deleted=False
            ).values_list("document_id", flat=True)
        )

        if not doc_ids:
            logger.info(f"Corpus {corpus_id} has no documents, nothing to re-embed")
            return result

        # Get all annotation IDs for documents in this corpus
        # Include both corpus-scoped annotations and structural annotations
        annotation_ids = list(
            Annotation.objects.filter(
                Q(document_id__in=doc_ids)
                | Q(structural=True, structural_set__documents__in=doc_ids)
            )
            .distinct()
            .values_list("id", flat=True)
        )

        result["total_annotations"] = len(annotation_ids)

        if not annotation_ids:
            logger.info(f"No annotations found for corpus {corpus_id}")
            return result

        # Find which annotations already have embeddings for the new embedder
        existing_ids = set(
            Embedding.objects.filter(
                annotation_id__in=annotation_ids,
                embedder_path=new_embedder_path,
            ).values_list("annotation_id", flat=True)
        )
        result["already_embedded"] = len(existing_ids)

        # Queue tasks only for annotations missing the new embedder's embeddings
        missing_ids = [aid for aid in annotation_ids if aid not in existing_ids]

        if not missing_ids:
            logger.info(
                f"All {len(annotation_ids)} annotations already have embeddings "
                f"for {new_embedder_path}"
            )
            return result

        total_batches = (
            len(missing_ids) + EMBEDDING_BATCH_SIZE - 1
        ) // EMBEDDING_BATCH_SIZE
        logger.info(
            f"Queueing re-embedding for {len(missing_ids)} annotations "
            f"(of {len(annotation_ids)} total) in up to {total_batches} batches "
            f"using {new_embedder_path}"
        )

        # Queue in batches, capped to prevent flooding the Celery queue.
        # The task is idempotent: re-running it will skip already-embedded
        # annotations, so capping here is safe for very large corpuses.
        for i in range(0, len(missing_ids), EMBEDDING_BATCH_SIZE):
            if result["tasks_queued"] >= MAX_REEMBED_TASKS_PER_RUN:
                remaining = total_batches - result["tasks_queued"]
                logger.warning(
                    f"Reached task queue cap ({MAX_REEMBED_TASKS_PER_RUN}). "
                    f"{remaining} batches deferred. Re-run to continue."
                )
                result["capped"] = True
                break

            batch = missing_ids[i : i + EMBEDDING_BATCH_SIZE]
            calculate_embeddings_for_annotation_batch.delay(
                annotation_ids=batch,
                corpus_id=corpus_id,
                embedder_path=new_embedder_path,
            )
            result["tasks_queued"] += 1

            # Progress logging every 50 batches
            if result["tasks_queued"] % 50 == 0:
                logger.info(
                    f"reembed_corpus() progress: {result['tasks_queued']}/{total_batches} "
                    f"batches queued for corpus {corpus_id}"
                )

        logger.info(
            f"reembed_corpus() complete - queued {result['tasks_queued']} tasks "
            f"for {len(missing_ids)} annotations"
        )

    except Exception as e:
        logger.error(f"reembed_corpus() failed: {e}")
        result["errors"].append(str(e))
        # Mark corpus as errored so the UI can display the failure
        if corpus:
            try:
                corpus.error = True
                corpus.save(update_fields=["error", "modified"])
            except Exception:
                pass

    finally:
        # Always unlock the corpus, whether we succeeded, failed, or returned early.
        # This prevents permanently locked corpuses from any code path.
        if corpus:
            try:
                Corpus.objects.filter(pk=corpus.pk).update(backend_lock=False)
            except Exception:
                logger.error(
                    f"CRITICAL: Failed to unlock corpus {corpus_id} after re-embed"
                )

    return result
