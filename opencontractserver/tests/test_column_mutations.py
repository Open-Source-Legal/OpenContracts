import logging

from django.contrib.auth import get_user_model
from django.test import TestCase
from graphene.test import Client
from graphql_relay import to_global_id
from graphql_relay.node.node import from_global_id

from config.graphql.schema import schema
from opencontractserver.extracts.models import Column, Fieldset
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()
logger = logging.getLogger(__name__)


class TestContext:
    def __init__(self, user):
        self.user = user


class ColumnMutationTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpassword"
        )
        self.graphene_client = Client(schema, context_value=TestContext(self.user))

        self.fieldset = Fieldset.objects.create(
            name="TestFieldset",
            description="Test description",
            creator=self.user,
        )
        self.column = Column.objects.create(
            fieldset=self.fieldset,
            query="OriginalQuery",
            match_text="OriginalMatchText",
            output_type="str",
            limit_to_label="OriginalLimit",
            instructions="OriginalInstructions",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, self.column, [PermissionTypes.CRUD])

    def test_update_column_mutation(self):
        mutation = """
            mutation {{
                updateColumn(
                    id: "{}",
                    query: "UpdatedQuery",
                    matchText: "UpdatedMatchText",
                    outputType: "int",
                    limitToLabel: "UpdatedLimit",
                    instructions: "UpdatedInstructions"
                ) {{
                    ok
                    objId
                    message
                }}
            }}
        """.format(
            to_global_id("ColumnType", self.column.id),
        )
        logger.info(f"Test mutation: {mutation}")

        result = self.graphene_client.execute(mutation)
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["updateColumn"]["ok"])

        updated_column = Column.objects.get(id=self.column.id)
        self.assertEqual(updated_column.query, "UpdatedQuery")
        self.assertEqual(updated_column.match_text, "UpdatedMatchText")
        self.assertEqual(updated_column.output_type, "int")
        self.assertEqual(updated_column.limit_to_label, "UpdatedLimit")
        self.assertEqual(updated_column.instructions, "UpdatedInstructions")

    def test_delete_column_mutation(self):
        mutation = """
            mutation {{
                deleteColumn(id: "{}") {{
                    ok
                }}
            }}
        """.format(to_global_id("ColumnType", self.column.id))

        result = self.graphene_client.execute(mutation)
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["deleteColumn"]["ok"])

        with self.assertRaises(Column.DoesNotExist):
            Column.objects.get(id=self.column.id)

    def test_create_column_mutation(self):
        mutation = """
            mutation {{
                createColumn(
                    name: "Test Col",
                    fieldsetId: "{}",
                    query: "NewQuery",
                    outputType: "int",
                    matchText: "NewMatchText",
                    limitToLabel: "NewLimit",
                    instructions: "NewInstructions"
                ) {{
                    ok
                    obj {{
                        id
                        query
                        matchText
                        outputType
                        limitToLabel
                        instructions
                    }}
                }}
            }}
        """.format(
            to_global_id("FieldsetType", self.fieldset.id),
        )

        result = self.graphene_client.execute(mutation)
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["createColumn"]["ok"])

        created_column_id = result["data"]["createColumn"]["obj"]["id"]
        created_column = Column.objects.get(id=from_global_id(created_column_id)[1])

        self.assertEqual(created_column.query, "NewQuery")
        self.assertEqual(created_column.match_text, "NewMatchText")
        self.assertEqual(created_column.output_type, "int")
        self.assertEqual(created_column.limit_to_label, "NewLimit")
        self.assertEqual(created_column.instructions, "NewInstructions")
