"""
Command for generating test fixtures, with an added step to filter out certain users
(e.g. 'admin' and 'Anonymous') from the dumped JSON instead of removing them
from the database before dumping.
"""

import json
from pathlib import Path
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.models.signals import post_save
from django.test.utils import (
    override_settings,
    setup_test_environment,
    teardown_test_environment,
)

from opencontractserver.annotations.models import Annotation
from opencontractserver.annotations.signals import (
    ANNOT_CREATE_UID,
    process_annot_on_create_atomic,
)
from opencontractserver.documents.models import Document
from opencontractserver.documents.signals import process_doc_on_create_atomic
from opencontractserver.tasks.doc_tasks import ingest_doc
from opencontractserver.tasks.embeddings_task import (
    calculate_embedding_for_annotation_text,
)
from opencontractserver.tests.fixtures import SAMPLE_PDF_FILE_TWO_PATH

User = get_user_model()


class Command(BaseCommand):
    """
    Generate test fixtures by running document processing pipeline and dumping results.
    The command sets up a test DB, creates some Document objects and their annotations,
    and dumps fixture data into two JSON files: contenttypes.json and test_data.json.
    After dumping, unwanted users (e.g. 'admin' and 'AnonymousUser') are filtered out
    of the JSON fixture file, ensuring they do not appear in the final fixture.
    """

    help = "Generate test fixtures using an all-natural-keys approach."

    def setup_test_db(self) -> None:
        """
        Set up a test database environment.
        Creates a test database (like Django's TestCase does under the hood)
        and configures the test environment.
        """
        setup_test_environment()
        self.old_db_name = connection.settings_dict["NAME"]
        test_db_name = connection.creation.create_test_db(
            verbosity=1,
            autoclobber=True,
            serialize=False,
        )
        self.stdout.write(f"Created test database '{test_db_name}'")

    def teardown_test_db(self) -> None:
        """
        Destroy the test database and restore the environment.
        """
        connection.creation.destroy_test_db(self.old_db_name, verbosity=1)
        teardown_test_environment()
        self.stdout.write("Destroyed test database")

    def save_file_to_fixtures(self, file_obj, filename: str) -> str:
        """
        Save a file to the fixtures directory and return its relative path.

        Args:
            file_obj: The file field object, e.g. doc.pdf_file.file
            filename: The desired filename in the fixtures directory

        Returns:
            str: The new, relative path for the fixture
        """
        fixtures_dir = Path("opencontractserver/tests/fixtures/files")
        fixtures_dir.mkdir(exist_ok=True)

        dest_path = fixtures_dir / filename

        # Read the file contents
        file_obj.seek(0)
        file_contents = file_obj.read()

        # Write to fixtures directory
        with open(dest_path, "wb") as f:
            f.write(file_contents)

        # Return a path relative to the fixtures directory - use files/ not fixtures/files/
        return f"files/{filename}"

    def process_fixtures(self, fixture_path: str) -> None:
        """
        Process the generated fixtures to:
        1) Update file paths for Documents so that file fields point to the newly copied files.
        2) Filter out unwanted users (e.g. 'admin' or 'AnonymousUser') from the fixture JSON.

        Args:
            fixture_path: The file path of the fixture JSON to process.
        """
        with open(fixture_path, encoding="utf-8") as f:
            data = json.load(f)

        # Update file fields for Document objects
        for item in data:
            if item["model"] == "documents.document":
                fields = item["fields"]
                file_fields = [
                    "pdf_file",
                    "txt_extract_file",
                    "pawls_parse_file",
                    "icon",
                ]
                for field in file_fields:
                    if fields.get(field):
                        doc = Document.objects.get(pk=item["pk"])
                        file_obj = getattr(doc, field)
                        if file_obj:
                            # Generate a unique filename
                            filename = (
                                f"doc_{item['pk']}_{field}{Path(file_obj.name).suffix}"
                            )
                            # Save the file and update the path
                            new_path = self.save_file_to_fixtures(
                                file_obj.file, filename
                            )
                            fields[field] = new_path

        # Filter out unwanted users at the JSON level (e.g. "admin", "Anonymous")
        data = [
            record
            for record in data
            if not (
                record["model"] == "users.user"
                and record["fields"]["username"] in ["admin", "Anonymous"]
            )
        ]

        # Write updated data back
        with open(fixture_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def handle(self, *args: Any, **options: Any) -> None:
        """
        Main command execution method. Sets up a test database, creates sample documents
        and annotations, and dumps them to JSON fixtures. Then cleans up the test database.
        """
        try:
            # Set up test database
            self.setup_test_db()

            # Disconnect signals just like in the test
            post_save.disconnect(
                process_annot_on_create_atomic,
                sender=Annotation,
                dispatch_uid=ANNOT_CREATE_UID,
            )
            post_save.disconnect(process_doc_on_create_atomic, sender=Document)

            # Create default group for newly created user
            group, _ = Group.objects.get_or_create(
                name=settings.DEFAULT_PERMISSIONS_GROUP
            )

            # Create a test user
            user = User.objects.create_user(username="testuser", password="testpass")

            # Prepare and create documents
            pdf_file_content = SAMPLE_PDF_FILE_TWO_PATH.open("rb").read()

            pdf_file = ContentFile(pdf_file_content, name="test.pdf")
            doc1 = Document.objects.create(
                creator=user,
                title="Test Doc",
                description="USC Title 1 - Chapter 1",
                custom_meta={},
                pdf_file=pdf_file,
                backend_lock=True,
            )
            self.stdout.write("Processing first document...")
            ingest_doc.delay(user_id=user.id, doc_id=doc1.id)

            # Additional docs for more coverage
            pdf_file = ContentFile(pdf_file_content, name="test.pdf")
            doc2 = Document.objects.create(
                creator=user,
                title="Rando Doc",
                description="RANDO DOC!",
                custom_meta={},
                pdf_file=pdf_file,
                backend_lock=True,
            )
            self.stdout.write("Processing second document...")
            ingest_doc.delay(user_id=user.id, doc_id=doc2.id)

            pdf_file = ContentFile(pdf_file_content, name="test.pdf")
            doc3 = Document.objects.create(
                creator=user,
                title="Rando Doc 2",
                description="RANDO DOC! 2",
                custom_meta={},
                pdf_file=pdf_file,
                backend_lock=True,
            )
            self.stdout.write("Processing third document...")
            ingest_doc.delay(user_id=user.id, doc_id=doc3.id)

            pdf_file = ContentFile(pdf_file_content, name="test.pdf")
            doc4 = Document.objects.create(
                creator=user,
                title="Rando Doc 3",
                description="RANDO DOC! 3",
                custom_meta={},
                pdf_file=pdf_file,
                backend_lock=True,
            )
            self.stdout.write("Processing fourth document...")
            ingest_doc.delay(user_id=user.id, doc_id=doc4.id)

            # Generate embeddings synchronously to ensure they're ready before dumping
            self.stdout.write("Generating embeddings for annotations...")
            annot_count = Annotation.objects.count()
            for i, annot in enumerate(Annotation.objects.all(), 1):
                calculate_embedding_for_annotation_text.delay(annotation_id=annot.id)
                if i % 100 == 0:
                    self.stdout.write(
                        f"  Progress: {i}/{annot_count} ({i/annot_count*100:.1f}%)"
                    )

            # Wait a moment for eager tasks to complete
            import time

            time.sleep(2)

            embed_count = Annotation.objects.filter(embeddings__isnull=False).count()
            self.stdout.write(
                f"Generated {embed_count} embeddings for {annot_count} annotations"
            )

            # Dump all apps with natural keys into a single fixture
            apps_to_dump = [
                "contenttypes",
                "auth.permission",
                "auth.group",
                "users.user",
                "guardian.groupobjectpermission",
                "guardian.userobjectpermission",
                "documents.document",
                "annotations.annotationlabel",
                "annotations.annotation",
                "annotations.embedding",
                "annotations.relationship",
            ]

            fixture_path = Path("opencontractserver/tests/fixtures/test_data.json")
            call_command(
                "dumpdata",
                *apps_to_dump,
                "--natural-foreign",
                "--natural-primary",
                indent=2,
                output=str(fixture_path),
            )

            # Process fixture to remove admin/Anonymous users
            self.process_fixtures(str(fixture_path))

            self.stdout.write(
                self.style.SUCCESS(
                    "Successfully generated test fixtures in opencontractserver/tests/fixtures/"
                )
            )

        finally:
            self.teardown_test_db()
