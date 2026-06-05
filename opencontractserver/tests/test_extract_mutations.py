from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.extracts.models import Column, Datacell, Extract, Fieldset
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class TestContext:
    def __init__(self, user):
        self.user = user


class ExtractsMutationTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpassword"
        )
        self.graphene_client = Client(schema, context_value=TestContext(self.user))

        self.fieldset = Fieldset.objects.create(
            name="TestFieldset", description="Test description", creator=self.user
        )
        self.extract = Extract.objects.create(
            name="TestExtract",
            fieldset=self.fieldset,
            creator=self.user,
        )
        self.corpus = Corpus.objects.create(title="TestCorpus", creator=self.user)
        self.document1 = Document.objects.create(
            title="TestDocument1",
            description="Test Description 1",
            pdf_file="path/to/file1.pdf",
            creator=self.user,
        )
        self.document2 = Document.objects.create(
            title="TestDocument2",
            description="Test Description 2",
            pdf_file="path/to/file2.pdf",
            creator=self.user,
        )

    def test_create_fieldset_mutation(self):
        mutation = """
            mutation {
                createFieldset(name: "TestFieldset", description: "Test description") {
                    ok
                    obj {
                        id
                        name
                        description
                    }
                }
            }
        """

        result = self.graphene_client.execute(mutation)
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["createFieldset"]["ok"])
        self.assertIsNotNone(result["data"]["createFieldset"]["obj"]["id"])
        self.assertEqual(
            result["data"]["createFieldset"]["obj"]["name"], "TestFieldset"
        )
        self.assertEqual(
            result["data"]["createFieldset"]["obj"]["description"],
            "Test description",
        )

    def test_create_column_mutation(self):
        fieldset = Fieldset.objects.create(
            name="TestFieldset",
            description="Test description",
            creator=self.user,
        )

        mutation = """
            mutation {{
                createColumn(
                    name: "BIAD"
                    fieldsetId: "{}",
                    query: "TestQuery",
                    outputType: "str"
                ) {{
                    ok
                    obj {{
                        id
                        query
                        outputType
                    }}
                }}
            }}
        """.format(
            to_global_id("FieldsetType", fieldset.id),
        )

        result = self.graphene_client.execute(mutation)
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["createColumn"]["ok"])
        self.assertIsNotNone(result["data"]["createColumn"]["obj"]["id"])
        self.assertEqual(result["data"]["createColumn"]["obj"]["query"], "TestQuery")
        self.assertEqual(result["data"]["createColumn"]["obj"]["outputType"], "str")

    def test_start_extract_mutation(self):
        mutation = """
            mutation {{
                startExtract(
                    extractId: "{}",
                ) {{
                    ok
                    message
                }}
            }}
        """.format(to_global_id("ExtractType", self.extract.id))

        with patch("config.graphql.extract_mutations.run_extract") as mock_task:
            # Setup the mock to handle .s().apply_async() chain
            from unittest.mock import MagicMock

            mock_signature = MagicMock()
            mock_task.s.return_value = mock_signature
            mock_signature.apply_async = MagicMock()

            # Also need to handle transaction.on_commit in TestCase
            with patch("django.db.transaction.on_commit") as mock_on_commit:
                # Execute on_commit callbacks immediately in tests
                mock_on_commit.side_effect = lambda f: f()

                result = self.graphene_client.execute(mutation)
                self.assertIsNone(result.get("errors"))
                self.assertTrue(result["data"]["startExtract"]["ok"])
                self.assertEqual("STARTED!", result["data"]["startExtract"]["message"])

                # Verify the task was called with correct arguments
                # Note: from_global_id returns a string, not an int
                mock_task.s.assert_called_once_with(str(self.extract.id), self.user.id)

    def test_add_documents_to_extract_mutation(self):
        mutation = """
            mutation {{
                addDocsToExtract(
                    extractId: "{}",
                    documentIds: ["{}", "{}"]
                ) {{
                    ok
                    message
                }}
            }}
        """.format(
            to_global_id("ExtractType", self.extract.id),
            to_global_id("DocumentType", self.document1.id),
            to_global_id("DocumentType", self.document2.id),
        )

        result = self.graphene_client.execute(mutation)
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["addDocsToExtract"]["ok"])

        self.extract.refresh_from_db()
        self.assertIn(self.document1, self.extract.documents.all())
        self.assertIn(self.document2, self.extract.documents.all())

    def test_remove_documents_from_extract_mutation(self):
        self.extract.documents.add(self.document1, self.document2)

        mutation = """
            mutation {{
                removeDocsFromExtract(
                    extractId: "{}",
                    documentIdsToRemove: ["{}", "{}"]
                ) {{
                    ok
                    message
                }}
            }}
        """.format(
            to_global_id("ExtractType", self.extract.id),
            to_global_id("DocumentType", self.document1.id),
            to_global_id("DocumentType", self.document2.id),
        )

        result = self.graphene_client.execute(mutation)
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["removeDocsFromExtract"]["ok"])

        self.extract.refresh_from_db()
        self.assertNotIn(self.document1, self.extract.documents.all())
        self.assertNotIn(self.document2, self.extract.documents.all())

    def test_approve_datacell_mutation(self):
        """Test approving a datacell."""
        datacell = Datacell.objects.create(
            extract=self.extract,
            column=Column.objects.create(
                name="TestColumn",
                fieldset=self.fieldset,
                output_type="str",
                creator=self.user,
            ),
            document=self.document1,
            data="Test Data",
            data_definition="Test Definition",
            creator=self.user,
        )

        mutation = """
            mutation {{
                approveDatacell(
                    datacellId: "{}"
                ) {{
                    ok
                    message
                    obj {{
                        id
                        approvedBy {{
                            username
                        }}
                    }}
                }}
            }}
        """.format(to_global_id("DatacellType", datacell.id))

        result = self.graphene_client.execute(mutation)
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["approveDatacell"]["ok"])

        datacell.refresh_from_db()
        self.assertEqual(datacell.approved_by, self.user)
        self.assertIsNone(datacell.rejected_by)

    def test_reject_datacell_mutation(self):
        """Test rejecting a datacell."""
        datacell = Datacell.objects.create(
            extract=self.extract,
            column=Column.objects.create(
                name="TestColumn",
                fieldset=self.fieldset,
                output_type="str",
                creator=self.user,
            ),
            document=self.document1,
            data="Test Data",
            data_definition="Test Definition",
            creator=self.user,
        )

        mutation = """
            mutation {{
                rejectDatacell(
                    datacellId: "{}"
                ) {{
                    ok
                    message
                    obj {{
                        id
                        rejectedBy {{
                            username
                        }}
                    }}
                }}
            }}
        """.format(to_global_id("DatacellType", datacell.id))

        result = self.graphene_client.execute(mutation)
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["rejectDatacell"]["ok"])

        datacell.refresh_from_db()
        self.assertEqual(datacell.rejected_by, self.user)
        self.assertIsNone(datacell.approved_by)

    def test_edit_datacell_mutation(self):
        """Test editing a datacell's corrected data."""
        datacell = Datacell.objects.create(
            extract=self.extract,
            column=Column.objects.create(
                name="TestColumn",
                fieldset=self.fieldset,
                output_type="str",
                creator=self.user,
            ),
            document=self.document1,
            data="Test Data",
            data_definition="Test Definition",
            creator=self.user,
        )

        new_data = {"corrected": "New Test Data"}
        mutation = """
            mutation {{
                editDatacell(
                    datacellId: "{}",
                    editedData: {{corrected: "New Test Data"}}
                ) {{
                    ok
                    message
                    obj {{
                        id
                        correctedData
                    }}
                }}
            }}
        """.format(to_global_id("DatacellType", datacell.id))

        result = self.graphene_client.execute(mutation)
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["editDatacell"]["ok"])

        datacell.refresh_from_db()
        self.assertEqual(datacell.corrected_data, new_data)

    def test_delete_extract_mutation(self):
        """Test deleting an extract."""
        # Set proper permissions for the user to delete the extract
        set_permissions_for_obj_to_user(
            self.user, self.extract, [PermissionTypes.DELETE]
        )

        mutation = """
            mutation {{
                deleteExtract(
                    id: "{}"
                ) {{
                    ok
                    message
                }}
            }}
        """.format(to_global_id("ExtractType", self.extract.id))

        result = self.graphene_client.execute(mutation)
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["deleteExtract"]["ok"])

        # Verify the extract was deleted
        with self.assertRaises(Extract.DoesNotExist):
            Extract.objects.get(id=self.extract.id)
