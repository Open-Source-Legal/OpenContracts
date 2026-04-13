from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.extracts.models import Column, Datacell, Extract, Fieldset
from opencontractserver.tests.fixtures import SAMPLE_PDF_FILE_TWO_PATH

User = get_user_model()


class TestContext:
    def __init__(self, user):
        self.user = user


class ExtractsQueryTestCase(TestCase):
    def setUp(self):

        self.user = User.objects.create_user(
            username="testuser", password="testpassword"
        )
        self.client = Client(schema, context_value=TestContext(self.user))
        self.fieldset = Fieldset.objects.create(
            name="TestFieldset",
            description="Test description",
            creator=self.user,
        )
        self.column = Column.objects.create(
            creator=self.user,
            fieldset=self.fieldset,
            query="TestQuery",
            output_type="str",
        )
        self.corpus = Corpus.objects.create(title="TestCorpus", creator=self.user)
        self.extract = Extract.objects.create(
            corpus=self.corpus,
            name="TestExtract",
            fieldset=self.fieldset,
            creator=self.user,
        )

        pdf_file = ContentFile(
            SAMPLE_PDF_FILE_TWO_PATH.open("rb").read(), name="test.pdf"
        )

        # We're going to manually process three docs
        self.doc = Document.objects.create(
            creator=self.user,
            title="Rando Doc",
            description="RANDO DOC!",
            custom_meta={},
            pdf_file=pdf_file,
            backend_lock=True,
        )

        self.row = Datacell.objects.create(
            extract=self.extract,
            column=self.column,
            data={"data": "TestData"},
            data_definition="str",
            creator=self.user,
            document=self.doc,
        )

    def test_fieldset_query(self):
        query = """
            query {
                fieldset(id: "%s") {
                    id
                    name
                    description
                }
            }
        """ % to_global_id("FieldsetType", self.fieldset.id)

        result = self.client.execute(query)
        self.assertIsNone(result.get("errors"))
        self.assertEqual(
            result["data"]["fieldset"]["id"],
            to_global_id("FieldsetType", self.fieldset.id),
        )
        self.assertEqual(result["data"]["fieldset"]["name"], "TestFieldset")
        self.assertEqual(result["data"]["fieldset"]["description"], "Test description")

    def test_column_query(self):
        query = """
            query {
                column(id: "%s") {
                    id
                    query
                    outputType
                }
            }
        """ % to_global_id("ColumnType", self.column.id)

        result = self.client.execute(query)
        self.assertIsNone(result.get("errors"))
        self.assertEqual(
            result["data"]["column"]["id"], to_global_id("ColumnType", self.column.id)
        )
        self.assertEqual(result["data"]["column"]["query"], "TestQuery")
        self.assertEqual(result["data"]["column"]["outputType"], "str")

    def test_extract_query(self):
        query = """
            query {
                extract(id: "%s") {
                    id
                    name
                }
            }
        """ % to_global_id("ExtractType", self.extract.id)

        result = self.client.execute(query)
        self.assertIsNone(result.get("errors"))
        self.assertEqual(
            result["data"]["extract"]["id"],
            to_global_id("ExtractType", self.extract.id),
        )
        self.assertEqual(result["data"]["extract"]["name"], "TestExtract")

    def test_datacell_query(self):
        query = """
            query {
                datacell(id: "%s") {
                    id
                    data
                    dataDefinition
                }
            }
        """ % to_global_id("DatacellType", self.row.id)

        result = self.client.execute(query)
        self.assertIsNone(result.get("errors"))
        self.assertEqual(
            result["data"]["datacell"]["id"], to_global_id("DatacellType", self.row.id)
        )
        self.assertEqual(result["data"]["datacell"]["data"], {"data": "TestData"})
        self.assertEqual(result["data"]["datacell"]["dataDefinition"], "str")


class ExtractFullDatacellListFirstArgTestCase(TestCase):
    """Tests for the `first` argument on ExtractType.fullDatacellList.

    Verifies that:
    - A positive `first` caps the returned datacell count.
    - Zero or negative `first` returns all cells (no-cap path).
    - Omitting `first` returns all cells.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="firstarguser", password="testpassword"
        )
        self.client = Client(schema, context_value=TestContext(self.user))
        self.fieldset = Fieldset.objects.create(
            name="FirstArgFieldset",
            description="Fieldset for first-arg tests",
            creator=self.user,
        )
        self.column = Column.objects.create(
            creator=self.user,
            fieldset=self.fieldset,
            query="TestQuery",
            output_type="str",
        )
        self.corpus = Corpus.objects.create(title="FirstArgCorpus", creator=self.user)
        self.extract = Extract.objects.create(
            corpus=self.corpus,
            name="FirstArgExtract",
            fieldset=self.fieldset,
            creator=self.user,
        )

        pdf_file = ContentFile(
            SAMPLE_PDF_FILE_TWO_PATH.open("rb").read(), name="test.pdf"
        )

        # Create 3 documents with one datacell each
        self.docs = []
        self.cells = []
        for i in range(3):
            doc = Document.objects.create(
                creator=self.user,
                title=f"Doc {i}",
                description=f"Test doc {i}",
                custom_meta={},
                pdf_file=pdf_file,
                backend_lock=True,
            )
            self.docs.append(doc)
            cell = Datacell.objects.create(
                extract=self.extract,
                column=self.column,
                data={"value": f"data-{i}"},
                data_definition="str",
                creator=self.user,
                document=doc,
            )
            self.cells.append(cell)

    def _query_datacells(self, first_arg=None):
        """Helper to query fullDatacellList with optional first argument."""
        extract_gid = to_global_id("ExtractType", self.extract.id)
        if first_arg is not None:
            query = """
                query {
                    extract(id: "%s") {
                        fullDatacellList(first: %d) {
                            id
                            data
                        }
                    }
                }
            """ % (extract_gid, first_arg)
        else:
            query = """
                query {
                    extract(id: "%s") {
                        fullDatacellList {
                            id
                            data
                        }
                    }
                }
            """ % extract_gid
        return self.client.execute(query)

    def test_first_positive_caps_results(self):
        """A positive `first` should limit the returned datacell count."""
        result = self._query_datacells(first_arg=2)
        self.assertIsNone(result.get("errors"))
        datacells = result["data"]["extract"]["fullDatacellList"]
        self.assertEqual(len(datacells), 2)

    def test_first_zero_returns_all(self):
        """Zero `first` is treated as 'no cap' and returns all cells."""
        result = self._query_datacells(first_arg=0)
        self.assertIsNone(result.get("errors"))
        datacells = result["data"]["extract"]["fullDatacellList"]
        self.assertEqual(len(datacells), 3)

    def test_first_negative_returns_all(self):
        """Negative `first` is treated as 'no cap' and returns all cells."""
        result = self._query_datacells(first_arg=-1)
        self.assertIsNone(result.get("errors"))
        datacells = result["data"]["extract"]["fullDatacellList"]
        self.assertEqual(len(datacells), 3)

    def test_first_omitted_returns_all(self):
        """Omitting `first` should return all cells."""
        result = self._query_datacells(first_arg=None)
        self.assertIsNone(result.get("errors"))
        datacells = result["data"]["extract"]["fullDatacellList"]
        self.assertEqual(len(datacells), 3)

    def test_first_larger_than_count_returns_all(self):
        """A `first` larger than the total count returns all cells."""
        result = self._query_datacells(first_arg=100)
        self.assertIsNone(result.get("errors"))
        datacells = result["data"]["extract"]["fullDatacellList"]
        self.assertEqual(len(datacells), 3)

    def test_first_capped_at_server_maximum(self):
        """Server-side cap (MAX_DATACELL_FIRST) prevents unbounded payloads."""
        from opencontractserver.constants.annotations import MAX_DATACELL_FIRST

        # Requesting more than the server cap should silently clamp
        result = self._query_datacells(first_arg=MAX_DATACELL_FIRST + 500)
        self.assertIsNone(result.get("errors"))
        # Only 3 cells exist, so the cap doesn't visibly reduce the count,
        # but the resolver path through `min(first, MAX_DATACELL_FIRST)` is
        # exercised without error.
        datacells = result["data"]["extract"]["fullDatacellList"]
        self.assertEqual(len(datacells), 3)
