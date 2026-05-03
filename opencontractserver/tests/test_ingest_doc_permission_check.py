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
