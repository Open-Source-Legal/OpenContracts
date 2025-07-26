import base64
import json
import pathlib

from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from config.graphql.serializers import CorpusSerializer
from opencontractserver.annotations.models import LabelSet
from opencontractserver.corpuses.models import Corpus
from opencontractserver.tasks.utils import package_zip_into_base64
from opencontractserver.tests.fixtures import SAMPLE_PDF_FILE_TWO_PATH
from opencontractserver.types.dicts import OpenContractsAnnotatedDocumentImportType
from opencontractserver.types.enums import LabelType

User = get_user_model()


def _import_corpus_zip(user: User):

    fixtures_path = pathlib.Path(__file__).parent / "fixtures"
    client = Client(schema, context_value=TestContext(user))
    export_zip_base64_file_string = package_zip_into_base64(
        fixtures_path / "Test_Corpus_EXPORT.zip"
    )

    executed = client.execute(
        """
        mutation($base64FileString: String!) {
            importOpenContractsZip(base64FileString: $base64FileString) {
              ok
              message
              corpus {
                id
                icon
                description
                title
                backendLock
              }
            }
          }
        """,
        variable_values={"base64FileString": export_zip_base64_file_string},
    )
    return executed


class TestContext:
    def __init__(self, user):
        self.user = user


class GraphQLTestCase(TestCase):

    fixtures_path = pathlib.Path(__file__).parent / "fixtures"

    def setUp(self):

        with transaction.atomic():
            self.user = User.objects.create_user(
                username="bob",
                password="12345678",
                is_usage_capped=False,  # Otherwise no importing...
            )
            self.label_set = LabelSet.objects.create(
                title="Test Label Set",
                description="Test Label Set Description",
                creator=self.user,
            )
            self.corpus = Corpus.objects.create(
                title="Test Corpus",
                description="Test Corpus Description",
                label_set=self.label_set,
                creator=self.user,
            )

    def test_zip_upload(self):
        """
        Test that we can import an OpenContracts export via GraphQL and get back the expected
        responses from the endpoint.
        """
        executed = _import_corpus_zip(self.user)

        serializer = CorpusSerializer(
            data=executed["data"]["importOpenContractsZip"]["corpus"]
        )
        assert serializer.is_valid(raise_exception=True)
        assert executed["data"]["importOpenContractsZip"]["ok"] is True
        assert executed["data"]["importOpenContractsZip"]["message"] == "Started"

        # NOTE - in our current test environment, celery worker is not booted... so this never runs

    def test_import_document_to_corpus_mutation(self):

        client = Client(schema, context_value=TestContext(self.user))

        with open(SAMPLE_PDF_FILE_TWO_PATH, "rb") as pdf_file:
            pdf_data = pdf_file.read()
            pdf_base64 = base64.b64encode(pdf_data).decode("utf-8")

        # Create test labels
        text_labels = {
            "test_text_label": {
                "id": "0",
                "color": "red",
                "description": "Test Text Label",
                "icon": "tags",
                "text": "test_text_label",
                "label_type": LabelType.TOKEN_LABEL.value,
            }
        }
        doc_labels = {
            "test_doc_label": {
                "id": "1",
                "color": "yellow",
                "description": "Test Doc Label",
                "icon": "tags",
                "text": "test_doc_label",
                "label_type": LabelType.DOC_TYPE_LABEL.value,
            }
        }

        # Create test annotations
        annotations = [
            {
                "id": None,
                "annotationLabel": "test_text_label",
                "rawText": "Test Text",
                "page": 1,
                "annotation_json": {
                    "1": {
                        "bounds": {"top": 0, "bottom": 1, "left": 0, "right": 1},
                        "tokensJsons": [{"pageIndex": 1, "tokenIndex": 0}],
                        "rawText": "Test Text",
                    }
                },
                "structural": False,
                "annotation_type": LabelType.TOKEN_LABEL.value,
                "parent_id": None,
            }
        ]

        # Create test data for import_document_to_corpus
        document_import_data: OpenContractsAnnotatedDocumentImportType = {
            "doc_data": {
                "title": "Test Document",
                "content": "Dummy",
                "description": "Dummy",
                "doc_labels": ["test_doc_label"],
                "labelled_text": annotations,
                "page_count": 1,
                "pawls_file_content": [
                    {
                        "page": {"width": 100, "height": 100, "index": 1},
                        "tokens": [
                            {"x": 0, "y": 0, "width": 10, "height": 10, "text": "Test"}
                        ],
                    }
                ],
            },
            "pdf_name": "test_document",
            "pdf_base64": pdf_base64,
            "text_labels": text_labels,
            "doc_labels": doc_labels,

        }

        mutation = """
            mutation ImportAnnotatedDocToCorpus($targetCorpusId: String!, $documentImportData: String!) {
                importAnnotatedDocToCorpus(targetCorpusId: $targetCorpusId, documentImportData:
                $documentImportData) {
                    ok
                    message
                }
            }
        """

        variables = {
            "targetCorpusId": to_global_id("CorpusType", self.corpus.id),
            "documentImportData": json.dumps(document_import_data),
        }

        response = client.execute(mutation, variables=variables)

        assert response["data"]["importAnnotatedDocToCorpus"]["ok"] is True
        assert response["data"]["importAnnotatedDocToCorpus"]["message"] == "SUCCESS"
