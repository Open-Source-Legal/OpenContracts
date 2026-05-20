"""Unit tests for the Phase 1 service-layer foundation.

Covers ``ServiceResult`` (no DB), ``get_for_user_or_none`` (DB), and
``BaseService`` (DB). See
docs/refactor_plans/2026-05-19-service-layer-phase1-foundation-plan.md.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from opencontractserver.corpuses.models import Corpus
from opencontractserver.shared.services.conventions import (
    ServiceResult,
    get_for_user_or_none,
)
from opencontractserver.types.enums import PermissionTypes

User = get_user_model()


class TestServiceResult(SimpleTestCase):
    """SCENARIO: ServiceResult is the uniform write-operation envelope.

    BUSINESS RULE: a result is successful exactly when its error string is
    empty; it also tuple-unpacks to ``(value, error)`` so legacy callers
    written against the ``(obj, error)`` convention keep working.
    """

    def test_success_has_value_and_is_ok(self):
        result = ServiceResult.success(42)
        self.assertEqual(result.value, 42)
        self.assertEqual(result.error, "")
        self.assertTrue(result.ok)

    def test_failure_has_error_and_is_not_ok(self):
        result = ServiceResult.failure("boom")
        self.assertIsNone(result.value)
        self.assertEqual(result.error, "boom")
        self.assertFalse(result.ok)

    def test_failure_rejects_empty_error(self):
        with self.assertRaises(ValueError):
            ServiceResult.failure("")

    def test_tuple_unpacking_yields_value_then_error(self):
        value, error = ServiceResult.success("doc")
        self.assertEqual(value, "doc")
        self.assertEqual(error, "")
        value, error = ServiceResult.failure("nope")
        self.assertIsNone(value)
        self.assertEqual(error, "nope")


class TestGetForUserOrNone(TestCase):
    """SCENARIO: get_for_user_or_none is the IDOR-safe single-object lookup.

    BUSINESS RULE: it returns the instance only when it exists AND the user
    holds the requested permission. Every other case — not-found,
    permission-denied, malformed pk — returns None, so a caller cannot
    distinguish "does not exist" from "exists but forbidden".
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.other = User.objects.create_user(
            username="other", email="other@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Owned Corpus", creator=self.owner, is_public=False
        )

    def test_owner_gets_instance(self):
        result = get_for_user_or_none(Corpus, self.corpus.pk, self.owner)
        self.assertEqual(result, self.corpus)

    def test_other_user_gets_none(self):
        result = get_for_user_or_none(Corpus, self.corpus.pk, self.other)
        self.assertIsNone(result)

    def test_nonexistent_pk_gets_none(self):
        result = get_for_user_or_none(Corpus, 999999999, self.owner)
        self.assertIsNone(result)

    def test_malformed_pk_gets_none(self):
        result = get_for_user_or_none(Corpus, "not-a-pk", self.owner)
        self.assertIsNone(result)

    def test_permission_argument_is_honored(self):
        # Owner has full CRUD on their own corpus, so UPDATE also resolves.
        result = get_for_user_or_none(
            Corpus, self.corpus.pk, self.owner, PermissionTypes.UPDATE
        )
        self.assertEqual(result, self.corpus)
