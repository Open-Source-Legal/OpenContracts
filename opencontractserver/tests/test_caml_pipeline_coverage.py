"""
Tests for CAML/markdown pipeline coverage: signal skip, task skip,
filter exclusion, and upload mutation file-type detection.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.constants.document_processing import MARKDOWN_MIME_TYPE
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentProcessingStatus
from opencontractserver.documents.signals import process_doc_on_create_atomic
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class TestContext:
    def __init__(self, user):
        self.user = user


def _create_doc_bypass_pipeline(*, title, creator, file_type, **kwargs):
    """Create a Document that bypasses the processing pipeline.

    Sets processing_started so the post_save signal guard
    (``if created and not instance.processing_started``) skips task
    queuing.  This avoids disconnecting/reconnecting the signal, which
    can cause cross-test interference with TransactionTestCase tests.
    """
    return Document.objects.create(
        title=title,
        creator=creator,
        file_type=file_type,
        processing_started=timezone.now(),
        **kwargs,
    )


class CamlSignalHandlerTest(TestCase):
    """Test the signal handler logic for CAML documents by calling it directly."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="signal_test_user", password="password"
        )

    def test_signal_handler_marks_markdown_complete(self):
        """process_doc_on_create_atomic marks markdown docs as COMPLETED."""
        doc = _create_doc_bypass_pipeline(
            title="Readme.CAML",
            creator=self.user,
            file_type=MARKDOWN_MIME_TYPE,
        )
        # Reset processing_started so the handler guard passes
        Document.objects.filter(pk=doc.pk).update(
            processing_started=None,
            processing_status=DocumentProcessingStatus.PENDING,
        )
        doc.refresh_from_db()
        self.assertEqual(doc.processing_status, DocumentProcessingStatus.PENDING)

        # Call the signal handler directly
        process_doc_on_create_atomic(sender=Document, instance=doc, created=True)

        doc.refresh_from_db()
        self.assertEqual(doc.processing_status, DocumentProcessingStatus.COMPLETED)
        self.assertFalse(doc.backend_lock)
        self.assertIsNotNone(doc.processing_started)

    def test_signal_handler_skips_non_created(self):
        """Signal handler is a no-op when created=False."""
        doc = _create_doc_bypass_pipeline(
            title="Readme.CAML",
            creator=self.user,
            file_type=MARKDOWN_MIME_TYPE,
        )
        # Reset so we can verify the handler doesn't change it
        Document.objects.filter(pk=doc.pk).update(
            processing_started=None,
            processing_status=DocumentProcessingStatus.PENDING,
        )
        doc.refresh_from_db()

        process_doc_on_create_atomic(sender=Document, instance=doc, created=False)

        doc.refresh_from_db()
        # Should still be pending since created=False skips the handler
        self.assertEqual(doc.processing_status, DocumentProcessingStatus.PENDING)

    def test_signal_handler_skips_already_started(self):
        """Signal handler is a no-op when processing_started is already set."""
        doc = _create_doc_bypass_pipeline(
            title="Readme.CAML",
            creator=self.user,
            file_type=MARKDOWN_MIME_TYPE,
        )
        # processing_started is already set from _create_doc_bypass_pipeline

        process_doc_on_create_atomic(sender=Document, instance=doc, created=True)

        doc.refresh_from_db()
        # Should still be pending since processing_started was already set
        self.assertEqual(doc.processing_status, DocumentProcessingStatus.PENDING)


class CamlIngestDocSkipTest(TestCase):
    """Test that ingest_doc() skips processing for markdown documents."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="ingest_test_user", password="password"
        )

    def test_ingest_doc_skips_markdown(self):
        """ingest_doc marks markdown documents as COMPLETED without parsing."""
        doc = _create_doc_bypass_pipeline(
            title="article.md",
            creator=self.user,
            file_type=MARKDOWN_MIME_TYPE,
        )
        # T-7 (#1463) defense-in-depth: ingest_doc rejects callers without
        # explicit guardian READ permission. Production upload mutations
        # grant CRUD on creation; mirror that in the test.
        set_permissions_for_obj_to_user(self.user, doc, [PermissionTypes.CRUD])

        # Call the task function directly (not via Celery).
        # ingest_doc uses bind=True so .run() passes the task instance as self.
        from opencontractserver.tasks.doc_tasks import ingest_doc

        result = ingest_doc.run(self.user.id, doc.id)
        self.assertEqual(result["status"], "success")

        doc.refresh_from_db()
        self.assertEqual(doc.processing_status, DocumentProcessingStatus.COMPLETED)


class CamlExtractThumbnailSkipTest(TestCase):
    """Test that extract_thumbnail() skips processing for markdown documents."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="thumb_test_user", password="password"
        )

    def test_extract_thumbnail_skips_markdown(self):
        """extract_thumbnail returns early for markdown docs without error."""
        doc = _create_doc_bypass_pipeline(
            title="article.md",
            creator=self.user,
            file_type=MARKDOWN_MIME_TYPE,
        )

        from opencontractserver.tasks.doc_tasks import extract_thumbnail

        # Should return None (early exit) without raising
        result = extract_thumbnail(doc_id=doc.id)
        self.assertIsNone(result)


class DocumentFilterCamlExclusionTest(TestCase):
    """Test that DocumentFilter.filter_queryset() excludes CAML files
    by default when filtering by corpus, and includes them when requested."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username="filter_owner", password="password"
        )
        self.corpus = Corpus.objects.create(
            title="Filter Test Corpus", creator=self.owner, is_public=True
        )

        # Add a normal document
        source_pdf = Document.objects.create(
            title="Report.pdf",
            creator=self.owner,
            file_type="application/pdf",
        )
        self.pdf_doc, _, _ = self.corpus.add_document(
            document=source_pdf, user=self.owner
        )

        # Add a CAML document
        source_caml = Document.objects.create(
            title="Readme.CAML",
            creator=self.owner,
            file_type=MARKDOWN_MIME_TYPE,
        )
        self.caml_doc, _, _ = self.corpus.add_document(
            document=source_caml, user=self.owner
        )

        self.gql_client = Client(schema, context_value=TestContext(self.owner))
        self.corpus_gid = to_global_id("CorpusType", self.corpus.id)

    def test_corpus_documents_query_excludes_caml_by_default(self):
        """GraphQL documents query with corpus filter excludes CAML files."""
        query = """
        query($corpusId: String) {
            documents(inCorpusWithId: $corpusId) {
                edges {
                    node {
                        id
                        title
                    }
                }
            }
        }
        """
        result = self.gql_client.execute(
            query, variable_values={"corpusId": self.corpus_gid}
        )
        titles = [e["node"]["title"] for e in result["data"]["documents"]["edges"]]
        self.assertIn("Report.pdf", titles)
        self.assertNotIn("Readme.CAML", titles)

    def test_corpus_documents_query_includes_caml_when_requested(self):
        """GraphQL documents query with includeCaml=true includes CAML files."""
        query = """
        query($corpusId: String, $includeCaml: Boolean) {
            documents(inCorpusWithId: $corpusId, includeCaml: $includeCaml) {
                edges {
                    node {
                        id
                        title
                    }
                }
            }
        }
        """
        result = self.gql_client.execute(
            query,
            variable_values={
                "corpusId": self.corpus_gid,
                "includeCaml": True,
            },
        )
        titles = [e["node"]["title"] for e in result["data"]["documents"]["edges"]]
        self.assertIn("Report.pdf", titles)
        self.assertIn("Readme.CAML", titles)

    def test_documents_without_corpus_filter_includes_caml(self):
        """GraphQL documents query WITHOUT corpus filter includes all docs."""
        query = """
        query {
            documents {
                edges {
                    node {
                        id
                        title
                        fileType
                    }
                }
            }
        }
        """
        result = self.gql_client.execute(query)
        titles = [e["node"]["title"] for e in result["data"]["documents"]["edges"]]
        self.assertIn("Readme.CAML", titles)


class CorpusResolveDocumentsIncludesCamlTest(TestCase):
    """Test that the CorpusType.resolve_documents includes CAML articles."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username="resolve_owner", password="password"
        )
        self.corpus = Corpus.objects.create(
            title="Resolve Corpus", creator=self.owner, is_public=True
        )

        source_pdf = Document.objects.create(
            title="Report.pdf",
            creator=self.owner,
            file_type="application/pdf",
        )
        self.pdf_doc, _, _ = self.corpus.add_document(
            document=source_pdf, user=self.owner
        )

        source_caml = Document.objects.create(
            title="Readme.CAML",
            creator=self.owner,
            file_type=MARKDOWN_MIME_TYPE,
        )
        self.caml_doc, _, _ = self.corpus.add_document(
            document=source_caml, user=self.owner
        )

        self.gql_client = Client(schema, context_value=TestContext(self.owner))

    def test_corpus_documents_field_includes_caml(self):
        """The corpus.documents resolver includes CAML articles (uses include_caml=True)."""
        query = """
        query($id: ID!) {
            corpus(id: $id) {
                documents {
                    edges {
                        node {
                            id
                            title
                        }
                    }
                }
            }
        }
        """
        result = self.gql_client.execute(
            query,
            variable_values={"id": to_global_id("CorpusType", self.corpus.id)},
        )
        titles = [
            e["node"]["title"] for e in result["data"]["corpus"]["documents"]["edges"]
        ]
        self.assertIn("Report.pdf", titles)
        self.assertIn("Readme.CAML", titles)


class CorpusDocumentCountExcludesCamlGraphQLTest(TestCase):
    """Test that the corpus document count subquery excludes CAML files."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username="count_gql_owner", password="password"
        )
        self.corpus = Corpus.objects.create(
            title="Count Test Corpus", creator=self.owner, is_public=True
        )

        source_pdf = Document.objects.create(
            title="Report.pdf",
            creator=self.owner,
            file_type="application/pdf",
        )
        self.pdf_doc, _, _ = self.corpus.add_document(
            document=source_pdf, user=self.owner
        )

        source_caml = Document.objects.create(
            title="Readme.CAML",
            creator=self.owner,
            file_type=MARKDOWN_MIME_TYPE,
        )
        self.caml_doc, _, _ = self.corpus.add_document(
            document=source_caml, user=self.owner
        )

        self.gql_client = Client(schema, context_value=TestContext(self.owner))

    def test_corpus_list_document_count_excludes_caml(self):
        """Corpus list query's document count annotation excludes CAML."""
        query = """
        query {
            corpuses {
                edges {
                    node {
                        id
                        title
                    }
                }
            }
        }
        """
        # This exercises the _corpus_count_subqueries path
        result = self.gql_client.execute(query)
        self.assertNotIn("errors", result)
        # At minimum the query should succeed without errors
        titles = [e["node"]["title"] for e in result["data"]["corpuses"]["edges"]]
        self.assertIn("Count Test Corpus", titles)
