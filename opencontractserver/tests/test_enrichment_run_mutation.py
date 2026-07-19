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
from graphql_relay import to_global_id

from config.graphql.testing import Client
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

    def test_no_active_job_oracle_for_unauthorized_user(self):
        """A caller with no permission on the corpus must get the SAME generic
        message whether or not the corpus has an active enrichment job.

        Regression test for the duplicate-job guard firing before the corpus
        permission check: without the visibility gate, ``active_analysis_exists``
        would leak "an enrichment analysis is already queued or running" to a
        user who cannot even see the corpus, letting them probe arbitrary
        corpus IDs for running-job state.
        """
        from opencontractserver.analyzer.models import Analysis
        from opencontractserver.enrichment.services import EnrichmentService
        from opencontractserver.types.enums import JobStatus

        analyzer = EnrichmentService.get_or_create_analyzer(self.owner.id)
        Analysis.objects.create(
            analyzer=analyzer,
            analyzed_corpus=self.corpus,
            creator=self.owner,
            status=JobStatus.RUNNING.value,
        )

        stranger = User.objects.create_user(username="stranger-oracle", password="p")
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
        # Same IDOR-safe generic message as the no-permission / no-active-job
        # case — never the job-specific "already queued or running" text.
        assert data["message"] == "Resource not found or you do not have permission."

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
    # Superuser exemption: may trigger WITHOUT UPDATE on a readable corpus
    # (retained admin privilege for the superuser-gated runner). Direct
    # contrast with test_rejects_read_only_user.
    # ------------------------------------------------------------------

    def test_superuser_triggers_without_corpus_update(self):
        """A superuser who is NOT the owner and holds no UPDATE may still
        trigger enrichment on a corpus they can READ — the enrichment/crawl
        runner is a retained superuser admin privilege (see
        docs/permissioning/consolidated_permissioning_guide.md). A
        non-superuser with the same access is rejected (test_rejects_read_only_user)."""
        from opencontractserver.analyzer.models import Analysis

        su = User.objects.create_user(
            username="su-run", password="p", is_superuser=True
        )
        # Public corpus owned by someone else → READ-visible to the superuser,
        # but they hold no UPDATE grant on it.
        public_corpus = Corpus.objects.create(
            title="Public Corpus", creator=self.owner, is_public=True
        )
        result = self._execute(
            {
                "corpusId": to_global_id("CorpusType", public_corpus.id),
                "runEnrichment": True,
                "runCrawl": False,
            },
            user=su,
        )
        assert result.get("errors") is None, result
        data = result["data"]["runCorpusEnrichment"]
        assert data["ok"] is True, data
        assert Analysis.objects.filter(
            analyzed_corpus=public_corpus,
            analyzer__task_name=C.ENRICHMENT_ANALYZER_TASK,
        ).exists()

    def test_superuser_exemption_is_scoped_to_update_not_read(self):
        """The exemption widens write-trigger only — a superuser is still NOT
        exempt from READ visibility, so a PRIVATE corpus they cannot see stays
        unreachable (no blanket bypass)."""
        su = User.objects.create_user(
            username="su-run2", password="p", is_superuser=True
        )
        # self.corpus is private + owned by self.owner; su has no grants on it.
        result = self._execute(
            {
                "corpusId": to_global_id("CorpusType", self.corpus.id),
                "runEnrichment": True,
                "runCrawl": False,
            },
            user=su,
        )
        assert result.get("errors") is None, result
        data = result["data"]["runCorpusEnrichment"]
        assert data["ok"] is False, data

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
        assert data["partial"] is False
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
        from opencontractserver.types.enums import JobStatus

        # A real enrichment Analysis to stand in as the dispatched running job.
        analyzer = EnrichmentService.get_or_create_analyzer(self.owner.id)
        analysis = Analysis.objects.create(
            analyzer=analyzer,
            analyzed_corpus=self.corpus,
            creator=self.owner,
            status=JobStatus.COMPLETED.value,
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
        # `partial` is a concrete False (never null) on every ok=False path.
        assert data["partial"] is False
        assert data["analyses"] == []

    def test_rejects_unbounded_crawl_options(self):
        """Each over-limit crawl bound is rejected by name before any dispatch.

        Tested one field at a time (not all four at once) so the assertion does
        not depend on ``CRAWL_BOUND_LIMITS`` iteration order:
        ``_validate_crawl_bounds`` returns on the FIRST bad field, so a
        reordering of the dict must not silently change which field the test
        happens to catch.
        """
        from opencontractserver.analyzer.models import Analysis

        # camelCase GraphQL option -> (over-limit value, snake_case message field)
        cases = {
            "maxDepth": (C.CRAWL_MAX_ALLOWED_DEPTH + 1, "max_depth"),
            "maxAuthorities": (C.CRAWL_DEFAULT_MAX_AUTHORITIES + 1, "max_authorities"),
            "perJurisdictionCap": (
                C.CRAWL_DEFAULT_PER_JURISDICTION_CAP + 1,
                "per_jurisdiction_cap",
            ),
            "tokenBudget": (0, "token_budget"),  # below the minimum of 1
        }
        for gql_field, (bad_value, msg_field) in cases.items():
            with self.subTest(field=gql_field):
                result = self._execute(
                    {
                        "corpusId": to_global_id("CorpusType", self.corpus.id),
                        "runEnrichment": False,
                        "runCrawl": True,
                        "options": {gql_field: bad_value},
                    }
                )
                assert result.get("errors") is None, result
                data = result["data"]["runCorpusEnrichment"]
                assert data["ok"] is False
                assert data["partial"] is False
                assert msg_field in data["message"]
        # No invalid request dispatched an analysis.
        assert not Analysis.objects.filter(analyzed_corpus=self.corpus).exists()

    def test_high_min_demand_is_accepted(self):
        """A ``min_demand`` ABOVE the default is MORE selective (it skips more
        frontier rows), so it is cheaper and must be accepted — the upper bound
        was removed because capping at the default wrongly rejected conservative
        values. Mirrors the crawl analyzer input schema, which sets only a floor
        on min_demand."""
        from opencontractserver.analyzer.models import Analysis

        result = self._execute(
            {
                "corpusId": to_global_id("CorpusType", self.corpus.id),
                "runEnrichment": False,
                "runCrawl": True,
                "options": {"minDemand": C.CRAWL_DEFAULT_MIN_DEMAND + 100},
            }
        )
        assert result.get("errors") is None, result
        data = result["data"]["runCorpusEnrichment"]
        assert data["ok"] is True, data
        assert Analysis.objects.filter(
            analyzed_corpus=self.corpus,
            analyzer__task_name=C.CRAWL_ANALYZER_TASK,
        ).exists()

    def test_rejects_llm_tier_for_non_admin(self):
        """Low-privileged UPDATE users cannot opt corpus text into LLM export."""
        from opencontractserver.analyzer.models import Analysis
        from opencontractserver.enrichment.services.authority_permissions import (
            is_authority_admin,
        )

        # Precondition: the corpus owner is a plain UPDATE user, NOT an authority
        # admin — otherwise the LLM-tier gate would pass and this test would fail
        # for the wrong reason (and silently stop covering the rejection path).
        assert not is_authority_admin(self.owner)

        result = self._execute(
            {
                "corpusId": to_global_id("CorpusType", self.corpus.id),
                "runEnrichment": True,
                "runCrawl": False,
                "options": {"useLlmTier": True},
            }
        )
        assert result.get("errors") is None, result
        data = result["data"]["runCorpusEnrichment"]
        assert data["ok"] is False
        assert "LLM tier" in data["message"]
        assert not Analysis.objects.filter(analyzed_corpus=self.corpus).exists()

    def test_rejects_duplicate_running_enrichment_job(self):
        """The mutation enforces one active enrichment job per corpus."""
        from opencontractserver.analyzer.models import Analysis
        from opencontractserver.enrichment.services import EnrichmentService
        from opencontractserver.types.enums import JobStatus

        analyzer = EnrichmentService.get_or_create_analyzer(self.owner.id)
        Analysis.objects.create(
            analyzer=analyzer,
            analyzed_corpus=self.corpus,
            creator=self.owner,
            status=JobStatus.RUNNING.value,
        )

        result = self._execute(
            {
                "corpusId": to_global_id("CorpusType", self.corpus.id),
                "runEnrichment": True,
                "runCrawl": False,
            }
        )
        assert result.get("errors") is None, result
        data = result["data"]["runCorpusEnrichment"]
        assert data["ok"] is False
        assert "already queued or running" in data["message"]
        assert (
            Analysis.objects.filter(
                analyzed_corpus=self.corpus,
                analyzer__task_name=C.ENRICHMENT_ANALYZER_TASK,
            ).count()
            == 1
        )

    def test_rejects_duplicate_running_crawl_job(self):
        """The mutation enforces one active crawl job per corpus.

        Symmetric counterpart to ``test_rejects_duplicate_running_enrichment_job``
        — covers the crawl branch of the duplicate-job guard, which previously
        had no direct test coverage.
        """
        from opencontractserver.analyzer.models import Analysis
        from opencontractserver.enrichment.services.crawl_authorities_service import (
            CrawlAuthoritiesService,
        )
        from opencontractserver.types.enums import JobStatus

        analyzer = CrawlAuthoritiesService.get_or_create_analyzer(self.owner.id)
        Analysis.objects.create(
            analyzer=analyzer,
            analyzed_corpus=self.corpus,
            creator=self.owner,
            status=JobStatus.RUNNING.value,
        )

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
        assert "already queued or running" in data["message"]
        assert (
            Analysis.objects.filter(
                analyzed_corpus=self.corpus,
                analyzer__task_name=C.CRAWL_ANALYZER_TASK,
            ).count()
            == 1
        )
