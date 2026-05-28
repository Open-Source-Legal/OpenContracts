"""Batch-execution operations for agent-based corpus actions.

``CorpusActionService`` owns the *batch* side of corpus actions — running a
single ``CorpusAction`` across every active document in its corpus that has
not yet been processed. The per-row CRUD for ``CorpusAction`` lives in
``config/graphql/corpus_mutations.py`` and is mediated by DRF; this service
is specifically the "Run on all documents" surface that the
``StartCorpusActionBatchRun`` GraphQL mutation calls into.

Pairs with the existing single-document ``RunCorpusAction`` mutation: same
``run_agent_corpus_action`` Celery task, same ``CorpusActionExecution.bulk_queue``
row creation, same ``transaction.on_commit`` dispatch — but for the whole
corpus at once.
"""

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
    """Result envelope for ``CorpusActionService.batch_run_on_corpus``.

    ``executions`` is the list of freshly created ``CorpusActionExecution``
    rows (status = ``QUEUED``). ``skipped_already_run_count`` counts active
    documents that were excluded because they already had a queued, running,
    or completed execution for the same action — these are intentionally
    not re-queued. ``total_active_documents`` is the size of the corpus's
    active-document set before filtering, so callers can render a sensible
    progress message.
    """

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
        """Queue an agent action against every eligible document in its corpus.

        ``action_id`` is the raw PK of the ``CorpusAction``. The service
        resolves it internally — the gate is corpus ``UPDATE``, not direct
        permission on the action row, so corpus collaborators (who hold
        corpus UPDATE but not necessarily a Guardian grant on the action
        itself) can press the button.

        Eligibility:
        * The document has an active (non-deleted, non-CAML) path in
          ``action.corpus``.
        * The document does NOT already have a queued, running, or completed
          ``CorpusActionExecution`` for this exact ``action``. Failed and
          skipped executions are deliberately re-queued so the button doubles
          as a retry path.

        IDOR safety: a missing action and an action in a corpus the user
        lacks UPDATE on both return the same ``_NOT_FOUND_MESSAGE``.

        Dispatch happens inside ``transaction.on_commit`` so the
        ``CorpusActionExecution`` rows are visible to the Celery worker
        before it tries to load them.
        """
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

        active_doc_ids = set(
            corpus._get_active_documents().values_list("id", flat=True)
        )
        total_active = len(active_doc_ids)

        already_run_ids = cls._already_run_document_ids(action)
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
                f"Batch run would queue {len(eligible_ids)} documents, "
                f"which exceeds the per-call cap of {BATCH_RUN_MAX_DOCS}. "
                "Wait for in-flight runs to finish before pressing again, or "
                "narrow the corpus first."
            )

        with transaction.atomic():
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
        """Document IDs that already have a non-terminal-failed execution for ``action``.

        "Already run" = ``QUEUED`` (in flight), ``RUNNING`` (in flight), or
        ``COMPLETED`` (success). ``FAILED`` and ``SKIPPED`` are intentionally
        excluded so the batch button retries them.

        Backed by the composite ``corpusactionexec_dedup`` index on
        ``(corpus_action, document, status)``.
        """
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
            ).values_list("document_id", flat=True)
        )
