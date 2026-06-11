"""One-click "collection intelligence" setup.

Composes the existing enrichment machinery into a single idempotent call —
the orchestration layer the pieces were missing:

1. **Deterministic**: installs the reference-enrichment analyzer as an
   ``add_document`` CorpusAction (the same row the governance graph's
   "Map the reference web" CTA creates) and starts an immediate corpus
   analysis so the reference web weaves now, not just on the next upload.
2. **LLM-backed**: clones the seeded action templates named in
   ``INTELLIGENCE_SETUP_TEMPLATE_NAMES`` (document descriptions + summaries)
   into the corpus and batch-runs each over every document already present.

Every step skips work that already exists (action rows are deduped, batch
runs skip already-executed documents, an in-flight reference analysis is not
duplicated), so the call is safe to repeat — re-running converges instead of
fanning out duplicate agent runs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from opencontractserver.constants.corpus_actions import (
    INTELLIGENCE_SETUP_TEMPLATE_NAMES,
    REFERENCE_ENRICHMENT_ACTION_NAME,
)
from opencontractserver.shared.services.base import BaseService
from opencontractserver.shared.services.conventions import ServiceResult
from opencontractserver.types.enums import PermissionTypes

logger = logging.getLogger(__name__)


@dataclass
class TemplateSetupOutcome:
    """Per-template result of the LLM half of the bundle."""

    template_name: str
    installed_now: bool
    already_installed: bool
    queued_count: int
    skipped_already_run_count: int
    error: str = ""


@dataclass
class IntelligenceSetupSummary:
    """Result envelope for ``CorpusIntelligenceSetupService.setup``."""

    reference_action_installed_now: bool
    reference_action_already_installed: bool
    reference_analysis_started: bool
    reference_available: bool
    templates: list[TemplateSetupOutcome] = field(default_factory=list)
    total_active_documents: int = 0


@dataclass
class IntelligenceSetupStatus:
    """Which bundle pieces a corpus already has (drives the setup CTA)."""

    reference_action_installed: bool
    installed_template_names: list[str]
    missing_template_names: list[str]

    @property
    def is_fully_set_up(self) -> bool:
        return self.reference_action_installed and not self.missing_template_names


class CorpusIntelligenceSetupService(BaseService):
    """Install + kick off the default corpus-intelligence bundle."""

    _NOT_FOUND_MESSAGE = "Corpus not found or you don't have permission."

    # ------------------------------------------------------------------
    # Status (read-only; powers the CTA's visibility)
    # ------------------------------------------------------------------
    @classmethod
    def status(
        cls,
        user: Any,
        corpus_pk: int,
        *,
        request: Any = None,
    ) -> ServiceResult[IntelligenceSetupStatus]:
        """Report which bundle pieces are already installed on the corpus."""
        from opencontractserver.corpuses.models import Corpus, CorpusAction

        corpus = cls.get_or_none(Corpus, corpus_pk, user)
        if corpus is None:
            return ServiceResult.failure(cls._NOT_FOUND_MESSAGE)

        reference_installed = cls._reference_action_qs(corpus).exists()
        installed = list(
            CorpusAction.objects.filter(
                corpus=corpus,
                source_template__name__in=INTELLIGENCE_SETUP_TEMPLATE_NAMES,
            ).values_list("source_template__name", flat=True)
        )
        missing = [
            name for name in INTELLIGENCE_SETUP_TEMPLATE_NAMES if name not in installed
        ]
        return ServiceResult.success(
            IntelligenceSetupStatus(
                reference_action_installed=reference_installed,
                installed_template_names=installed,
                missing_template_names=missing,
            )
        )

    # ------------------------------------------------------------------
    # Setup (mutating)
    # ------------------------------------------------------------------
    @classmethod
    def setup(
        cls,
        user: Any,
        corpus_pk: int,
        *,
        request: Any = None,
    ) -> ServiceResult[IntelligenceSetupSummary]:
        """Install the bundle and kick off enrichment over existing documents."""
        from opencontractserver.corpuses.models import Corpus

        corpus = cls.get_or_none(Corpus, corpus_pk, user)
        if corpus is None:
            return ServiceResult.failure(cls._NOT_FOUND_MESSAGE)
        error = cls.require_permission(
            corpus,
            user,
            PermissionTypes.UPDATE,
            request=request,
            error_message=cls._NOT_FOUND_MESSAGE,
        )
        if error:
            return ServiceResult.failure(error)

        summary = IntelligenceSetupSummary(
            reference_action_installed_now=False,
            reference_action_already_installed=False,
            reference_analysis_started=False,
            reference_available=False,
            total_active_documents=corpus._get_active_documents().count(),
        )

        cls._setup_reference_enrichment(user, corpus, summary, request=request)
        cls._setup_templates(user, corpus, summary, request=request)

        cls.log_action(
            "Intelligence setup for",
            corpus,
            user,
            reference_started=summary.reference_analysis_started,
            templates_installed=[
                t.template_name for t in summary.templates if t.installed_now
            ],
            queued=sum(t.queued_count for t in summary.templates),
        )
        return ServiceResult.success(summary)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    @classmethod
    def _reference_action_qs(cls, corpus: Any):
        """The corpus's add_document reference-enrichment action rows."""
        from opencontractserver.corpuses.models import (
            CorpusAction,
            CorpusActionTrigger,
        )
        from opencontractserver.enrichment import constants as enrichment_constants

        return CorpusAction.objects.filter(
            corpus=corpus,
            trigger=CorpusActionTrigger.ADD_DOCUMENT.value,
            analyzer__task_name=enrichment_constants.ENRICHMENT_ANALYZER_TASK,
        )

    @classmethod
    def _setup_reference_enrichment(
        cls,
        user: Any,
        corpus: Any,
        summary: IntelligenceSetupSummary,
        *,
        request: Any = None,
    ) -> None:
        """Install the reference-web action and start the first weave."""
        from opencontractserver.analyzer.models import Analysis, Analyzer
        from opencontractserver.analyzer.services.analysis_lifecycle_service import (
            AnalysisLifecycleService,
        )
        from opencontractserver.corpuses.models import (
            CorpusAction,
            CorpusActionTrigger,
        )
        from opencontractserver.enrichment import constants as enrichment_constants
        from opencontractserver.types.enums import JobStatus
        from opencontractserver.utils.permissioning import (
            set_permissions_for_obj_to_user,
        )

        analyzer = Analyzer.objects.filter(
            task_name=enrichment_constants.ENRICHMENT_ANALYZER_TASK
        ).first()
        if analyzer is None:
            # Deployment without the enrichment analyzer registered — the
            # LLM half of the bundle still proceeds.
            logger.info(
                "Intelligence setup: reference-enrichment analyzer not "
                "registered; skipping the deterministic half."
            )
            return
        summary.reference_available = True

        if cls._reference_action_qs(corpus).exists():
            summary.reference_action_already_installed = True
        else:
            action = CorpusAction.objects.create(
                name=REFERENCE_ENRICHMENT_ACTION_NAME,
                corpus=corpus,
                analyzer=analyzer,
                trigger=CorpusActionTrigger.ADD_DOCUMENT.value,
                creator=user,
            )
            set_permissions_for_obj_to_user(
                user, action, [PermissionTypes.CRUD], request=request
            )
            summary.reference_action_installed_now = True

        # First weave now (not just on the next upload) — unless one is
        # already in flight, in which case starting another would only
        # duplicate work the running analysis will do anyway.
        in_flight = Analysis.objects.filter(
            analyzer=analyzer,
            analyzed_corpus=corpus,
            status__in=[JobStatus.QUEUED.value, JobStatus.RUNNING.value],
        ).exists()
        if in_flight:
            return
        result = AnalysisLifecycleService.start_document_analysis(
            user,
            analyzer_pk=analyzer.pk,
            corpus_pk=corpus.pk,
            request=request,
        )
        summary.reference_analysis_started = bool(result.ok)
        if not result.ok:
            logger.warning(
                "Intelligence setup: reference analysis failed to start for "
                "corpus %s: %s",
                corpus.pk,
                result.error,
            )

    @classmethod
    def _setup_templates(
        cls,
        user: Any,
        corpus: Any,
        summary: IntelligenceSetupSummary,
        *,
        request: Any = None,
    ) -> None:
        """Clone the bundle templates and batch-run each over existing docs."""
        from django.db import IntegrityError, transaction

        from opencontractserver.corpuses.models import (
            CorpusAction,
            CorpusActionTemplate,
        )
        from opencontractserver.corpuses.services.corpus_actions import (
            CorpusActionService,
        )
        from opencontractserver.utils.permissioning import (
            set_permissions_for_obj_to_user,
        )

        for name in INTELLIGENCE_SETUP_TEMPLATE_NAMES:
            outcome = TemplateSetupOutcome(
                template_name=name,
                installed_now=False,
                already_installed=False,
                queued_count=0,
                skipped_already_run_count=0,
            )
            summary.templates.append(outcome)

            template = CorpusActionTemplate.objects.filter(
                name=name, is_active=True
            ).first()
            if template is None:
                outcome.error = "Template not found or inactive."
                logger.warning(
                    "Intelligence setup: template %r missing on corpus %s",
                    name,
                    corpus.pk,
                )
                continue

            action = CorpusAction.objects.filter(
                corpus=corpus, source_template=template
            ).first()
            if action is not None:
                outcome.already_installed = True
            else:
                try:
                    # Savepoint so a duplicate-insert race doesn't poison the
                    # outer transaction (mirrors AddTemplateToCorpus).
                    with transaction.atomic():
                        action = template.clone_to_corpus(corpus, creator=user)
                except IntegrityError:
                    action = CorpusAction.objects.filter(
                        corpus=corpus, source_template=template
                    ).first()
                    outcome.already_installed = action is not None
                if action is None:
                    outcome.error = "Failed to install template."
                    continue
                if outcome.already_installed is False:
                    set_permissions_for_obj_to_user(
                        user, action, [PermissionTypes.CRUD], request=request
                    )
                    outcome.installed_now = True

            batch = CorpusActionService.batch_run_on_corpus(
                user, action.pk, request=request
            )
            if batch.ok and batch.value is not None:
                outcome.queued_count = batch.value.queued_count
                outcome.skipped_already_run_count = (
                    batch.value.skipped_already_run_count
                )
            else:
                # Surface (e.g. the BATCH_RUN_MAX_DOCS cap) without failing
                # the whole setup — the action is installed and will run on
                # future uploads regardless.
                outcome.error = batch.error or "Batch run failed."
