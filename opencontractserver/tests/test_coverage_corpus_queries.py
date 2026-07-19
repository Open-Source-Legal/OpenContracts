"""Coverage-driving tests for ``config/graphql/corpus_queries.py``.

Targets query resolvers ported from the graphene ``CorpusQueryMixin`` that the
rest of the suite never happens to exercise: the singular ``corpusGroup(id:)``
relay fetch, the malformed-corpus-id guards on
``corpusIntelligenceSetupStatus`` / ``corpusDataStory`` / ``corpusArtifacts`` /
``corpusArtifactTemplates``, the "corpus not visible" branch of
``corpusDataStory``, the logged-and-reraised exception path in
``corpusStats``, and the artifact resolvers (``artifactBySlug`` /
``corpusArtifacts`` / ``corpusArtifactTemplates``, which also exercises the
shared ``_artifact_to_type`` builder).

Tests go through the actual GraphQL schema (``Client(schema).execute``) rather
than calling the ``_resolve_Query_*`` functions directly, since these are
thin, field-registered query resolvers and the schema execution path is what
production traffic actually takes (argument stripping, relay id decoding,
connection wrapping).
"""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from graphql_relay import to_global_id

from config.graphql.schema import schema
from config.graphql.testing import Client
from opencontractserver.corpuses.models import Artifact, Corpus, CorpusGroup
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class _FakeRequest:
    """Minimal request object accepted by the strawberry resolvers under test."""

    def __init__(self, user):
        self.user = user

    def build_absolute_uri(self, path: str) -> str:
        return path


class CorpusQueriesCoverageTestCase(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="cqcov_user", password="pw")
        self.corpus = Corpus.objects.create(
            title="Coverage Corpus",
            creator=self.user,
            backend_lock=False,
            is_public=False,
        )
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.ALL])

    def _execute(self, query: str, variables: dict | None = None, user=None) -> dict:
        return Client(schema).execute(
            query,
            variables=variables,
            context_value=_FakeRequest(user or self.user),
        )

    # ------------------------------------------------------------------ #
    # corpusGroup(id:) singular relay fetch
    # ------------------------------------------------------------------ #

    def test_corpus_group_resolves_by_global_id(self):
        group = CorpusGroup.objects.create(title="Coverage Group", creator=self.user)
        set_permissions_for_obj_to_user(self.user, group, [PermissionTypes.ALL])

        result = self._execute(
            "query ($id: ID!) { corpusGroup(id: $id) { title slug } }",
            variables={"id": to_global_id("CorpusGroupType", group.pk)},
        )

        self.assertIsNone(result.get("errors"), msg=result.get("errors"))
        self.assertEqual(result["data"]["corpusGroup"]["title"], "Coverage Group")

    # ------------------------------------------------------------------ #
    # corpusIntelligenceSetupStatus — malformed corpus id
    # ------------------------------------------------------------------ #

    def test_corpus_intelligence_setup_status_returns_none_for_malformed_corpus_id(
        self,
    ):
        result = self._execute(
            "query ($id: ID!) { corpusIntelligenceSetupStatus(corpusId: $id) "
            "{ referenceAvailable } }",
            variables={"id": to_global_id("CorpusType", "not-a-number")},
        )

        self.assertIsNone(result.get("errors"), msg=result.get("errors"))
        self.assertIsNone(result["data"]["corpusIntelligenceSetupStatus"])

    # ------------------------------------------------------------------ #
    # corpusStats — logged-and-reraised service failure
    # ------------------------------------------------------------------ #

    def test_corpus_stats_logs_and_reraises_when_a_backing_service_fails(self):
        query = "query ($id: ID!) { corpusStats(corpusId: $id) { totalDocs } }"
        variables = {"id": to_global_id("CorpusType", self.corpus.pk)}

        with mock.patch(
            "opencontractserver.analyzer.services.AnalysisService.get_visible_analyses",
            side_effect=RuntimeError("simulated service outage"),
        ):
            with self.assertLogs(
                "config.graphql.corpus_queries", level="ERROR"
            ) as logs:
                result = self._execute(query, variables=variables)

        self.assertTrue(
            any("Error in resolve_corpus_stats" in message for message in logs.output),
            msg=logs.output,
        )
        self.assertIsNotNone(result.get("errors"))

    # ------------------------------------------------------------------ #
    # corpusDataStory
    # ------------------------------------------------------------------ #

    def test_corpus_data_story_returns_none_for_malformed_corpus_id(self):
        result = self._execute(
            "query ($id: ID!) { corpusDataStory(corpusId: $id) { totalDocuments } }",
            variables={"id": to_global_id("CorpusType", "not-a-number")},
        )

        self.assertIsNone(result.get("errors"), msg=result.get("errors"))
        self.assertIsNone(result["data"]["corpusDataStory"])

    def test_corpus_data_story_returns_none_for_invisible_corpus(self):
        stranger = User.objects.create_user(username="cqcov_stranger", password="pw")

        result = self._execute(
            "query ($id: ID!) { corpusDataStory(corpusId: $id) { totalDocuments } }",
            variables={"id": to_global_id("CorpusType", self.corpus.pk)},
            user=stranger,
        )

        self.assertIsNone(result.get("errors"), msg=result.get("errors"))
        self.assertIsNone(result["data"]["corpusDataStory"])

    def test_corpus_data_story_returns_empty_story_for_visible_corpus_without_profile(
        self,
    ):
        result = self._execute(
            "query ($id: ID!) { corpusDataStory(corpusId: $id) "
            "{ totalDocuments profiles { title } } }",
            variables={"id": to_global_id("CorpusType", self.corpus.pk)},
        )

        self.assertIsNone(result.get("errors"), msg=result.get("errors"))
        story = result["data"]["corpusDataStory"]
        self.assertIsNotNone(story)
        self.assertEqual(story["totalDocuments"], 0)
        self.assertEqual(story["profiles"], [])

    # ------------------------------------------------------------------ #
    # artifactBySlug (+ the shared _artifact_to_type builder)
    # ------------------------------------------------------------------ #

    def test_artifact_by_slug_returns_artifact_for_visible_corpus(self):
        Artifact.objects.create(
            corpus=self.corpus,
            template="spending-beeswarm",
            title="Spending Over Time",
            slug="coverage-artifact",
            creator=self.user,
        )

        result = self._execute(
            "query ($slug: String!) { artifactBySlug(slug: $slug) "
            "{ slug title corpusSlug creatorSlug } }",
            variables={"slug": "coverage-artifact"},
        )

        self.assertIsNone(result.get("errors"), msg=result.get("errors"))
        data = result["data"]["artifactBySlug"]
        self.assertEqual(data["slug"], "coverage-artifact")
        self.assertEqual(data["title"], "Spending Over Time")
        self.assertEqual(data["corpusSlug"], self.corpus.slug)
        self.assertEqual(data["creatorSlug"], self.user.slug)

    # ------------------------------------------------------------------ #
    # corpusArtifacts
    # ------------------------------------------------------------------ #

    def test_corpus_artifacts_returns_empty_list_for_malformed_corpus_id(self):
        result = self._execute(
            "query ($id: ID!) { corpusArtifacts(corpusId: $id) { slug } }",
            variables={"id": to_global_id("CorpusType", "not-a-number")},
        )

        self.assertIsNone(result.get("errors"), msg=result.get("errors"))
        self.assertEqual(result["data"]["corpusArtifacts"], [])

    def test_corpus_artifacts_lists_artifacts_for_visible_corpus(self):
        Artifact.objects.create(
            corpus=self.corpus,
            template="spending-beeswarm",
            slug="coverage-artifact-2",
            creator=self.user,
        )

        result = self._execute(
            "query ($id: ID!) { corpusArtifacts(corpusId: $id) { slug } }",
            variables={"id": to_global_id("CorpusType", self.corpus.pk)},
        )

        self.assertIsNone(result.get("errors"), msg=result.get("errors"))
        slugs = [a["slug"] for a in result["data"]["corpusArtifacts"]]
        self.assertIn("coverage-artifact-2", slugs)

    # ------------------------------------------------------------------ #
    # corpusArtifactTemplates
    # ------------------------------------------------------------------ #

    def test_corpus_artifact_templates_returns_empty_list_for_malformed_corpus_id(
        self,
    ):
        result = self._execute(
            "query ($id: ID!) { corpusArtifactTemplates(corpusId: $id) "
            "{ id eligible } }",
            variables={"id": to_global_id("CorpusType", "not-a-number")},
        )

        self.assertIsNone(result.get("errors"), msg=result.get("errors"))
        self.assertEqual(result["data"]["corpusArtifactTemplates"], [])

    def test_corpus_artifact_templates_lists_templates_for_visible_corpus(self):
        result = self._execute(
            "query ($id: ID!) { corpusArtifactTemplates(corpusId: $id) "
            "{ id eligible reason } }",
            variables={"id": to_global_id("CorpusType", self.corpus.pk)},
        )

        self.assertIsNone(result.get("errors"), msg=result.get("errors"))
        templates = result["data"]["corpusArtifactTemplates"]
        self.assertEqual(len(templates), 1)
        self.assertEqual(templates[0]["id"], "spending-beeswarm")
        # No Collection Profile extract exists for this corpus, so the
        # dated-documents eligibility threshold is never met.
        self.assertFalse(templates[0]["eligible"])
