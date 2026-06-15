"""The 0083 data migration classifies existing law references by prefix."""

from importlib import import_module

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


class BackfillClassificationTests(TestCase):
    def _ref(self, key, **extra):
        user = User.objects.create_user(username=f"u{key}", password="p")
        corpus = Corpus.objects.create(title="C", creator=user)
        doc = Document.objects.create(title="D", creator=user)
        label = corpus.ensure_label_and_labelset(
            label_text=C.LABEL_REF_LAW, creator_id=user.id, label_type=SPAN_LABEL
        )
        ann = Annotation.objects.create(
            raw_text=key, page=1, json={"start": 0, "end": 3},
            annotation_label=label, document=doc, corpus=corpus,
            creator=user, annotation_type=SPAN_LABEL,
        )
        return CorpusReference.objects.create(
            corpus=corpus, reference_type=C.REF_LAW, source_annotation=ann,
            canonical_key=key, resolution_status=C.STATUS_EXTERNAL, creator=user,
            **extra,
        )

    def test_backfill_function_classifies_known_prefixes(self):
        mod = import_module(
            "opencontractserver.annotations.migrations."
            "0083_backfill_corpusreference_classification"
        )
        ref = self._ref("dgcl:145")
        CorpusReference.objects.filter(pk=ref.pk).update(
            jurisdiction=None, authority_type=None
        )
        from django.apps import apps

        mod.backfill(apps, None)
        ref.refresh_from_db()
        assert ref.jurisdiction == "us-de"
        assert ref.authority_type == "statute"

    def test_unknown_prefix_left_null(self):
        mod = import_module(
            "opencontractserver.annotations.migrations."
            "0083_backfill_corpusreference_classification"
        )
        ref = self._ref("mystery-code:1")
        from django.apps import apps

        mod.backfill(apps, None)
        ref.refresh_from_db()
        assert ref.jurisdiction is None
        assert ref.authority_type is None
