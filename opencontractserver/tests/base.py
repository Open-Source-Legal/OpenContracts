import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any, ClassVar

import pytest
from django.conf import settings
from django.db import connection, connections
from django.db.utils import OperationalError
from django.test import TestCase, TransactionTestCase, override_settings
from graphql_jwt.shortcuts import get_token

from config.asgi import application
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.users.models import User

logger = logging.getLogger(__name__)

# Settings shared by both fixture-backed base classes.
_FIXTURE_TEST_SETTINGS = dict(
    STORAGES={
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    },
    MEDIA_ROOT="test_media/",
    CELERY_TASK_ALWAYS_EAGER=True,
)

# Document file fields materialised from opencontractserver/tests/fixtures/files/.
_FIXTURE_FILE_FIELDS: tuple[str, ...] = (
    "pdf_file",
    "txt_extract_file",
    "pawls_parse_file",
    "icon",
    "md_summary_file",
)


class _FixtureSetupMixin:
    """Shared fixture-backed test-data construction.

    Mixed into both :class:`BaseFixtureTestCase` (``TestCase``) and
    :class:`TransactionFixtureTestCase` (``TransactionTestCase``). Setup splits
    into two cooperating phases:

    * :meth:`_build_corpus_fixture_state` — pure DB work: load the ``testuser``
      account, normalise the fixture documents' file-field paths, create the
      test corpus, add the documents with corpus isolation, and grant
      django-guardian permissions. For the ``TestCase`` variant this runs
      **once per class** in ``setUpTestData`` (inside the class transaction);
      for the ``TransactionTestCase`` variant it runs **once per test** in
      ``setUp``, because committed-data semantics require a fresh build that
      survives the per-test database flush.
    * :meth:`_materialize_fixture_files` — copies the fixture files into the
      live ``MEDIA_ROOT``. Always per-test: the autouse ``media_storage``
      fixture (``opencontractserver/conftest.py``) repoints ``MEDIA_ROOT`` at a
      fresh tmpdir for every test, so the files must be re-copied into it.

    The fixture (``test_data.json``) itself is loaded by Django's fixture
    machinery — once per class for ``TestCase``, once per test for
    ``TransactionTestCase``.
    """

    fixtures: ClassVar[list[str]] = [
        "opencontractserver/tests/fixtures/test_data.json",
    ]

    # Populated by _build_corpus_fixture_state (class attrs for the TestCase
    # variant, instance attrs for the TransactionTestCase variant).
    user: ClassVar[User]
    docs: ClassVar[list[Document]]
    corpus: ClassVar[Corpus]

    @property
    def doc(self) -> Document:
        """First corpus document — kept identity-consistent with ``docs[0]``."""
        return self.docs[0]

    @property
    def doc2(self) -> Document:
        """Second corpus document."""
        return self.docs[1]

    @property
    def doc3(self) -> Document:
        """Third corpus document."""
        return self.docs[2]

    @staticmethod
    def copy_fixture_file(fixture_path: str, dest_path: str) -> None:
        """Copy a file from the fixtures directory into the test media directory.

        Args:
            fixture_path: Path relative to the 'files' directory in
                'opencontractserver/tests/fixtures' (a leading 'files/' is
                stripped if present).
            dest_path: Destination path relative to ``MEDIA_ROOT``.
        """
        if fixture_path.startswith("files/"):
            fixture_path = fixture_path.replace("files/", "", 1)

        src = Path("opencontractserver/tests/fixtures/files") / fixture_path
        dest = Path(settings.MEDIA_ROOT) / dest_path

        os.makedirs(os.path.dirname(dest), exist_ok=True)

        with open(src, "rb") as f:
            file_contents = f.read()

        with open(dest, "wb") as f:
            f.write(file_contents)

    @classmethod
    def _build_corpus_fixture_state(cls, ns: Any) -> None:
        """Build the corpus/document test state on ``ns``.

        ``ns`` is the namespace to populate — the class itself when called from
        ``TestCase.setUpTestData``, or a test instance when called from
        ``TransactionTestCase.setUp``.
        """
        from opencontractserver.types.enums import PermissionTypes
        from opencontractserver.utils.permissioning import (
            set_permissions_for_obj_to_user,
        )

        ns.user = User.objects.get(username="testuser")

        fixture_docs = list(Document.objects.all().order_by("id"))
        if not fixture_docs:
            ns.docs = []
            return

        # Normalise fixture file-field paths to media-relative form. The
        # fixture stores them prefixed with "files/"; strip that so the stored
        # path matches where copy_fixture_file() writes them under MEDIA_ROOT.
        for doc in fixture_docs:
            for field in _FIXTURE_FILE_FIELDS:
                file_field = getattr(doc, field, None)
                if file_field and str(file_field.name).startswith("files/"):
                    setattr(doc, field, str(file_field.name).replace("files/", "", 1))
            doc.save()

        # Create the test corpus and grant the creator full permissions
        # (django-guardian requires explicit assignment).
        ns.corpus = Corpus.objects.create(
            title="Test Corpus",
            description="A collection of contracts.",
            creator=ns.user,
            backend_lock=False,
        )
        set_permissions_for_obj_to_user(ns.user, ns.corpus, [PermissionTypes.ALL])

        # Add documents to the corpus. add_document() creates corpus-isolated
        # copies; tests interact with those copies, not the raw fixture docs.
        ns.docs = []
        for doc in fixture_docs:
            corpus_doc, _, _ = ns.corpus.add_document(document=doc, user=ns.user)
            set_permissions_for_obj_to_user(ns.user, corpus_doc, [PermissionTypes.ALL])
            ns.docs.append(corpus_doc)

    def _materialize_fixture_files(self) -> None:
        """Copy every corpus document's fixture files into the current MEDIA_ROOT.

        Runs per-test because the autouse ``media_storage`` fixture points
        ``MEDIA_ROOT`` at a fresh tmpdir for each test.
        """
        for doc in self.docs:
            for field in _FIXTURE_FILE_FIELDS:
                file_field = getattr(doc, field, None)
                if file_field and file_field.name:
                    self.copy_fixture_file(file_field.name, file_field.name)


@pytest.mark.django_db
@override_settings(**_FIXTURE_TEST_SETTINGS)
class BaseFixtureTestCase(_FixtureSetupMixin, TestCase):
    """Fixture-backed base test case (``TestCase`` variant — the default).

    The 18 MB ``test_data.json`` fixture and the derived corpus/document state
    load **once per class** (``setUpTestData``), inside the class-level
    transaction, instead of once per test. Each test still runs in its own
    savepoint, so per-test database mutations are rolled back.

    Use the ``TransactionTestCase``-backed variants instead when a test needs
    committed-data semantics — i.e. data must be visible across database
    connections (async consumers, websockets, Celery-eager tasks that read the
    database from a worker thread). Those are :class:`TransactionFixtureTestCase`,
    :class:`WebsocketFixtureBaseTestCase` and :class:`CeleryEagerModeFixtureTestCase`.

    Signal management is handled globally by the ``conftest.py`` fixture
    ``disable_document_processing_signals``.
    """

    @classmethod
    def setUpClass(cls) -> None:
        os.makedirs(settings.MEDIA_ROOT, exist_ok=True)
        super().setUpClass()

    @classmethod
    def setUpTestData(cls) -> None:
        """Build the corpus/document fixture state once per class."""
        cls._build_corpus_fixture_state(cls)

    def setUp(self) -> None:
        super().setUp()
        self._materialize_fixture_files()

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            super().tearDownClass()
        finally:
            if os.path.exists(settings.MEDIA_ROOT):
                shutil.rmtree(settings.MEDIA_ROOT)


@pytest.mark.django_db
@override_settings(**_FIXTURE_TEST_SETTINGS)
class TransactionFixtureTestCase(_FixtureSetupMixin, TransactionTestCase):
    """Fixture-backed base test case (``TransactionTestCase`` variant).

    Backed by ``TransactionTestCase``: the fixture and the derived
    corpus/document state are rebuilt for **every test**, committed (not rolled
    back). Required for tests whose code under test reads the database across
    connections — async consumers, websockets, Celery-eager tasks. Slower than
    :class:`BaseFixtureTestCase`; use it only when committed data is genuinely
    needed.

    Keeps explicit database-connection management because ``TransactionTestCase``
    truncates and reloads between tests, and async/Celery code can leave
    connections lingering.
    """

    @classmethod
    def _terminate_other_connections(cls) -> None:
        """
        Force-terminate any extra sessions connected to the test database so there are
        no lingering connections that block teardown or DB deletion.
        """
        db_name = settings.DATABASES["default"]["NAME"]
        with connection.cursor() as cursor:
            logger.info(f"Terminating stale DB connections for DB: {db_name}")
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM pg_stat_activity
                WHERE datname = %s AND pid <> pg_backend_pid();
                """,
                [db_name],
            )
            count = cursor.fetchone()[0]
            logger.info(f"Found {count} other connections to {db_name}")

            if count > 0:
                cursor.execute(
                    """
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE pid <> pg_backend_pid()
                      AND datname = %s;
                    """,
                    [db_name],
                )
                logger.info(f"Terminated {count} connections to {db_name}")

    @classmethod
    def setUpClass(cls) -> None:
        """
        Set up test class, closing any lingering DB connections before continuing.
        """
        os.makedirs(settings.MEDIA_ROOT, exist_ok=True)

        # Close any existing connections before setup
        for conn in connections.all():
            conn.close()

        super().setUpClass()

    @classmethod
    def _pre_setup(cls):
        """
        Additional setup before each test, ensuring no stale database
        connections remain.
        """
        for conn in connections.all():
            conn.close()
        super()._pre_setup()

    def _post_teardown(self):
        """
        Additional teardown after each test method, ensuring connections
        are closed.
        """
        super()._post_teardown()
        for conn in connections.all():
            conn.close()

    @classmethod
    def tearDownClass(cls) -> None:
        """
        Clean up test media and database connections.
        """
        try:
            # First, just close connections normally without terminating
            for conn in connections.all():
                conn.close_if_unusable_or_obsolete()
                conn.close()
            connection.close()

            # Try the parent teardown without forcibly terminating connections
            try:
                super().tearDownClass()
            except OperationalError as e:
                if "database is being accessed by other users" in str(e):
                    logger.warning(
                        "Warning: Could not delete test database (in use by other connections)."
                    )

                    # Only now, as a last resort, terminate connections
                    time.sleep(2)  # Give any in-progress operations time to finish
                    cls._terminate_other_connections()

                    # Try again with super teardown
                    try:
                        super().tearDownClass()
                    except OperationalError:
                        logger.warning(
                            "Still could not delete test database after terminating connections."
                        )
                else:
                    raise
        finally:
            # Clean up test media directory
            if os.path.exists(settings.MEDIA_ROOT):
                shutil.rmtree(settings.MEDIA_ROOT)

    def setUp(self) -> None:
        """
        Rebuild the fixture-backed corpus/document state for each test, then
        materialize the fixture files into MEDIA_ROOT.
        """
        super().setUp()
        self._build_corpus_fixture_state(self)
        self._materialize_fixture_files()


class WebsocketFixtureBaseTestCase(TransactionFixtureTestCase):
    """
    TransactionTestCase-backed fixture base for WebSocket tests.

    WebSocket consumers run inside their own database connection, so they need
    the committed-data semantics of :class:`TransactionFixtureTestCase`. Adds a
    JWT token for the fixture user and the default agent configurations the
    UnifiedAgentConsumer expects.
    """

    def setUp(self) -> None:
        """
        Build the fixture state (user, documents, corpus), then create a token
        for the fixture user and the agent configurations WebSocket connections
        require.
        """
        super().setUp()
        self.token = get_token(user=self.user)
        self.application = application

        # Create required agent configurations for UnifiedAgentConsumer
        # These are needed for WebSocket connections to be accepted
        from opencontractserver.agents.models import AgentConfiguration

        AgentConfiguration.objects.get_or_create(
            slug="default-corpus-agent",
            defaults={
                "name": "Default Corpus Agent",
                "description": "Default agent for corpus-level queries",
                "system_instructions": "You are a helpful assistant.",
                "available_tools": [],
                "is_active": True,
                "scope": "GLOBAL",
                "creator": self.user,
            },
        )
        AgentConfiguration.objects.get_or_create(
            slug="default-document-agent",
            defaults={
                "name": "Default Document Agent",
                "description": "Default agent for document-level queries",
                "system_instructions": "You are a helpful assistant.",
                "available_tools": [],
                "is_active": True,
                "scope": "GLOBAL",
                "creator": self.user,
            },
        )


class CeleryEagerModeTestCase(TransactionTestCase):
    """
    Base test case for tests that use Celery's eager mode.

    This test case ensures that database connections are properly managed
    when running Celery tasks in eager mode during tests.
    """

    def setUp(self):
        super().setUp()
        # Ensure we have a fresh connection before each test
        for alias in connections:
            connections[alias].close()
            connections[alias].connect()

    def tearDown(self):
        # Close connections after each test to prevent them from being terminated
        # while still in use
        for alias in connections:
            connections[alias].close()
        super().tearDown()


class CeleryEagerModeFixtureTestCase(
    TransactionFixtureTestCase, CeleryEagerModeTestCase
):
    """
    Combines :class:`TransactionFixtureTestCase` with :class:`CeleryEagerModeTestCase`.

    Use this for tests that need both fixtures and Celery eager mode with
    committed-data semantics.
    """

    def setUp(self):
        # Call both parent setUp methods
        TransactionFixtureTestCase.setUp(self)
        CeleryEagerModeTestCase.setUp(self)

        # Ensure we have fresh connections before running async tasks
        for alias in connections:
            connections[alias].close()
            connections[alias].connect()

    def tearDown(self):
        # IMPORTANT: Django will close and terminate connections during test teardown,
        # but our Celery tasks in eager mode might still be using them.
        # We need to make sure all Celery tasks are done before closing connections.

        # Give pending tasks a chance to complete
        time.sleep(0.5)  # Add a small delay to ensure tasks have a chance to finish

        try:
            # Close connections before teardown to prevent them from being terminated
            # while still in use by async tasks
            for alias in connections:
                connections[alias].close_if_unusable_or_obsolete()
                connections[alias].close()
        except Exception as e:
            logging.warning(f"Error closing connections during tearDown: {e}")

        # Call both parent tearDown methods in reverse order
        CeleryEagerModeTestCase.tearDown(self)
        TransactionFixtureTestCase.tearDown(self)
