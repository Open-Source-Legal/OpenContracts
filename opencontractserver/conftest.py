from typing import cast

import pytest

from opencontractserver.tests.factories import UserFactory
from opencontractserver.users.models import User


@pytest.fixture(autouse=True)
def media_storage(settings, tmpdir):
    settings.MEDIA_ROOT = tmpdir.strpath


@pytest.fixture(autouse=True)
def _invalidate_pipeline_settings_singleton_cache():
    """Clear the ``PipelineSettings`` singleton cache before every test.

    ``PipelineSettings.get_instance()`` caches the singleton row in Django's
    cache framework (``LocMemCache`` in tests, 5-min TTL — see
    ``opencontractserver/documents/models.py``). The cache is per-worker
    process and survives both ``TestCase`` rollback and
    ``TransactionTestCase`` truncation: neither fires the model signal that
    would invalidate the cache.

    Tests that explicitly populate ``PipelineSettings`` with non-default
    values inside their own transaction — most notably
    ``TestPipelineComponentBaseSettings`` and siblings in
    ``test_pipeline_component_base.py``, which do
    ``PipelineSettings.objects.all().delete(); PipelineSettings.objects.
    create(id=1)`` (i.e. an empty ``default_embedder``) — leave a stale
    Python instance in the cache once their transaction rolls back. A
    later test on the same worker that calls ``get_instance()`` then hits
    that stale cache and sees fields the migration-seeded DB row would
    have populated. The historical symptom was a flaky ``ValueError:
    get_embedder() resolved no embedder_path`` in agent/tool tests
    (``TestPydanticAIConversationAdaptersAsync``,
    ``TestDuplicateToolRegistration``, ``TestApprovalFlow``, …),
    appearing only when a polluting class ran first on the same worker.

    Invalidating the singleton key before each test guarantees that
    ``get_instance()`` falls through to ``get_or_create(pk=1, defaults=
    {...settings.DEFAULT_EMBEDDER...})``, which restores the
    migration-seeded state on cache miss.
    """
    from opencontractserver.documents.models import PipelineSettings

    PipelineSettings._invalidate_cache()
    yield


@pytest.fixture
def user() -> User:
    return cast(User, UserFactory())
