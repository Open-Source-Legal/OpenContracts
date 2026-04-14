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

        with SAMPLE_PDF_FILE_TWO_PATH.open("rb") as f:
            pdf_file = ContentFile(f.read(), name="test.pdf")

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
        fieldset_gid = to_global_id("FieldsetType", self.fieldset.id)
        query = f"""
            query {{
                fieldset(id: "{fieldset_gid}") {{
                    id
                    name
                    description
                }}
            }}
        """

        result = self.client.execute(query)
        self.assertIsNone(result.get("errors"))
        self.assertEqual(
            result["data"]["fieldset"]["id"],
            to_global_id("FieldsetType", self.fieldset.id),
        )
        self.assertEqual(result["data"]["fieldset"]["name"], "TestFieldset")
        self.assertEqual(result["data"]["fieldset"]["description"], "Test description")

    def test_column_query(self):
        column_gid = to_global_id("ColumnType", self.column.id)
        query = f"""
            query {{
                column(id: "{column_gid}") {{
                    id
                    query
                    outputType
                }}
            }}
        """

        result = self.client.execute(query)
        self.assertIsNone(result.get("errors"))
        self.assertEqual(
            result["data"]["column"]["id"], to_global_id("ColumnType", self.column.id)
        )
        self.assertEqual(result["data"]["column"]["query"], "TestQuery")
        self.assertEqual(result["data"]["column"]["outputType"], "str")

    def test_extract_query(self):
        extract_gid = to_global_id("ExtractType", self.extract.id)
        query = f"""
            query {{
                extract(id: "{extract_gid}") {{
                    id
                    name
                }}
            }}
        """

        result = self.client.execute(query)
        self.assertIsNone(result.get("errors"))
        self.assertEqual(
            result["data"]["extract"]["id"],
            to_global_id("ExtractType", self.extract.id),
        )
        self.assertEqual(result["data"]["extract"]["name"], "TestExtract")

    def test_datacell_query(self):
        datacell_gid = to_global_id("DatacellType", self.row.id)
        query = f"""
            query {{
                datacell(id: "{datacell_gid}") {{
                    id
                    data
                    dataDefinition
                }}
            }}
        """

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
        self.user = User.objects.create_superuser(
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

        with SAMPLE_PDF_FILE_TWO_PATH.open("rb") as f:
            pdf_bytes = f.read()

        # Create 3 documents with one datacell each
        self.docs = []
        self.cells = []
        for i in range(3):
            # Create a fresh ContentFile per iteration — ContentFile wraps a
            # BytesIO whose pointer advances to the end after Django's storage
            # backend reads it during save(), so reusing a single instance
            # would produce empty files for the 2nd and 3rd documents.
            pdf_file = ContentFile(pdf_bytes, name="test.pdf")
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

        # Add documents to the extract's M2M so the resolver can find them
        self.extract.documents.add(*self.docs)

    def _query_datacells(self, first_arg=None):
        """Helper to query fullDatacellList with optional first argument."""
        extract_gid = to_global_id("ExtractType", self.extract.id)
        if first_arg is not None:
            query = f"""
                query {{
                    extract(id: "{extract_gid}") {{
                        fullDatacellList(first: {first_arg}) {{
                            id
                            data
                        }}
                    }}
                }}
            """
        else:
            query = f"""
                query {{
                    extract(id: "{extract_gid}") {{
                        fullDatacellList {{
                            id
                            data
                        }}
                    }}
                }}
            """
        return self.client.execute(query)

    def test_first_positive_caps_results(self):
        """A positive `first` should limit the returned datacell count."""
        result = self._query_datacells(first_arg=2)
        self.assertIsNone(result.get("errors"))
        datacells = result["data"]["extract"]["fullDatacellList"]
        self.assertEqual(len(datacells), 2)

    def test_first_zero_falls_back_to_default_cap(self):
        """Zero `first` falls back to the default MAX_DATACELL_FIRST cap.

        With only 3 fixture cells and a cap of 10 000, all cells are returned.
        """
        result = self._query_datacells(first_arg=0)
        self.assertIsNone(result.get("errors"))
        datacells = result["data"]["extract"]["fullDatacellList"]
        self.assertEqual(len(datacells), 3)

    def test_first_negative_falls_back_to_default_cap(self):
        """Negative `first` falls back to the default MAX_DATACELL_FIRST cap.

        With only 3 fixture cells and a cap of 10 000, all cells are returned.
        """
        result = self._query_datacells(first_arg=-1)
        self.assertIsNone(result.get("errors"))
        datacells = result["data"]["extract"]["fullDatacellList"]
        self.assertEqual(len(datacells), 3)

    def test_first_zero_still_capped_by_server_maximum(self):
        """first=0 must not bypass the server-side cap.

        Regression test: previously first<=0 skipped the MAX_DATACELL_FIRST
        guard entirely, allowing unbounded payloads.
        """
        from unittest.mock import patch

        with patch("config.graphql.extract_types.MAX_DATACELL_FIRST", 2):
            result = self._query_datacells(first_arg=0)
        self.assertIsNone(result.get("errors"))
        datacells = result["data"]["extract"]["fullDatacellList"]
        self.assertEqual(
            len(datacells),
            2,
            "first=0 should still be capped by MAX_DATACELL_FIRST",
        )

    def test_first_omitted_uses_default_cap(self):
        """Omitting `first` applies the default MAX_DATACELL_FIRST cap.

        With only 3 fixture cells and a cap of 10 000, all cells are returned.
        """
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
        """Server-side cap (MAX_DATACELL_FIRST) prevents unbounded payloads.

        We temporarily lower the cap to 2 (below the 3 fixture cells) so we
        can verify the resolver actually clamps the queryset.  Requesting a
        value above the cap should return at most `cap` results.
        """
        from unittest.mock import patch

        # Patch at the resolver's lookup site so the mock survives if the
        # import is ever hoisted to module level in extract_types.py.
        with patch("config.graphql.extract_types.MAX_DATACELL_FIRST", 2):
            # Ask for 500 — the patched cap of 2 should bind.
            result = self._query_datacells(first_arg=500)
        self.assertIsNone(result.get("errors"))
        datacells = result["data"]["extract"]["fullDatacellList"]
        self.assertEqual(
            len(datacells),
            2,
            "Server-side cap should limit results even when `first` is higher",
        )
