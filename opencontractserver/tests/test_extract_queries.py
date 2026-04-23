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
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

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

        # Associate the document with the extract and grant the user read
        # permission so that the permission-aware datacell resolver returns
        # results for non-superuser queries.
        self.extract.documents.add(self.doc)
        set_permissions_for_obj_to_user(self.user, self.doc, [PermissionTypes.READ])

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

    def test_full_datacell_list_limit_offset_and_count(self):
        """
        Covers the ExtractType.full_datacell_list pagination arguments (`limit`,
        `offset`) and the `datacell_count` field introduced to resolve #1204.

        Scenario: create 5 datacells on the extract, then verify that
        - `fullDatacellList` with no args still returns all visible datacells
        - `fullDatacellList(limit: 2)` returns exactly 2 cells
        - `fullDatacellList(limit: 2, offset: 2)` returns the next 2 cells
          (different from the first page)
        - `datacellCount` reports the full total regardless of limit/offset
        """
        extract_id = to_global_id("ExtractType", self.extract.id)

        # The setUp already created one datacell (self.row). Add four more so
        # we have 5 cells total on the same extract+column+document (which is
        # allowed because the uniqueness constraint only applies when
        # extract is NULL).
        for i in range(4):
            Datacell.objects.create(
                extract=self.extract,
                column=self.column,
                data={"data": f"TestData{i}"},
                data_definition="str",
                creator=self.user,
                document=self.doc,
            )

        unbounded_query = """
            query GetExtract($extractId: ID!) {
                extract(id: $extractId) {
                    id
                    datacellCount
                    fullDatacellList {
                        id
                    }
                }
            }
        """
        paginated_query = """
            query GetExtract($extractId: ID!, $limit: Int, $offset: Int) {
                extract(id: $extractId) {
                    datacellCount
                    fullDatacellList(limit: $limit, offset: $offset) {
                        id
                    }
                }
            }
        """

        # Unbounded fetch should return all 5 cells and datacellCount=5.
        result = self.client.execute(
            unbounded_query, variables={"extractId": extract_id}
        )
        self.assertIsNone(result.get("errors"))
        extract_data = result["data"]["extract"]
        self.assertEqual(extract_data["datacellCount"], 5)
        self.assertEqual(len(extract_data["fullDatacellList"]), 5)

        # First page: limit=2 → exactly 2 cells, datacellCount still 5.
        result_page1 = self.client.execute(
            paginated_query, variables={"extractId": extract_id, "limit": 2}
        )
        self.assertIsNone(result_page1.get("errors"))
        page1 = result_page1["data"]["extract"]
        self.assertEqual(page1["datacellCount"], 5)
        self.assertEqual(len(page1["fullDatacellList"]), 2)

        # Second page: limit=2, offset=2 → next 2 cells, disjoint from page 1.
        result_page2 = self.client.execute(
            paginated_query,
            variables={"extractId": extract_id, "limit": 2, "offset": 2},
        )
        self.assertIsNone(result_page2.get("errors"))
        page2 = result_page2["data"]["extract"]
        self.assertEqual(page2["datacellCount"], 5)
        self.assertEqual(len(page2["fullDatacellList"]), 2)

        page1_ids = {cell["id"] for cell in page1["fullDatacellList"]}
        page2_ids = {cell["id"] for cell in page2["fullDatacellList"]}
        self.assertTrue(
            page1_ids.isdisjoint(page2_ids),
            "Pagination produced overlapping pages — offset is not applied.",
        )

        # Final page: limit=2, offset=4 → only 1 cell remains.
        result_page3 = self.client.execute(
            paginated_query,
            variables={"extractId": extract_id, "limit": 2, "offset": 4},
        )
        self.assertIsNone(result_page3.get("errors"))
        self.assertEqual(
            len(result_page3["data"]["extract"]["fullDatacellList"]),
            1,
            "Expected 1 remaining cell after offset=4 on a 5-row list.",
        )

    def test_full_datacell_list_negative_offset_clamped_to_zero(self):
        """
        A negative ``offset`` must be clamped to 0 rather than crashing.
        Django does not support negative indexing on querysets; passing a
        negative offset should behave identically to offset=0.
        """
        extract_id = to_global_id("ExtractType", self.extract.id)

        query = """
            query GetExtract($extractId: ID!, $limit: Int, $offset: Int) {
                extract(id: $extractId) {
                    fullDatacellList(limit: $limit, offset: $offset) {
                        id
                    }
                }
            }
        """
        result = self.client.execute(
            query,
            variables={"extractId": extract_id, "limit": 10, "offset": -5},
        )
        self.assertIsNone(result.get("errors"))
        # With offset clamped to 0, the single existing datacell is returned.
        self.assertEqual(len(result["data"]["extract"]["fullDatacellList"]), 1)

    def test_full_datacell_list_limit_capped_at_server_max(self):
        """
        A ``limit`` exceeding ``MAX_FULL_DATACELL_LIST_LIMIT`` must be
        silently capped to the server maximum. Verifies both:
        1. No server error when an over-sized limit is passed.
        2. The returned count does not exceed ``MAX_FULL_DATACELL_LIST_LIMIT``
           even when more cells exist.
        """
        from opencontractserver.constants.extracts import MAX_FULL_DATACELL_LIST_LIMIT

        extract_id = to_global_id("ExtractType", self.extract.id)

        # Create enough datacells to exceed the cap. setUp already created 1,
        # so we need MAX_FULL_DATACELL_LIST_LIMIT more to have cap + 1 total.
        Datacell.objects.bulk_create(
            [
                Datacell(
                    extract=self.extract,
                    column=self.column,
                    data={"data": f"Cap{i}"},
                    data_definition="str",
                    creator=self.user,
                    document=self.doc,
                )
                for i in range(MAX_FULL_DATACELL_LIST_LIMIT)
            ]
        )
        total_cells = Datacell.objects.filter(extract=self.extract).count()
        self.assertGreater(total_cells, MAX_FULL_DATACELL_LIST_LIMIT)

        query = """
            query GetExtract($extractId: ID!, $limit: Int) {
                extract(id: $extractId) {
                    datacellCount
                    fullDatacellList(limit: $limit) {
                        id
                    }
                }
            }
        """
        huge_limit = MAX_FULL_DATACELL_LIST_LIMIT + 9999
        result = self.client.execute(
            query,
            variables={"extractId": extract_id, "limit": huge_limit},
        )
        self.assertIsNone(result.get("errors"))
        returned = len(result["data"]["extract"]["fullDatacellList"])
        self.assertEqual(
            returned,
            MAX_FULL_DATACELL_LIST_LIMIT,
            f"Expected server to cap at {MAX_FULL_DATACELL_LIST_LIMIT}, "
            f"got {returned} (total cells: {total_cells}).",
        )
        # datacellCount should reflect the true total, not the capped limit.
        self.assertEqual(result["data"]["extract"]["datacellCount"], total_cells)

    def test_full_datacell_list_offset_only_without_limit(self):
        """
        Providing ``offset`` without ``limit`` should skip the first N cells
        and return up to ``MAX_FULL_DATACELL_LIST_LIMIT`` of the remainder.
        This exercises the resolver's offset-only branch, which applies the
        server cap to prevent unbounded payloads when ``limit`` is omitted.

        Note: the test dataset (5 cells) is smaller than the cap so all
        remaining cells are returned; the cap is separately verified by
        ``test_full_datacell_list_limit_capped_at_server_max``.
        """
        extract_id = to_global_id("ExtractType", self.extract.id)

        # Create extra datacells so we have enough to see the offset effect.
        # setUp already created 1; add 4 more for 5 total.
        for i in range(4):
            Datacell.objects.create(
                extract=self.extract,
                column=self.column,
                data={"data": f"OffsetOnly{i}"},
                data_definition="str",
                creator=self.user,
                document=self.doc,
            )

        no_args_query = """
            query GetExtract($extractId: ID!) {
                extract(id: $extractId) {
                    fullDatacellList {
                        id
                    }
                }
            }
        """
        offset_query = """
            query GetExtract($extractId: ID!, $offset: Int) {
                extract(id: $extractId) {
                    fullDatacellList(offset: $offset) {
                        id
                    }
                }
            }
        """

        # No-args fetch: server-capped, but 5 < cap so all 5 are returned.
        result_all = self.client.execute(
            no_args_query, variables={"extractId": extract_id}
        )
        self.assertIsNone(result_all.get("errors"))
        all_ids = [c["id"] for c in result_all["data"]["extract"]["fullDatacellList"]]
        self.assertEqual(len(all_ids), 5)

        # Offset-only: skip the first 2 cells, no limit.
        result_offset = self.client.execute(
            offset_query, variables={"extractId": extract_id, "offset": 2}
        )
        self.assertIsNone(result_offset.get("errors"))
        offset_ids = [
            c["id"] for c in result_offset["data"]["extract"]["fullDatacellList"]
        ]
        self.assertEqual(
            len(offset_ids),
            3,
            "Expected 3 cells after skipping the first 2 of 5.",
        )
        # The returned ids should match the last 3 from the unbounded result.
        self.assertEqual(offset_ids, all_ids[2:])

    def test_full_datacell_list_limit_zero_returns_empty(self):
        """
        ``limit=0`` should return an empty list rather than crashing.
        The resolver clamps limit to ``max(0, ...)`` so zero is valid.
        """
        extract_id = to_global_id("ExtractType", self.extract.id)

        query = """
            query GetExtract($extractId: ID!, $limit: Int) {
                extract(id: $extractId) {
                    datacellCount
                    fullDatacellList(limit: $limit) {
                        id
                    }
                }
            }
        """
        result = self.client.execute(
            query, variables={"extractId": extract_id, "limit": 0}
        )
        self.assertIsNone(result.get("errors"))
        self.assertEqual(len(result["data"]["extract"]["fullDatacellList"]), 0)
        # datacellCount should still reflect the true total (1 from setUp).
        self.assertEqual(result["data"]["extract"]["datacellCount"], 1)

    def test_full_datacell_list_no_args_capped_at_server_max(self):
        """
        Calling ``fullDatacellList`` with no arguments must still cap the
        response at ``MAX_FULL_DATACELL_LIST_LIMIT``. Prevents authenticated
        API callers from bypassing the payload bound by omitting ``limit``.
        """
        from opencontractserver.constants.extracts import MAX_FULL_DATACELL_LIST_LIMIT

        extract_id = to_global_id("ExtractType", self.extract.id)

        # Create enough datacells so the total exceeds the cap by one.
        # setUp already created 1, so MAX_FULL_DATACELL_LIST_LIMIT extra
        # gives total = cap + 1.
        Datacell.objects.bulk_create(
            [
                Datacell(
                    extract=self.extract,
                    column=self.column,
                    data={"data": f"NoArgs{i}"},
                    data_definition="str",
                    creator=self.user,
                    document=self.doc,
                )
                for i in range(MAX_FULL_DATACELL_LIST_LIMIT)
            ]
        )
        total_cells = Datacell.objects.filter(extract=self.extract).count()
        self.assertGreater(total_cells, MAX_FULL_DATACELL_LIST_LIMIT)

        query = """
            query GetExtract($extractId: ID!) {
                extract(id: $extractId) {
                    datacellCount
                    fullDatacellList {
                        id
                    }
                }
            }
        """
        result = self.client.execute(query, variables={"extractId": extract_id})
        self.assertIsNone(result.get("errors"))
        returned = len(result["data"]["extract"]["fullDatacellList"])
        self.assertEqual(
            returned,
            MAX_FULL_DATACELL_LIST_LIMIT,
            f"Expected no-args path to cap at {MAX_FULL_DATACELL_LIST_LIMIT}, "
            f"got {returned} (total cells: {total_cells}).",
        )
        # datacellCount must reflect the true total, not the capped payload.
        self.assertEqual(result["data"]["extract"]["datacellCount"], total_cells)

    def test_full_datacell_list_negative_limit_clamped_to_zero(self):
        """
        A negative ``limit`` is clamped to 0 via ``max(0, ...)`` and returns
        an empty list, mirroring the ``limit=0`` behaviour.
        """
        extract_id = to_global_id("ExtractType", self.extract.id)

        query = """
            query GetExtract($extractId: ID!, $limit: Int) {
                extract(id: $extractId) {
                    fullDatacellList(limit: $limit) {
                        id
                    }
                }
            }
        """
        result = self.client.execute(
            query, variables={"extractId": extract_id, "limit": -1}
        )
        self.assertIsNone(result.get("errors"))
        self.assertEqual(len(result["data"]["extract"]["fullDatacellList"]), 0)
