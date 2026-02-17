from unittest.mock import MagicMock, patch

from django.test import TestCase


class TestCeleryWorkerSignals(TestCase):
    """Test Celery signal handlers for database connection management."""

    def test_worker_process_init_closes_db_connections(self):
        """Verify worker_process_init signal handler calls connections.close_all().

        When a Celery prefork worker child is spawned, inherited database connections
        from the parent process are invalid and must be closed. This test ensures the
        signal handler performs that cleanup.
        """
        from config.celery_app import close_db_connections_on_worker_init

        with patch("django.db.connections") as mock_connections:
            close_db_connections_on_worker_init(sender=MagicMock())
            mock_connections.close_all.assert_called_once()
