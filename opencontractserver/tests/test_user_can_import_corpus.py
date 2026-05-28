"""Tests for the `me { canImportCorpus }` GraphQL field.

The frontend uses this server-derived flag to gate visibility of the
"Import Corpus" action. It must mirror the permission check enforced by
the corpus-export and zip-to-corpus REST import endpoints
(``/api/imports/corpus/`` and ``/api/imports/zip-to-corpus/``).
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase, override_settings
from graphene.test import Client

from config.graphql.schema import schema

User = get_user_model()


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

    @override_settings(USAGE_CAPPED_USER_CAN_IMPORT_CORPUS=True)
    def test_anonymous_user_me_returns_null(self) -> None:
        """Anonymous users get ``me: null`` rather than a partial ``UserType``.

        ``resolve_me`` short-circuits on unauthenticated requests so callers
        never see a partially-resolved ``AnonymousUser`` (which lacks
        model-only fields like ``is_usage_capped``). This means the
        frontend's ``canImportCorpus`` gating defaults to ``false`` for
        anonymous users via the absent ``me`` payload.
        """
        client = Client(schema, context_value=_Ctx(AnonymousUser()))
        result = client.execute(ME_QUERY)
        self.assertIsNone(result.get("errors"))
        self.assertIsNone(result["data"]["me"])
