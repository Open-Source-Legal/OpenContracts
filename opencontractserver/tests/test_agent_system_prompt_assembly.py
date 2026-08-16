"""The configured persona must actually reach the model.

Regression coverage for issue #2247: ``corpus_agent_instructions`` /
``document_agent_instructions`` were stored, exposed through the API — and
silently discarded on every agent.  The factory appended its computed blocks
(temporal grounding, corpus memory) straight onto ``config.system_prompt``,
which made the field non-``None`` before the core factories read
``system_prompt is None`` as "the caller supplied nothing, resolve the
configured persona".  The signal was consumed before it was read, so the
persona never resolved and the agent ran on the computed blocks alone.

The blocks are short, so the result looked like a plausible system prompt
rather than an empty one.  These tests therefore assert on the *assembled*
prompt rather than on the field round-tripping through the DB.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgiref.sync import sync_to_async
from django.conf import settings
from django.test import TestCase, TransactionTestCase

from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.llms.agents.agent_factory import (
    UnifiedAgentFactory,
    _inject_temporal_grounding,
)
from opencontractserver.llms.agents.core_agents import (
    AgentConfig,
    CoreCorpusAgentFactory,
    CoreDocumentAgentFactory,
)
from opencontractserver.llms.types import AgentFramework
from opencontractserver.users.models import User

CORPUS_PERSONA = "You are a helpful assistant. ALWAYS say BANANA."
DOCUMENT_PERSONA = "Read this document like a paralegal. ALWAYS say PLANTAIN."


class SystemPromptAssemblyTestCase(TestCase):
    """Persona resolution and computed context, assembled in the right order."""

    user: User
    corpus: Corpus
    document: Document

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="prompt-user", password="x")
        cls.corpus = Corpus.objects.create(
            title="Persona Corpus",
            creator=cls.user,
            is_public=True,
            corpus_agent_instructions=CORPUS_PERSONA,
            document_agent_instructions=DOCUMENT_PERSONA,
            preferred_embedder="test/embedder/persona",
        )
        original = Document.objects.create(
            title="Persona Doc", creator=cls.user, is_public=True
        )
        cls.document, _, _ = cls.corpus.add_document(document=original, user=cls.user)

    # ------------------------------------------------------------------
    # End-to-end: factory injection followed by context creation
    # ------------------------------------------------------------------

    async def test_corpus_persona_reaches_the_system_prompt(self):
        config = AgentConfig(user_id=self.user.id)
        await _inject_temporal_grounding(config, self.corpus)

        context = await CoreCorpusAgentFactory.create_context(self.corpus.id, config)

        prompt = context.config.system_prompt or ""
        self.assertIn(CORPUS_PERSONA, prompt)
        # Grounding still lands, and lands after the persona.
        self.assertIn("Research performed at:", prompt)
        self.assertLess(
            prompt.index(CORPUS_PERSONA), prompt.index("Research performed at:")
        )

    async def test_document_persona_reaches_the_system_prompt(self):
        config = AgentConfig(user_id=self.user.id)
        await _inject_temporal_grounding(config, self.corpus)

        context = await CoreDocumentAgentFactory.create_context(
            self.document, self.corpus, config
        )

        prompt = context.config.system_prompt or ""
        self.assertIn(DOCUMENT_PERSONA, prompt)
        self.assertIn("Research performed at:", prompt)
        self.assertLess(
            prompt.index(DOCUMENT_PERSONA), prompt.index("Research performed at:")
        )

    async def test_explicit_caller_prompt_still_wins_and_still_gets_grounded(self):
        """A caller-supplied prompt suppresses the persona, not the grounding."""
        config = AgentConfig(user_id=self.user.id, system_prompt="CALLER PROMPT.")
        await _inject_temporal_grounding(config, self.corpus)

        context = await CoreCorpusAgentFactory.create_context(self.corpus.id, config)

        prompt = context.config.system_prompt or ""
        self.assertTrue(prompt.startswith("CALLER PROMPT."))
        self.assertNotIn(CORPUS_PERSONA, prompt)
        self.assertIn("Research performed at:", prompt)

    async def test_persona_survives_a_repeated_context_creation(self):
        """create_context is idempotent — no duplicated grounding block."""
        config = AgentConfig(user_id=self.user.id)
        await _inject_temporal_grounding(config, self.corpus)

        await CoreCorpusAgentFactory.create_context(self.corpus.id, config)
        first = config.system_prompt or ""
        await CoreCorpusAgentFactory.create_context(self.corpus.id, config)

        self.assertEqual(config.system_prompt, first)
        self.assertEqual(
            (config.system_prompt or "").count("Research performed at:"), 1
        )

    async def test_falls_back_to_settings_instructions_without_a_persona(self):
        """No configured persona ⇒ the settings default, never the grounding alone."""
        plain = await Corpus.objects.acreate(
            title="Plain Corpus", creator=self.user, is_public=True
        )
        config = AgentConfig(user_id=self.user.id)
        await _inject_temporal_grounding(config, plain)

        context = await CoreCorpusAgentFactory.create_context(plain.id, config)

        prompt = context.config.system_prompt or ""
        self.assertIn(settings.DEFAULT_CORPUS_AGENT_INSTRUCTIONS, prompt)
        self.assertIn(plain.title, prompt)

    # ------------------------------------------------------------------
    # AgentConfig contract
    # ------------------------------------------------------------------

    def test_computed_context_is_appended_in_queue_order(self):
        config = AgentConfig(system_prompt=None)
        config.add_computed_context("<FIRST>")
        config.add_computed_context("<SECOND>")

        # Queuing must not disturb the "caller supplied nothing" signal.
        self.assertIsNone(config.system_prompt)

        config.resolve_system_prompt(lambda: "PERSONA.")
        self.assertEqual(config.system_prompt, "PERSONA.\n\n<FIRST>\n\n<SECOND>")
        self.assertEqual(config.computed_context, [])

    def test_blocks_are_separated_without_relying_on_caller_discipline(self):
        """A block that supplies no leading newlines must not run into its
        neighbour — the queue delimits, the block only carries content."""
        config = AgentConfig(system_prompt="PERSONA.   \n\n")
        config.add_computed_context("\n\n<PADDED>\n")
        config.add_computed_context("<BARE>")

        config.resolve_system_prompt(lambda: "unused")
        self.assertEqual(config.system_prompt, "PERSONA.\n\n<PADDED>\n\n<BARE>")

    def test_resolve_is_idempotent(self):
        config = AgentConfig(system_prompt=None)
        config.add_computed_context("<BLOCK>")

        config.resolve_system_prompt(lambda: "PERSONA.")
        config.resolve_system_prompt(lambda: "OTHER PERSONA.")

        self.assertEqual(config.system_prompt, "PERSONA.\n\n<BLOCK>")

    def test_default_factory_is_not_called_when_a_prompt_was_supplied(self):
        config = AgentConfig(system_prompt="CALLER PROMPT.")

        def _explode() -> str:  # pragma: no cover - must never run
            raise AssertionError("default persona resolved despite explicit prompt")

        config.resolve_system_prompt(_explode)
        self.assertEqual(config.system_prompt, "CALLER PROMPT.")

    def test_empty_blocks_are_not_queued(self):
        config = AgentConfig(system_prompt="BASE.")
        config.add_computed_context("")
        config.add_computed_context("   \n  ")

        self.assertEqual(config.computed_context, [])
        config.resolve_system_prompt(lambda: "PERSONA.")
        self.assertEqual(config.system_prompt, "BASE.")


@pytest.mark.serial
class SystemPromptThroughPublicFactoryTestCase(TransactionTestCase):
    """The persona must survive the *real* entry point, not just its pieces.

    Every other test here drives the injectors and ``create_context``
    directly.  The bug lived in how ``UnifiedAgentFactory`` *sequences* them —
    build config, inject memory, inject grounding, then create the context —
    so a reordering there, or a fresh ``config.system_prompt`` mutation added
    inside the factory itself, would slip past all of them.  This test goes
    through the public entry point that production uses.

    ``TransactionTestCase`` + ``serial``: the factory makes async ORM calls
    that need fresh DB connections, which do not survive ``TestCase``'s
    transaction isolation.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="e2e-prompt-user", password="x")
        self.corpus = Corpus.objects.create(
            title="E2E Persona Corpus",
            creator=self.user,
            is_public=True,
            corpus_agent_instructions=CORPUS_PERSONA,
            preferred_embedder="test/embedder/persona",
        )

    async def _corpus_agent_prompt(self) -> str:
        """Build a corpus agent through the real factory; return its prompt.

        ``PydanticAIAgent`` is patched at the seam the rest of the suite uses,
        so no LLM is constructed — everything up to and including persona
        resolution still runs for real.
        """
        with patch(
            "opencontractserver.llms.agents.pydantic_ai_factory.PydanticAIAgent"
        ) as mock_agent_cls:
            instance = MagicMock()
            instance.toolsets = []
            instance.run = AsyncMock()
            mock_agent_cls.return_value = instance

            agent = await UnifiedAgentFactory.create_corpus_agent(
                corpus=self.corpus.id,
                framework=AgentFramework.PYDANTIC_AI,
                user_id=self.user.id,
            )
        return agent.config.system_prompt or ""

    async def test_corpus_persona_reaches_the_prompt_through_the_factory(self):
        prompt = await self._corpus_agent_prompt()

        self.assertIn(CORPUS_PERSONA, prompt)
        # The computed block still lands, and still lands last.
        self.assertIn("Research performed at:", prompt)
        self.assertLess(
            prompt.index(CORPUS_PERSONA), prompt.index("Research performed at:")
        )

    async def test_persona_edit_changes_the_prompt(self):
        """The symptom that made this bug unmeasurable: editing the persona
        produced no change in what the agent received."""
        before = await self._corpus_agent_prompt()

        self.corpus.corpus_agent_instructions = "ALWAYS say KUMQUAT instead."
        await sync_to_async(self.corpus.save)()

        after = await self._corpus_agent_prompt()

        self.assertIn("ALWAYS say KUMQUAT instead.", after)
        self.assertNotIn(CORPUS_PERSONA, after)
        self.assertNotEqual(before, after)

    async def test_persona_survives_real_memory_injection_through_the_factory(self):
        """Persona, real DB-backed memory, and grounding must all coexist.

        The other memory coverage in this suite (``test_agent_memory.py``)
        calls ``_inject_corpus_memory`` directly against a config that is
        resolved by hand — it never exercises a corpus with
        ``memory_enabled=True`` and an actual persisted memory document
        through ``UnifiedAgentFactory``, which is the exact combination that
        used to make ``corpus_agent_instructions`` disappear for every
        memory-enabled corpus (memory injection ran first and consumed the
        ``system_prompt is None`` signal before this test's persona could be
        resolved).
        """
        from opencontractserver.agents.memory import update_memory_content

        self.corpus.memory_enabled = True
        await sync_to_async(self.corpus.save)()
        await update_memory_content(
            self.corpus,
            "## Collection Patterns\n\n- Prefer semantic search for dates.\n\n"
            "## Query Patterns\n\n- Real recorded insight, not a placeholder.",
            self.user,
        )

        prompt = await self._corpus_agent_prompt()

        self.assertIn(CORPUS_PERSONA, prompt)
        self.assertIn("Real recorded insight", prompt)
        self.assertIn("Research performed at:", prompt)
