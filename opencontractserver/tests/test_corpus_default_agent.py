"""``Corpus.default_agent`` — the corpus-level counterpart of
``CorpusGroup.default_agent``.

Two behaviours are under test, and they fail in different directions:

* **The guard.** ``default_agent`` is what corpus chat falls back to, so a
  pointer at a CORPUS-scoped agent belonging to a *different* corpus would
  serve that corpus's private instructions to this corpus's users.
* **The preference.** Before this field existed, a chat opened with no
  ``agent_id`` always resolved to the GLOBAL ``default-corpus-agent`` slug, so
  an agent scoped to the corpus could never be the default however it was
  configured. The whole point is that the corpus's own choice wins.
"""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.test import TestCase

from config.websocket.consumers.unified_agent_conversation import (
    UnifiedAgentConsumer,
)
from opencontractserver.agents.models import AgentConfiguration
from opencontractserver.corpuses.models import Corpus
from opencontractserver.users.models import User


class CorpusDefaultAgentGuardTestCase(TestCase):
    """A corpus may only default to a GLOBAL agent or one of its own."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="corpusowner", password="x", email="a@b.c"
        )
        self.corpus = Corpus.objects.create(title="Mine", creator=self.user)
        self.other = Corpus.objects.create(title="Theirs", creator=self.user)

    def _agent(self, slug: str, *, scope: str, corpus: Corpus | None = None):
        return AgentConfiguration.objects.create(
            name=slug,
            slug=slug,
            creator=self.user,
            scope=scope,
            corpus=corpus,
            system_instructions="hi",
        )

    def test_global_agent_is_accepted(self) -> None:
        agent = self._agent("g", scope=AgentConfiguration.SCOPE_GLOBAL)
        self.corpus.default_agent = agent
        self.corpus.save()
        self.corpus.refresh_from_db()
        self.assertEqual(self.corpus.default_agent_id, agent.pk)

    def test_agent_scoped_to_this_corpus_is_accepted(self) -> None:
        agent = self._agent(
            "mine", scope=AgentConfiguration.SCOPE_CORPUS, corpus=self.corpus
        )
        self.corpus.default_agent = agent
        self.corpus.save()
        self.corpus.refresh_from_db()
        self.assertEqual(self.corpus.default_agent_id, agent.pk)

    def test_agent_scoped_to_another_corpus_is_refused(self) -> None:
        """The leak this guard exists to stop."""
        agent = self._agent(
            "theirs", scope=AgentConfiguration.SCOPE_CORPUS, corpus=self.other
        )
        self.corpus.default_agent = agent
        with self.assertRaises(ValidationError) as ctx:
            self.corpus.save()
        self.assertIn("default_agent", ctx.exception.message_dict)

        self.corpus.refresh_from_db()
        self.assertIsNone(self.corpus.default_agent_id)


@pytest.mark.asyncio
class CorpusDefaultAgentResolutionTestCase(TestCase):
    """Priority 3 prefers ``Corpus.default_agent`` over the global slug."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="resolveowner", password="x", email="r@b.c"
        )
        self.corpus = Corpus.objects.create(title="Docs", creator=self.user)
        # The historical fallback. Present in every deployment via migration
        # 0002/0004; recreated here so the test does not depend on fixtures.
        self.global_default, _ = AgentConfiguration.objects.get_or_create(
            slug="default-corpus-agent",
            defaults={
                "name": "Default corpus agent",
                "creator": self.user,
                "system_instructions": "generic",
            },
        )

    def _consumer(self) -> UnifiedAgentConsumer:
        consumer = UnifiedAgentConsumer()
        consumer.session_id = "s"
        consumer.agent_config_id = None
        consumer.document_id = None
        consumer.corpus_id = self.corpus.id
        return consumer

    async def test_falls_back_to_the_global_slug_when_unset(self) -> None:
        resolved = await self._consumer()._resolve_agent_config()
        assert resolved is not None
        self.assertEqual(resolved.slug, "default-corpus-agent")

    async def test_corpus_default_wins(self) -> None:
        mine = await AgentConfiguration.objects.acreate(
            name="Mine",
            slug="corpus-default",
            creator=self.user,
            scope=AgentConfiguration.SCOPE_CORPUS,
            corpus=self.corpus,
            system_instructions="specific",
            system_instructions_mode="EXTEND",
        )
        self.corpus.default_agent = mine
        await self.corpus.asave(update_fields=["default_agent"])

        resolved = await self._consumer()._resolve_agent_config()
        assert resolved is not None
        self.assertEqual(resolved.slug, "corpus-default")

    async def test_inactive_corpus_default_falls_back_rather_than_failing(
        self,
    ) -> None:
        """Deactivating a corpus agent should restore the global default, not
        break corpus chat — that is what switching it off is asking for."""
        mine = await AgentConfiguration.objects.acreate(
            name="Mine",
            slug="corpus-default-off",
            creator=self.user,
            scope=AgentConfiguration.SCOPE_CORPUS,
            corpus=self.corpus,
            system_instructions="specific",
            is_active=False,
        )
        self.corpus.default_agent = mine
        await self.corpus.asave(update_fields=["default_agent"])

        resolved = await self._consumer()._resolve_agent_config()
        assert resolved is not None
        self.assertEqual(resolved.slug, "default-corpus-agent")
