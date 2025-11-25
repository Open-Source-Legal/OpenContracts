import logging
import os
import shutil
import time
from pathlib import Path
from typing import ClassVar

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection, connections
from django.db.models.signals import post_save
from django.db.utils import OperationalError
from django.test import TransactionTestCase, override_settings
from graphql_jwt.shortcuts import get_token

from config.asgi import application
from opencontractserver.annotations.models import Annotation
from opencontractserver.annotations.signals import (
    ANNOT_CREATE_UID,  # Import the static UID
)
from opencontractserver.annotations.signals import (
    process_annot_on_create_atomic,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.documents.signals import (
    DOC_CREATE_UID,
    process_doc_on_create_atomic,
)

User = get_user_model()
logger = logging.getLogger(__name__)


@pytest.mark.django_db
@override_settings(
    DEFAULT_FILE_STORAGE="django.core.files.storage.FileSystemStorage",
    MEDIA_ROOT="test_media/",
    CELERY_TASK_ALWAYS_EAGER=True,
)
class BaseFixtureTestCase(TransactionTestCase):
    """
    Base test case that loads fixtures using natural keys and disables signals.

    This test case:
    1. Loads the test fixtures automatically (split into contenttypes and test_data).
    2. Disables document and annotation processing signals.
    3. Provides helper methods to access test data.
    4. Handles file field storage and cleanup.
    """

    fixtures: ClassVar[list[str]] = [
        "opencontractserver/tests/fixtures/test_data.json",
    ]

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
        Set up test class with patched signals.
        Also closes any lingering DB connections before continuing.
        """
        os.makedirs(settings.MEDIA_ROOT, exist_ok=True)

        # Disconnect signals before loading fixtures
        post_save.disconnect(
            process_doc_on_create_atomic, sender=Document, dispatch_uid=DOC_CREATE_UID
        )
        post_save.disconnect(
            process_annot_on_create_atomic,
            sender=Annotation,
            dispatch_uid=ANNOT_CREATE_UID,  # Use static UID
        )

        # Close any existing connections before setup
        for conn in connections.all():
            conn.close()

        super().setUpClass()

    def _pre_setup(self):
        """
        Additional setup before each test method, which includes ensuring
        no stale database connections remain.
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
        Clean up signal patches, test media, and database connections.
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
            # Reconnect signals and clean up the filesystem
            post_save.connect(
                process_doc_on_create_atomic,
                sender=Document,
                dispatch_uid=DOC_CREATE_UID,
            )
            post_save.connect(
                process_annot_on_create_atomic,
                sender=Annotation,
                dispatch_uid=ANNOT_CREATE_UID,  # Use static UID
            )

            if os.path.exists(settings.MEDIA_ROOT):
                shutil.rmtree(settings.MEDIA_ROOT)

    def copy_fixture_file(self, fixture_path: str, dest_path: str) -> None:
        """
        Copy a file from fixtures to the test media directory.

        Args:
            fixture_path: Path relative to the 'files' directory in 'opencontractserver/tests/fixtures'
            dest_path: Destination path in test media directory
        """
        # If the fixture path starts with "files/", remove that portion so we can build the local path
        if fixture_path.startswith("files/"):
            fixture_path = fixture_path.replace("files/", "", 1)

        src = Path("opencontractserver/tests/fixtures/files") / fixture_path
        dest = Path(settings.MEDIA_ROOT) / dest_path

        os.makedirs(os.path.dirname(dest), exist_ok=True)

        with open(src, "rb") as f:
            file_contents = f.read()

        with open(dest, "wb") as f:
            f.write(file_contents)

    def setUp(self) -> None:
        """
        Set up test instance with commonly needed objects, including user
        and any documents that were loaded in the fixtures.
        """
        super().setUp()

        self.user = User.objects.get(username="testuser")

        self.docs = list(Document.objects.all().order_by("id"))
        if not self.docs:
            return

        self.doc = self.docs[0]
        if len(self.docs) > 1:
            self.doc2 = self.docs[1]
        if len(self.docs) > 2:
            self.doc3 = self.docs[2]

        # ------------------------------------------------------------------ #
        # 0. Migrate old-style structural annotations to StructuralAnnotationSet
        # ------------------------------------------------------------------ #
        from opencontractserver.annotations.models import (
            Annotation,
            Relationship,
            StructuralAnnotationSet,
        )

        for doc in self.docs:
            # Check if document has old-style structural annotations (document FK set)
            old_structural = Annotation.objects.filter(
                document=doc, structural=True, structural_set__isnull=True
            )

            if old_structural.exists() and not doc.structural_annotation_set:
                # Create a StructuralAnnotationSet for this document
                content_hash = doc.pdf_file_hash or f"test_doc_{doc.pk}"
                struct_set, created = StructuralAnnotationSet.objects.get_or_create(
                    content_hash=content_hash,
                    defaults={
                        "creator": self.user,
                        "parser_name": "FixtureMigration",
                        "parser_version": "1.0",
                        "page_count": doc.page_count,
                        "pawls_parse_file": doc.pawls_parse_file,
                        "txt_extract_file": doc.txt_extract_file,
                    },
                )

                # Migrate annotations to the structural set
                for annot in old_structural:
                    annot.structural_set = struct_set
                    annot.document = None  # Remove document link (XOR constraint)
                    annot.save()

                # Migrate relationships between structural annotations
                # Get relationships where both source and target are structural annotations
                old_structural_ids = set(old_structural.values_list("id", flat=True))
                old_relationships = Relationship.objects.filter(
                    document=doc, structural_set__isnull=True
                ).filter(
                    source_annotations__id__in=old_structural_ids,
                    target_annotations__id__in=old_structural_ids,
                )

                for rel in old_relationships:
                    rel.structural_set = struct_set
                    rel.document = None  # Remove document link (XOR constraint)
                    rel.save()

                # Update document to reference the structural set
                doc.structural_annotation_set = struct_set
                doc.save()

                logger.info(
                    f"Migrated {old_structural.count()} structural annotations "
                    f"and {old_relationships.count()} relationships "
                    f"from doc {doc.pk} to StructuralAnnotationSet {struct_set.pk}"
                )

        # ------------------------------------------------------------------ #
        # 1. Copy existing fixture files  +  ensure md_summary_file is copied #
        # ------------------------------------------------------------------ #
        FILE_FIELDS: tuple[str, ...] = (
            "pdf_file",
            "txt_extract_file",
            "pawls_parse_file",
            "icon",
            "md_summary_file",  # <- NEW
        )

        for doc in self.docs:
            for field in FILE_FIELDS:
                file_field = getattr(doc, field, None)
                if file_field:
                    file_path = str(file_field.name)
                    if file_path.startswith("files/"):
                        media_path = file_path.replace("files/", "", 1)
                        self.copy_fixture_file(file_path, media_path)
                        setattr(doc, field, media_path)
                    # Else, if not starting with "files/", assume it's already a relative media path
                    # and self.copy_fixture_file is not needed as it's presumably already in MEDIA_ROOT
                    # or the path on the model is already correct.

            # -------------------------------------------------------------- #
            #  Handle md_summary_file: Prioritize manual, then generate.     #
            # -------------------------------------------------------------- #
            placeholder_phrase: str = (
                "Autogenerated test summary – replace with real content if needed."
            )
            doc_summary_final_media_rel_path: str | None = (
                None  # This will be the relative path in MEDIA_ROOT
            )

            # Step 1: Check if md_summary_file was already set (e.g., by test_data.json and copied above)
            # If it was, doc_summary_final_media_rel_path is its media-relative path.
            # If not, it's None.
            potential_summary_from_fixture = getattr(doc, "md_summary_file", None)
            if potential_summary_from_fixture and isinstance(
                potential_summary_from_fixture, str
            ):
                # Assume it has been converted to a media-relative path by the loop above
                # or was already a correct relative path.
                doc_summary_final_media_rel_path = potential_summary_from_fixture

            # Step 2: If no summary from test_data.json, try to load a manual one by convention
            if not doc_summary_final_media_rel_path:
                manual_summary_fixture_rel_path = (
                    f"files/md_summaries/{doc.pk}_summary.md"
                )
                manual_summary_fixture_abs_path = (
                    Path("opencontractserver/tests/fixtures")
                    / manual_summary_fixture_rel_path
                )

                if manual_summary_fixture_abs_path.exists():
                    # Destination in media: md_summaries/{doc.pk}_summary.md
                    target_media_rel_path = f"md_summaries/{doc.pk}_summary.md"
                    self.copy_fixture_file(
                        manual_summary_fixture_rel_path, target_media_rel_path
                    )
                    doc_summary_final_media_rel_path = target_media_rel_path
                    # We've copied it to media, so set it on the doc object
                    # setattr(doc, "md_summary_file", target_media_rel_path) # This will be done before doc.save()

            # Step 3: Ensure the summary (whether from test_data.json, manual file, or to-be-generated)
            # is useful. If not (missing or placeholder), generate it.
            summary_abs_path_in_media: Path | None = None
            regenerate_summary_content = False

            if doc_summary_final_media_rel_path:
                summary_abs_path_in_media = (
                    Path(settings.MEDIA_ROOT) / doc_summary_final_media_rel_path
                )
                if summary_abs_path_in_media.exists():
                    try:
                        existing_content = summary_abs_path_in_media.read_text(
                            encoding="utf-8", errors="ignore"
                        )
                        if (
                            placeholder_phrase in existing_content
                            and len(existing_content.strip())
                            <= len(placeholder_phrase) + 50
                        ):  # Allow some minor variation
                            regenerate_summary_content = True
                    except Exception as e:
                        logger.warning(
                            f"Could not read existing summary {summary_abs_path_in_media}: {e}"
                        )
                        regenerate_summary_content = True  # Treat as if placeholder
                else:
                    # File path is set on doc, but file doesn't exist in media_root
                    regenerate_summary_content = True
            else:
                # No summary file path determined yet, so we definitely need to generate one.
                regenerate_summary_content = True
                # Create a conventional path for the new summary
                doc_summary_final_media_rel_path = f"md_summaries/{doc.pk}_summary.md"
                summary_abs_path_in_media = (
                    Path(settings.MEDIA_ROOT) / doc_summary_final_media_rel_path
                )

            if (
                regenerate_summary_content and summary_abs_path_in_media
            ):  # summary_abs_path_in_media must be set
                summary_abs_path_in_media.parent.mkdir(parents=True, exist_ok=True)

                excerpt: str = ""
                txt_rel_path: str | None = getattr(doc, "txt_extract_file", None)

                if txt_rel_path:  # txt_rel_path should be a media-relative path now
                    txt_abs_path_in_media = Path(settings.MEDIA_ROOT) / txt_rel_path
                    if txt_abs_path_in_media.exists():
                        try:
                            raw_text = txt_abs_path_in_media.read_text(
                                encoding="utf-8", errors="ignore"
                            )
                            excerpt = raw_text.strip()[:2000]
                        except Exception as e:
                            logger.warning(
                                f"Could not read txt_extract_file {txt_abs_path_in_media} for doc {doc.pk}: {e}"
                            )

                final_excerpt = excerpt if excerpt else placeholder_phrase

                summary_md: str = (
                    f"# Summary for Document {doc.title or f'ID {doc.pk}'}\\n\\n"
                    f"{placeholder_phrase}\\n\\n"  # Keep for VCR compatibility
                    f"---\\n\\n"
                    f"{final_excerpt}"
                )
                try:
                    summary_abs_path_in_media.write_text(summary_md, encoding="utf-8")
                except Exception as e:
                    logger.error(
                        f"Failed to write summary for doc {doc.pk} to {summary_abs_path_in_media}: {e}"
                    )

            # Step 4: Ensure doc.md_summary_file is set to the final relative path before saving
            if doc_summary_final_media_rel_path:
                setattr(doc, "md_summary_file", doc_summary_final_media_rel_path)
            else:
                # This case should ideally not be reached if logic is correct,
                # as a path should always be determined or generated.
                # But as a fallback, remove it if it's somehow None.
                if hasattr(
                    doc, "md_summary_file"
                ):  # Should not be necessary, but defensive
                    setattr(doc, "md_summary_file", None)

            doc.save()

        # -------------------------------------------------------------- #
        # 2. Create a corpus with a proper description                   #
        # -------------------------------------------------------------- #
        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            description="A collection of contracts.",
            creator=self.user,
            backend_lock=False,
        )

        # -------------------------------------------------------------- #
        # 3. Add documents to corpus (corpus isolation)                  #
        # -------------------------------------------------------------- #
        # Update self.doc(s) to point to corpus-isolated copies
        for i, doc in enumerate(self.docs):
            corpus_doc, _, _ = self.corpus.add_document(document=doc, user=self.user)
            self.docs[i] = corpus_doc

        # Update individual doc references
        if self.docs:
            self.doc = self.docs[0]
        if len(self.docs) > 1:
            self.doc2 = self.docs[1]
        if len(self.docs) > 2:
            self.doc3 = self.docs[2]


class WebsocketFixtureBaseTestCase(BaseFixtureTestCase):
    """
    Inherits from BaseFixtureTestCase to load fixtures (test_data.json) and
    provide a realistic set of data for WebSocket tests. This ensures that
    we have a user named 'testuser' and at least one Document from the fixtures.
    """

    def setUp(self) -> None:
        """
        Hooks into the BaseFixtureTestCase setUp, which loads a user (self.user)
        and any documents (self.doc, self.docs, etc.) from the fixture.
        We then create a token for the fixture user.
        """
        super().setUp()
        self.token = get_token(user=self.user)
        self.application = application


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


class CeleryEagerModeFixtureTestCase(BaseFixtureTestCase, CeleryEagerModeTestCase):
    """
    Combines BaseFixtureTestCase with CeleryEagerModeTestCase.

    Use this for tests that need both fixtures and Celery eager mode.
    """

    def setUp(self):
        # Call both parent setUp methods
        BaseFixtureTestCase.setUp(self)
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
        BaseFixtureTestCase.tearDown(self)
