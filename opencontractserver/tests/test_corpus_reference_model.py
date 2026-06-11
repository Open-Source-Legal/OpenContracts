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
