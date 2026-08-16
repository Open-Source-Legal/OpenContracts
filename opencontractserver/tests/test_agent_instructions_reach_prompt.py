"""Configured agent instructions must reach the system prompt actually sent.

The regression these guard against was invisible from outside: the value
round-tripped through the database and the API correctly, so every check of the
form "are the instructions set?" passed while the agent never received them.

So these assert the BUILT PROMPT, never the field. A test that reads back
``corpus.corpus_agent_instructions`` would have passed throughout the entire
period the bug existed.

``TransactionTestCase`` rather than ``TestCase`` on purpose: the prompt-building
path reaches the database from async context (corpus currency is read while
assembling the preamble), and ``TestCase``'s wrapping transaction makes that
raise. Mocking the factory instead — as the other agent tests do — would skip
the very code these exist to cover.
"""

from __future__ import annotations

import asyncio

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase

from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.llms import agents

User = get_user_model()

SENTINEL = "SENTINEL-corpus-instructions-must-survive-to-the-prompt"
DOC_SENTINEL = "SENTINEL-document-instructions-must-survive-to-the-prompt"


class AgentInstructionsReachPromptTests(TransactionTestCase):
    """Corpus instructions survive into the system prompt the agent is built with."""

    def setUp(self):
        self.user = User.objects.create_user(username="promptowner", password="p")
        self.corpus = Corpus.objects.create(
            title="Instruction corpus", creator=self.user
        )
        self.document = Document.objects.create(
            title="Instruction document", creator=self.user, is_public=True
        )
        self.corpus.add_document(document=self.document, user=self.user)

    def _prompt(self, **kwargs) -> str:
        async def build():
            agent = await agents.for_corpus(
                corpus=self.corpus.id,
                user_id=self.user.id,
                streaming=False,
                persist=False,
                **kwargs,
            )
            return agent.config.system_prompt or ""

        return asyncio.run(build())

    def _document_prompt(self, **kwargs) -> str:
        async def build():
            agent = await agents.for_document(
                document=self.document.id,
                corpus=self.corpus.id,
                user_id=self.user.id,
                streaming=False,
                persist=False,
                **kwargs,
            )
            return agent.config.system_prompt or ""

        return asyncio.run(build())

    def test_corpus_instructions_are_in_the_prompt(self):
        """The bug: temporal grounding consumed the ``system_prompt is None`` signal.

        ``_inject_temporal_grounding`` wrote to ``config.system_prompt`` before
        the factory resolved its default. That made the field non-None, so the
        ``if config.system_prompt is None`` branch that applies
        ``corpus_agent_instructions`` never ran — on every corpus agent, every
        time. Measured before the fix: a 657-character prompt containing only
        the computed preamble.
        """
        self.corpus.corpus_agent_instructions = SENTINEL
        self.corpus.save()

        prompt = self._prompt()
        self.assertIn(
            SENTINEL,
            prompt,
            "configured corpus instructions must reach the system prompt",
        )

    def test_computed_context_is_still_appended(self):
        """The fix must not drop the computed preamble to make room for the persona."""
        self.corpus.corpus_agent_instructions = SENTINEL
        self.corpus.save()

        prompt = self._prompt()
        self.assertIn(SENTINEL, prompt)
        self.assertIn(
            "Temporal grounding",
            prompt,
            "computed context must still be appended after the default resolves",
        )

    def test_explicit_system_prompt_still_wins(self):
        """A caller-supplied prompt keeps precedence, and still gets the preamble."""
        self.corpus.corpus_agent_instructions = SENTINEL
        self.corpus.save()

        prompt = self._prompt(system_prompt="EXPLICIT-CALLER-PROMPT")
        self.assertIn("EXPLICIT-CALLER-PROMPT", prompt)
        self.assertNotIn(
            SENTINEL,
            prompt,
            "an explicit system_prompt must not be merged with the corpus default",
        )
        self.assertIn("Temporal grounding", prompt)

    def test_corpus_without_instructions_still_gets_a_prompt(self):
        """Nothing configured is not the same as configuration dropped."""
        prompt = self._prompt()
        self.assertTrue(prompt.strip(), "a prompt is always built")
        self.assertNotIn(SENTINEL, prompt)

    def test_document_instructions_are_in_the_prompt(self):
        """The same bug, via ``CoreDocumentAgentFactory.create_context``.

        ``document_agent_instructions`` resolves through the same
        ``if config.system_prompt is None`` branch as the corpus persona, but
        the pre-fix regression tests here only exercised ``agents.for_corpus``
        — a document agent hitting the identical order-dependent bug would not
        have been caught.
        """
        self.corpus.document_agent_instructions = DOC_SENTINEL
        self.corpus.save()

        prompt = self._document_prompt()
        self.assertIn(
            DOC_SENTINEL,
            prompt,
            "configured document instructions must reach the system prompt",
        )
        self.assertIn(
            "Temporal grounding",
            prompt,
            "computed context must still be appended after the default resolves",
        )

    def test_corpus_instructions_survive_memory_injection(self):
        """The same bug, reached via ``_inject_corpus_memory``.

        ``_inject_corpus_memory`` runs before ``_inject_temporal_grounding`` and
        used to write straight to ``config.system_prompt`` whenever the corpus
        had memory content — making ``system_prompt`` non-``None`` before the
        default-resolution check ran, for every ``memory_enabled=True`` corpus.
        """
        from opencontractserver.agents.memory import update_memory_content

        self.corpus.corpus_agent_instructions = SENTINEL
        self.corpus.memory_enabled = True
        self.corpus.save()

        async def build():
            await update_memory_content(
                self.corpus,
                "## Collection Patterns\n\n- Prefer semantic search for dates.\n\n"
                "## Query Patterns\n\n- Real recorded insight, not a placeholder.",
                self.user,
            )
            agent = await agents.for_corpus(
                corpus=self.corpus.id,
                user_id=self.user.id,
                streaming=False,
                persist=False,
            )
            return agent.config.system_prompt or ""

        prompt = asyncio.run(build())
        self.assertIn(
            SENTINEL,
            prompt,
            "corpus instructions must survive memory injection reaching "
            "system_prompt first",
        )
        self.assertIn("Real recorded insight", prompt)
        self.assertIn("Temporal grounding", prompt)
