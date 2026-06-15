"""Tests for the bounded recursive authority crawl engine (Phase 5)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase

from opencontractserver.annotations.models import AuthorityFrontier
from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.services import CrawlAuthoritiesService

User = get_user_model()


def _make_user(username="crawl-user"):
    return User.objects.create_user(username=username, password="x")


def _make_bootstrap_mock(status="ingested", corpus_id=999):
    """Return a callable that marks the frontier row terminal (like the real method)."""

    def _mock(*, creator_id, frontier_row, make_public=True, relink_async=True):
        from opencontractserver.enrichment.services import AuthorityFrontierService

        AuthorityFrontierService.mark(frontier_row, status)
        if status == "ingested":
            return {
                "status": "ingested",
                "corpus_id": corpus_id,
                "documents_created": 1,
                "documents_updated": 0,
                "documents_skipped": 0,
                "documents_restamped": 0,
                "canonical_key": frontier_row.canonical_key,
            }
        return {"status": status, "canonical_key": frontier_row.canonical_key}

    return _mock


class ImportTest(TransactionTestCase):
    def test_import(self):
        """CrawlAuthoritiesService is importable."""
        self.assertIsNotNone(CrawlAuthoritiesService)


class CeleryTaskImportTest(TransactionTestCase):
    def test_crawl_authorities_task_importable(self):
        from opencontractserver.tasks.corpus_analysis_tasks import crawl_authorities

        self.assertTrue(
            getattr(crawl_authorities, "is_corpus_analyzer_task", False),
            "crawl_authorities must be decorated with @corpus_analyzer_task",
        )
