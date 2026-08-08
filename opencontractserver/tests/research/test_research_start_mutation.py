"""``startResearchReport`` — the explicit, non-chat kickoff path.

Focused on the optional ``corpusGroupId``, which widens retrieval past the
anchor corpus. The capability existed in the service and in the chat agent's
``start_deep_research`` tool but not on the mutation, so it was unreachable
from the interface: the corpus Research tab could only ever run against one
corpus, and a question whose answer lives in a sibling authority quietly got
answered from the anchor alone.

The gate that matters is what happens to a group the caller cannot see. It must
be REFUSED, not ignored — a silently narrowed run produces a report that reads
as group-wide and is not, which is worse than an error.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from graphql_relay import to_global_id

from config.graphql.schema import schema
from config.graphql.testing import Client
from opencontractserver.corpuses.models import Corpus, CorpusGroup
from opencontractserver.research.models import ResearchReport

User = get_user_model()

START = """
mutation ($corpusId: ID!, $prompt: String!, $corpusGroupId: ID) {
  startResearchReport(
    corpusId: $corpusId, prompt: $prompt, corpusGroupId: $corpusGroupId
  ) {
    ok
    message
    obj { id }
  }
}
"""


class _Ctx:
    def __init__(self, user):
        self.user = user


class StartResearchReportGroupScopeTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="x")
        self.other = User.objects.create_user(username="bob", password="x")
        self.corpus = Corpus.objects.create(title="Rules", creator=self.user)
        self.group = CorpusGroup.objects.create(
            title="DFW Authorities", creator=self.user
        )
        self.foreign_group = CorpusGroup.objects.create(
            title="Someone else's", creator=self.other
        )

    def _start(self, user, **overrides):
        variables = {
            "corpusId": to_global_id("CorpusType", self.corpus.pk),
            "prompt": "Which requirements apply to a 100 MW facility?",
        }
        variables.update(overrides)
        client = Client(schema, context_value=_Ctx(user))
        return client.execute(START, variables=variables)

    def test_a_run_without_a_group_stays_scoped_to_the_corpus(self):
        result = self._start(self.user)
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["startResearchReport"]["ok"])
        report = ResearchReport.objects.get(creator=self.user)
        self.assertIsNone(report.corpus_group)

    def test_a_visible_group_is_recorded_on_the_report(self):
        result = self._start(
            self.user,
            corpusGroupId=to_global_id("CorpusGroupType", self.group.pk),
        )
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["startResearchReport"]["ok"])
        report = ResearchReport.objects.get(creator=self.user)
        self.assertEqual(report.corpus_group_id, self.group.pk)

    def test_a_group_the_caller_cannot_see_is_refused_not_ignored(self):
        result = self._start(
            self.user,
            corpusGroupId=to_global_id("CorpusGroupType", self.foreign_group.pk),
        )
        payload = result["data"]["startResearchReport"]
        self.assertFalse(payload["ok"])
        self.assertIn("not found or not visible", payload["message"])
        # Refused means NO run: a report scoped to the anchor alone would look
        # like the group run the caller asked for.
        self.assertFalse(ResearchReport.objects.filter(creator=self.user).exists())

    def test_an_unparseable_group_id_is_refused(self):
        result = self._start(self.user, corpusGroupId="not-a-global-id")
        payload = result["data"]["startResearchReport"]
        self.assertFalse(payload["ok"])
        self.assertFalse(ResearchReport.objects.filter(creator=self.user).exists())
