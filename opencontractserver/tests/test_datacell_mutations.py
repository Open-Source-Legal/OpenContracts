from django.contrib.auth import get_user_model
from django.test import TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.extracts.models import Column, Datacell, Extract, Fieldset

User = get_user_model()


class TestContext:
    def __init__(self, user):
        self.user = user


class DatacellMutationTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpassword"
        )
        self.graphene_client = Client(schema, context_value=TestContext(self.user))

        self.corpus = Corpus.objects.create(title="TestCorpus", creator=self.user)
        self.document = Document.objects.create(
            title="TestDocument",
            description="Test Description",
            pdf_file="path/to/file.pdf",
            creator=self.user,
        )
        self.fieldset = Fieldset.objects.create(
            name="TestFieldset",
            description="Test description",
            creator=self.user,
        )
        self.extract = Extract.objects.create(
            name="TestExtract",
            corpus=self.corpus,
            creator=self.user,
            fieldset=self.fieldset,
        )
        self.column = Column.objects.create(
            fieldset=self.extract.fieldset,
            query="TestQuery",
            output_type="str",
            creator=self.user,
        )
        self.datacell = Datacell.objects.create(
            extract=self.extract,
            column=self.column,
            document=self.document,
            data_definition="Test Data Definition",
            creator=self.user,
        )

    def test_approve_datacell_mutation(self):
        mutation = """
            mutation {{
                approveDatacell(datacellId: "{}") {{
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
        """.format(to_global_id("DatacellType", self.datacell.id))

        result = self.graphene_client.execute(mutation)
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["approveDatacell"]["ok"])

        approved_datacell = Datacell.objects.get(id=self.datacell.id)
        self.assertEqual(approved_datacell.approved_by, self.user)

    def test_reject_datacell_mutation(self):
        mutation = """
            mutation {{
                rejectDatacell(datacellId: "{}") {{
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
        """.format(to_global_id("DatacellType", self.datacell.id))

        result = self.graphene_client.execute(mutation)
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["rejectDatacell"]["ok"])

        rejected_datacell = Datacell.objects.get(id=self.datacell.id)
        self.assertEqual(rejected_datacell.rejected_by, self.user)

    def test_edit_datacell_mutation(self):
        edited_data = {"key": "value"}
        mutation = """
            mutation {{
                editDatacell(datacellId: "{}", editedData: {{key: "value"}}) {{
                    ok
                    message
                    obj {{
                        id
                        correctedData
                    }}
                }}
            }}
        """.format(to_global_id("DatacellType", self.datacell.id))

        result = self.graphene_client.execute(mutation)
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["editDatacell"]["ok"])

        edited_datacell = Datacell.objects.get(id=self.datacell.id)
        self.assertEqual(edited_datacell.corrected_data, edited_data)

    def test_approve_datacell_not_found(self):
        """IDOR-safe: requesting an unknown datacell yields a generic
        ``Datacell not found.`` message instead of leaking ORM error text."""
        nonexistent_gid = to_global_id("DatacellType", 999_999)
        mutation = """
            mutation {{
                approveDatacell(datacellId: "{}") {{ ok message }}
            }}
        """.format(nonexistent_gid)
        result = self.graphene_client.execute(mutation)
        self.assertIsNone(result.get("errors"))
        data = result["data"]["approveDatacell"]
        self.assertFalse(data["ok"])
        self.assertEqual(data["message"], "Datacell not found.")

    def test_reject_datacell_not_found(self):
        nonexistent_gid = to_global_id("DatacellType", 999_999)
        mutation = """
            mutation {{
                rejectDatacell(datacellId: "{}") {{ ok message }}
            }}
        """.format(nonexistent_gid)
        result = self.graphene_client.execute(mutation)
        self.assertIsNone(result.get("errors"))
        data = result["data"]["rejectDatacell"]
        self.assertFalse(data["ok"])
        self.assertEqual(data["message"], "Datacell not found.")

    def test_edit_datacell_not_found(self):
        nonexistent_gid = to_global_id("DatacellType", 999_999)
        mutation = """
            mutation {{
                editDatacell(datacellId: "{}", editedData: {{key: "value"}}) {{
                    ok message
                }}
            }}
        """.format(nonexistent_gid)
        result = self.graphene_client.execute(mutation)
        self.assertIsNone(result.get("errors"))
        data = result["data"]["editDatacell"]
        self.assertFalse(data["ok"])
        self.assertEqual(data["message"], "Datacell not found.")

    def test_approve_datacell_owned_by_other_user_returns_not_found(self):
        """IDOR-safe: a different user requesting a datacell they don't own
        receives the same ``Datacell not found.`` message as for a missing id
        (the queryset filters by creator, so DoesNotExist is raised)."""
        other_user = User.objects.create_user(username="other", password="x")
        other_client = Client(schema, context_value=TestContext(other_user))
        mutation = """
            mutation {{
                approveDatacell(datacellId: "{}") {{ ok message }}
            }}
        """.format(to_global_id("DatacellType", self.datacell.id))
        result = other_client.execute(mutation)
        self.assertIsNone(result.get("errors"))
        data = result["data"]["approveDatacell"]
        self.assertFalse(data["ok"])
        self.assertEqual(data["message"], "Datacell not found.")
