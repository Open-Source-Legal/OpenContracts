"""The agent must be told what 'now' is rather than inferring it.

Nothing in the stack used to tell an agent the current date, so a prompt that
asked it to state an analysis date got one from training data: a July-2026
question answered over 2026 authorities was reported "as of June 2024".
Substantively right, immediately untrustworthy — a wrong analysis date
discredits correct temporal reasoning.
"""

from __future__ import annotations

from asgiref.sync import async_to_sync
from django.test import TestCase
from django.utils import timezone

from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.llms.agents.agent_factory import (
    _corpus_current_through,
    _inject_temporal_grounding,
)
from opencontractserver.llms.agents.core_agents import AgentConfig
from opencontractserver.users.models import User


class TemporalGroundingTestCase(TestCase):
    """Grounding is queued as computed context and folded in at resolution.

    These tests drive the *real* ``AgentConfig`` rather than a stand-in: a
    stand-in exposing only ``system_prompt`` is how the injector and the
    persona-default resolution drifted apart unnoticed (issue #2247).
    """

    @staticmethod
    def _ground(config: AgentConfig, corpus=None) -> str:
        """Inject grounding and return the finalised system prompt."""
        async_to_sync(_inject_temporal_grounding)(config, corpus)
        config.resolve_system_prompt(lambda: "DEFAULT PERSONA.")
        return config.system_prompt or ""

    def setUp(self):
        self.user = User.objects.create_user(username="temporal-user", password="x")
        self.corpus = Corpus.objects.create(
            title="Dated Corpus", creator=self.user, is_public=False
        )

    def _add_document(self, retrieved_at: str | None):
        document = Document.objects.create(
            title=f"doc-{retrieved_at}",
            creator=self.user,
            file_type="text/plain",
            custom_meta=({"retrieved_at": retrieved_at} if retrieved_at else {}),
            processing_started=timezone.now(),
        )
        DocumentPath.objects.create(
            document=document,
            corpus=self.corpus,
            path=f"/{document.title}",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )
        return document

    def test_injects_a_computed_research_timestamp(self):
        prompt = self._ground(AgentConfig(system_prompt="BASE."), self.corpus)

        self.assertIn("BASE.", prompt)
        self.assertIn("Research performed at:", prompt)
        self.assertIn(str(timezone.now().year), prompt)

    def test_grounding_does_not_consume_the_default_prompt_signal(self):
        """Grounding must not stand in for an unresolved persona (issue #2247).

        The injector used to append straight onto ``system_prompt``, which
        made it non-``None`` before the factories read ``system_prompt is
        None`` as "the caller supplied nothing, use the configured persona" —
        so every configured persona was silently dropped.
        """
        config = AgentConfig(system_prompt=None)
        async_to_sync(_inject_temporal_grounding)(config, self.corpus)

        self.assertIsNone(config.system_prompt)
        self.assertTrue(config.computed_context)

        config.resolve_system_prompt(lambda: "DEFAULT PERSONA.")
        prompt = config.system_prompt or ""
        self.assertIn("DEFAULT PERSONA.", prompt)
        # Both injections landed, persona first, grounding after.
        self.assertLess(
            prompt.index("DEFAULT PERSONA."), prompt.index("Research performed at:")
        )

    def test_forbids_inventing_an_as_of_date(self):
        prompt = self._ground(AgentConfig(system_prompt="BASE."), self.corpus)

        self.assertIn("no other knowledge of the current date", prompt)
        self.assertIn("training data", prompt)

    def test_separates_approval_from_effectiveness(self):
        """`approved_on != effective_from` is the invariant temporal questions turn on."""
        prompt = self._ground(AgentConfig(system_prompt="BASE."), self.corpus)

        self.assertIn("APPROVED", prompt)
        self.assertIn("EFFECTIVE", prompt)
        self.assertIn("the date the question asks about", prompt)

    def test_reports_corpus_currency_from_the_latest_retrieval(self):
        self._add_document("2026-07-20T00:00:00+00:00")
        self._add_document("2026-07-26T18:38:19+00:00")
        self._add_document(None)

        currency = async_to_sync(_corpus_current_through)(self.corpus)
        self.assertEqual(currency, "2026-07-26T18:38:19+00:00")

        prompt = self._ground(AgentConfig(system_prompt="BASE."), self.corpus)
        self.assertIn("Corpus current through: 2026-07-26", prompt)

    def test_omits_currency_rather_than_inventing_one(self):
        """Most corpora carry no retrieval metadata; silence beats a guess."""
        self._add_document(None)

        self.assertIsNone(async_to_sync(_corpus_current_through)(self.corpus))
        prompt = self._ground(AgentConfig(system_prompt="BASE."), self.corpus)
        self.assertNotIn("Corpus current through", prompt)
        # The research timestamp is unconditional, though.
        self.assertIn("Research performed at:", prompt)

    def test_never_blocks_agent_creation(self):
        """Grounding is additive context; a failure must not break the agent."""

        class _Exploding:
            id = 1

            def _get_active_documents(self, include_caml=False):
                raise RuntimeError("db down")

        prompt = self._ground(AgentConfig(system_prompt="BASE."), _Exploding())
        # Still grounded on the timestamp, just without corpus currency.
        self.assertIn("Research performed at:", prompt)
        self.assertNotIn("Corpus current through", prompt)

    def test_works_without_a_corpus(self):
        prompt = self._ground(AgentConfig(system_prompt="BASE."), None)
        self.assertIn("Research performed at:", prompt)
