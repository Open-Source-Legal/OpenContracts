"""GraphQL query tests for deep-research reports.

Focused on the ``researchReportBySlug`` resolver added so the frontend can
resolve the ``/research/{slug}`` route the completion chat message links to.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from graphene.test import Client

from config.graphql.schema import schema
from opencontractserver.corpuses.models import Corpus
from opencontractserver.research.models import ResearchReport

User = get_user_model()


class _Ctx:
    """Minimal GraphQL context carrying the authenticated user."""

    def __init__(self, user):
        self.user = user


SLUG_QUERY = """
query ($slug: String!) {
  researchReportBySlug(slug: $slug) {
    id
    slug
    title
    status
  }
}
"""


class ResearchReportBySlugTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="x")
        self.other = User.objects.create_user(username="bob", password="x")
        self.corpus = Corpus.objects.create(title="Cases", creator=self.user)
        self.report = ResearchReport.objects.create(
            creator=self.user, corpus=self.corpus, prompt="x", title="My Report"
        )

    def _execute(self, user, slug):
        client = Client(schema, context_value=_Ctx(user))
        return client.execute(SLUG_QUERY, variables={"slug": slug})

    def test_creator_can_fetch_by_slug(self):
        result = self._execute(self.user, self.report.slug)
        self.assertIsNone(result.get("errors"))
        node = result["data"]["researchReportBySlug"]
        self.assertIsNotNone(node)
        self.assertEqual(node["slug"], self.report.slug)
        self.assertEqual(node["title"], "My Report")

    def test_non_creator_gets_null(self):
        result = self._execute(self.other, self.report.slug)
        self.assertIsNone(result["data"]["researchReportBySlug"])

    def test_unknown_slug_gets_null(self):
        result = self._execute(self.user, "does-not-exist")
        self.assertIsNone(result["data"]["researchReportBySlug"])

    def test_anonymous_user_is_rejected(self):
        """The resolver is ``@login_required``: an unauthenticated request must
        be rejected (PermissionDenied → GraphQL error + null data), not silently
        treated like a non-owner. This locks in the auth gate so it can't be
        dropped without a failing test.
        """
        result = self._execute(AnonymousUser(), self.report.slug)
        self.assertIsNotNone(result.get("errors"))
        self.assertIsNone(result["data"]["researchReportBySlug"])
