"""Tests for the `me { canImportCorpus }` GraphQL field.

The frontend uses this server-derived flag to gate visibility of the
"Import Corpus" action. It must mirror the permission check enforced by
UploadCorpusImportZip / ImportZipToCorpus.
"""

import logging

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from graphene.test import Client

from config.graphql.schema import schema

User = get_user_model()
logger = logging.getLogger(__name__)


class _Ctx:
    def __init__(self, user):
        self.user = user


ME_QUERY = """
    query GetMe {
        me {
            id
            isUsageCapped
            canImportCorpus
        }
    }
"""


class CanImportCorpusFieldTestCase(TestCase):
    def setUp(self) -> None:
        self.capped_user = User.objects.create_user(
            username="capped",
            password="pw",
            is_usage_capped=True,
        )
        self.uncapped_user = User.objects.create_user(
            username="uncapped",
            password="pw",
            is_usage_capped=False,
        )

    def _run(self, user) -> dict:
        client = Client(schema, context_value=_Ctx(user))
        return client.execute(ME_QUERY)

    @override_settings(USAGE_CAPPED_USER_CAN_IMPORT_CORPUS=False)
    def test_capped_user_cannot_import_when_setting_disabled(self) -> None:
        result = self._run(self.capped_user)
        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["me"]["canImportCorpus"])

    @override_settings(USAGE_CAPPED_USER_CAN_IMPORT_CORPUS=True)
    def test_capped_user_can_import_when_setting_enabled(self) -> None:
        result = self._run(self.capped_user)
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["me"]["canImportCorpus"])

    @override_settings(USAGE_CAPPED_USER_CAN_IMPORT_CORPUS=False)
    def test_uncapped_user_can_always_import(self) -> None:
        result = self._run(self.uncapped_user)
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["me"]["canImportCorpus"])
