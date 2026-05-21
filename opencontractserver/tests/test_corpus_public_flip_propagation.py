"""
Regression tests for the I-1 public-flip cascade fix.

Before the fix, flipping a corpus to is_public=True bulk-updated EVERY
document in the corpus to is_public=True, with no notification to document
owners and no protection against publicizing material that was also a
member of a private corpus owned by a different user (cross-corpus leak).

These tests pin two behaviors:

1. Documents that are also members of a private corpus owned by someone
   other than the corpus creator are NOT publicized when the corpus flips.
2. For documents that ARE publicized, every distinct document creator
   (other than the corpus creator who took the action) receives a
   DOCUMENT_PUBLICIZED notification.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.notifications.models import (
    Notification,
    NotificationTypeChoices,
)

User = get_user_model()


def _attach_doc_to_corpus(doc: Document, corpus: Corpus, *, path: str) -> DocumentPath:
    """
    Wire a DocumentPath row directly so a single Document is shared across
    multiple corpora. Bypasses Corpus.add_document() which would create a
    corpus-isolated copy and defeat the cross-corpus scenario this test
    exercises.
    """
    return DocumentPath.objects.create(
        document=doc,
        corpus=corpus,
        path=path,
        version_number=1,
        is_current=True,
        is_deleted=False,
        creator=corpus.creator,
    )


class PublicFlipCascadeTests(TestCase):
    """The cascade now respects cross-owner privacy and notifies owners."""

    def setUp(self):
        self.publisher = User.objects.create_user(username="publisher", password="x")
        self.other_owner = User.objects.create_user(username="other", password="x")

        # Documents we'll wire into the publisher's corpus via direct
        # DocumentPath rows (no corpus-isolated copy):
        self.doc_owned_by_publisher = Document.objects.create(
            title="Publisher Doc",
            creator=self.publisher,
            is_public=False,
            backend_lock=False,
        )
        # Cross-owner doc: also lives in another, private, foreign-owned
        # corpus so the I-1 protection must keep it private.
        self.doc_owned_by_other = Document.objects.create(
            title="Other Doc",
            creator=self.other_owner,
            is_public=False,
            backend_lock=False,
        )

        # Publisher's corpus — the one we will flip.
        self.publisher_corpus = Corpus.objects.create(
            title="Publisher Corpus", creator=self.publisher, is_public=False
        )
        _attach_doc_to_corpus(
            self.doc_owned_by_publisher,
            self.publisher_corpus,
            path="/documents/publisher_doc",
        )
        _attach_doc_to_corpus(
            self.doc_owned_by_other,
            self.publisher_corpus,
            path="/documents/other_doc",
        )

        # other_owner's PRIVATE corpus that ALSO contains doc_owned_by_other.
        # This is the cross-owner constraint that triggers the I-1 block.
        self.cross_owner_private_corpus = Corpus.objects.create(
            title="Other Private Corpus", creator=self.other_owner, is_public=False
        )
        _attach_doc_to_corpus(
            self.doc_owned_by_other,
            self.cross_owner_private_corpus,
            path="/documents/other_doc",
        )

        # Clear any auto-created notifications from corpus/doc setup so
        # we can assert exactly which DOCUMENT_PUBLICIZED rows were created.
        Notification.objects.filter(
            recipient__in=[self.publisher, self.other_owner]
        ).delete()

    def _flip_public(self):
        self.publisher_corpus.is_public = True
        self.publisher_corpus.save()
        self.doc_owned_by_publisher.refresh_from_db()
        self.doc_owned_by_other.refresh_from_db()

    def test_cross_owner_doc_is_not_publicized(self):
        """Doc shared with other_owner's private corpus stays private."""
        self._flip_public()
        # Publisher-owned doc is publicized.
        self.assertTrue(self.doc_owned_by_publisher.is_public)
        # Cross-owner doc remains private — this is the I-1 fix.
        self.assertFalse(
            self.doc_owned_by_other.is_public,
            msg=(
                "Cross-owner document was publicized via corpus flip. "
                "I-1 cascade-leak protection regressed."
            ),
        )

    def test_doc_creator_receives_notification_when_their_doc_is_publicized(self):
        """Per-doc notification lands on the document creator (when != actor)."""
        # A second doc owned by other_owner that is NOT in any other
        # private corpus, so it WILL be publicized and the owner must
        # hear about it.
        notifiable_doc = Document.objects.create(
            title="Other Public-Eligible Doc",
            creator=self.other_owner,
            is_public=False,
            backend_lock=False,
        )
        _attach_doc_to_corpus(
            notifiable_doc,
            self.publisher_corpus,
            path="/documents/notifiable_doc",
        )
        Notification.objects.filter(recipient=self.other_owner).delete()

        self._flip_public()

        notifiable_doc.refresh_from_db()
        self.assertTrue(notifiable_doc.is_public)
        notifications = Notification.objects.filter(
            recipient=self.other_owner,
            notification_type=NotificationTypeChoices.DOCUMENT_PUBLICIZED,
        )
        self.assertEqual(notifications.count(), 1, msg=list(notifications))
        notification = notifications.get()
        self.assertEqual(notification.actor_id, self.publisher.id)
        self.assertEqual(notification.data["document_id"], notifiable_doc.id)
        self.assertEqual(notification.data["corpus_id"], self.publisher_corpus.pk)

    def test_publisher_does_not_notify_themselves(self):
        """The actor is not notified for docs they themselves own."""
        self._flip_public()
        self.assertFalse(
            Notification.objects.filter(
                recipient=self.publisher,
                notification_type=NotificationTypeChoices.DOCUMENT_PUBLICIZED,
            ).exists()
        )

    def test_all_docs_cross_owner_blocked_no_publicize_and_no_notification(self):
        """When every document in the corpus is blocked by the cross-owner
        constraint, the early-return inside transaction.atomic() must fire and
        no document must be publicized and no notification sent.

        This exercises the `if not publicize_ids: return` branch that now lives
        inside the atomic block after the I-1 follow-up review fix.
        """
        # Build a corpus that contains ONLY documents also held by a foreign
        # private corpus — so publicize_ids will be empty after filtering.
        sole_publisher = User.objects.create_user(
            username="sole_publisher", password="x"
        )
        foreign_owner = User.objects.create_user(username="foreign", password="x")

        foreign_doc = Document.objects.create(
            title="All-Blocked Doc",
            creator=foreign_owner,
            is_public=False,
            backend_lock=False,
        )
        publisher_corpus = Corpus.objects.create(
            title="All-Blocked Corpus", creator=sole_publisher, is_public=False
        )
        _attach_doc_to_corpus(
            foreign_doc,
            publisher_corpus,
            path="/documents/foreign_doc",
        )

        # Wire the same doc into a private corpus owned by foreign_owner so
        # cross_owner_blocked_ids will include it and publicize_ids is empty.
        foreign_private_corpus = Corpus.objects.create(
            title="Foreign Private Corpus", creator=foreign_owner, is_public=False
        )
        _attach_doc_to_corpus(
            foreign_doc,
            foreign_private_corpus,
            path="/documents/foreign_doc",
        )

        Notification.objects.filter(
            recipient__in=[sole_publisher, foreign_owner]
        ).delete()

        publisher_corpus.is_public = True
        publisher_corpus.save()

        foreign_doc.refresh_from_db()
        self.assertFalse(
            foreign_doc.is_public,
            msg="Document was incorrectly publicized when all docs were cross-owner blocked.",
        )
        self.assertFalse(
            Notification.objects.filter(
                recipient=foreign_owner,
                notification_type=NotificationTypeChoices.DOCUMENT_PUBLICIZED,
            ).exists(),
            msg="Notification was sent for a document that was not actually publicized.",
        )
        # The publisher (corpus owner) should also receive no spurious
        # DOCUMENT_PUBLICIZED notification — the early-return inside the
        # atomic block exits before the fan-out runs.
        self.assertFalse(
            Notification.objects.filter(
                recipient=sole_publisher,
                notification_type=NotificationTypeChoices.DOCUMENT_PUBLICIZED,
            ).exists(),
            msg="Publisher received a spurious DOCUMENT_PUBLICIZED notification "
            "even though no documents were actually publicized.",
        )
