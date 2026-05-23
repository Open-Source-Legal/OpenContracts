"""
Tests for ``DocumentRelationshipService.get_relationship_counts_by_document``.

The method replaces the per-document ``.count()`` pattern in
``resolve_doc_relationship_count`` with a single pair of aggregated queries.
These tests cover:

1. Normal case: each side of a relationship gets +1 to its count.
2. Self-referential safeguard: a relationship where source == target only
   contributes once to that document's count, not twice.
3. Corpus filter: ``corpus_id`` argument restricts counts to that corpus.
4. Permission boundary: counts respect document/corpus visibility.
5. Request-level cache: the result is memoised on the request object.
"""

import logging
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase

from opencontractserver.annotations.models import AnnotationLabel
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import (
    Document,
    DocumentPath,
    DocumentRelationship,
)
from opencontractserver.documents.services import DocumentRelationshipService
from opencontractserver.tests.fixtures import SAMPLE_PDF_FILE_TWO_PATH
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()
logger = logging.getLogger(__name__)


class GetRelationshipCountsByDocumentTestCase(TestCase):
    """Verify ``get_relationship_counts_by_document`` returns the expected counts."""

    def setUp(self):
        self.owner = User.objects.create_user(username="counts_owner", password="x")
        self.outsider = User.objects.create_user(
            username="counts_outsider", password="x"
        )

        self.corpus = Corpus.objects.create(
            title="CountsCorpus",
            creator=self.owner,
            is_public=False,
        )

        with SAMPLE_PDF_FILE_TWO_PATH.open("rb") as f:
            pdf_bytes = f.read()

        def _make_doc(title: str) -> Document:
            return Document.objects.create(
                creator=self.owner,
                title=title,
                description=title,
                custom_meta={},
                pdf_file=ContentFile(pdf_bytes, name=f"{title}.pdf"),
                backend_lock=True,
                is_public=False,
            )

        self.doc_a = _make_doc("doc_a")
        self.doc_b = _make_doc("doc_b")
        self.doc_c = _make_doc("doc_c")

        for doc, path in [
            (self.doc_a, "/a"),
            (self.doc_b, "/b"),
            (self.doc_c, "/c"),
        ]:
            DocumentPath.objects.create(
                document=doc,
                corpus=self.corpus,
                creator=self.owner,
                path=path,
                version_number=1,
                is_current=True,
                is_deleted=False,
            )

        self.label = AnnotationLabel.objects.create(
            text="counts_label",
            label_type="RELATIONSHIP_LABEL",
            creator=self.owner,
        )

        # Two relationships: A↔B and B↔C
        self.rel_ab = DocumentRelationship.objects.create(
            source_document=self.doc_a,
            target_document=self.doc_b,
            relationship_type="RELATIONSHIP",
            annotation_label=self.label,
            creator=self.owner,
            corpus=self.corpus,
        )
        self.rel_bc = DocumentRelationship.objects.create(
            source_document=self.doc_b,
            target_document=self.doc_c,
            relationship_type="RELATIONSHIP",
            annotation_label=self.label,
            creator=self.owner,
            corpus=self.corpus,
        )

        # Owner gets full visibility, outsider gets none
        for obj in (self.doc_a, self.doc_b, self.doc_c, self.corpus):
            set_permissions_for_obj_to_user(self.owner, obj, [PermissionTypes.CRUD])

    def test_each_side_of_relationship_counts_once(self):
        """A and C each appear in one relationship; B is in both."""
        counts = DocumentRelationshipService.get_relationship_counts_by_document(
            user=self.owner,
        )
        self.assertEqual(counts.get(self.doc_a.pk, 0), 1)
        self.assertEqual(counts.get(self.doc_b.pk, 0), 2)
        self.assertEqual(counts.get(self.doc_c.pk, 0), 1)

    def test_self_referential_relationship_counts_once(self):
        """Source == target should contribute 1, not 2, to the count."""
        # Bypass full_clean so the self-referential row can be inserted; the
        # model's clean() rejects it via the corpus-membership check, but
        # we want to verify the optimizer is robust to data that bypassed
        # validation (e.g. via bulk_create or future schema changes).
        DocumentRelationship.objects.bulk_create(
            [
                DocumentRelationship(
                    source_document=self.doc_a,
                    target_document=self.doc_a,
                    relationship_type="NOTES",
                    annotation_label=None,
                    creator=self.owner,
                    corpus=self.corpus,
                )
            ]
        )

        counts = DocumentRelationshipService.get_relationship_counts_by_document(
            user=self.owner,
        )
        # doc_a now has its original A↔B relationship plus 1 self-relationship,
        # for a total of 2 (NOT 3, which would happen if the self-relationship
        # was double-counted).
        self.assertEqual(counts.get(self.doc_a.pk, 0), 2)

    def test_corpus_filter_restricts_to_corpus(self):
        """``corpus_id`` argument should restrict counts to that corpus."""
        other_corpus = Corpus.objects.create(
            title="OtherCorpus",
            creator=self.owner,
            is_public=False,
        )
        set_permissions_for_obj_to_user(
            self.owner, other_corpus, [PermissionTypes.CRUD]
        )

        counts_in_main = (
            DocumentRelationshipService.get_relationship_counts_by_document(
                user=self.owner, corpus_id=self.corpus.pk
            )
        )
        counts_in_other = (
            DocumentRelationshipService.get_relationship_counts_by_document(
                user=self.owner, corpus_id=other_corpus.pk
            )
        )
        self.assertEqual(counts_in_main.get(self.doc_b.pk, 0), 2)
        self.assertEqual(counts_in_other.get(self.doc_b.pk, 0), 0)

    def test_outsider_sees_no_counts(self):
        """An outsider with no document/corpus permissions sees no counts."""
        counts = DocumentRelationshipService.get_relationship_counts_by_document(
            user=self.outsider,
        )
        self.assertEqual(counts.get(self.doc_a.pk, 0), 0)
        self.assertEqual(counts.get(self.doc_b.pk, 0), 0)
        self.assertEqual(counts.get(self.doc_c.pk, 0), 0)

    def test_one_sided_visibility_excludes_relationship(self):
        """
        A relationship counts toward a document only when BOTH endpoints are
        visible. If the user can see one side but not the other, the badge
        must be 0 — otherwise the count would leak the existence of the
        hidden document.
        """
        partial_user = User.objects.create_user(username="partial", password="x")
        # Grant permission on doc_a (and the corpus) but explicitly NOT on
        # doc_b. A↔B is the only relationship that touches doc_a, so its
        # count must collapse to 0 under the AND visibility rule.
        set_permissions_for_obj_to_user(
            partial_user, self.doc_a, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            partial_user, self.corpus, [PermissionTypes.READ]
        )

        counts = DocumentRelationshipService.get_relationship_counts_by_document(
            user=partial_user,
        )
        self.assertEqual(counts.get(self.doc_a.pk, 0), 0)
        self.assertEqual(counts.get(self.doc_b.pk, 0), 0)

    def test_request_level_cache_returns_same_result(self):
        """A second call with the same request should return the cached dict."""
        request = SimpleNamespace()
        first = DocumentRelationshipService.get_relationship_counts_by_document(
            user=self.owner, request=request
        )
        # Mutate the underlying data to confirm the cache is being hit
        # (a fresh query would now return different numbers).
        DocumentRelationship.objects.filter(pk=self.rel_ab.pk).delete()

        second = DocumentRelationshipService.get_relationship_counts_by_document(
            user=self.owner, request=request
        )
        self.assertIs(first, second)
        self.assertEqual(second.get(self.doc_a.pk, 0), 1)
