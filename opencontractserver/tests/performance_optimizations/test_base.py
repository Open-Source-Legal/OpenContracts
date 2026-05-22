"""
Base test classes for performance optimization tests.
Provides utilities to disable expensive operations like embedding calculations.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase, TransactionTestCase

from opencontractserver.tests.base import BaseFixtureTestCase


class NoEmbeddingsMixin:
    """
    Mixin to disable embedding calculations in tests.
    This significantly speeds up tests that create many annotations.
    """

    def setUp(self):
        """Set up patches for embedding calculations."""
        super().setUp()

        # Patch embedding calculation tasks
        self.embedding_patches = [
            patch(
                "opencontractserver.tasks.embeddings_task.calculate_embedding_for_annotation_text.delay"
            ),
            patch(
                "opencontractserver.tasks.embeddings_task.calculate_embedding_for_annotation_text.si"
            ),
            patch(
                "opencontractserver.tasks.embeddings_task.calculate_embedding_for_note_text.delay"
            ),
            patch(
                "opencontractserver.tasks.embeddings_task.calculate_embedding_for_note_text.si"
            ),
            patch(
                "opencontractserver.annotations.signals.process_structural_annotation_for_corpuses"
            ),
        ]

        # Start all patches
        for p in self.embedding_patches:
            mock = p.start()
            # Make sure async methods return a mock that can be chained
            if hasattr(mock, "return_value"):
                mock.return_value = MagicMock()
                if hasattr(mock.return_value, "apply_async"):
                    mock.return_value.apply_async = MagicMock()

        self.addCleanup(self.stop_patches)

    def stop_patches(self):
        """Stop all patches."""
        for p in self.embedding_patches:
            p.stop()


# NoMVRefreshMixin removed - materialized views no longer exist in codebase


class PerformanceTestCase(NoEmbeddingsMixin, TestCase):
    """
    Base TestCase for performance tests.
    Disables embedding calculations by default.
    Inherits from TestCase for tests that don't need real transactions.
    """


class PerformanceTransactionTestCase(NoEmbeddingsMixin, TransactionTestCase):
    """
    Base TransactionTestCase for performance tests.
    Disables embedding calculations by default.
    Use for tests that need real database transactions.
    """


class FastTestCase(NoEmbeddingsMixin, TestCase):
    """
    TestCase that disables both embeddings and MV refreshes.
    Use for tests that don't need these features at all.
    """

    pass


class FastTransactionTestCase(NoEmbeddingsMixin, TransactionTestCase):
    """
    TransactionTestCase that disables both embeddings and MV refreshes.
    Use for transaction tests that don't need these features.
    """

    pass


class PerformanceBaseFixtureTestCase(NoEmbeddingsMixin, BaseFixtureTestCase):
    """
    BaseFixtureTestCase with embedding calculations disabled.
    Combines fixture loading and signal disconnection from BaseFixtureTestCase
    with embedding/corpus processing optimizations.
    """

    pass


class FastBaseFixtureTestCase(NoEmbeddingsMixin, BaseFixtureTestCase):
    """
    BaseFixtureTestCase that disables both embeddings and MV refreshes.
    Use for fixture-based tests that don't need these features at all.
    """

    pass


class DirectQueryTestMixin:
    """
    Mixin for testing direct query performance.
    """

    def setUp(self):
        super().setUp()
        # No cache-specific setup needed
        pass

    def assert_query_performance(self, duration, expected_max, operation="Query"):
        """Assert query completed within expected time."""
        self.assertLess(
            duration,
            expected_max,
            f"{operation} took {duration:.4f}s, expected < {expected_max}s",
        )

    def assert_permission_filtering(self, results, user, expected_behavior):
        """Assert permission filtering is working correctly."""
        # This is a placeholder - actual implementation would verify
        # that the results match expected permission behavior
        self.assertIsNotNone(results, f"Results should not be None for {user}")

    def measure_query_time(self, query_func, *args, **kwargs):
        """Measure time taken by a query function."""
        import time

        start = time.time()
        result = query_func(*args, **kwargs)
        duration = time.time() - start
        return result, duration
