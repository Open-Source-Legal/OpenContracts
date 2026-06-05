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

    def test_ingestion_run_id_groups_rows(self):
        """A run id can be stamped and filtered on; default is NULL."""
        import uuid

        user = get_user_model().objects.create_user(username="u2", password="p")
        doc = Document.objects.create(title="d2", creator=user)

        run = uuid.uuid4()
        tagged = PendingDocumentAnnotations.objects.create(
            document=doc,
            creator=user,
            payload={"annotations": [], "doc_labels": []},
            ingestion_run_id=run,
        )
        untagged = PendingDocumentAnnotations.objects.create(
            document=doc,
            creator=user,
            payload={"annotations": [], "doc_labels": []},
        )

        self.assertIsNone(untagged.ingestion_run_id)
        self.assertEqual(
            list(
                PendingDocumentAnnotations.objects.filter(
                    ingestion_run_id=run
                ).values_list("id", flat=True)
            ),
            [tagged.id],
        )
