"""Model-level invariants for ``CorpusReference``.

Covers the two integrity guards that back the enrichment writer:

* DB-level uniqueness for *keyless* rows — Postgres treats NULLs as distinct,
  so the (source_annotation, reference_type, canonical_key) constraint alone
  does not stop concurrent writers from duplicating refs with no canonical
  key. A partial unique constraint closes that hole.
* ``reference_type`` must agree with the mention's ``OC_REF_*`` label —
  the column denormalizes the label for indexing, and the two must never
  drift apart.
"""

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from opencontractserver.annotations.models import (
    SPAN_LABEL,
    Annotation,
    CorpusReference,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.services import CorpusReferenceService

User = get_user_model()


class CorpusReferenceIntegrityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="p")
        self.corpus = Corpus.objects.create(title="Corpus", creator=self.user)
        self.doc = Document.objects.create(title="Doc", creator=self.user)

    def _mention(self, label_text: str, start: int = 0) -> Annotation:
        label = self.corpus.ensure_label_and_labelset(
            label_text=label_text, creator_id=self.user.id, label_type=SPAN_LABEL
        )
        return Annotation.objects.create(
            raw_text="mention",
            page=1,
            json={"start": start, "end": start + 7},
            annotation_label=label,
            document_id=self.doc.id,
            corpus=self.corpus,
            creator=self.user,
            annotation_type=SPAN_LABEL,
        )

    def test_duplicate_keyless_reference_rejected_at_db_level(self):
        """Two rows with the same (source_annotation, reference_type) and a
        NULL canonical_key must violate a DB constraint — get_or_create only
        guards a single process, not concurrent runs."""
        mention = self._mention(C.LABEL_REF_SECTION)
        CorpusReference.objects.create(
            corpus=self.corpus,
            reference_type=C.REF_SECTION,
            source_annotation=mention,
            canonical_key=None,
            resolution_status=C.STATUS_UNRESOLVED,
            creator=self.user,
        )
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                CorpusReference.objects.create(
                    corpus=self.corpus,
                    reference_type=C.REF_SECTION,
                    source_annotation=mention,
                    canonical_key=None,
                    resolution_status=C.STATUS_UNRESOLVED,
                    creator=self.user,
                )

    def test_reference_type_must_agree_with_mention_label(self):
        """``reference_type`` denormalizes the mention's OC_REF_* label for
        indexing — creating a row where the two disagree must raise."""
        from django.core.exceptions import ValidationError

        law_mention = self._mention(C.LABEL_REF_LAW)
        with self.assertRaises(ValidationError):
            CorpusReference.objects.create(
                corpus=self.corpus,
                reference_type=C.REF_DOCUMENT,  # disagrees with OC_REF_LAW
                source_annotation=law_mention,
                canonical_key="exhibit:1.1",
                resolution_status=C.STATUS_UNRESOLVED,
                creator=self.user,
            )

    def test_reference_type_agreeing_with_label_saves(self):
        law_mention = self._mention(C.LABEL_REF_LAW, start=10)
        ref = CorpusReference.objects.create(
            corpus=self.corpus,
            reference_type=C.REF_LAW,
            source_annotation=law_mention,
            canonical_key="dgcl:145",
            resolution_status=C.STATUS_EXTERNAL,
            creator=self.user,
        )
        assert ref.pk is not None

    def test_distinct_keyed_references_still_allowed(self):
        """The partial constraint must not block legitimate keyed rows on the
        same mention (different canonical keys)."""
        mention = self._mention(C.LABEL_REF_LAW)
        for key in ("dgcl:145", "dgcl:203"):
            CorpusReference.objects.create(
                corpus=self.corpus,
                reference_type=C.REF_LAW,
                source_annotation=mention,
                canonical_key=key,
                resolution_status=C.STATUS_EXTERNAL,
                creator=self.user,
            )
        assert CorpusReference.objects.filter(source_annotation=mention).count() == 2


class CorpusReferenceVisibilityTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner2", password="p")
        self.viewer = User.objects.create_user(username="viewer", password="p")
        self.corpus = Corpus.objects.create(
            title="Readable Corpus", creator=self.owner, is_public=True
        )
        self.visible_doc = Document.objects.create(
            title="Visible Doc", creator=self.owner, is_public=True
        )
        self.private_source_doc = Document.objects.create(
            title="Private Source", creator=self.owner, is_public=False
        )
        self.private_target_doc = Document.objects.create(
            title="Private Target", creator=self.owner, is_public=False
        )
        self.private_target_corpus = Corpus.objects.create(
            title="Private Authority", creator=self.owner, is_public=False
        )
        self.label = self.corpus.ensure_label_and_labelset(
            label_text=C.LABEL_REF_LAW,
            creator_id=self.owner.id,
            label_type=SPAN_LABEL,
        )

    def _mention(self, document: Document, start: int = 0) -> Annotation:
        return Annotation.objects.create(
            raw_text="mention",
            page=1,
            json={"start": start, "end": start + 7},
            annotation_label=self.label,
            document_id=document.id,
            corpus=self.corpus,
            creator=self.owner,
            annotation_type=SPAN_LABEL,
        )

    def _reference(self, mention: Annotation, **kwargs) -> CorpusReference:
        defaults = {
            "corpus": self.corpus,
            "reference_type": C.REF_LAW,
            "source_annotation": mention,
            "canonical_key": f"dgcl:{mention.id}",
            "resolution_status": C.STATUS_EXTERNAL,
            "creator": self.owner,
        }
        defaults.update(kwargs)
        return CorpusReference.objects.create(**defaults)

    def test_visible_to_user_requires_visible_source_document(self):
        ref = self._reference(self._mention(self.private_source_doc))

        assert (
            not CorpusReferenceService.visible_to_user(self.viewer)
            .filter(pk=ref.pk)
            .exists()
        )

    def test_visible_to_user_requires_visible_target_document(self):
        ref = self._reference(
            self._mention(self.visible_doc), target_document=self.private_target_doc
        )

        assert (
            not CorpusReferenceService.visible_to_user(self.viewer)
            .filter(pk=ref.pk)
            .exists()
        )

    def test_visible_to_user_requires_visible_target_corpus(self):
        ref = self._reference(
            self._mention(self.visible_doc), target_corpus=self.private_target_corpus
        )

        assert (
            not CorpusReferenceService.visible_to_user(self.viewer)
            .filter(pk=ref.pk)
            .exists()
        )

    def test_visible_to_user_returns_reference_when_all_edges_visible(self):
        ref = self._reference(self._mention(self.visible_doc))

        assert (
            CorpusReferenceService.visible_to_user(self.viewer)
            .filter(pk=ref.pk)
            .exists()
        )

    def test_visible_to_user_by_source_retains_hidden_target_for_ghosting(self):
        # A reference with a visible source but a hidden target document is
        # dropped by the strict ``visible_to_user`` (which backs the
        # ``corpusReferences`` GraphQL surface that exposes target FKs) but
        # RETAINED by ``visible_to_user_by_source`` so aggregate consumers (the
        # governance graph) can degrade the hidden target to a ghost node rather
        # than losing the citation entirely.
        ref = self._reference(
            self._mention(self.visible_doc), target_document=self.private_target_doc
        )

        assert (
            not CorpusReferenceService.visible_to_user(self.viewer)
            .filter(pk=ref.pk)
            .exists()
        )
        assert (
            CorpusReferenceService.visible_to_user_by_source(self.viewer)
            .filter(pk=ref.pk)
            .exists()
        )

    def test_visible_to_user_by_source_still_requires_visible_source(self):
        # The source-privacy guard is preserved by the source-only variant: a
        # citation made by a hidden document is never surfaced.
        ref = self._reference(self._mention(self.private_source_doc))

        assert (
            not CorpusReferenceService.visible_to_user_by_source(self.viewer)
            .filter(pk=ref.pk)
            .exists()
        )
