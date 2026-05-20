"""Unit tests for the Phase 1 service-layer foundation.

Covers ``ServiceResult`` (no DB), ``get_for_user_or_none`` (DB), and
``BaseService`` (DB). See
docs/refactor_plans/2026-05-19-service-layer-phase1-foundation-plan.md.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from opencontractserver.shared.services.conventions import ServiceResult

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
