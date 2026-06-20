"""Tests for the RunCorpusEnrichmentMutation GraphQL mutation.

Verifies that the mutation:
- dispatches the enrichment analyzer when ``run_enrichment=True``
- dispatches the crawl analyzer when ``run_crawl=True``
- rejects callers who do not have READ on the corpus
- rejects callers who have READ but not UPDATE on the corpus
- rejects calls with neither flag set
- rejects invalid reference_type codes (rather than silently dropping them)
- returns partial success (ok=True) when enrichment dispatches but the crawl
  fails, so the running enrichment job is surfaced to the caller
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from opencontractserver.analyzer.services.analysis_lifecycle_service import (
    AnalysisLifecycleService,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.enrichment import constants as C
from opencontractserver.shared.services.conventions import ServiceResult
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()

RUN_MUTATION = """
mutation Run(
  $corpusId: ID!
  $runEnrichment: Boolean
  $runCrawl: Boolean
  $options: RunEnrichmentOptionsInput
) {
  runCorpusEnrichment(
    corpusId: $corpusId
    runEnrichment: $runEnrichment
    runCrawl: $runCrawl
    options: $options
  ) {
    ok
    message
    partial
    analyses {
      id
      status
      analyzer {
        taskName
      }
    }
  }
}
"""


class _GQLContext:
    def __init__(self, user):
        self.user = user


def _make_private_corpus(user, title="Test Corpus"):
    """Create a PRIVATE corpus owned by *user* (no is_public flag → private)."""
    return Corpus.objects.create(title=title, creator=user)


class RunCorpusEnrichmentMutationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner-run", password="p")
        self.corpus = _make_private_corpus(self.owner)
        # Lazy import: building the graphene schema at module import time can
        # trip a graphene-django field-resolution error under coverage
        # instrumentation. Defer to setUp so the schema builds at runtime.
        from config.graphql.schema import schema

        self.client = Client(schema)

    def _execute(self, variables, user=None):
        user = user or self.owner
        # graphene.test.Client.execute is missing from graphene's type stubs.
        return self.client.execute(  # type: ignore[attr-defined]
            RUN_MUTATION,
            variable_values=variables,
            context_value=_GQLContext(user),
        )

    # ------------------------------------------------------------------
    # Happy-path: enrichment analyzer
    # ------------------------------------------------------------------

    def test_run_enrichment_dispatches_enrichment_analyzer(self):
        from opencontractserver.analyzer.models import Analysis

        result = self._execute(
            {
                "corpusId": to_global_id("CorpusType", self.corpus.id),
                "runEnrichment": True,
                "runCrawl": False,
                "options": {"referenceTypes": ["LAW"], "useLlmTier": False},
            }
        )
        assert result.get("errors") is None, result
        data = result["data"]["runCorpusEnrichment"]
        assert data["ok"] is True
        assert data["message"] == "SUCCESS"
        assert len(data["analyses"]) == 1
        assert data["analyses"][0]["analyzer"]["taskName"] == C.ENRICHMENT_ANALYZER_TASK
        assert Analysis.objects.filter(
            analyzed_corpus=self.corpus,
            analyzer__task_name=C.ENRICHMENT_ANALYZER_TASK,
        ).exists()

    # ------------------------------------------------------------------
    # Happy-path: crawl analyzer
    # ------------------------------------------------------------------

    def test_run_crawl_dispatches_crawl_analyzer(self):
        from opencontractserver.analyzer.models import Analysis

        result = self._execute(
            {
                "corpusId": to_global_id("CorpusType", self.corpus.id),
                "runEnrichment": False,
                "runCrawl": True,
            }
        )
        assert result.get("errors") is None, result
        data = result["data"]["runCorpusEnrichment"]
        assert data["ok"] is True
        assert Analysis.objects.filter(
            analyzed_corpus=self.corpus,
            analyzer__task_name=C.CRAWL_ANALYZER_TASK,
        ).exists()

    # ------------------------------------------------------------------
    # Happy-path: both flags
    # ------------------------------------------------------------------

    def test_run_both_creates_two_analyses(self):
        from opencontractserver.analyzer.models import Analysis

        result = self._execute(
            {
                "corpusId": to_global_id("CorpusType", self.corpus.id),
                "runEnrichment": True,
                "runCrawl": True,
            }
        )
        assert result.get("errors") is None, result
        data = result["data"]["runCorpusEnrichment"]
        assert data["ok"] is True
        assert len(data["analyses"]) == 2
        task_names = {a["analyzer"]["taskName"] for a in data["analyses"]}
        assert task_names == {C.ENRICHMENT_ANALYZER_TASK, C.CRAWL_ANALYZER_TASK}
        assert Analysis.objects.filter(analyzed_corpus=self.corpus).count() == 2

    # ------------------------------------------------------------------
    # Error: no permission (corpus is PRIVATE; stranger has no READ)
    # ------------------------------------------------------------------

    def test_rejects_corpus_without_permission(self):
        stranger = User.objects.create_user(username="stranger-run", password="p")
        result = self._execute(
            {
                "corpusId": to_global_id("CorpusType", self.corpus.id),
                "runEnrichment": True,
                "runCrawl": False,
            },
            user=stranger,
        )
        assert result.get("errors") is None, result
        data = result["data"]["runCorpusEnrichment"]
        assert data["ok"] is False

    # ------------------------------------------------------------------
    # Error: neither flag set
    # ------------------------------------------------------------------

    def test_rejects_when_no_job_selected(self):
        result = self._execute(
            {
                "corpusId": to_global_id("CorpusType", self.corpus.id),
                "runEnrichment": False,
                "runCrawl": False,
            }
        )
        assert result.get("errors") is None, result
        data = result["data"]["runCorpusEnrichment"]
        assert data["ok"] is False
        assert "at least one" in data["message"].lower()

    # ------------------------------------------------------------------
    # Error: malformed corpus global-id
    # ------------------------------------------------------------------

    def test_rejects_malformed_corpus_id(self):
        result = self._execute(
            {
                "corpusId": "not-a-relay-id",
                "runEnrichment": True,
                "runCrawl": False,
            }
        )
        assert result.get("errors") is None, result
        data = result["data"]["runCorpusEnrichment"]
        assert data["ok"] is False

    # ------------------------------------------------------------------
    # Security: a well-formed relay id of the WRONG type (e.g. DocumentType)
    # must not have its numeric pk flow through as a corpus pk.
    # ------------------------------------------------------------------

    def test_rejects_wrong_global_id_type(self):
        """``from_global_id`` decodes ``DocumentType:<pk>`` happily; the mutation
        must reject any non-Corpus type prefix rather than relying on the
        downstream visibility filter to (maybe) miss the smuggled pk."""
        # Encode this corpus's own pk under a DocumentType prefix — without the
        # type guard the numeric pk would resolve to the real corpus.
        result = self._execute(
            {
                "corpusId": to_global_id("DocumentType", self.corpus.id),
                "runEnrichment": True,
                "runCrawl": False,
            }
        )
        assert result.get("errors") is None, result
        data = result["data"]["runCorpusEnrichment"]
        assert data["ok"] is False
        # Same generic message as the not-found path (no type oracle).
        assert "not found" in data["message"].lower()

    # ------------------------------------------------------------------
    # Error: READ-only user cannot trigger enrichment (requires UPDATE)
    # ------------------------------------------------------------------

    def test_rejects_read_only_user(self):
        """A user with READ but not UPDATE on the corpus must be rejected."""
        reader = User.objects.create_user(username="reader-run", password="p")
        # Grant READ (and only READ) on the private corpus.
        set_permissions_for_obj_to_user(reader, self.corpus, [PermissionTypes.READ])

        result = self._execute(
            {
                "corpusId": to_global_id("CorpusType", self.corpus.id),
                "runEnrichment": True,
                "runCrawl": False,
            },
            user=reader,
        )
        assert result.get("errors") is None, result
        data = result["data"]["runCorpusEnrichment"]
        assert data["ok"] is False

    # ------------------------------------------------------------------
    # Validation: invalid reference_types are REJECTED (not silently dropped)
    # ------------------------------------------------------------------

    def test_invalid_reference_types_are_rejected(self):
        """Unknown type codes are rejected so a caller cannot accidentally
        trigger an all-types scan by sending only-bogus codes.

        Previously unknown codes were filtered out; an all-bogus list collapsed
        to an empty filter and scanned EVERY reference type — the opposite of
        the caller's intent. The mutation now rejects any unknown code and
        dispatches nothing.
        """
        from opencontractserver.analyzer.models import Analysis

        result = self._execute(
            {
                "corpusId": to_global_id("CorpusType", self.corpus.id),
                "runEnrichment": True,
                "runCrawl": False,
                # Mix of one valid and one completely bogus code.
                "options": {"referenceTypes": ["LAW", "INVALID_CODE"]},
            }
        )
        assert result.get("errors") is None, result
        data = result["data"]["runCorpusEnrichment"]
        assert data["ok"] is False
        # The offending code is named so the caller knows what to fix.
        assert "INVALID_CODE" in data["message"]
        # Nothing was dispatched.
        assert not Analysis.objects.filter(
            analyzed_corpus=self.corpus,
            analyzer__task_name=C.ENRICHMENT_ANALYZER_TASK,
        ).exists()

    def test_valid_reference_types_are_accepted(self):
        """A fully valid multi-type list dispatches enrichment normally."""
        from opencontractserver.analyzer.models import Analysis

        result = self._execute(
            {
                "corpusId": to_global_id("CorpusType", self.corpus.id),
                "runEnrichment": True,
                "runCrawl": False,
                # Sourced from the constant so the test stays correct if the
                # reference-type vocabulary changes.
                "options": {"referenceTypes": list(C.ALL_REFERENCE_TYPES)},
            }
        )
        assert result.get("errors") is None, result
        data = result["data"]["runCorpusEnrichment"]
        assert data["ok"] is True
        assert data["partial"] is False
        assert Analysis.objects.filter(
            analyzed_corpus=self.corpus,
            analyzer__task_name=C.ENRICHMENT_ANALYZER_TASK,
        ).exists()

    # ------------------------------------------------------------------
    # Partial success: enrichment dispatched but crawl failed
    # ------------------------------------------------------------------

    def test_partial_success_when_crawl_fails(self):
        """When enrichment dispatches but the crawl fails, the mutation returns
        ok=True with the running enrichment row and a non-fatal message — so the
        caller shows the running job rather than retrying (double-dispatching)
        enrichment."""
        from opencontractserver.analyzer.models import Analysis
        from opencontractserver.enrichment.services import EnrichmentService

        # A real enrichment Analysis to stand in as the dispatched running job.
        analyzer = EnrichmentService.get_or_create_analyzer(self.owner.id)
        analysis = Analysis.objects.create(
            analyzer=analyzer,
            analyzed_corpus=self.corpus,
            creator=self.owner,
        )

        # First call (enrichment) succeeds, second call (crawl) fails.
        with patch.object(
            AnalysisLifecycleService,
            "start_document_analysis",
            side_effect=[
                ServiceResult.success(analysis),
                ServiceResult.failure("crawl boom"),
            ],
        ):
            result = self._execute(
                {
                    "corpusId": to_global_id("CorpusType", self.corpus.id),
                    "runEnrichment": True,
                    "runCrawl": True,
                }
            )

        assert result.get("errors") is None, result
        data = result["data"]["runCorpusEnrichment"]
        assert data["ok"] is True
        # partial=True flags the half-failure without coupling callers to the
        # message text.
        assert data["partial"] is True
        assert "crawl boom" in data["message"]
        # Only the enrichment row is returned (the crawl never started).
        assert len(data["analyses"]) == 1
        assert data["analyses"][0]["analyzer"]["taskName"] == C.ENRICHMENT_ANALYZER_TASK

    def test_crawl_only_failure_returns_not_ok(self):
        """A crawl-only run that fails has no already-dispatched job, so it
        returns ok=False (no partial-success masking)."""
        with patch.object(
            AnalysisLifecycleService,
            "start_document_analysis",
            side_effect=[ServiceResult.failure("crawl boom")],
        ):
            result = self._execute(
                {
                    "corpusId": to_global_id("CorpusType", self.corpus.id),
                    "runEnrichment": False,
                    "runCrawl": True,
                }
            )

        assert result.get("errors") is None, result
        data = result["data"]["runCorpusEnrichment"]
        assert data["ok"] is False
        assert data["analyses"] == []
