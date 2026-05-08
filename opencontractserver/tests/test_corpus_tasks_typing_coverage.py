"""
Coverage tests for typing-graduated paths in ``corpus_tasks``.

PR #1482 added a ``raise ValueError`` guard in ``process_analyzer`` for the
``analyzer is None`` case (previously the function silently dereferenced
``analyzer.id`` and only failed deeper in the call stack).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.tasks.corpus_tasks import process_analyzer

User = get_user_model()


class ProcessAnalyzerNoneGuardTestCase(TestCase):
    """``process_analyzer`` must reject ``analyzer=None`` upfront."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="proc_analyzer_user", password="pw"
        )

    def test_raises_value_error_when_analyzer_is_none(self):
        """A ``None`` analyzer triggers the explicit guard, not a deeper crash."""
        with self.assertRaises(ValueError) as cm:
            process_analyzer(
                user_id=self.user.id,
                analyzer=None,
                corpus_id=None,
                document_ids=[],
            )

        self.assertIn("non-null analyzer", str(cm.exception))
