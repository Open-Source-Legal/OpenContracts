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
from opencontractserver.llms import agents

User = get_user_model()

SENTINEL = "SENTINEL-corpus-instructions-must-survive-to-the-prompt"


class AgentInstructionsReachPromptTests(TransactionTestCase):
    """Corpus instructions survive into the system prompt the agent is built with."""

    def setUp(self):
        self.user = User.objects.create_user(username="promptowner", password="p")
        self.corpus = Corpus.objects.create(
            title="Instruction corpus", creator=self.user
        )

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
