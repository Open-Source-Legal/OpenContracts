"""``Corpus.default_agent`` — the guard on what a corpus may default to.

``default_agent`` is what corpus chat falls back to, so a pointer at a
CORPUS-scoped agent belonging to a *different* corpus would serve that corpus's
private instructions to this corpus's users. The condition spans two tables, so
it is enforced in ``Corpus.save`` rather than as a DB constraint.

The *resolution* half — that priority 3 prefers this field over the global
``default-corpus-agent`` slug — lives in
``tests/websocket/test_unified_agent_consumer.py``. It needs committed-data
semantics (the consumer resolves on its own connection), which is what
``WebsocketFixtureBaseTestCase`` provides and a plain ``TestCase`` does not.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.test import TestCase

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

    def test_pointer_at_a_nonexistent_agent_is_refused(self):
        """``default_agent_id`` can be set without loading the row — a stale
        pk from a fixture or a fork would otherwise persist and only surface
        when chat tried to resolve it."""
        self.corpus.default_agent_id = 99999999
        with self.assertRaises(ValidationError) as ctx:
            self.corpus.save()
        self.assertIn("default_agent", ctx.exception.message_dict)
        self.assertIn("does not exist", str(ctx.exception))
