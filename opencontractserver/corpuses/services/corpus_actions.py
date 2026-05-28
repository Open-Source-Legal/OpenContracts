"""Batch-execution operations for agent-based corpus actions."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Any

from django.db import transaction

from opencontractserver.constants.corpus_actions import BATCH_RUN_MAX_DOCS
from opencontractserver.shared.services.base import BaseService
from opencontractserver.shared.services.conventions import ServiceResult
from opencontractserver.types.enums import PermissionTypes

if TYPE_CHECKING:
    from opencontractserver.corpuses.models import (
        CorpusAction,
        CorpusActionExecution,
    )
    from opencontractserver.users.models import User

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BatchRunSummary:
    """Result envelope for ``CorpusActionService.batch_run_on_corpus``."""

    executions: list[CorpusActionExecution]
    queued_count: int
    skipped_already_run_count: int
    total_active_documents: int


class CorpusActionService(BaseService):
    """Batch-execution operations for agent-based ``CorpusAction`` rows."""

    # IDOR-safe failure message: both "action doesn't exist" and
    # "action exists but you have no access to its corpus" return the same
    # string, so an attacker cannot enumerate corpus actions via differential
    # error responses.
    _NOT_FOUND_MESSAGE = "Corpus action not found."

    @classmethod
    def batch_run_on_corpus(
        cls,
        user: User,
        action_id: int,
        *,
        request: Any = None,
    ) -> ServiceResult[BatchRunSummary]:
        """Queue an agent action against every eligible document in its corpus."""
        # Local imports keep this module importable when the corpuses app is
        # still loading (the model module is heavy and pulls in signals).
        from opencontractserver.corpuses.models import (
            CorpusAction,
            CorpusActionExecution,
            CorpusActionTrigger,
        )
        from opencontractserver.tasks.agent_tasks import run_agent_corpus_action

        try:
            action = CorpusAction.objects.select_related("corpus").get(pk=action_id)
        except CorpusAction.DoesNotExist:
            return ServiceResult.failure(cls._NOT_FOUND_MESSAGE)

        corpus = action.corpus
        if not cls.user_has(corpus, user, PermissionTypes.UPDATE, request=request):
            # Collapse "no permission" into the same not-found error as
            # missing-action to avoid leaking action existence.
            return ServiceResult.failure(cls._NOT_FOUND_MESSAGE)

        if not action.is_agent_action:
            return ServiceResult.failure(
                "Only agent-based corpus actions can be batch-run on every "
                "document. Fieldset and analyzer actions already have "
                "corpus-wide execution paths."
            )

        if action.disabled:
            return ServiceResult.failure(
                "This action is disabled. Re-enable it before batch-running."
            )

        # Atomic block narrows (does not eliminate) the double-queue race;
        # real fix is a partial unique index on (corpus_action, document) WHERE status IN ('queued','running').
        with transaction.atomic():
            active_doc_ids = set(
                corpus._get_active_documents().values_list("id", flat=True)
            )
            total_active = len(active_doc_ids)
            already_run_ids = cls._already_run_document_ids(action)
            # sort eligible_ids so insertion order is deterministic
            # (tests + logs)
            eligible_ids = sorted(active_doc_ids - already_run_ids)
            skipped_count = len(active_doc_ids & already_run_ids)

            if not eligible_ids:
                cls.log_action(
                    "Batch-run skipped (no eligible docs) for",
                    action,
                    user,
                    total_active=total_active,
                    skipped_already_run=skipped_count,
                )
                return ServiceResult.success(
                    BatchRunSummary(
                        executions=[],
                        queued_count=0,
                        skipped_already_run_count=skipped_count,
                        total_active_documents=total_active,
                    )
                )

            if len(eligible_ids) > BATCH_RUN_MAX_DOCS:
                return ServiceResult.failure(
                    f"The eligible set ({len(eligible_ids)} documents) "
                    f"exceeds the per-call cap of {BATCH_RUN_MAX_DOCS}. "
                    "Wait for in-flight runs to complete, or narrow the "
                    "corpus first."
                )

            executions = CorpusActionExecution.bulk_queue(
                corpus_action=action,
                document_ids=eligible_ids,
                trigger=CorpusActionTrigger.MANUAL_BATCH.value,
                user_id=user.id,
            )

            action_pk = action.id
            user_pk = user.id
            for execution in executions:
                # ``functools.partial`` eagerly binds the arguments, so each
                # callback captures the row it was created for (a lambda
                # closing over the loop variable would leak the last
                # iteration's value into every scheduled call).
                transaction.on_commit(
                    partial(
                        run_agent_corpus_action.delay,
                        corpus_action_id=action_pk,
                        document_id=execution.document_id,
                        user_id=user_pk,
                        execution_id=execution.id,
                        force=True,
                    )
                )

        cls.log_action(
            "Batch-queued",
            action,
            user,
            queued=len(executions),
            skipped_already_run=skipped_count,
            total_active=total_active,
        )

        return ServiceResult.success(
            BatchRunSummary(
                executions=list(executions),
                queued_count=len(executions),
                skipped_already_run_count=skipped_count,
                total_active_documents=total_active,
            )
        )

    @classmethod
    def _already_run_document_ids(cls, action: CorpusAction) -> set[int]:
        """Document IDs with a QUEUED, RUNNING, or COMPLETED execution for ``action``."""
        from opencontractserver.corpuses.models import CorpusActionExecution

        return set(
            CorpusActionExecution.objects.filter(
                corpus_action_id=action.id,
                status__in=[
                    CorpusActionExecution.Status.QUEUED,
                    CorpusActionExecution.Status.RUNNING,
                    CorpusActionExecution.Status.COMPLETED,
                ],
                document_id__isnull=False,
            )
            .values_list("document_id", flat=True)
            .distinct()
        )
