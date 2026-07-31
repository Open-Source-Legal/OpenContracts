"""Cross-corpus hits must carry a citable, version-correct authority identity.

Authority corpora annotate *structurally*: every annotation has
``document_id=None`` and reaches its document through a shared
``StructuralAnnotationSet``. The search tool therefore used to hand the model
hits with no document at all, which is how a conclusion ended up cited as
"paragraph p.0" instead of a rule section with an effective date.

The version-correctness case below is the one that matters most: a structural
set is shared by every sibling in a version tree, so resolving carelessly can
cite a superseded rule as though it were current — the exact error this corpus
design exists to prevent.
"""

from __future__ import annotations

from django.test import TestCase
from django.utils import timezone

from opencontractserver.annotations.models import (
    Annotation,
    StructuralAnnotationSet,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.llms.tools.core_tools.multi_corpus import (
    _authority_citation_fields,
    _documents_by_structural_set,
)
from opencontractserver.users.models import User


class MultiCorpusCitationFieldsTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="cite-user", password="x")
        self.corpus = Corpus.objects.create(
            title="Authority Corpus", creator=self.user, is_public=False
        )
        self.structural_set = StructuralAnnotationSet.objects.create(creator=self.user)

    def _document(self, title: str, *, meta: dict, is_current: bool, version: int):
        document = Document.objects.create(
            title=title,
            creator=self.user,
            file_type="text/plain",
            custom_meta=meta,
            is_current=is_current,
            structural_annotation_set=self.structural_set,
            processing_started=timezone.now(),
        )
        DocumentPath.objects.create(
            document=document,
            corpus=self.corpus,
            path="/planning-guide-9",
            version_number=version,
            is_current=is_current,
            is_deleted=False,
            creator=self.user,
        )
        return document

    def test_extracts_the_citable_authority_identity(self):
        document = self._document(
            "ERCOT Planning Guide Section 9",
            meta={
                "canonical_key": "ercot-planning:9.2.1.1",
                "authority_weight": "CONTROLLING",
                "publisher": "Electric Reliability Council of Texas",
                "status": "CURRENT",
                "effective_from": "2026-07-11",
                "version_label": "2026-07-11",
                "current_version": True,
                "metadata": {"instrument_type": "PLANNING_GUIDE"},
            },
            is_current=True,
            version=2,
        )

        fields = _authority_citation_fields(document)
        self.assertEqual(fields["canonical_key"], "ercot-planning:9.2.1.1")
        self.assertEqual(fields["authority_weight"], "CONTROLLING")
        self.assertEqual(fields["effective_from"], "2026-07-11")
        # The section falls out of the canonical key rather than being guessed.
        self.assertEqual(fields["section"], "9.2.1.1")
        # ``instrument_type`` is nested for pack-built records; surfaced anyway.
        self.assertEqual(fields["instrument_type"], "PLANNING_GUIDE")

    def test_omits_absent_fields_rather_than_emitting_nulls(self):
        """An ordinary upload has no authority identity; nulls invite the model
        to cite empty fields as if they were real."""
        plain = Document.objects.create(
            title="Some upload",
            creator=self.user,
            file_type="application/pdf",
            custom_meta={},
            processing_started=timezone.now(),
        )
        self.assertEqual(_authority_citation_fields(plain), {})
        self.assertEqual(_authority_citation_fields(None), {})

    def test_resolves_structural_annotations_to_the_CURRENT_document(self):
        superseded = self._document(
            "ERCOT Planning Guide Section 9",
            meta={"canonical_key": "ercot-planning:9", "status": "SUPERSEDED"},
            is_current=False,
            version=1,
        )
        current = self._document(
            "ERCOT Planning Guide Section 9",
            meta={
                "canonical_key": "ercot-planning:9",
                "status": "CURRENT",
                "effective_from": "2026-07-11",
            },
            is_current=True,
            version=2,
        )

        resolved = _documents_by_structural_set(
            {self.structural_set.pk}, self.corpus.pk
        )

        # Both siblings share the set; only the current one may be cited.
        self.assertEqual(resolved[self.structural_set.pk].pk, current.pk)
        self.assertNotEqual(resolved[self.structural_set.pk].pk, superseded.pk)
        self.assertEqual(
            _authority_citation_fields(resolved[self.structural_set.pk])["status"],
            "CURRENT",
        )

    def test_structural_annotation_can_be_attributed_at_all(self):
        """Regression: these annotations carry no document_id of their own."""
        document = self._document(
            "ERCOT Planning Guide Section 9",
            meta={"canonical_key": "ercot-planning:9"},
            is_current=True,
            version=1,
        )
        annotation = Annotation.objects.create(
            raw_text="Batch Zero applies from July 11, 2026.",
            corpus=self.corpus,
            structural=True,
            structural_set=self.structural_set,
            creator=self.user,
        )

        self.assertIsNone(annotation.document_id)
        resolved = _documents_by_structural_set(
            {annotation.structural_set_id}, self.corpus.pk
        )
        self.assertEqual(resolved[annotation.structural_set_id].pk, document.pk)

    def test_ignores_sets_whose_document_is_not_in_this_corpus(self):
        other_corpus = Corpus.objects.create(
            title="Elsewhere", creator=self.user, is_public=False
        )
        self._document(
            "ERCOT Planning Guide Section 9",
            meta={"canonical_key": "ercot-planning:9"},
            is_current=True,
            version=1,
        )

        self.assertEqual(
            _documents_by_structural_set({self.structural_set.pk}, other_corpus.pk),
            {},
        )
