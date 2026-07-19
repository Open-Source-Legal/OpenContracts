import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase
from graphql_relay import to_global_id

from config.graphql.schema import schema
from config.graphql.testing import Client
from opencontractserver.corpuses.models import Corpus
from opencontractserver.tests import fixtures
from opencontractserver.utils.files import base_64_encode_bytes

User = get_user_model()

logger = logging.getLogger(__name__)


class TestContext:
    def __init__(self, user):
        self.user = user

    # My doc url field resolver is expecting this
    def build_absolute_uri(self, location=None):
        return "www.IAmNotARealURL.com"


class GraphQLUsageLimitTestCase(TestCase):
    """
    In a public deployment, I want to limit any given user's doc count to 10, as
    well as to be able to turn on or off analyzer-running permissions for same users.
    Running all this stuff requires processing power that costs $$$.
    """

    def setUp(self):

        # Setup a test user ######################################################################
        with transaction.atomic():
            self.user = User.objects.create_user(username="bob", password="12345678")

        # Set up a GraphQL client authorized for user
        self.graphene_client = Client(schema, context_value=TestContext(self.user))

        # Create a test corpus
        with transaction.atomic():
            corpus = Corpus.objects.create(
                title="Test Analysis Corpus", creator=self.user, backend_lock=False
            )
        self.global_corpus_id = to_global_id("CorpusType", corpus.id)

        # Grab a pdf and encode to base64
        self.base_64_encoded_pdf_contents = base_64_encode_bytes(
            fixtures.SAMPLE_PDF_FILE_ONE_PATH.open("rb").read()
        )

    def __test_doc_upload_limit(self):

        logger.info("Test analyzer list query...")

        UPLOAD_DOC_RESQUEST = """
            mutation (
                $base64FileString: String!
                $filename: String!
                $customMeta: GenericScalar!
                $description: String!
                $title: String!,
                $addToCorpusId: ID,
                $makePublic: Boolean!
              ) {
                uploadDocument(
                  base64FileString: $base64FileString
                  filename: $filename
                  customMeta: $customMeta
                  description: $description
                  title: $title,
                  addToCorpusId: $addToCorpusId,
                  makePublic: $makePublic
                ) {
                  document {
                    id
                    icon
                    pdfFile
                    title
                    description
                    backendLock
                    docAnnotations {
                      edges {
                        node {
                          id
                        }
                      }
                    }
                  }
                }
              }
            """

        # Upload 10 docs (should be fine)
        for doc_index in range(0, 11):
            doc_upload_response = self.graphene_client.execute(
                UPLOAD_DOC_RESQUEST,
                variables={
                    "base64FileString": self.base_64_encoded_pdf_contents,
                    "filename": "dumdum.pdf",
                    "customMeta": {},
                    "description": "Some stuff happening here",
                    "title": "Taking up space!",
                    "makePublic": True,
                },
            )
            logger.info(f"Doc upload response: {doc_upload_response}")

            if doc_index <= 9:
                self.assertIsNotNone(
                    doc_upload_response["data"]["uploadDocument"]["document"]["id"]
                )
            else:
                self.assertTrue(
                    f"Your usage is capped at {settings.USAGE_CAPPED_USER_DOC_CAP_COUNT} documents."
                    in doc_upload_response["errors"][0]["message"]
                )

    def test_endpoints(self):

        self.__test_doc_upload_limit()
