from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.documents.models import Document, PendingDocumentAnnotations


class PendingDocumentAnnotationsModelTests(TestCase):
    def test_create_and_defaults(self):
        user = get_user_model().objects.create_user(username="u", password="p")
        doc = Document.objects.create(title="d", creator=user)
        row = PendingDocumentAnnotations.objects.create(
            document=doc, creator=user, payload={"annotations": [], "doc_labels": []}
        )
        self.assertEqual(row.status, PendingDocumentAnnotations.Status.PENDING)
        self.assertEqual(row.report, [])
        self.assertEqual(doc.pending_annotations.count(), 1)
