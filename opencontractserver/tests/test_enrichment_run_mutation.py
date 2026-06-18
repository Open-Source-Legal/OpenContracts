"""Tests for the RunCorpusEnrichmentMutation GraphQL mutation.

Verifies that the mutation:
- dispatches the enrichment analyzer when ``run_enrichment=True``
- dispatches the crawl analyzer when ``run_crawl=True``
- rejects callers who do not have READ on the corpus
- rejects callers who have READ but not UPDATE on the corpus
- rejects calls with neither flag set
- silently drops invalid reference_type codes
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from opencontractserver.corpuses.models import Corpus
from opencontractserver.enrichment import constants as C
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
    # Validation: invalid reference_types are silently dropped
    # ------------------------------------------------------------------

    def test_invalid_reference_types_are_filtered(self):
        """Unknown type codes are dropped; the call still succeeds if valid ones remain."""
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
        assert data["ok"] is True
        assert Analysis.objects.filter(
            analyzed_corpus=self.corpus,
            analyzer__task_name=C.ENRICHMENT_ANALYZER_TASK,
        ).exists()
