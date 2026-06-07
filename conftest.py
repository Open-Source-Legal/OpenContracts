"""
Root pytest configuration for OpenContracts.

This file provides pytest-xdist parallel testing support and ensures proper
worker isolation for tests.
"""

import asyncio
import os

import pytest
from django import db

from opencontractserver.utils.vcr_replay import ensure_aiohttp_vcr_compat

# Many integration tests record/replay VCR cassettes. vcrpy 8.1.1 imports its
# aiohttp stub lazily when a cassette is entered, and that stub subclasses
# ``aiohttp.streams.AsyncStreamReaderMixin`` — a symbol aiohttp 3.14 removed — at
# module-evaluation time. A fresh CI resolution that picks up aiohttp >= 3.14
# would therefore make every VCR-using test raise AttributeError. Apply the
# compat shim here, at conftest import, so the symbol exists before any test
# runs. See opencontractserver/utils/vcr_replay.py and issue #1920.
ensure_aiohttp_vcr_compat()


@pytest.fixture(scope="session", autouse=True)
def make_create_permissions_xdist_safe():
    """Make ``django.contrib.auth.management.create_permissions`` idempotent
    under pytest-xdist worker concurrency.

    Each ``TransactionTestCase._fixture_teardown`` calls Django's ``flush``
    management command, which fires ``emit_post_migrate_signal``, which calls
    ``create_permissions`` and ends in
    ``Permission.objects.bulk_create(perms)``. Under xdist with 4 workers,
    every worker's per-test teardown races on the shared ``auth_permission``
    table — content_type ids overlap across the per-worker test databases
    (postgres assigns them serially during migrate), so the
    ``(content_type_id, codename)`` unique constraint produces
    ``IntegrityError`` for whichever worker loses the race. The losing
    worker's teardown then dies, the next test's ``setUp`` finds an
    un-rolled-back transaction and an empty fixture, and we get a cascade of
    ``User matching query does not exist`` setUp failures.

    Fix: wrap the registered ``create_permissions`` handler in
    ``transaction.atomic`` and swallow ``IntegrityError``. The conflicting
    rows are exactly the permissions we'd have inserted anyway (already
    present courtesy of the winning worker), so the swallow is safe — and
    the atomic block guarantees no half-inserted state leaks past the
    rollback.

    This is a test-only patch. The fixture re-registers the original handler
    at session teardown so no production import path is affected.
    """
    from django.contrib.auth.management import create_permissions
    from django.db import IntegrityError, transaction
    from django.db.models.signals import post_migrate

    _UID = "django.contrib.auth.management.create_permissions"

    def safe_create_permissions(app_config, **kwargs):
        using = kwargs.get("using", "default")
        try:
            with transaction.atomic(using=using):
                return create_permissions(app_config, **kwargs)
        except IntegrityError:
            # Another xdist worker won the race and inserted the same
            # (content_type_id, codename) rows; the atomic block has rolled
            # back any partial inserts on our side. The post-condition
            # ``create_permissions`` cares about — every expected Permission
            # row exists — is already satisfied.
            return None

    # ``post_migrate.disconnect`` returns ``True`` only if a receiver
    # registered with the given ``dispatch_uid`` was actually removed. Fail
    # loudly if Django ever changes the UID string that ``AuthConfig.ready``
    # uses to register ``create_permissions``: a silent no-op here would
    # leave the unsafe original handler in place and quietly re-introduce
    # the xdist race this fixture exists to fix.
    disconnected = post_migrate.disconnect(dispatch_uid=_UID)
    assert disconnected, (
        f"Expected Django to have registered ``create_permissions`` with "
        f"dispatch_uid={_UID!r}; nothing was disconnected. The xdist race "
        f"this fixture mitigates may have been silently re-introduced. "
        f"Check django.contrib.auth.apps.AuthConfig.ready for the new UID."
    )
    post_migrate.connect(safe_create_permissions, dispatch_uid=_UID)

    yield

    post_migrate.disconnect(dispatch_uid=_UID)
    post_migrate.connect(create_permissions, dispatch_uid=_UID)


@pytest.fixture(scope="session", autouse=True)
def disable_document_processing_signals(django_db_setup):
    """
    Disable document, annotation, and note processing signals for all tests by default.

    This prevents Celery tasks from being triggered when creating test documents,
    annotations, or notes, which would fail because test fixtures typically don't
    have a configured embedder/storage backend.

    Tests that specifically need processing signals (e.g., integration tests for
    the processing pipeline) can use the `enable_doc_processing_signals` fixture
    to temporarily re-enable them.

    The signals are reconnected after all tests complete.
    """
    from django.db.models.signals import post_save

    from opencontractserver.annotations.models import Annotation, Note
    from opencontractserver.annotations.signals import (
        ANNOT_CREATE_UID,
        NOTE_CREATE_UID,
        process_annot_on_create_atomic,
        process_note_on_create_atomic,
    )
    from opencontractserver.documents.models import Document, DocumentPath
    from opencontractserver.documents.signals import (
        DOC_CREATE_UID,
        DOC_PATH_CREATE_UID,
        process_doc_on_create_atomic,
        process_doc_on_document_path_create,
    )

    # Disconnect signals
    post_save.disconnect(
        process_doc_on_create_atomic, sender=Document, dispatch_uid=DOC_CREATE_UID
    )
    post_save.disconnect(
        process_annot_on_create_atomic, sender=Annotation, dispatch_uid=ANNOT_CREATE_UID
    )
    post_save.disconnect(
        process_note_on_create_atomic, sender=Note, dispatch_uid=NOTE_CREATE_UID
    )
    post_save.disconnect(
        process_doc_on_document_path_create,
        sender=DocumentPath,
        dispatch_uid=DOC_PATH_CREATE_UID,
    )

    yield

    # Reconnect signals after all tests complete
    post_save.connect(
        process_doc_on_create_atomic, sender=Document, dispatch_uid=DOC_CREATE_UID
    )
    post_save.connect(
        process_annot_on_create_atomic, sender=Annotation, dispatch_uid=ANNOT_CREATE_UID
    )
    post_save.connect(
        process_note_on_create_atomic, sender=Note, dispatch_uid=NOTE_CREATE_UID
    )
    post_save.connect(
        process_doc_on_document_path_create,
        sender=DocumentPath,
        dispatch_uid=DOC_PATH_CREATE_UID,
    )


@pytest.fixture
def enable_doc_processing_signals():
    """
    Re-enable document, annotation, and note processing signals for a specific test.

    Use this fixture in tests that specifically need to test processing
    pipeline behavior with signals firing.

    Example:
        def test_document_processing_flow(enable_doc_processing_signals):
            # Signals are enabled for this test
            doc = Document.objects.create(...)  # Will trigger processing
    """
    from django.db.models.signals import post_save

    from opencontractserver.annotations.models import Annotation, Note
    from opencontractserver.annotations.signals import (
        ANNOT_CREATE_UID,
        NOTE_CREATE_UID,
        process_annot_on_create_atomic,
        process_note_on_create_atomic,
    )
    from opencontractserver.documents.models import Document, DocumentPath
    from opencontractserver.documents.signals import (
        DOC_CREATE_UID,
        DOC_PATH_CREATE_UID,
        process_doc_on_create_atomic,
        process_doc_on_document_path_create,
    )

    # Re-enable signals for this test
    post_save.connect(
        process_doc_on_create_atomic, sender=Document, dispatch_uid=DOC_CREATE_UID
    )
    post_save.connect(
        process_annot_on_create_atomic, sender=Annotation, dispatch_uid=ANNOT_CREATE_UID
    )
    post_save.connect(
        process_note_on_create_atomic, sender=Note, dispatch_uid=NOTE_CREATE_UID
    )
    post_save.connect(
        process_doc_on_document_path_create,
        sender=DocumentPath,
        dispatch_uid=DOC_PATH_CREATE_UID,
    )

    yield

    # Disable signals again after the test
    post_save.disconnect(
        process_doc_on_create_atomic, sender=Document, dispatch_uid=DOC_CREATE_UID
    )
    post_save.disconnect(
        process_annot_on_create_atomic, sender=Annotation, dispatch_uid=ANNOT_CREATE_UID
    )
    post_save.disconnect(
        process_note_on_create_atomic, sender=Note, dispatch_uid=NOTE_CREATE_UID
    )
    post_save.disconnect(
        process_doc_on_document_path_create,
        sender=DocumentPath,
        dispatch_uid=DOC_PATH_CREATE_UID,
    )


def pytest_configure(config):
    """Configure pytest settings, including xdist worker handling."""
    # Ensure the serial marker is registered only once
    if not hasattr(config, "_serial_marker_registered"):
        config.addinivalue_line(
            "markers",
            "serial: mark test to run serially (not in parallel with other tests)",
        )
        config._serial_marker_registered = True


def pytest_collection_modifyitems(config, items):
    """Modify test collection to handle serial tests when running with xdist."""
    # Check if running with xdist by looking at numprocesses option
    # Note: workerinput is only on workers, but collection happens on controller
    numprocesses = getattr(config.option, "numprocesses", None)
    if not numprocesses:
        return

    # When running with xdist, mark serial tests to run on worker gw0 only
    # This ensures they run sequentially without interference from other workers
    for item in items:
        if item.get_closest_marker("serial"):
            # Add xdist_group to ensure all serial tests run on same worker
            item.add_marker(pytest.mark.xdist_group(name="serial"))


@pytest.fixture(scope="session")
def django_db_modify_db_settings(django_db_modify_db_settings_parallel_suffix):
    """
    Fixture to ensure each xdist worker gets its own database.

    This is automatically handled by pytest-django when running with xdist,
    but we explicitly include it here for clarity.
    """
    pass


def pytest_xdist_setupnodes(config, specs):
    """Called before any workers are created. Use for one-time setup."""
    pass


def pytest_xdist_make_scheduler(config, log):
    """
    Create a scheduler that respects test grouping.

    Using LoadScopeScheduling keeps tests from the same class together,
    which is important for setUpClass/setUpTestData patterns.
    """
    # Return None to use the default scheduler specified by --dist option
    # Users should specify --dist loadscope for proper class-level grouping
    return None


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    """Setup hook that runs before each test."""
    # Get worker ID for logging (empty string if not using xdist)
    worker_id = os.environ.get("PYTEST_XDIST_WORKER", "")
    if worker_id:
        # Set worker ID in environment for tests that need to know
        os.environ["TEST_WORKER_ID"] = worker_id

    # NOTE: We intentionally do NOT call db.close_old_connections() here.
    # Hooks run BEFORE pytest-django's db fixtures are applied, so calling
    # db.close_old_connections() would fail with "Database access not allowed".
    # Connection cleanup is handled in pytest_runtest_teardown() instead,
    # which runs AFTER the test when database access is available.

    # Ensure a fresh event loop is available for each test.
    # This prevents "Event loop is closed" errors when using pydantic-ai's
    # run_sync() or other async code with pytest-xdist.
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("Event loop is closed")
    except RuntimeError:
        # Create a new event loop if one doesn't exist or is closed
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)


@pytest.hookimpl(trylast=True)
def pytest_runtest_teardown(item, nextitem):
    """Teardown hook that runs after each test."""
    # Clean up any event loop that was created during the test
    # to prevent resource leaks, but don't close it as the next test may need it
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If the loop is still running, we can't close it safely
            pass
        elif not loop.is_closed():
            # Cancel any pending tasks
            pending = asyncio.all_tasks(loop) if hasattr(asyncio, "all_tasks") else []
            for task in pending:
                task.cancel()
    except RuntimeError:
        # No event loop, nothing to clean up
        pass

    # For serial tests (which use async code with asyncio.run()), close ALL
    # database connections to prevent stale/corrupted connections from affecting
    # subsequent tests. asyncio.run() can leave connections in a bad state when
    # it closes its event loop.
    #
    # NOTE: Unlike db.close_old_connections() which checks connection state
    # (and requires DB access to be allowed), db.connections.close_all() just
    # directly closes connections without state checks. This should be safe
    # in teardown, but we wrap in try/except for robustness.
    if item.get_closest_marker("serial"):
        try:
            db.connections.close_all()
        except Exception:
            # If connection cleanup fails, log but don't fail the test
            # This can happen in edge cases with pytest-django fixture teardown
            pass
