"""
Regression tests for the T-7 defense-in-depth permission check.

The ingest_doc and retry_document_processing Celery tasks accept (user_id,
doc_id) as separate arguments. Before the fix, neither task verified that
user_id actually had permission to operate on doc_id — they trusted the
enqueueing GraphQL mutation. A future mutation that forgets to check would
allow cross-account processing on the worker side.

These tests pin the new defensive checks and ensure they fail closed with
a SECURITY log line rather than processing a foreign document.
"""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.documents.models import Document, DocumentProcessingStatus
from opencontractserver.tasks.doc_tasks import ingest_doc, retry_document_processing
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class IngestDocPermissionCheckTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="x")
        self.attacker = User.objects.create_user(username="attacker", password="x")

        self.doc = Document.objects.create(
            title="Owner Doc",
            creator=self.owner,
            is_public=False,
            backend_lock=True,
            processing_status=DocumentProcessingStatus.PENDING,
        )
        # Grant owner full perms; attacker gets nothing.
        set_permissions_for_obj_to_user(self.owner, self.doc, [PermissionTypes.CRUD])

    def test_ingest_doc_refuses_when_user_lacks_permission(self):
        """A task enqueued with attacker's user_id on owner's doc must refuse."""
        with self.assertLogs(
            "opencontractserver.tasks.doc_tasks", level=logging.ERROR
        ) as captured:
            result = ingest_doc.apply(
                kwargs={"user_id": self.attacker.id, "doc_id": self.doc.id}
            ).get()
        self.assertEqual(result["status"], "failed")
        self.assertIn("permission", result["error"].lower())
        # Doc must remain untouched (still PENDING, still locked).
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.processing_status, DocumentProcessingStatus.PENDING)
        self.assertTrue(
            any("[SECURITY]" in line for line in captured.output),
            msg=f"Expected a SECURITY-tagged log line; got: {captured.output}",
        )

    def test_ingest_doc_refuses_for_unknown_user(self):
        """An invalid user_id must fail closed without touching the doc."""
        result = ingest_doc.apply(
            kwargs={"user_id": 999_999_999, "doc_id": self.doc.id}
        ).get()
        self.assertEqual(result["status"], "failed")

    def test_retry_document_processing_refuses_when_user_lacks_permission(self):
        """retry_document_processing must also reject cross-user retries."""
        # Put doc into FAILED state so the retry path is reachable.
        Document.objects.filter(pk=self.doc.id).update(
            processing_status=DocumentProcessingStatus.FAILED
        )
        with self.assertLogs(
            "opencontractserver.tasks.doc_tasks", level=logging.ERROR
        ) as captured:
            result = retry_document_processing.apply(
                kwargs={"user_id": self.attacker.id, "doc_id": self.doc.id}
            ).get()
        self.assertEqual(result["status"], "error")
        self.assertIn("permission", result["message"].lower())
        # State must remain FAILED — no retry kicked off.
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.processing_status, DocumentProcessingStatus.FAILED)
        self.assertTrue(
            any("[SECURITY]" in line for line in captured.output),
            msg=f"Expected a SECURITY-tagged log line; got: {captured.output}",
        )

    def test_retry_document_processing_refuses_for_nonexistent_user(self):
        """retry_document_processing must fail closed with [SECURITY] log when
        the supplied user_id does not correspond to any User row.

        This exercises the new User.DoesNotExist branch added in the T-7
        follow-up review, which returns 'Invalid user for retry' (distinct from
        'Document not found') and emits a [SECURITY]-tagged audit line.
        """
        Document.objects.filter(pk=self.doc.id).update(
            processing_status=DocumentProcessingStatus.FAILED
        )
        with self.assertLogs(
            "opencontractserver.tasks.doc_tasks", level=logging.ERROR
        ) as captured:
            result = retry_document_processing.apply(
                kwargs={"user_id": 999_999_999, "doc_id": self.doc.id}
            ).get()
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["message"], "Invalid user for retry")
        # The document must remain untouched.
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.processing_status, DocumentProcessingStatus.FAILED)
        self.assertTrue(
            any("[SECURITY]" in line for line in captured.output),
            msg=f"Expected a SECURITY-tagged log line; got: {captured.output}",
        )

    def test_retry_document_processing_refuses_for_nonexistent_document(self):
        """retry_document_processing must fail closed with a WARNING audit
        log when the supplied doc_id does not correspond to any Document row.

        Pins the Document.DoesNotExist branch contract: returns
        'Document not found' (status=error) and emits a log line at
        WARNING level so ops can spot sequential-id probing if it ever
        shows up in the wild. Distinct from User.DoesNotExist (which is
        ERROR + [SECURITY] tagged because a missing user is a stronger
        signal of misuse than a missing document).
        """
        nonexistent_doc_id = 999_999_999
        # Ensure no Document with this id exists.
        self.assertFalse(Document.objects.filter(pk=nonexistent_doc_id).exists())
        with self.assertLogs(
            "opencontractserver.tasks.doc_tasks", level=logging.WARNING
        ) as captured:
            # Use ``self.attacker`` here — any valid user is fine for this
            # test, the contract under inspection is the ``Document.DoesNotExist``
            # branch. The class fixture defines ``self.owner`` and
            # ``self.attacker``; there is no ``self.user``.
            result = retry_document_processing.apply(
                kwargs={"user_id": self.attacker.id, "doc_id": nonexistent_doc_id}
            ).get()
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["message"], "Document not found")
        self.assertEqual(result["doc_id"], nonexistent_doc_id)
        self.assertTrue(
            any("does not exist" in line for line in captured.output),
            msg=f"Expected a doc_id-not-found audit log; got: {captured.output}",
        )
