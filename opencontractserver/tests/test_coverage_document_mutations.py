"""Coverage-focused tests for ``config/graphql/document_mutations.py``.

Targets branches with zero test coverage identified by a full-suite coverage
run: extract-linking during upload, error-handling in the versioning/trash
mutations, ``DeleteMultipleDocuments``, ``RetryDocumentProcessing``,
``EmptyCorpus``, ``UploadDocumentsZip``/``UploadAnnotatedDocument`` error
paths, ``StartCorpusExport`` format branches, and ``DeleteExport``.

Deliberately does not duplicate scenarios already covered by
``test_document_mutations.py``, ``test_document_versioning_graphql.py``,
``test_permanent_deletion.py``, ``test_export_mutations.py``,
``test_permission_fixes.py``, or ``test_graphql_import_export_mutations.py``.

Two recurring failure-injection patterns are reused across many mutations
rather than re-derived per test:

* ``BaseService.get_or_none`` is imported once at module scope in
  ``document_mutations.py`` and called near the top of nearly every
  try/except block, so patching it with a ``side_effect`` is a single choke
  point for exercising each mutation's generic ``except Exception`` branch.
* ``DocumentLifecycleService`` methods are patched directly (rather than
  reproducing the exact DB state that would make the *service* return a
  partial-failure tuple) to isolate the *resolver's* branch selection from
  the service's own internal logic, which has its own test coverage.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from graphql_relay import to_global_id

from config.graphql.schema import schema
from config.graphql.testing import Client
from opencontractserver.annotations.models import LabelSet
from opencontractserver.corpuses.models import Corpus, CorpusFolder
from opencontractserver.corpuses.services import DocumentLifecycleService
from opencontractserver.documents.models import (
    Document,
    DocumentPath,
    DocumentProcessingStatus,
)
from opencontractserver.documents.versioning import delete_document, import_document
from opencontractserver.extracts.models import Extract, Fieldset
from opencontractserver.tests.base import BaseFixtureTestCase
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.users.models import UserExport
from opencontractserver.utils.files import base_64_encode_bytes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()

GET_OR_NONE_TARGET = "config.graphql.document_mutations.BaseService.get_or_none"

UPLOAD_DOCUMENT_MUTATION = """
    mutation UploadDocument(
        $file: String!,
        $filename: String!,
        $title: String!,
        $description: String!,
        $customMeta: GenericScalar!,
        $makePublic: Boolean!,
        $addToCorpusId: ID,
        $addToExtractId: ID
    ) {
        uploadDocument(
            base64FileString: $file,
            filename: $filename,
            title: $title,
            description: $description,
            customMeta: $customMeta,
            makePublic: $makePublic,
            addToCorpusId: $addToCorpusId,
            addToExtractId: $addToExtractId
        ) {
            ok
            message
            document { id title }
        }
    }
"""


class TestContext:
    def __init__(self, user):
        self.user = user


class UploadDocumentExtractLinkingTests(TestCase):
    """``UploadDocument`` with ``addToExtractId``/``addToCorpusId``
    (document_mutations.py:317-322, 356-360, 390-402)."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="extract_uploader", password="test", email="eu@test.com"
        )
        self.fieldset = Fieldset.objects.create(
            name="Coverage Fieldset", creator=self.user
        )
        self.graphene_client = Client(schema, context_value=TestContext(self.user))

    def _variables(self, **overrides):
        variables = {
            "file": base_64_encode_bytes(b"Plain text upload content."),
            "filename": "extract_link.txt",
            "title": "Extract Link Doc",
            "description": "Doc for extract-linking coverage",
            "makePublic": False,
            "customMeta": {},
            "addToCorpusId": None,
            "addToExtractId": None,
        }
        variables.update(overrides)
        return variables

    def test_rejects_both_corpus_and_extract_id(self):
        variables = self._variables(
            addToCorpusId=to_global_id("CorpusType", 1),
            addToExtractId=to_global_id("ExtractType", 1),
        )

        result = self.graphene_client.execute(
            UPLOAD_DOCUMENT_MUTATION, variables=variables
        )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["uploadDocument"]
        self.assertFalse(data["ok"])
        self.assertEqual(
            data["message"],
            "Cannot simultaneously add document to both corpus and extract",
        )

    def test_invalid_base64_file_string_returns_error(self):
        variables = self._variables(file="not-valid-base64-content!!!@@@###")

        result = self.graphene_client.execute(
            UPLOAD_DOCUMENT_MUTATION, variables=variables
        )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["uploadDocument"]
        self.assertFalse(data["ok"])
        self.assertTrue(data["message"].startswith("Error on upload:"))

    def test_links_uploaded_document_to_open_extract(self):
        extract = Extract.objects.create(
            name="Open Extract", fieldset=self.fieldset, creator=self.user
        )
        variables = self._variables(
            addToExtractId=to_global_id("ExtractType", extract.id)
        )

        with self.captureOnCommitCallbacks(execute=True):
            result = self.graphene_client.execute(
                UPLOAD_DOCUMENT_MUTATION, variables=variables
            )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["uploadDocument"]
        self.assertTrue(data["ok"], data.get("message"))
        self.assertEqual(data["message"], "Success")
        self.assertEqual(extract.documents.count(), 1)

    def test_extract_link_failure_is_reported_but_upload_still_succeeds(self):
        """A finished extract rejects new documents; the upload itself is
        unaffected (``ok`` stays ``True`` — only ``message`` reports the
        secondary failure), matching the mutation's documented contract."""
        finished_extract = Extract.objects.create(
            name="Finished Extract",
            fieldset=self.fieldset,
            creator=self.user,
            finished=timezone.now(),
        )
        variables = self._variables(
            addToExtractId=to_global_id("ExtractType", finished_extract.id)
        )

        with self.captureOnCommitCallbacks(execute=True):
            result = self.graphene_client.execute(
                UPLOAD_DOCUMENT_MUTATION, variables=variables
            )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["uploadDocument"]
        self.assertTrue(data["ok"])
        self.assertIn("Adding to extract failed due to error", data["message"])
        self.assertEqual(finished_extract.documents.count(), 0)

    def test_extract_link_to_missing_extract_is_reported(self):
        variables = self._variables(addToExtractId=to_global_id("ExtractType", 999_999))

        with self.captureOnCommitCallbacks(execute=True):
            result = self.graphene_client.execute(
                UPLOAD_DOCUMENT_MUTATION, variables=variables
            )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["uploadDocument"]
        self.assertTrue(data["ok"])
        self.assertIn("Adding to extract failed due to error", data["message"])

    def test_permission_error_from_import_service_propagates_as_graphql_error(self):
        """``import_document_for_user`` raising ``PermissionError`` is
        re-raised (not swallowed into ``ok=False``), surfacing as a top-level
        GraphQL error — the documented legacy usage-cap contract."""
        variables = self._variables()

        with patch(
            "config.graphql.document_mutations.import_document_for_user",
            side_effect=PermissionError("Usage cap exceeded"),
        ):
            result = self.graphene_client.execute(
                UPLOAD_DOCUMENT_MUTATION, variables=variables
            )

        self.assertIsNotNone(result.get("errors"))
        self.assertIn("Usage cap exceeded", result["errors"][0]["message"])


class UpdateDocumentSummaryEdgeCaseTests(TestCase):
    """``UpdateDocumentSummary`` not-found/permission/exception branches
    (document_mutations.py:568-579, 593-611, 641-648)."""

    SUMMARY_MUTATION = """
        mutation UpdateSummary($documentId: ID!, $corpusId: ID!, $newContent: String!) {
            updateDocumentSummary(
                documentId: $documentId, corpusId: $corpusId, newContent: $newContent
            ) {
                ok
                message
                version
            }
        }
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="summary_owner", password="test", email="so@test.com"
        )
        self.other_user = User.objects.create_user(
            username="summary_outsider", password="test", email="soo@test.com"
        )
        self.corpus = Corpus.objects.create(
            title="Summary Corpus", creator=self.user, is_public=True
        )
        self.document = Document.objects.create(
            creator=self.user,
            title="Summary Doc",
            description="Doc for summary coverage",
            is_public=True,
        )
        set_permissions_for_obj_to_user(
            self.user, self.document, [PermissionTypes.CRUD]
        )
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.CRUD])

    def _execute(self, user, **variables):
        client = Client(schema, context_value=TestContext(user))
        return client.execute(self.SUMMARY_MUTATION, variables=variables)

    def test_document_not_found(self):
        result = self._execute(
            self.user,
            documentId=to_global_id("DocumentType", 999_999),
            corpusId=to_global_id("CorpusType", self.corpus.id),
            newContent="content",
        )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["updateDocumentSummary"]
        self.assertFalse(data["ok"])
        self.assertIn("not found", data["message"].lower())

    def test_corpus_not_found(self):
        result = self._execute(
            self.user,
            documentId=to_global_id("DocumentType", self.document.id),
            corpusId=to_global_id("CorpusType", 999_999),
            newContent="content",
        )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["updateDocumentSummary"]
        self.assertFalse(data["ok"])
        self.assertIn("not found", data["message"].lower())

    def test_existing_summary_can_only_be_updated_by_original_author(self):
        variables = dict(
            documentId=to_global_id("DocumentType", self.document.id),
            corpusId=to_global_id("CorpusType", self.corpus.id),
            newContent="initial content",
        )
        created = self._execute(self.user, **variables)
        self.assertTrue(created["data"]["updateDocumentSummary"]["ok"])

        result = self._execute(
            self.other_user, **{**variables, "newContent": "hijacked content"}
        )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["updateDocumentSummary"]
        self.assertFalse(data["ok"])
        self.assertIn("not found", data["message"].lower())

    def test_first_summary_requires_corpus_update_permission(self):
        result = self._execute(
            self.other_user,
            documentId=to_global_id("DocumentType", self.document.id),
            corpusId=to_global_id("CorpusType", self.corpus.id),
            newContent="content from an outsider",
        )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["updateDocumentSummary"]
        self.assertFalse(data["ok"])
        self.assertIn("not found", data["message"].lower())

    def test_unexpected_error_returns_generic_failure_message(self):
        with patch.object(Document, "update_summary", side_effect=RuntimeError("boom")):
            result = self._execute(
                self.user,
                documentId=to_global_id("DocumentType", self.document.id),
                corpusId=to_global_id("CorpusType", self.corpus.id),
                newContent="content",
            )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["updateDocumentSummary"]
        self.assertFalse(data["ok"])
        self.assertEqual(data["message"], "Error updating document summary.")


class DeleteMultipleDocumentsMutationTests(TestCase):
    """``DeleteMultipleDocuments`` (document_mutations.py:702-720)."""

    DELETE_MULTIPLE_MUTATION = """
        mutation DeleteMultiple($ids: [String]!) {
            deleteMultipleDocuments(documentIdsToDelete: $ids) {
                ok
                message
            }
        }
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="bulk_delete_user", password="test", email="bd@test.com"
        )
        self.other_user = User.objects.create_user(
            username="bulk_delete_other", password="test", email="bdo@test.com"
        )
        self.graphene_client = Client(schema, context_value=TestContext(self.user))

    def test_deletes_only_documents_owned_by_requesting_user(self):
        own_doc_1 = Document.objects.create(creator=self.user, title="Own 1")
        own_doc_2 = Document.objects.create(creator=self.user, title="Own 2")
        foreign_doc = Document.objects.create(creator=self.other_user, title="Foreign")

        result = self.graphene_client.execute(
            self.DELETE_MULTIPLE_MUTATION,
            variables={
                "ids": [
                    to_global_id("DocumentType", own_doc_1.id),
                    to_global_id("DocumentType", own_doc_2.id),
                    to_global_id("DocumentType", foreign_doc.id),
                ]
            },
        )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["deleteMultipleDocuments"]
        self.assertTrue(data["ok"])
        self.assertEqual(data["message"], "Success")
        self.assertFalse(Document.objects.filter(pk=own_doc_1.pk).exists())
        self.assertFalse(Document.objects.filter(pk=own_doc_2.pk).exists())
        self.assertTrue(Document.objects.filter(pk=foreign_doc.pk).exists())

    def test_handles_unexpected_error_during_deletion(self):
        doc = Document.objects.create(creator=self.user, title="Doomed")

        with patch.object(Document.objects, "filter", side_effect=RuntimeError("boom")):
            result = self.graphene_client.execute(
                self.DELETE_MULTIPLE_MUTATION,
                variables={"ids": [to_global_id("DocumentType", doc.id)]},
            )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["deleteMultipleDocuments"]
        self.assertFalse(data["ok"])
        self.assertTrue(data["message"].startswith("Delete failed due to error:"))


class UploadDocumentsZipEdgeCaseTests(TestCase):
    """``UploadDocumentsZip`` decode/validation failures
    (document_mutations.py:766-770, 782-787)."""

    ZIP_UPLOAD_MUTATION = """
        mutation UploadZip($file: String!, $makePublic: Boolean!) {
            uploadDocumentsZip(base64FileString: $file, makePublic: $makePublic) {
                ok
                message
                jobId
            }
        }
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="zip_uploader",
            password="test",
            email="zu@test.com",
            is_usage_capped=False,
        )
        self.graphene_client = Client(schema, context_value=TestContext(self.user))

    def test_invalid_base64_returns_decode_error(self):
        result = self.graphene_client.execute(
            self.ZIP_UPLOAD_MUTATION,
            variables={
                "file": "not-valid-base64-content!!!@@@###",
                "makePublic": False,
            },
        )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["uploadDocumentsZip"]
        self.assertFalse(data["ok"])
        self.assertTrue(data["message"].startswith("Could not decode base64 zip:"))
        self.assertIsNone(data["jobId"])

    def test_non_zip_content_returns_validation_error(self):
        result = self.graphene_client.execute(
            self.ZIP_UPLOAD_MUTATION,
            variables={
                "file": base_64_encode_bytes(b"This is definitely not a zip file."),
                "makePublic": False,
            },
        )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["uploadDocumentsZip"]
        self.assertFalse(data["ok"])
        self.assertIn("does not appear to be a valid ZIP archive", data["message"])
        self.assertIsNone(data["jobId"])


class RetryDocumentProcessingMutationTests(TestCase):
    """``RetryDocumentProcessing`` mutation (document_mutations.py:861-922)."""

    RETRY_MUTATION = """
        mutation Retry($documentId: String!) {
            retryDocumentProcessing(documentId: $documentId) {
                ok
                message
                document { id }
            }
        }
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="retry_owner", password="test", email="ro@test.com"
        )
        self.outsider = User.objects.create_user(
            username="retry_outsider", password="test", email="rout@test.com"
        )

    def _execute(self, user, doc):
        client = Client(schema, context_value=TestContext(user))
        return client.execute(
            self.RETRY_MUTATION,
            variables={"documentId": to_global_id("DocumentType", doc.id)},
        )

    def test_document_not_found(self):
        client = Client(schema, context_value=TestContext(self.owner))
        result = client.execute(
            self.RETRY_MUTATION,
            variables={"documentId": to_global_id("DocumentType", 999_999)},
        )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["retryDocumentProcessing"]
        self.assertFalse(data["ok"])
        self.assertEqual(data["message"], "Document not found")

    def test_document_not_in_failed_state_is_rejected(self):
        doc = Document.objects.create(
            creator=self.owner,
            title="Completed Doc",
            processing_status=DocumentProcessingStatus.COMPLETED,
        )
        set_permissions_for_obj_to_user(self.owner, doc, [PermissionTypes.CRUD])

        result = self._execute(self.owner, doc)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["retryDocumentProcessing"]
        self.assertFalse(data["ok"])
        self.assertIn("not in a failed state", data["message"])

    def test_permission_denied_for_public_document_without_update_grant(self):
        doc = Document.objects.create(
            creator=self.owner,
            title="Failed Doc",
            description="Needs retry",
            processing_status=DocumentProcessingStatus.FAILED,
            is_public=True,
        )

        result = self._execute(self.outsider, doc)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["retryDocumentProcessing"]
        self.assertFalse(data["ok"])
        self.assertIn("permission", data["message"].lower())

    def test_success_queues_retry_task(self):
        doc = Document.objects.create(
            creator=self.owner,
            title="Failed Doc",
            description="Needs retry",
            processing_status=DocumentProcessingStatus.FAILED,
        )
        set_permissions_for_obj_to_user(self.owner, doc, [PermissionTypes.CRUD])

        with patch(
            "opencontractserver.tasks.doc_tasks.retry_document_processing.delay"
        ) as mock_delay:
            result = self._execute(self.owner, doc)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["retryDocumentProcessing"]
        self.assertTrue(data["ok"], data.get("message"))
        self.assertIn("queued", data["message"])
        mock_delay.assert_called_once_with(user_id=self.owner.id, doc_id=doc.id)

    def test_unexpected_error_returns_generic_failure_message(self):
        doc = Document.objects.create(
            creator=self.owner,
            title="Failed Doc",
            processing_status=DocumentProcessingStatus.FAILED,
        )
        set_permissions_for_obj_to_user(self.owner, doc, [PermissionTypes.CRUD])

        with patch(
            "config.graphql.document_mutations.BaseService.require_permission",
            side_effect=RuntimeError("boom"),
        ):
            result = self._execute(self.owner, doc)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["retryDocumentProcessing"]
        self.assertFalse(data["ok"])
        self.assertTrue(data["message"].startswith("Retry failed:"))


class RestoreDeletedDocumentEdgeCaseTests(TestCase):
    """Complements ``TestRestoreDeletedDocumentMutation`` in
    ``test_document_versioning_graphql.py`` with the corpus-not-found and
    generic exception branches (document_mutations.py:969-975, 1013-1015)."""

    RESTORE_MUTATION = """
        mutation Restore($documentId: String!, $corpusId: String!) {
            restoreDeletedDocument(documentId: $documentId, corpusId: $corpusId) {
                ok
                message
            }
        }
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="restore_edge_user", password="test", email="reu@test.com"
        )
        self.corpus = Corpus.objects.create(
            title="Restore Edge Corpus", creator=self.user
        )
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.CRUD])
        self.doc, _, self.path = import_document(
            corpus=self.corpus,
            path="/deletable.pdf",
            content=b"content",
            user=self.user,
            title="Deletable",
        )
        set_permissions_for_obj_to_user(self.user, self.doc, [PermissionTypes.CRUD])
        delete_document(corpus=self.corpus, path="/deletable.pdf", user=self.user)
        self.graphene_client = Client(schema, context_value=TestContext(self.user))

    def test_corpus_not_found(self):
        result = self.graphene_client.execute(
            self.RESTORE_MUTATION,
            variables={
                "documentId": to_global_id("DocumentType", self.doc.id),
                "corpusId": to_global_id("CorpusType", 999_999),
            },
        )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["restoreDeletedDocument"]
        self.assertFalse(data["ok"])
        self.assertIn("not found", data["message"].lower())

    def test_unexpected_error_returns_generic_failure_message(self):
        variables = {
            "documentId": to_global_id("DocumentType", self.doc.id),
            "corpusId": to_global_id("CorpusType", self.corpus.id),
        }
        with patch(GET_OR_NONE_TARGET, side_effect=RuntimeError("boom")):
            result = self.graphene_client.execute(
                self.RESTORE_MUTATION, variables=variables
            )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["restoreDeletedDocument"]
        self.assertFalse(data["ok"])
        self.assertEqual(data["message"], "Failed to restore document.")


class RestoreDocumentToVersionEdgeCaseTests(TestCase):
    """Complements ``TestRestoreDocumentToVersionMutation`` in
    ``test_document_versioning_graphql.py``: the corpus-permission branch is
    distinct from the document-permission branch (document_mutations.py:
    1087-1095), plus the current-path/current-version/exception branches
    (1102-1108, 1126-1132, 1196-1198)."""

    RESTORE_VERSION_MUTATION = """
        mutation RestoreVersion($documentId: String!, $corpusId: String!) {
            restoreDocumentToVersion(documentId: $documentId, corpusId: $corpusId) {
                ok
                message
                newVersionNumber
            }
        }
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="version_edge_user", password="test", email="vex@test.com"
        )
        self.other_user = User.objects.create_user(
            username="version_edge_other", password="test", email="vexo@test.com"
        )
        self.corpus = Corpus.objects.create(
            title="Version Edge Corpus", creator=self.user, is_public=True
        )
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.CRUD])

        self.doc_v1, _, _ = import_document(
            corpus=self.corpus,
            path="/versioned.pdf",
            content=b"v1",
            user=self.user,
            title="V1",
        )
        set_permissions_for_obj_to_user(self.user, self.doc_v1, [PermissionTypes.CRUD])
        self.doc_v2, _, _ = import_document(
            corpus=self.corpus,
            path="/versioned.pdf",
            content=b"v2",
            user=self.user,
            title="V2",
        )
        set_permissions_for_obj_to_user(self.user, self.doc_v2, [PermissionTypes.CRUD])

    def _execute(self, user, doc, corpus):
        client = Client(schema, context_value=TestContext(user))
        return client.execute(
            self.RESTORE_VERSION_MUTATION,
            variables={
                "documentId": to_global_id("DocumentType", doc.id),
                "corpusId": to_global_id("CorpusType", corpus.id),
            },
        )

    def test_corpus_permission_denied_is_distinct_from_document_permission(self):
        """``other_user`` has UPDATE on the old version directly, but only
        public READ (no UPDATE) on the corpus — the corpus check must still
        deny, exercising the second (corpus) permission branch rather than
        the first (document) one."""
        set_permissions_for_obj_to_user(
            self.other_user, self.doc_v1, [PermissionTypes.CRUD]
        )

        result = self._execute(self.other_user, self.doc_v1, self.corpus)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["restoreDocumentToVersion"]
        self.assertFalse(data["ok"])
        self.assertIn("permission", data["message"].lower())

    def test_current_path_not_found_in_different_corpus(self):
        other_corpus = Corpus.objects.create(
            title="Unrelated Corpus", creator=self.user
        )
        set_permissions_for_obj_to_user(self.user, other_corpus, [PermissionTypes.CRUD])

        result = self._execute(self.user, self.doc_v1, other_corpus)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["restoreDocumentToVersion"]
        self.assertFalse(data["ok"])
        self.assertEqual(data["message"], "Document not found in this corpus")

    def test_current_version_missing_returns_error(self):
        """Defensive branch: no ``Document`` in the version tree is marked
        ``is_current`` (a data anomaly, simulated directly here since the
        mutation itself always maintains exactly one)."""
        Document.objects.filter(version_tree_id=self.doc_v1.version_tree_id).update(
            is_current=False
        )

        result = self._execute(self.user, self.doc_v1, self.corpus)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["restoreDocumentToVersion"]
        self.assertFalse(data["ok"])
        self.assertEqual(
            data["message"], "Cannot find current version of this document"
        )

    def test_unexpected_error_returns_generic_failure_message(self):
        with patch(GET_OR_NONE_TARGET, side_effect=RuntimeError("boom")):
            result = self._execute(self.user, self.doc_v1, self.corpus)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["restoreDocumentToVersion"]
        self.assertFalse(data["ok"])
        self.assertTrue(data["message"].startswith("Failed to restore document:"))


class PermanentlyDeleteDocumentEdgeCaseTests(TestCase):
    """Complements ``TestPermanentDeletionGraphQL`` in
    ``test_permanent_deletion.py`` with the corpus-not-found and generic
    exception branches (document_mutations.py:1256-1257, 1273-1277)."""

    DELETE_MUTATION = """
        mutation PermanentlyDelete($documentId: String!, $corpusId: String!) {
            permanentlyDeleteDocument(documentId: $documentId, corpusId: $corpusId) {
                ok
                message
            }
        }
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="perm_delete_edge_user", password="test", email="pdeu@test.com"
        )
        self.corpus = Corpus.objects.create(
            title="Perm Delete Edge Corpus", creator=self.user
        )
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.CRUD])
        self.doc, _, _ = import_document(
            corpus=self.corpus,
            path="/perm_delete.pdf",
            content=b"content",
            user=self.user,
            title="Perm Delete Doc",
        )
        set_permissions_for_obj_to_user(self.user, self.doc, [PermissionTypes.CRUD])
        delete_document(corpus=self.corpus, path="/perm_delete.pdf", user=self.user)
        self.graphene_client = Client(schema, context_value=TestContext(self.user))

    def test_corpus_not_found(self):
        result = self.graphene_client.execute(
            self.DELETE_MUTATION,
            variables={
                "documentId": to_global_id("DocumentType", self.doc.id),
                "corpusId": to_global_id("CorpusType", 999_999),
            },
        )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["permanentlyDeleteDocument"]
        self.assertFalse(data["ok"])
        self.assertIn("not found", data["message"].lower())

    def test_unexpected_error_returns_generic_failure_message(self):
        variables = {
            "documentId": to_global_id("DocumentType", self.doc.id),
            "corpusId": to_global_id("CorpusType", self.corpus.id),
        }
        with patch(GET_OR_NONE_TARGET, side_effect=RuntimeError("boom")):
            result = self.graphene_client.execute(
                self.DELETE_MUTATION, variables=variables
            )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["permanentlyDeleteDocument"]
        self.assertFalse(data["ok"])
        self.assertEqual(data["message"], "Failed to permanently delete document.")


class EmptyTrashEdgeCaseTests(TestCase):
    """Complements the ``TestEmptyTrashBulk``/``TestPermanentDeletionGraphQL``
    coverage with the partial-success and generic exception branches
    (document_mutations.py:1332-1338, 1348-1352)."""

    EMPTY_TRASH_MUTATION = """
        mutation EmptyTrash($corpusId: String!) {
            emptyTrash(corpusId: $corpusId) {
                ok
                message
                deletedCount
            }
        }
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="empty_trash_edge_user", password="test", email="ete@test.com"
        )
        self.corpus = Corpus.objects.create(
            title="Empty Trash Edge Corpus", creator=self.user
        )
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.CRUD])
        self.graphene_client = Client(schema, context_value=TestContext(self.user))

    def test_partial_success_reports_error_and_count(self):
        with patch.object(
            DocumentLifecycleService,
            "empty_trash",
            return_value=(2, "Deleted 2 documents with 1 errors: boom"),
        ):
            result = self.graphene_client.execute(
                self.EMPTY_TRASH_MUTATION,
                variables={"corpusId": to_global_id("CorpusType", self.corpus.id)},
            )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["emptyTrash"]
        self.assertTrue(data["ok"])
        self.assertEqual(data["deletedCount"], 2)
        self.assertIn("errors", data["message"])

    def test_unexpected_error_returns_generic_failure_message(self):
        with patch(GET_OR_NONE_TARGET, side_effect=RuntimeError("boom")):
            result = self.graphene_client.execute(
                self.EMPTY_TRASH_MUTATION,
                variables={"corpusId": to_global_id("CorpusType", self.corpus.id)},
            )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["emptyTrash"]
        self.assertFalse(data["ok"])
        self.assertTrue(data["message"].startswith("Failed to empty trash:"))
        self.assertEqual(data["deletedCount"], 0)


class EmptyCorpusMutationTests(TestCase):
    """``EmptyCorpus`` mutation — no prior GraphQL test coverage at all
    (document_mutations.py:1376-1426)."""

    EMPTY_CORPUS_MUTATION = """
        mutation EmptyCorpus($corpusId: String!) {
            emptyCorpus(corpusId: $corpusId) {
                ok
                message
                trashedCount
            }
        }
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="empty_corpus_user", password="test", email="ecu@test.com"
        )
        self.other_user = User.objects.create_user(
            username="empty_corpus_other", password="test", email="ecuo@test.com"
        )
        self.corpus = Corpus.objects.create(
            title="Empty Corpus Target", creator=self.user, is_public=True
        )
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.CRUD])

    def _execute(self, user, corpus_id):
        client = Client(schema, context_value=TestContext(user))
        return client.execute(
            self.EMPTY_CORPUS_MUTATION,
            variables={"corpusId": to_global_id("CorpusType", corpus_id)},
        )

    def test_success_trashes_documents_and_removes_folders(self):
        folder = CorpusFolder.objects.create(
            corpus=self.corpus, name="A Folder", creator=self.user
        )
        for i in range(2):
            doc, _, _ = import_document(
                corpus=self.corpus,
                path=f"/doc_{i}.pdf",
                content=f"content {i}".encode(),
                user=self.user,
                title=f"Doc {i}",
                folder=folder,
            )
            set_permissions_for_obj_to_user(self.user, doc, [PermissionTypes.CRUD])

        result = self._execute(self.user, self.corpus.id)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["emptyCorpus"]
        self.assertTrue(data["ok"], data.get("message"))
        self.assertEqual(data["trashedCount"], 2)
        self.assertEqual(
            DocumentPath.objects.filter(
                corpus=self.corpus, is_current=True, is_deleted=False
            ).count(),
            0,
        )
        self.assertFalse(CorpusFolder.objects.filter(corpus=self.corpus).exists())

    def test_permission_denied(self):
        result = self._execute(self.other_user, self.corpus.id)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["emptyCorpus"]
        self.assertFalse(data["ok"])
        self.assertIn("permission", data["message"].lower())
        self.assertEqual(data["trashedCount"], 0)

    def test_corpus_not_found(self):
        result = self._execute(self.user, 999_999)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["emptyCorpus"]
        self.assertFalse(data["ok"])
        self.assertEqual(data["message"], "Corpus not found")

    def test_unexpected_error_returns_generic_failure_message(self):
        with patch(GET_OR_NONE_TARGET, side_effect=RuntimeError("boom")):
            result = self._execute(self.user, self.corpus.id)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["emptyCorpus"]
        self.assertFalse(data["ok"])
        self.assertEqual(data["message"], "Failed to empty corpus.")


class UploadAnnotatedDocumentEdgeCaseTests(TestCase):
    """``importAnnotatedDocToCorpus`` shape-validation failure
    (document_mutations.py:1461, 1469-1472)."""

    IMPORT_MUTATION = """
        mutation ImportAnnotatedDoc($targetCorpusId: String!, $documentImportData: String!) {
            importAnnotatedDocToCorpus(
                targetCorpusId: $targetCorpusId, documentImportData: $documentImportData
            ) {
                ok
                message
            }
        }
    """

    def test_invalid_document_import_data_shape_returns_error(self):
        import json

        user = User.objects.create_user(
            username="annotated_import_user", password="test", email="aiu@test.com"
        )
        corpus = Corpus.objects.create(title="Import Target", creator=user)
        client = Client(schema, context_value=TestContext(user))

        result = client.execute(
            self.IMPORT_MUTATION,
            variables={
                "targetCorpusId": to_global_id("CorpusType", corpus.id),
                "documentImportData": json.dumps({"unexpected": "shape"}),
            },
        )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["importAnnotatedDocToCorpus"]
        self.assertFalse(data["ok"])
        self.assertIn("document_import_data is invalid", data["message"])


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_STORE_EAGER_RESULT=True)
class StartCorpusExportEdgeCaseTests(BaseFixtureTestCase):
    """Complements ``TestExportMutations`` in ``test_export_mutations.py``
    with the usage-cap, invalid-analysis-id, V2 dispatch, unknown-format,
    and exception branches (document_mutations.py:1538-1545, 1588-1593,
    1638-1648, 1673-1675, 1686-1690)."""

    EXPORT_MUTATION = """
        mutation ExportCorpus(
            $corpusId: String!, $exportFormat: ExportType!, $analysesIds: [String!]
        ) {
            exportCorpus(
                corpusId: $corpusId, exportFormat: $exportFormat, analysesIds: $analysesIds
            ) {
                ok
                message
                export { id }
            }
        }
    """

    def setUp(self):
        super().setUp()
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.ALL])
        # The real OPEN_CONTRACTS export chain (build_label_lookups_task)
        # requires a label set on the corpus; BaseFixtureTestCase doesn't
        # attach one by default.
        self.corpus.label_set = LabelSet.objects.create(
            title="Coverage Label Set", creator=self.user
        )
        self.corpus.save()
        self.graphene_client = Client(schema, context_value=TestContext(self.user))

    def _execute(self, export_format, analyses_ids=None):
        return self.graphene_client.execute(
            self.EXPORT_MUTATION,
            variables={
                "corpusId": to_global_id("CorpusType", self.corpus.id),
                "exportFormat": export_format,
                "analysesIds": analyses_ids,
            },
        )

    def test_usage_capped_user_cannot_export(self):
        self.assertTrue(self.user.is_usage_capped)

        with override_settings(USAGE_CAPPED_USER_CAN_EXPORT_CORPUS=False):
            result = self._execute("OPEN_CONTRACTS")

        self.assertIsNotNone(result.get("errors"))
        self.assertIn("cannot create exports", result["errors"][0]["message"])

    def test_invalid_analysis_id_is_skipped_silently(self):
        result = self._execute("OPEN_CONTRACTS", analyses_ids=["not-a-valid-global-id"])

        self.assertIsNone(result.get("errors"))
        data = result["data"]["exportCorpus"]
        self.assertTrue(data["ok"], data.get("message"))
        self.assertEqual(data["message"], "SUCCESS")

    def test_open_contracts_v2_dispatches_export_task(self):
        with patch(
            "opencontractserver.tasks.export_tasks_v2.package_corpus_export_v2.delay"
        ) as mock_delay:
            result = self._execute("OPEN_CONTRACTS_V2")

        self.assertIsNone(result.get("errors"))
        data = result["data"]["exportCorpus"]
        self.assertTrue(data["ok"], data.get("message"))
        self.assertEqual(data["message"], "SUCCESS")
        mock_delay.assert_called_once()

    def test_unknown_export_format_is_rejected(self):
        result = self._execute("LANGCHAIN")

        self.assertIsNone(result.get("errors"))
        data = result["data"]["exportCorpus"]
        self.assertFalse(data["ok"])
        self.assertEqual(data["message"], "Unknown Format")

    def test_unexpected_error_returns_generic_failure_message(self):
        with patch(GET_OR_NONE_TARGET, side_effect=RuntimeError("boom")):
            result = self._execute("OPEN_CONTRACTS")

        self.assertIsNone(result.get("errors"))
        data = result["data"]["exportCorpus"]
        self.assertFalse(data["ok"])
        self.assertTrue(
            data["message"].startswith(
                "StartCorpusExport() - Unable to create export due to error:"
            )
        )


class DeleteExportMutationTests(TestCase):
    """``deleteExport`` — no prior GraphQL test coverage at all
    (document_mutations.py:1767-1779)."""

    DELETE_EXPORT_MUTATION = """
        mutation DeleteExport($id: String!) {
            deleteExport(id: $id) {
                ok
                message
            }
        }
    """

    def test_delete_export_success(self):
        user = User.objects.create_user(
            username="export_deleter", password="test", email="ed@test.com"
        )
        export = UserExport.objects.create(creator=user, name="Coverage export")
        set_permissions_for_obj_to_user(user, export, [PermissionTypes.CRUD])
        client = Client(schema, context_value=TestContext(user))

        result = client.execute(
            self.DELETE_EXPORT_MUTATION,
            variables={"id": to_global_id("UserExportType", export.id)},
        )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["deleteExport"]
        self.assertTrue(data["ok"], data.get("message"))
        self.assertFalse(UserExport.objects.filter(pk=export.pk).exists())
