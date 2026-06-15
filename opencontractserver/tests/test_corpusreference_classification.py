"""CorpusReference carries jurisdiction + authority_type (Phase 0)."""

from django.contrib.auth import get_user_model
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


class CorpusReferenceClassificationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="t", password="p")
        self.corpus = Corpus.objects.create(title="C", creator=self.user)
        self.doc = Document.objects.create(title="D", creator=self.user)
        label = self.corpus.ensure_label_and_labelset(
            label_text=C.LABEL_REF_LAW, creator_id=self.user.id, label_type=SPAN_LABEL
        )
        self.mention = Annotation.objects.create(
            raw_text="15 U.S.C. § 78j(b)",
            page=1,
            json={"start": 0, "end": 18},
            annotation_label=label,
            document=self.doc,
            corpus=self.corpus,
            creator=self.user,
            annotation_type=SPAN_LABEL,
        )

    def test_fields_persist_and_default_null(self):
        ref = CorpusReference.objects.create(
            corpus=self.corpus,
            reference_type=C.REF_LAW,
            source_annotation=self.mention,
            canonical_key="usc-15:78j(b)",
            resolution_status=C.STATUS_EXTERNAL,
            jurisdiction=C.JURISDICTION_US_FEDERAL,
            authority_type=C.AUTHORITY_TYPE_STATUTE,
            creator=self.user,
        )
        ref.refresh_from_db()
        assert ref.jurisdiction == "us-federal"
        assert ref.authority_type == "statute"

    def test_classification_is_optional(self):
        ref = CorpusReference.objects.create(
            corpus=self.corpus,
            reference_type=C.REF_LAW,
            source_annotation=self.mention,
            canonical_key="x:1",
            resolution_status=C.STATUS_EXTERNAL,
            creator=self.user,
        )
        assert ref.jurisdiction is None
        assert ref.authority_type is None
