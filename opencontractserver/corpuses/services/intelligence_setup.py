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
    # Documents deferred past the per-call batch cap — a later run (or the
    # add_document trigger) picks them up.
    remaining_count: int = 0


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

    reference_available: bool
    reference_action_installed: bool
    installed_template_names: list[str]
    missing_template_names: list[str]
    can_setup: bool

    @property
    def is_fully_set_up(self) -> bool:
        """Everything *installable on this deployment* is installed.

        Pieces the deployment cannot provide (no enrichment analyzer
        registered, bundle template missing/inactive) are excluded — they can
        never install, so requiring them would leave the setup CTA visible
        forever with nothing left for it to do.
        """
        reference_done = self.reference_action_installed or not self.reference_available
        return reference_done and not self.missing_template_names


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
        """Report which bundle pieces are already installed on the corpus.

        A handful of DB queries per call (corpus fetch, analyzer lookup,
        reference-action exists, available + installed template names, one
        permission check). Mounted once per corpus page load, so the cost is
        negligible; revisit (e.g. a single aggregated query) if this is ever
        polled or rendered per-row in the corpus list.
        """
        from opencontractserver.corpuses.models import (
            Corpus,
            CorpusAction,
            CorpusActionTemplate,
        )
        from opencontractserver.enrichment.services import EnrichmentService

        corpus = cls.get_or_none(Corpus, corpus_pk, user)
        if corpus is None:
            return ServiceResult.failure(cls._NOT_FOUND_MESSAGE)

        reference_available = EnrichmentService.get_analyzer() is not None
        reference_installed = cls._reference_action_qs(corpus).exists()
        available = set(
            CorpusActionTemplate.objects.filter(
                name__in=INTELLIGENCE_SETUP_TEMPLATE_NAMES, is_active=True
            ).values_list("name", flat=True)
        )
        installed = list(
            CorpusAction.objects.filter(
                corpus=corpus,
                source_template__name__in=INTELLIGENCE_SETUP_TEMPLATE_NAMES,
            ).values_list("source_template__name", flat=True)
        )
        # Only deployment-available templates count as missing — an inactive
        # or unseeded template can never install (see is_fully_set_up).
        missing = [
            name
            for name in INTELLIGENCE_SETUP_TEMPLATE_NAMES
            if name in available and name not in installed
        ]
        return ServiceResult.success(
            IntelligenceSetupStatus(
                reference_available=reference_available,
                reference_action_installed=reference_installed,
                installed_template_names=installed,
                missing_template_names=missing,
                # Mirrors setup()'s gate so the CTA never renders for viewers
                # whose click is guaranteed to fail.
                can_setup=cls.user_has(
                    corpus, user, PermissionTypes.CRUD, request=request
                ),
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
        """Install the bundle and kick off enrichment over existing documents.

        Gated at CRUD — the same tier ``AddTemplateToCorpus`` and
        ``CreateCorpusAction`` require for installing the identical rows
        individually, so this composite is never a weaker path to the same
        writes.
        """
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.corpuses.services.corpus_documents import (
            CorpusDocumentService,
        )

        # Single IDOR-safe CRUD lookup — collapses the READ gate and the CRUD
        # check into one call (the canonical pattern, same as ``status()``'s
        # READ gate). A user without CRUD gets ``None`` and the
        # indistinguishable not-found message, so existence can't be enumerated.
        corpus = cls.get_or_none(
            Corpus, corpus_pk, user, PermissionTypes.CRUD, request=request
        )
        if corpus is None:
            return ServiceResult.failure(cls._NOT_FOUND_MESSAGE)

        summary = IntelligenceSetupSummary(
            reference_action_installed_now=False,
            reference_action_already_installed=False,
            reference_analysis_started=False,
            reference_available=False,
        )

        cls._setup_reference_enrichment(user, corpus, summary, request=request)
        batch_total = cls._setup_templates(user, corpus, summary, request=request)
        cls._setup_structured_profile(user, corpus, request=request)
        # Every batch run already computes the active-document total; only
        # fall back to a standalone corpus-as-gate count through the service
        # (the setup user holds CRUD, hence READ) when no batch ran — same
        # active-document set, include_caml=False on both surfaces.
        summary.total_active_documents = (
            batch_total
            if batch_total is not None
            else CorpusDocumentService.get_corpus_documents(
                user, corpus, request=request
            ).count()
        )

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
        from opencontractserver.analyzer.models import Analysis
        from opencontractserver.analyzer.services.analysis_lifecycle_service import (
            AnalysisLifecycleService,
        )
        from opencontractserver.corpuses.models import CorpusActionTrigger
        from opencontractserver.enrichment.services import EnrichmentService
        from opencontractserver.types.enums import JobStatus
        from opencontractserver.utils.permissioning import (
            set_permissions_for_obj_to_user,
        )

        analyzer = EnrichmentService.get_analyzer()
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
            from opencontractserver.corpuses.models import CorpusAction

            # get_or_create (rather than a bare create()) narrows the
            # concurrent-double-install window and converges on the same row
            # the governance graph's bootstrap CTA creates, regardless of
            # which path ran first. No DB constraint backs this up
            # (source_template is NULL, so unique_template_per_corpus doesn't
            # apply) — a duplicate from a photo-finish race is wasted work,
            # not corruption (the enrichment writer is idempotent).
            action, created = CorpusAction.objects.get_or_create(
                corpus=corpus,
                trigger=CorpusActionTrigger.ADD_DOCUMENT.value,
                analyzer=analyzer,
                defaults={
                    "name": REFERENCE_ENRICHMENT_ACTION_NAME,
                    "creator": user,
                },
            )
            if created:
                set_permissions_for_obj_to_user(
                    user, action, [PermissionTypes.CRUD], request=request
                )
                summary.reference_action_installed_now = True
            else:
                summary.reference_action_already_installed = True

        # First weave now (not just on the next upload) — unless one is
        # already in flight, in which case starting another would only
        # duplicate work the running analysis will do anyway. The check and the
        # start below are intentionally non-atomic: a concurrent request could
        # slip between them and start a second analysis, but that is recoverable
        # (the enrichment writer is idempotent — just wasted work), so a lock is
        # not warranted here.
        in_flight = Analysis.objects.filter(
            analyzer=analyzer,
            analyzed_corpus=corpus,
            status__in=[JobStatus.QUEUED.value, JobStatus.RUNNING.value],
        ).exists()
        if in_flight:
            # A weave is already QUEUED/RUNNING — the reference web IS being
            # built, just not started by this call. Report it as started so the
            # summary (and the frontend toast) doesn't misleadingly omit the
            # "reference web weaving" note when an earlier setup/CTA is mid-run.
            summary.reference_analysis_started = True
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
    ) -> int | None:
        """Clone the bundle templates and batch-run each over existing docs.

        Returns the active-document total computed by the last batch run, or
        ``None`` when no batch ran (lets ``setup`` skip a redundant count).
        """
        from opencontractserver.corpuses.models import CorpusActionTemplate
        from opencontractserver.corpuses.services.corpus_actions import (
            CorpusActionService,
        )

        templates_by_name = {
            t.name: t
            for t in CorpusActionTemplate.objects.filter(
                name__in=INTELLIGENCE_SETUP_TEMPLATE_NAMES, is_active=True
            )
        }
        batch_total: int | None = None

        for name in INTELLIGENCE_SETUP_TEMPLATE_NAMES:
            outcome = TemplateSetupOutcome(
                template_name=name,
                installed_now=False,
                already_installed=False,
                queued_count=0,
                skipped_already_run_count=0,
            )
            summary.templates.append(outcome)

            template = templates_by_name.get(name)
            if template is None:
                outcome.error = "Template not found or inactive."
                logger.warning(
                    "Intelligence setup: template %r missing on corpus %s",
                    name,
                    corpus.pk,
                )
                continue

            try:
                action, created = CorpusActionService.install_template(
                    user, corpus, template, request=request
                )
            except Exception as exc:
                # Any non-IntegrityError clone failure (e.g. OperationalError,
                # ValueError) must stay contained to this template — the bundle
                # promises graceful partial success, so record it and move on
                # rather than aborting the remaining templates with a 500.
                outcome.error = f"Failed to install template: {exc}"
                logger.exception(
                    "Intelligence setup: clone failed for %r on corpus %s",
                    name,
                    corpus.pk,
                )
                continue
            if action is None:
                outcome.error = "Failed to install template."
                continue
            if created:
                outcome.installed_now = True
            else:
                outcome.already_installed = True

            # Partial mode: a corpus larger than the per-call cap queues the
            # first cap-many documents instead of nothing — the remainder is
            # reported so the UI can say what's deferred.
            batch = CorpusActionService.batch_run_action(
                user, action, request=request, allow_partial=True
            )
            if batch.ok and batch.value is not None:
                outcome.queued_count = batch.value.queued_count
                outcome.skipped_already_run_count = (
                    batch.value.skipped_already_run_count
                )
                batch_total = batch.value.total_active_documents
                outcome.remaining_count = max(
                    0,
                    batch_total
                    - outcome.skipped_already_run_count
                    - outcome.queued_count,
                )
            else:
                # Surface without failing the whole setup — the action is
                # installed and will run on future uploads regardless.
                outcome.error = batch.error or "Batch run failed."

        return batch_total

    @classmethod
    def _setup_structured_profile(
        cls,
        user: Any,
        corpus: Any,
        *,
        request: Any = None,
    ) -> None:
        """Install the default Collection Profile fieldset + add_document action,
        then backfill existing documents exactly once.

        The action keeps the per-document profile (type / counterparty / effective
        date / value) growing as documents arrive: each upload appends only the
        new document's cells to one accumulating Extract — ``process_corpus_action``
        ``get_or_create``s by ``(corpus, fieldset, corpus_action)`` and never
        spawns a fresh extract or recomputes existing rows. The backfill below
        runs only while that extract has no cells yet, so a freshly-set-up corpus
        profiles its initial batch once and re-running setup is a no-op.

        Failures here must never abort the rest of the bundle — the data story is
        an enhancement, not a precondition — so the whole method is best-effort.
        """
        from django.db import transaction
        from django.utils import timezone

        from opencontractserver.corpuses.models import (
            CorpusAction,
            CorpusActionTrigger,
        )
        from opencontractserver.corpuses.services.corpus_documents import (
            CorpusDocumentService,
        )
        from opencontractserver.corpuses.services.data_story import (
            PROFILE_ACTION_NAME,
            get_or_create_default_profile_fieldset,
        )
        from opencontractserver.extracts.models import Datacell, Extract
        from opencontractserver.tasks.extract_orchestrator_tasks import run_extract
        from opencontractserver.utils.permissioning import (
            set_permissions_for_obj_to_user,
        )

        try:
            fieldset, _ = get_or_create_default_profile_fieldset(user)

            action, action_created = CorpusAction.objects.get_or_create(
                corpus=corpus,
                fieldset=fieldset,
                trigger=CorpusActionTrigger.ADD_DOCUMENT.value,
                defaults={"name": PROFILE_ACTION_NAME, "creator": user},
            )
            if action_created:
                set_permissions_for_obj_to_user(
                    user, action, [PermissionTypes.CRUD], request=request
                )

            # The single accumulating extract — keyed on
            # ``(corpus, fieldset, corpus_action)``, the same canonical key
            # ``process_corpus_action`` uses, so the add_document action appends
            # new documents' cells into THIS extract rather than a new one.
            # ``name`` and ``creator`` are in ``defaults`` (NOT lookup fields):
            # the name embeds the mutable ``corpus.title`` and the creator differs
            # between the setup admin and later document-adders, so keying on
            # either would fork a second accumulating extract.
            extract, extract_created = Extract.objects.get_or_create(
                corpus=corpus,
                fieldset=fieldset,
                corpus_action=action,
                defaults={
                    "name": f"Action {action.name} for {corpus.title}",
                    "creator": user,
                },
            )
            if extract_created:
                set_permissions_for_obj_to_user(
                    user,
                    extract,
                    [PermissionTypes.CRUD],
                    request=request,
                    is_new=True,
                )

            # One-time backfill of the documents already in the corpus. New docs
            # added later flow through the add_document action, not here, so we
            # never recompute existing rows.
            if Datacell.objects.filter(extract=extract).exists():
                return
            docs = list(
                CorpusDocumentService.get_corpus_documents(
                    user, corpus, request=request
                )
            )
            if not docs:
                return
            extract.documents.add(*docs)
            extract.started = timezone.now()
            extract.finished = None
            extract.save()

            extract_id = extract.id
            user_id = user.id
            transaction.on_commit(lambda: run_extract.delay(extract_id, user_id))
        except Exception:
            logger.exception(
                "Intelligence setup: structured profile setup failed for corpus %s",
                getattr(corpus, "id", None),
            )
