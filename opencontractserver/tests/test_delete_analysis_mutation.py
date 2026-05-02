"""Regression coverage for the DeleteAnalysisMutation return value.

The mutation triggers an async deletion task and must return a
typed ``ok=True`` / ``message`` payload so the frontend can observe
the success shape rather than receiving ``null``.
"""

from __future__ import annotations

import logging

import factory
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models.signals import post_save
from django.test import TestCase
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.analyzer.models import Analysis, Analyzer, GremlinEngine
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()
logger = logging.getLogger(__name__)


class _Context:
    def __init__(self, user):
        self.user = user


class DeleteAnalysisMutationReturnValueTestCase(TestCase):
    """Pin the success-shape returned by ``DeleteAnalysisMutation.mutate``."""

    DELETE_ANALYSIS = """
        mutation ($id: String!) {
            deleteAnalysis(id: $id) {
                ok
                message
            }
        }
    """

    @factory.django.mute_signals(post_save)
    def setUp(self) -> None:
        with transaction.atomic():
            self.user = User.objects.create_user(
                username="alice",
                password="abcd1234",
            )

            self.gremlin = GremlinEngine.objects.create(
                url="http://example.invalid/gremlin",
                creator=self.user,
            )
            self.analyzer = Analyzer.objects.create(
                id="test-analyzer",
                description="Test analyzer for delete mutation",
                creator=self.user,
                host_gremlin=self.gremlin,
            )
            self.analysis = Analysis.objects.create(
                analyzer=self.analyzer,
                creator=self.user,
            )

        # The owner has CRUD via the post-creation signal in production, but
        # signals are muted in setUp so we grant DELETE explicitly here.
        set_permissions_for_obj_to_user(
            user_val=self.user,
            instance=self.analysis,
            permissions=[PermissionTypes.DELETE],
        )

    def test_mutation_returns_ok_and_success_message(self) -> None:
        from graphene.test import Client

        client = Client(schema, context_value=_Context(self.user))

        response = client.execute(
            self.DELETE_ANALYSIS,
            variable_values={
                "id": to_global_id("AnalysisType", self.analysis.id),
            },
        )

        # Without the restored return statement, ``response["data"]`` would
        # contain ``{"deleteAnalysis": null}`` and this assertion fails.
        self.assertIsNone(response.get("errors"))
        self.assertIsNotNone(response["data"]["deleteAnalysis"])
        self.assertTrue(response["data"]["deleteAnalysis"]["ok"])
        self.assertEqual(
            response["data"]["deleteAnalysis"]["message"],
            "SUCCESS",
        )
