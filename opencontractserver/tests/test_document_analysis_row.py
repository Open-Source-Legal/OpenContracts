import logging

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.test import TestCase

from opencontractserver.analyzer.models import Analysis, Analyzer, GremlinEngine
from opencontractserver.annotations.models import Annotation
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentAnalysisRow
from opencontractserver.extracts.models import Column, Datacell, Extract, Fieldset
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import (
    get_users_permissions_for_obj,
    set_permissions_for_obj_to_user,
    user_has_permission_for_obj,
)

User = get_user_model()


class DocumentAnalysisRowTestCase(TestCase):
    def setUp(self):
        with transaction.atomic():
            self.user = User.objects.create_user(
                username="testuser", password="testpassword"
            )
            self.user.save()  # Ensure the user is saved

            self.document = Document(
                title="Test Document", description="Test Description", creator=self.user
            )
            self.document.save()

            self.annotation = Annotation(
                document=self.document, creator=self.user, raw_text="Test annotation"
            )
            self.annotation.save()

            self.fieldset = Fieldset(
                name="Test Fieldset",
                description="Test Fieldset Description",
                creator=self.user,
            )
            self.fieldset.save()

            self.column = Column(
                fieldset=self.fieldset,
                name="Test Column",
                query="Test Query",
                output_type="str",
                creator=self.user,
            )
            self.column.save()

            self.extract = Extract(
                name="Test Extract", fieldset=self.fieldset, creator=self.user
            )
            self.extract.save()

            self.datacell = Datacell(
                document=self.document,
                creator=self.user,
                extract=self.extract,
                data_definition="Test data",
                column=self.column,
            )
            self.datacell.save()

            # Create a corpus for the analysis
            self.corpus = Corpus.objects.create(
                title="Test Corpus",
                description="Test Corpus Description",
                creator=self.user,
            )

            # Create a GremlinEngine (assuming it's required for Analyzer)
            self.gremlin_engine = GremlinEngine.objects.create(
                url="http://test-gremlin-engine.com", creator=self.user
            )

            # Create an Analyzer
            self.analyzer = Analyzer.objects.create(
                description="Test Analyzer",
                host_gremlin=self.gremlin_engine,
                creator=self.user,
                manifest={},  # Add a default empty manifest or appropriate test data
            )

            self.analysis = Analysis.objects.create(
                creator=self.user,
                analyzed_corpus=self.corpus,
                analyzer=self.analyzer,  # Associate the Analysis with the Analyzer
            )
            self.analysis.save()

            self.row = DocumentAnalysisRow(
                document=self.document,
                creator=self.user,
                extract=self.extract,  # Set extract, leaving analysis as None
            )
            self.row.save()

    def test_document_analysis_row_creation(self):
        self.assertIsNotNone(self.row)
        self.assertEqual(self.row.document, self.document)
        self.assertEqual(self.row.creator, self.user)
        self.assertEqual(self.row.extract, self.extract)
        self.assertIsNone(self.row.analysis)

    def test_document_analysis_row_relationships(self):
        self.row.annotations.add(self.annotation)
        self.row.data.add(self.datacell)

        self.assertEqual(self.row.annotations.count(), 1)
        self.assertEqual(self.row.data.count(), 1)
        self.assertIn(self.annotation, self.row.annotations.all())
        self.assertIn(self.datacell, self.row.data.all())

    def test_document_analysis_row_constraints(self):
        # Test that we can't create a row with both extract and analysis set
        with self.assertRaises(ValidationError):
            invalid_row = DocumentAnalysisRow(
                document=self.document,
                creator=self.user,
                extract=self.extract,
                analysis=self.analysis,
            )
            invalid_row.full_clean()

        # Test that we can't create a row with neither extract nor analysis set
        with self.assertRaises(ValidationError):
            invalid_row = DocumentAnalysisRow(document=self.document, creator=self.user)
            invalid_row.full_clean()

        # Test uniqueness constraint
        with self.assertRaises(ValidationError):
            duplicate_row = DocumentAnalysisRow(
                document=self.document, creator=self.user, extract=self.extract
            )
            duplicate_row.full_clean()

    def test_document_analysis_row_permissions(self):
        set_permissions_for_obj_to_user(
            self.user, self.row, [PermissionTypes.READ, PermissionTypes.UPDATE]
        )

        self.assertTrue(
            user_has_permission_for_obj(self.user, self.row, PermissionTypes.READ)
        )
        self.assertTrue(
            user_has_permission_for_obj(self.user, self.row, PermissionTypes.UPDATE)
        )
        self.assertTrue(
            user_has_permission_for_obj(self.user, self.row, PermissionTypes.DELETE)
        )

    def test_document_analysis_row_crud_permissions(self):
        logging.info("XOXOX - START")
        logging.info(
            get_users_permissions_for_obj(
                self.user, self.row, include_group_permissions=True
            )
        )

        set_permissions_for_obj_to_user(
            self.user,
            self.row,
            [
                PermissionTypes.CREATE,
                PermissionTypes.READ,
                PermissionTypes.UPDATE,
                PermissionTypes.DELETE,
            ],
        )

        self.assertTrue(
            user_has_permission_for_obj(
                self.user,
                self.row,
                PermissionTypes.CREATE,
                include_group_permissions=True,
            )
        )  # noqa
        self.assertTrue(
            user_has_permission_for_obj(self.user, self.row, PermissionTypes.READ)
        )
        self.assertTrue(
            user_has_permission_for_obj(self.user, self.row, PermissionTypes.UPDATE)
        )
        self.assertTrue(
            user_has_permission_for_obj(self.user, self.row, PermissionTypes.DELETE)
        )

    def test_document_analysis_row_all_permissions(self):
        set_permissions_for_obj_to_user(self.user, self.row, [PermissionTypes.ALL])

        self.assertTrue(
            user_has_permission_for_obj(self.user, self.row, PermissionTypes.CREATE)
        )
        self.assertTrue(
            user_has_permission_for_obj(self.user, self.row, PermissionTypes.READ)
        )
        self.assertTrue(
            user_has_permission_for_obj(self.user, self.row, PermissionTypes.UPDATE)
        )
        self.assertTrue(
            user_has_permission_for_obj(self.user, self.row, PermissionTypes.DELETE)
        )
        self.assertTrue(
            user_has_permission_for_obj(self.user, self.row, PermissionTypes.PUBLISH)
        )
        self.assertTrue(
            user_has_permission_for_obj(self.user, self.row, PermissionTypes.PERMISSION)
        )
