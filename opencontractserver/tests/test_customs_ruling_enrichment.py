"""DB-backed tests for :class:`CustomsRulingCitationService`.

Regression suite for the PR 2153 CROSS TXT zero-output failure
(``docs/benchmarks/pr2153-cross-txt-enrichment-handoff.md``): the official
CROSS bulk exporter emits ``text/plain`` documents whose valid SPAN anchoring
was rejected by an eligibility gate before either detection regex ran, so a
10,000-document run produced zero annotations, references, and graph edges.

Covers the handoff's required tests:

* the loader's TXT contract (text + ``None`` + ``SPAN_LABEL``);
* a two-document TXT corpus producing HTS span annotations (``page=0``,
  canonical ``{start, end, text}`` json), an ``OC_REF_DOC`` span mention, a
  resolved ``CorpusReference`` and one ``DocumentRelationship`` edge;
* unresolved citations (reference row, no edge);
* path-derived ruling identity (subject titles, title collisions, control
  characters, ``external_id`` priority, title-stem fallback, and ambiguous
  identities reported rather than silently overwritten);
* rerun idempotency across both anchor representations;
* the PDF/TOKEN branch preserved unchanged (mixed corpus);
* the renamed skip metric counting only genuine load failures;
* reconciliation policy for importer-style sidecar rows (SPAN annotations
  attached to a TOKEN-typed label — the documented import-contract mismatch).

The regex/normalization unit tests live in
``test_customs_ruling_citation_service.py``; this module is the DB-backed
integration boundary those tests cannot see.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, TransactionTestCase

from opencontractserver.annotations.models import (
    SPAN_LABEL,
    TOKEN_LABEL,
    Annotation,
    CorpusReference,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import (
    Document,
    DocumentPath,
    DocumentRelationship,
)
from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.services.customs_ruling_citation_service import (
    LABEL_HTS_CODE,
    CustomsRulingCitationService,
)

User = get_user_model()

# Two sibling rulings: DOC1 cites DOC2 by prefixed ruling number and carries a
# 10-digit HTS code; DOC2 carries its own 8-digit HTS code. Titles are the
# human-readable SUBJECTS (the official exporter's ``meta.csv`` shape), so any
# resolution below must come from the document's corpus path, not its title.
DOC1_BODY = (
    "NY H100001\n\n"
    "The merchandise, plastic serving trays, is classifiable under "
    "subheading 3924.90.5650, HTSUS. This conclusion is consistent with "
    "the analysis in HQ H100002, dated March 4, 2010."
)
DOC2_BODY = (
    "HQ H100002\n\n"
    "The applicable subheading for the kitchenware will be 8703.23.01, "
    "HTSUS."
)


def _make_txt_doc(user, corpus, *, title, path, body, external_id=""):
    doc = Document.objects.create(
        title=title,
        creator=user,
        file_type="text/plain",
    )
    doc.txt_extract_file.save("extract.txt", ContentFile(body.encode("utf-8")))
    DocumentPath.objects.create(
        document=doc,
        corpus=corpus,
        path=path,
        version_number=1,
        external_id=external_id,
        creator=user,
    )
    return doc


class _CustomsEnrichmentTestBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="cbp", password="p")
        self.corpus = Corpus.objects.create(title="CROSS Rulings", creator=self.user)

    def _run(self, **kwargs):
        return CustomsRulingCitationService.enrich_corpus(
            corpus_id=self.corpus.id, creator_id=self.user.id, **kwargs
        )

    def _annotations(self, label_text, document=None):
        qs = Annotation.objects.filter(
            corpus=self.corpus, annotation_label__text=label_text
        )
        if document is not None:
            qs = qs.filter(document=document)
        return qs

    def _references(self):
        return CorpusReference.objects.filter(
            corpus=self.corpus, reference_type=C.REF_DOCUMENT
        )

    def _edges(self):
        return DocumentRelationship.objects.filter(
            corpus=self.corpus, relationship_type=C.DOC_REL_RELATIONSHIP
        )


class TxtSpanEnrichmentTests(_CustomsEnrichmentTestBase):
    """The two-document TXT regression fixture from the handoff report."""

    def setUp(self):
        super().setUp()
        self.doc1 = _make_txt_doc(
            self.user,
            self.corpus,
            title="Plastic serving trays from China",
            path="/HQ/H100001.txt",
            body=DOC1_BODY,
        )
        self.doc2 = _make_txt_doc(
            self.user,
            self.corpus,
            title="Tariff classification of plastic kitchenware",
            path="/HQ/H100002.txt",
            body=DOC2_BODY,
        )

    def test_txt_documents_are_processed_not_skipped(self):
        """The zero-output repro: before the fix every TXT document was
        skipped as "not PDF" before either regex ran."""
        res = self._run()

        assert res["documents_scanned"] == 2
        assert res["documents_skipped_unanchorable"] == 0
        assert res["hts_codes_created"] == 2
        assert res["citations_resolved"] == 1
        assert res["references_created"] == 1
        assert res["document_relationships_created"] == 1
        # Per-phase instrumentation (handoff §E): storage, regex, and DB cost
        # are recorded separately; a real run spends measurable time in each.
        assert res["load_failures"] == 0
        assert res["load_seconds"] > 0
        assert res["match_seconds"] >= 0
        assert res["write_seconds"] > 0

    def test_hts_span_annotation_shape_and_provenance(self):
        res = self._run()

        start = DOC1_BODY.find("3924.90.5650")
        end = start + len("3924.90.5650")
        ann = self._annotations(LABEL_HTS_CODE, document=self.doc1).get()

        assert ann.annotation_type == SPAN_LABEL
        assert ann.annotation_label.label_type == SPAN_LABEL
        # Canonical text-span shape (annotation_anchoring._anchor_text):
        # page 0 is the no-page sentinel the frontend suppresses.
        assert ann.page == 0
        assert ann.json == {"start": start, "end": end, "text": "3924.90.5650"}
        assert ann.raw_text == "3924.90.5650"
        assert ann.data["code"] == "3924.90.56.50"
        assert ann.data["char_span"] == {"start": start, "end": end}
        # Run provenance: HTS rows carry the service's Analysis like the
        # citation mentions always did.
        assert ann.analysis_id == res["analysis_id"]

    def test_citation_span_mention_reference_and_edge(self):
        self._run()

        mention = self._annotations(C.LABEL_REF_DOC, document=self.doc1).get()
        start = DOC1_BODY.find("H100002")
        assert mention.annotation_type == SPAN_LABEL
        assert mention.page == 0
        assert mention.json == {
            "start": start,
            "end": start + len("H100002"),
            "text": "H100002",
        }

        ref = self._references().get()
        assert ref.source_annotation_id == mention.id
        assert ref.resolution_status == C.STATUS_RESOLVED
        assert ref.target_document_id == self.doc2.id
        assert ref.is_provisional is False

        edge = self._edges().get()
        assert edge.source_document_id == self.doc1.id
        assert edge.target_document_id == self.doc2.id

    def test_rerun_is_idempotent_for_span_representations(self):
        first = self._run()
        assert first["hts_codes_created"] == 2

        counts = (
            self._annotations(LABEL_HTS_CODE).count(),
            self._annotations(C.LABEL_REF_DOC).count(),
            self._references().count(),
            self._edges().count(),
        )

        second = self._run()
        assert second["hts_codes_created"] == 0
        assert second["references_created"] == 0
        assert second["document_relationships_created"] == 0
        assert counts == (
            self._annotations(LABEL_HTS_CODE).count(),
            self._annotations(C.LABEL_REF_DOC).count(),
            self._references().count(),
            self._edges().count(),
        )


class LegacyBareNumberCorpusTests(_CustomsEnrichmentTestBase):
    """The official export's legacy HQ/NY slice: bare zero-padded numeric
    ruling numbers (path ``HQ/084665.txt``), cited in text via series tokens
    ("HRL 087392") — the shape the prefixed grammar alone cannot see."""

    def setUp(self):
        super().setUp()
        self.doc1 = _make_txt_doc(
            self.user,
            self.corpus,
            title="Gasket material classification",
            path="/HQ/084665.txt",
            body=(
                "HQ 084665\n\n"
                "375 Fifth Avenue, New York, NY  10176\n\n"
                "Upon further consideration, HRL 087392 is deemed correct "
                "and HQ 555555 does not control."
            ),
        )
        self.doc2 = _make_txt_doc(
            self.user,
            self.corpus,
            title="Reconsideration of gasket ruling",
            path="/HQ/087392.txt",
            body="HQ 087392\n\nDecision text.",
        )

    def test_legacy_series_token_citations_resolve(self):
        res = self._run()

        # Two citations mined (HRL 087392 + HQ 555555); the ZIP code and the
        # document's own header number are not.
        assert res["citation_candidates"] == 2
        assert res["citations_resolved"] == 1
        assert res["citations_unresolved"] == 1

        mentions = self._annotations(C.LABEL_REF_DOC, document=self.doc1)
        assert {m.raw_text for m in mentions} == {"HRL 087392", "HQ 555555"}

        resolved = self._references().get(resolution_status=C.STATUS_RESOLVED)
        assert resolved.target_document_id == self.doc2.id
        edge = self._edges().get()
        assert edge.source_document_id == self.doc1.id
        assert edge.target_document_id == self.doc2.id

    def test_zero_padding_variance_still_resolves(self):
        """Identity ``084665`` and a citation padded differently agree on
        one canonical key (leading zeros stripped on both sides)."""
        _make_txt_doc(
            self.user,
            self.corpus,
            title="Third ruling",
            path="/NY/812345.txt",
            body="NY 812345\n\nWe reach the same result as HQ 084665.",
        )

        self._run()

        refs = self._references().filter(resolution_status=C.STATUS_RESOLVED)
        assert refs.filter(target_document_id=self.doc1.id).exists()


class SpanMentionHealTests(_CustomsEnrichmentTestBase):
    """Pre-fix span mentions carried ``page=1`` and no ``text`` anchor;
    re-running enrichment converges them on the canonical shape IN PLACE
    (same row — CorpusReference FKs survive), mirroring the writer's
    span→token backfill for PDFs."""

    def setUp(self):
        super().setUp()
        self.doc1 = _make_txt_doc(
            self.user,
            self.corpus,
            title="Plastic serving trays from China",
            path="/HQ/H100001.txt",
            body=DOC1_BODY,
        )
        _make_txt_doc(
            self.user,
            self.corpus,
            title="Tariff classification of plastic kitchenware",
            path="/HQ/H100002.txt",
            body=DOC2_BODY,
        )

    def test_rerun_heals_prefix_shaped_span_mention(self):
        self._run()
        mention = self._annotations(C.LABEL_REF_DOC, document=self.doc1).get()
        ref_id = self._references().get().id
        # Regress the row to the pre-fix shape (page=1, no text key).
        Annotation.objects.filter(pk=mention.pk).update(
            page=1,
            json={"start": mention.json["start"], "end": mention.json["end"]},
        )

        self._run()

        mention.refresh_from_db()
        assert mention.page == 0
        assert mention.json["text"] == "H100002"
        # Healed in place: the reference still hangs off the same row.
        assert self._references().get().id == ref_id
        assert self._annotations(C.LABEL_REF_DOC, document=self.doc1).count() == 1


class UnresolvedCitationTests(_CustomsEnrichmentTestBase):
    def test_absent_ruling_creates_unresolved_reference_and_no_edge(self):
        _make_txt_doc(
            self.user,
            self.corpus,
            title="Footwear classification",
            path="/HQ/H500001.txt",
            body="HQ H500001\n\nWe considered NY H999999 in reaching this result.",
        )

        res = self._run()

        assert res["citations_unresolved"] == 1
        ref = self._references().get()
        assert ref.resolution_status == C.STATUS_UNRESOLVED
        assert ref.target_document_id is None
        assert not self._edges().exists()


class LoaderContractTests(_CustomsEnrichmentTestBase):
    def test_text_plain_returns_text_none_span(self):
        from opencontractserver.utils.span_projection import (
            load_document_text_and_layer,
        )

        doc = _make_txt_doc(
            self.user,
            self.corpus,
            title="Anything",
            path="/HQ/H600001.txt",
            body=DOC1_BODY,
        )

        text, layer, ann_type = load_document_text_and_layer(doc)
        assert text == DOC1_BODY
        assert layer is None
        assert ann_type == SPAN_LABEL


class PathIdentityTests(_CustomsEnrichmentTestBase):
    """Canonical ruling identity comes from the corpus path / external_id,
    never from the display title (official-export titles are subjects — they
    collide, carry control characters, and never contain the ruling number)."""

    def test_colliding_control_character_titles_still_resolve(self):
        messy_title = "Tariff classification;\x07 polyester gloves"
        doc1 = _make_txt_doc(
            self.user,
            self.corpus,
            title=messy_title,
            path="/HQ/H700001.txt",
            body="HQ H700001\n\nSee NY H700002 for the analogous analysis.",
        )
        doc2 = _make_txt_doc(
            self.user,
            self.corpus,
            title=messy_title,  # identical display title — must not matter
            path="/NY/H700002.txt",
            body="NY H700002\n\nClassification under 6116.93.8800, HTSUS.",
        )

        res = self._run()

        assert res["canonical_id_collisions"] == 0
        ref = self._references().get()
        assert ref.resolution_status == C.STATUS_RESOLVED
        assert ref.target_document_id == doc2.id
        assert self._edges().get().source_document_id == doc1.id

    def test_external_id_namespace_match_is_case_insensitive(self):
        """Producers vary the namespace case (CROSS's house style is
        uppercase); a case-variant prefix must not be silently ignored."""
        _make_txt_doc(
            self.user,
            self.corpus,
            title="Source ruling",
            path="/HQ/H760001.txt",
            body="HQ H760001\n\nConsistent with HQ H760002.",
        )
        renamed = _make_txt_doc(
            self.user,
            self.corpus,
            title="Renamed after import",
            path="/HQ/opaque-name.txt",
            body="HQ H760002\n\nDecision text.",
            external_id="CROSS:H760002",
        )

        self._run()

        ref = self._references().get()
        assert ref.resolution_status == C.STATUS_RESOLVED
        assert ref.target_document_id == renamed.id

    def test_external_id_takes_priority_over_path_basename(self):
        _make_txt_doc(
            self.user,
            self.corpus,
            title="Source ruling",
            path="/HQ/H710001.txt",
            body="HQ H710001\n\nConsistent with HQ H710002.",
        )
        renamed = _make_txt_doc(
            self.user,
            self.corpus,
            title="Renamed after import",
            path="/HQ/some-renamed-file.txt",  # basename no longer the number
            body="HQ H710002\n\nOriginal decision text.",
            external_id="cross:H710002",
        )

        self._run()

        ref = self._references().get()
        assert ref.resolution_status == C.STATUS_RESOLVED
        assert ref.target_document_id == renamed.id

    def test_title_stem_is_backward_compatible_fallback(self):
        """Legacy ingests titled documents with the materialized filename;
        when neither external_id nor the path basename carries a ruling
        number, the title stem still resolves."""
        _make_txt_doc(
            self.user,
            self.corpus,
            title="Source ruling",
            path="/HQ/H720001.txt",
            body="HQ H720001\n\nWe reach the same result as HQ H720002.",
        )
        legacy = _make_txt_doc(
            self.user,
            self.corpus,
            title="H720002.doc",
            path="/HQ/plastic trays ruling.txt",
            body="HQ H720002\n\nDecision text.",
        )

        self._run()

        ref = self._references().get()
        assert ref.resolution_status == C.STATUS_RESOLVED
        assert ref.target_document_id == legacy.id

    def test_duplicate_identities_reported_and_left_unresolved(self):
        """Two documents normalizing to the same ruling number is ambiguity,
        not a last-write-wins lottery: the citation stays unresolved and the
        collision is surfaced in the summary."""
        _make_txt_doc(
            self.user,
            self.corpus,
            title="Source ruling",
            path="/HQ/H730001.txt",
            body="HQ H730001\n\nSee HQ H730002.",
        )
        _make_txt_doc(
            self.user,
            self.corpus,
            title="First twin",
            path="/HQ/H730002.txt",
            body="First twin body.",
        )
        _make_txt_doc(
            self.user,
            self.corpus,
            title="Second twin",
            path="/NY/H730002.txt",
            body="Second twin body.",
        )

        res = self._run()

        assert res["canonical_id_collisions"] == 1
        ref = self._references().get()
        assert ref.resolution_status == C.STATUS_UNRESOLVED
        assert ref.target_document_id is None
        assert not self._edges().exists()


class SkipMetricTests(_CustomsEnrichmentTestBase):
    def test_only_genuine_load_failures_count_as_skipped(self):
        # Healthy TXT document — must be processed, not skipped.
        _make_txt_doc(
            self.user,
            self.corpus,
            title="Healthy",
            path="/HQ/H800001.txt",
            body=DOC1_BODY,
        )
        # text/plain but no txt_extract_file: the loader raises.
        broken = Document.objects.create(
            title="Broken", creator=self.user, file_type="text/plain"
        )
        DocumentPath.objects.create(
            document=broken,
            corpus=self.corpus,
            path="/HQ/H800002.txt",
            version_number=1,
            creator=self.user,
        )
        # Unsupported file type: the loader raises.
        unsupported = Document.objects.create(
            title="Image", creator=self.user, file_type="image/png"
        )
        DocumentPath.objects.create(
            document=unsupported,
            corpus=self.corpus,
            path="/HQ/scan.png",
            version_number=1,
            creator=self.user,
        )

        res = self._run()

        assert res["documents_scanned"] == 3
        assert res["documents_skipped_unanchorable"] == 2
        assert res["load_failures"] == 2  # both skips were loader failures
        assert res["hts_codes_created"] == 1  # the healthy document still ran


class PdfTokenBranchTests(_CustomsEnrichmentTestBase):
    """PDF documents keep the TOKEN branch: the fix adds a span branch, it
    must not downgrade PDFs to spans. Mixed PDF+TXT corpus on purpose."""

    PAGES = [
        "HQ H900001 rules that the vehicles are classified under "
        "subheading 8703.23.01, HTSUS.",
        "This is consistent with NY H900002, which we decline to revoke.",
    ]

    def setUp(self):
        from plasmapdf.models.PdfDataLayer import build_translation_layer

        from opencontractserver.tests.test_extraction_grounding import (
            _build_pawls_for_text,
        )

        super().setUp()

        pawls_json = _build_pawls_for_text(self.PAGES)
        layer = build_translation_layer(json.loads(pawls_json))

        self.pdf_doc = Document.objects.create(
            title="Motor vehicle classification",
            creator=self.user,
            file_type="application/pdf",
        )
        self.pdf_doc.pawls_parse_file.save(
            "doc.pawls", ContentFile(pawls_json.encode("utf-8"))
        )
        self.pdf_doc.txt_extract_file.save(
            "doc.txt", ContentFile(layer.doc_text.encode("utf-8"))
        )
        DocumentPath.objects.create(
            document=self.pdf_doc,
            corpus=self.corpus,
            path="/HQ/H900001.pdf",
            version_number=1,
            creator=self.user,
        )
        self.txt_doc = _make_txt_doc(
            self.user,
            self.corpus,
            title="Sibling ruling",
            path="/NY/H900002.txt",
            body="NY H900002\n\nDecision text.",
        )

    def test_pdf_documents_still_produce_token_annotations(self):
        res = self._run()

        assert res["documents_skipped_unanchorable"] == 0

        hts = self._annotations(LABEL_HTS_CODE, document=self.pdf_doc).get()
        assert hts.annotation_type == TOKEN_LABEL
        assert hts.annotation_label.label_type == TOKEN_LABEL
        # Token payload: page-keyed PAWLS dict, NOT a char span.
        assert "start" not in hts.json
        assert hts.data["code"] == "8703.23.01"
        assert hts.analysis_id == res["analysis_id"]

        mention = self._annotations(C.LABEL_REF_DOC, document=self.pdf_doc).get()
        assert mention.annotation_type == TOKEN_LABEL
        # The citation sits on the second page — a hardcoded page would flunk.
        assert mention.page == 1

        ref = self._references().get()
        assert ref.resolution_status == C.STATUS_RESOLVED
        assert ref.target_document_id == self.txt_doc.id
        assert self._edges().count() == 1


class SidecarReconciliationTests(_CustomsEnrichmentTestBase):
    """Explicit policy for importer-style sidecar rows (handoff root cause 4).

    The official exporter ships producer labels as TOKEN_LABEL (the import
    contract's requirement) while the text anchorer stores the annotation as
    a SPAN — so real corpora contain SPAN annotations attached to TOKEN-typed
    ``HTS_CODE`` / ``CITED_RULING`` labels. Policy under test:

    * legacy producer HTS spans are retained as source evidence and deduped
      against by label TEXT across both representations — enrichment never
      paints a duplicate highlight, and never rewrites their label type;
    * citations get a dedicated, correctly-labelled ``OC_REF_DOC`` mention
      plus its ``CorpusReference`` while the producer's ``CITED_RULING``
      span is retained untouched (the reference is never attached to
      ``CITED_RULING`` — that would violate the CorpusReference invariant).
    """

    BODY = (
        "HQ H310001\n\n"
        "The applicable subheading is 6307.90.9889, HTSUS, and the rate "
        "under 3924.90.5650, HTSUS also applies. See NY H310002."
    )

    def setUp(self):
        super().setUp()
        self.doc1 = _make_txt_doc(
            self.user,
            self.corpus,
            title="Textile articles",
            path="/HQ/H310001.txt",
            body=self.BODY,
        )
        self.doc2 = _make_txt_doc(
            self.user,
            self.corpus,
            title="Sibling",
            path="/NY/H310002.txt",
            body="NY H310002\n\nDecision.",
        )

        # Importer-style rows: SPAN annotations attached to TOKEN-typed labels
        # (test_zip_import_integration documents this intentional mismatch).
        hts_token_label = self.corpus.ensure_label_and_labelset(
            label_text=LABEL_HTS_CODE,
            creator_id=self.user.id,
            label_type=TOKEN_LABEL,
        )
        start = self.BODY.find("6307.90.9889")
        end = start + len("6307.90.9889")
        self.legacy_hts = Annotation.objects.create(
            raw_text="6307.90.9889",
            page=0,
            json={"start": start, "end": end, "text": "6307.90.9889"},
            annotation_label=hts_token_label,
            document=self.doc1,
            corpus=self.corpus,
            creator=self.user,
            annotation_type=SPAN_LABEL,
        )
        cited_label = self.corpus.ensure_label_and_labelset(
            label_text="CITED_RULING",
            creator_id=self.user.id,
            label_type=TOKEN_LABEL,
        )
        cite_start = self.BODY.find("H310002")
        cite_end = cite_start + len("H310002")
        self.legacy_cite = Annotation.objects.create(
            raw_text="H310002",
            page=0,
            json={"start": cite_start, "end": cite_end, "text": "H310002"},
            annotation_label=cited_label,
            document=self.doc1,
            corpus=self.corpus,
            creator=self.user,
            annotation_type=SPAN_LABEL,
        )

    def test_legacy_sidecar_rows_are_respected_not_duplicated(self):
        res = self._run()

        # The legacy HTS span suppressed a duplicate enrichment highlight at
        # its offset; the second (uncovered) code was still created — with a
        # correctly SPAN-typed label row, not the legacy TOKEN-typed one.
        hts_anns = list(self._annotations(LABEL_HTS_CODE, document=self.doc1))
        assert res["hts_codes_created"] == 1
        assert len(hts_anns) == 2
        new_hts = [a for a in hts_anns if a.id != self.legacy_hts.id]
        assert len(new_hts) == 1
        assert new_hts[0].json["text"] == "3924.90.5650"
        assert new_hts[0].annotation_type == SPAN_LABEL
        assert new_hts[0].annotation_label.label_type == SPAN_LABEL

        # Citation: dedicated OC_REF_DOC mention + reference; the producer's
        # CITED_RULING span is retained untouched and carries no reference.
        mention = self._annotations(C.LABEL_REF_DOC, document=self.doc1).get()
        ref = self._references().get()
        assert ref.source_annotation_id == mention.id
        assert ref.resolution_status == C.STATUS_RESOLVED
        assert ref.target_document_id == self.doc2.id

        self.legacy_cite.refresh_from_db()
        assert self.legacy_cite.annotation_label.text == "CITED_RULING"
        assert not CorpusReference.objects.filter(
            source_annotation=self.legacy_cite
        ).exists()

    def test_rerun_with_legacy_rows_stays_idempotent(self):
        self._run()
        before = Annotation.objects.filter(corpus=self.corpus).count()

        second = self._run()

        assert second["hts_codes_created"] == 0
        assert second["references_created"] == 0
        assert Annotation.objects.filter(corpus=self.corpus).count() == before


class ExternalIdLifecycleTests(_CustomsEnrichmentTestBase):
    """A stamped ``DocumentPath.external_id`` must survive the versioning
    lifecycle: move/delete/restore always copied it, and the update
    (re-import at the same path) branch now inherits it too unless the
    caller supplies a fresh value."""

    def _import(self, body: bytes, **doc_kwargs):
        _doc, _status, path_row = self.corpus.import_content(
            content=body,
            path="/HQ/opaque-name.txt",
            user=self.user,
            filename="opaque-name.txt",
            file_type="text/plain",
            title="Some subject",
            **doc_kwargs,
        )
        return path_row

    def test_upversion_inherits_external_id(self):
        first = self._import(b"v1 body", external_id="cross:H850001")
        assert first.external_id == "cross:H850001"

        second = self._import(b"v2 body")  # same path, no external_id

        assert second.id != first.id
        assert second.is_current
        assert second.external_id == "cross:H850001"

    def test_upversion_caller_override_wins(self):
        self._import(b"v1 body", external_id="cross:H850001")

        second = self._import(b"v2 body", external_id="cross:H850099")

        assert second.external_id == "cross:H850099"


# --- Official bulk-export contract test -------------------------------------

# Two rulings shaped like the official CROSS bulk exporter's output
# (CROSS-Corpus crossfeed.export.oc_bulk): `{COLLECTION}/{ruling_number}.txt`
# documents, dumb-anchor sidecars whose producer labels are TOKEN_LABEL (the
# import contract's requirement), and meta.csv titles carrying the
# human-readable SUBJECT — never the ruling number.
CROSS_DOC1_BODY = (
    "HQ H830001\n\n"
    "The applicable subheading for the serving trays will be 3924.90.5650, "
    "HTSUS. The reasoning of NY H830002, which classified comparable goods "
    "under subheading 6307.90.9889, HTSUS, controls. We also considered "
    "NY N999999, which is not before us.\n"
)
CROSS_DOC2_BODY = (
    "NY H830002\n\n"
    "The applicable subheading for the textile bags will be 6307.90.9889, "
    "HTSUS.\n"
)


def _exporter_label(label_id, text, label_type, color="#F59E0B", icon="hash"):
    # Same key set the official exporter writes (oc_bulk._label).
    return {
        "id": label_id,
        "text": text,
        "label_type": label_type,
        "color": color,
        "description": f"{text} produced by the CROSS exporter.",
        "icon": icon,
    }


@pytest.mark.usefixtures("enable_doc_processing_signals")
class CrossOfficialExportIntegrationTests(TransactionTestCase):
    """End-to-end contract test: official-export-shaped ZIP -> zip-to-corpus
    import -> customs enrichment.

    This is the integration boundary the 10K release blocker slipped through:
    regex unit tests could not see the TXT format gate or the subject-title
    identity mismatch. ``TransactionTestCase`` + eager Celery lets the real
    import chain (parse -> text layer -> sidecar anchoring) run to completion
    before enrichment executes — completion is asserted from document state,
    never assumed from the import call returning.
    """

    def setUp(self):
        from django.db import transaction

        from opencontractserver.types.enums import PermissionTypes
        from opencontractserver.utils.permissioning import (
            set_permissions_for_obj_to_user,
        )

        with transaction.atomic():
            self.user = User.objects.create_user(username="cross-io", password="p")
        with transaction.atomic():
            self.corpus = Corpus.objects.create(
                title="CROSS Official Export", creator=self.user
            )
            set_permissions_for_obj_to_user(
                self.user, self.corpus, [PermissionTypes.ALL]
            )

    def _set_text_parser(self):
        """Use the real TxtParser (deterministic, no external service)."""
        from opencontractserver.documents.models import PipelineSettings

        pipeline_settings = PipelineSettings.get_instance(use_cache=False)
        pipeline_settings.preferred_parsers = {
            **(pipeline_settings.preferred_parsers or {}),
            "text/plain": "opencontractserver.pipeline.parsers.oc_text_parser.TxtParser",
        }
        pipeline_settings.save()
        PipelineSettings.clear_cache()
        self.addCleanup(PipelineSettings.clear_cache)

    def _build_official_zip(self) -> io.BytesIO:
        # meta.csv: exact official columns; titles are subjects.
        meta = io.StringIO()
        writer = csv.writer(meta)
        writer.writerow(["source_path", "title", "description"])
        writer.writerow(
            [
                "HQ/H830001.txt",
                "Plastic serving trays; classification",
                "CROSS HQ ruling H830001",
            ]
        )
        writer.writerow(
            [
                "HQ/H830002.txt",
                "Textile bags of man-made fibers",
                "CROSS NY ruling H830002",
            ]
        )

        labels = {
            "text_labels": {
                "HTS_CODE": _exporter_label("label-hts", "HTS_CODE", "TOKEN_LABEL"),
                "CITED_RULING": _exporter_label(
                    "label-cited-ruling", "CITED_RULING", "TOKEN_LABEL", icon="link"
                ),
            },
            "doc_labels": {},
        }

        hts1_start = CROSS_DOC1_BODY.find("3924.90.5650")
        cite_start = CROSS_DOC1_BODY.find("H830002")
        sidecar1 = {
            "annotations": [
                {
                    "id": 1,
                    "label": "HTS_CODE",
                    "rawText": "3924.90.5650",
                    "start": hts1_start,
                    "end": hts1_start + len("3924.90.5650"),
                    "parent_id": None,
                },
                {
                    "id": 2,
                    "label": "CITED_RULING",
                    "rawText": "H830002",
                    "start": cite_start,
                    "end": cite_start + len("H830002"),
                    "parent_id": None,
                },
            ],
            "doc_labels": [],
        }
        hts2_start = CROSS_DOC2_BODY.find("6307.90.9889")
        sidecar2 = {
            "annotations": [
                {
                    "id": 1,
                    "label": "HTS_CODE",
                    "rawText": "6307.90.9889",
                    "start": hts2_start,
                    "end": hts2_start + len("6307.90.9889"),
                    "parent_id": None,
                }
            ],
            "doc_labels": [],
        }

        files = {
            "meta.csv": meta.getvalue().encode("utf-8"),
            "labels.json": json.dumps(labels).encode("utf-8"),
            "HQ/H830001.txt": CROSS_DOC1_BODY.encode("utf-8"),
            "HQ/H830001.json": json.dumps(sidecar1).encode("utf-8"),
            "HQ/H830002.txt": CROSS_DOC2_BODY.encode("utf-8"),
            "HQ/H830002.json": json.dumps(sidecar2).encode("utf-8"),
        }
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, content in files.items():
                zf.writestr(name, content)
        buffer.seek(0)
        return buffer

    def _import_official_zip(self) -> dict[str, Document]:
        from opencontractserver.corpuses.models import TemporaryFileHandle
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        self._set_text_parser()
        handle = TemporaryFileHandle.objects.create(
            file=ContentFile(self._build_official_zip().read(), name="cross.zip")
        )
        result = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "cross-official-export",
                "corpus_id": self.corpus.id,
            }
        ).get()
        assert result["success"], result

        # Settle check from DOCUMENT STATE, not the import call returning:
        # every document must be unlocked with a parsed text layer.
        docs: dict[str, Document] = {}
        for number in ("H830001", "H830002"):
            path_row = DocumentPath.objects.get(
                corpus=self.corpus,
                path__endswith=f"{number}.txt",
                is_current=True,
                is_deleted=False,
            )
            doc = Document.objects.get(pk=path_row.document_id)
            assert not doc.backend_lock, f"{number} still locked"
            assert doc.txt_extract_file, f"{number} has no text layer"
            docs[number] = doc
        return docs

    def test_official_export_import_then_enrich(self):
        docs = self._import_official_zip()
        doc1, doc2 = docs["H830001"], docs["H830002"]

        # Producer sidecar rows landed (the importer-style representation the
        # enrichment must dedupe against): SPAN annotations, TOKEN-typed label.
        producer_hts = Annotation.objects.filter(
            corpus=self.corpus, annotation_label__text=LABEL_HTS_CODE
        )
        assert producer_hts.count() == 2
        assert {a.annotation_type for a in producer_hts} == {SPAN_LABEL}

        res = CustomsRulingCitationService.enrich_corpus(
            corpus_id=self.corpus.id, creator_id=self.user.id
        )

        assert res["documents_scanned"] == 2
        assert res["documents_skipped_unanchorable"] == 0
        # Doc1's 6307.90.9889 is the only code not already covered by a
        # producer sidecar annotation — dedupe across representations proven.
        assert res["hts_codes_created"] == 1
        assert res["citations_resolved"] == 1
        assert res["citations_unresolved"] == 1

        content = doc1.txt_extract_file.read().decode("utf-8")
        new_hts = Annotation.objects.get(
            corpus=self.corpus,
            document=doc1,
            annotation_label__text=LABEL_HTS_CODE,
            annotation_type=SPAN_LABEL,
            data__code="6307.90.98.89",
        )
        start = content.find("6307.90.9889")
        assert new_hts.json == {
            "start": start,
            "end": start + len("6307.90.9889"),
            "text": "6307.90.9889",
        }
        assert new_hts.page == 0

        mentions = Annotation.objects.filter(
            corpus=self.corpus, annotation_label__text=C.LABEL_REF_DOC
        )
        assert mentions.count() == 2
        assert {m.annotation_type for m in mentions} == {SPAN_LABEL}
        assert {m.page for m in mentions} == {0}

        refs = CorpusReference.objects.filter(
            corpus=self.corpus, reference_type=C.REF_DOCUMENT
        )
        assert refs.count() == 2
        resolved = refs.get(resolution_status=C.STATUS_RESOLVED)
        assert resolved.target_document_id == doc2.id
        unresolved = refs.get(resolution_status=C.STATUS_UNRESOLVED)
        assert unresolved.target_document_id is None

        edges = DocumentRelationship.objects.filter(
            corpus=self.corpus, relationship_type=C.DOC_REL_RELATIONSHIP
        )
        assert edges.count() == 1
        assert edges.get().target_document_id == doc2.id

        # Rerun: stable counts across both representations.
        second = CustomsRulingCitationService.enrich_corpus(
            corpus_id=self.corpus.id, creator_id=self.user.id
        )
        assert second["hts_codes_created"] == 0
        assert second["references_created"] == 0
        assert refs.count() == 2
        assert edges.count() == 1
        assert mentions.count() == 2

    def test_external_id_column_carries_identity_through_import(self):
        """The durable-identity contract end to end: a document whose
        filename is NOT its ruling number resolves via the meta.csv
        ``external_id`` column (stored on ``DocumentPath.external_id``)."""
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        source_body = "HQ H840001\n\nWe follow NY H840002 here."
        target_body = "NY H840002\n\nOriginal decision text."

        meta = io.StringIO()
        writer = csv.writer(meta)
        writer.writerow(["source_path", "title", "description", "external_id"])
        writer.writerow(["HQ/H840001.txt", "Source ruling", "desc", "cross:H840001"])
        writer.writerow(
            # Opaque filename — only external_id carries the identity.
            ["HQ/textile-bags-ruling.txt", "Textile bags", "desc", "cross:H840002"]
        )
        files = {
            "meta.csv": meta.getvalue().encode("utf-8"),
            "HQ/H840001.txt": source_body.encode("utf-8"),
            "HQ/textile-bags-ruling.txt": target_body.encode("utf-8"),
        }
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, content in files.items():
                zf.writestr(name, content)
        buffer.seek(0)

        from opencontractserver.corpuses.models import TemporaryFileHandle

        self._set_text_parser()
        handle = TemporaryFileHandle.objects.create(
            file=ContentFile(buffer.read(), name="cross-extid.zip")
        )
        result = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "cross-external-id",
                "corpus_id": self.corpus.id,
            }
        ).get()
        assert result["success"], result
        assert result["external_ids_applied"] == 2

        target_path = DocumentPath.objects.get(
            corpus=self.corpus,
            path__endswith="textile-bags-ruling.txt",
            is_current=True,
            is_deleted=False,
        )
        assert target_path.external_id == "cross:H840002"
        target_doc = Document.objects.get(pk=target_path.document_id)
        assert not target_doc.backend_lock
        assert target_doc.txt_extract_file

        res = CustomsRulingCitationService.enrich_corpus(
            corpus_id=self.corpus.id, creator_id=self.user.id
        )

        assert res["citations_resolved"] == 1
        ref = CorpusReference.objects.get(
            corpus=self.corpus, reference_type=C.REF_DOCUMENT
        )
        assert ref.resolution_status == C.STATUS_RESOLVED
        assert ref.target_document_id == target_doc.id


# --- Patch-coverage regression tests ----------------------------------------


class EnrichCommandTests(_CustomsEnrichmentTestBase):
    """The ``enrich_customs_rulings`` management-command entry point."""

    def _call(self, *args):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("enrich_customs_rulings", *args, stdout=out, no_color=True)
        return json.loads(out.getvalue())

    def test_runs_with_named_owner(self):
        _make_txt_doc(
            self.user,
            self.corpus,
            title="Ruling",
            path="/HQ/H910001.txt",
            body=DOC1_BODY,
        )
        payload = self._call(
            "--corpus-id", str(self.corpus.id), "--owner", self.user.username
        )
        assert payload["corpus_id"] == self.corpus.id
        assert payload["documents_scanned"] == 1

    def test_defaults_to_first_superuser_and_accepts_limit(self):
        User.objects.create_superuser(username="root", password="p")
        _make_txt_doc(
            self.user,
            self.corpus,
            title="Ruling",
            path="/HQ/H910002.txt",
            body=DOC2_BODY,
        )
        self.corpus.is_public = True
        self.corpus.save(update_fields=["is_public"])

        payload = self._call("--corpus-id", str(self.corpus.id), "--limit", "1")
        assert payload["documents_scanned"] == 1

    def test_unknown_owner_raises(self):
        from django.core.management import CommandError

        with pytest.raises(CommandError):
            self._call("--corpus-id", str(self.corpus.id), "--owner", "nobody")

    def test_no_superuser_raises(self):
        from django.core.management import CommandError

        User.objects.filter(is_superuser=True).delete()
        with pytest.raises(CommandError):
            self._call("--corpus-id", str(self.corpus.id))


class ServiceEdgeBranchTests(_CustomsEnrichmentTestBase):
    """Edge branches: defensive anchor gate, failure path, prefetch setting,
    third-claimant ambiguity, HTS normalization rejects, projection failure."""

    def test_unknown_anchor_type_counts_unanchorable_not_load_failure(self):
        from unittest import mock

        _make_txt_doc(
            self.user,
            self.corpus,
            title="Ruling",
            path="/HQ/H920001.txt",
            body=DOC1_BODY,
        )
        with mock.patch(
            "opencontractserver.enrichment.services."
            "customs_ruling_citation_service.load_document_text_and_layer",
            return_value=("text", None, "BOGUS_ANCHOR_TYPE"),
        ):
            res = self._run()

        assert res["documents_skipped_unanchorable"] == 1
        assert res["load_failures"] == 0
        assert res["hts_codes_created"] == 0

    def test_failure_marks_analysis_failed_and_reraises(self):
        from unittest import mock

        from opencontractserver.analyzer.models import Analysis
        from opencontractserver.enrichment.writer import EnrichmentWriter
        from opencontractserver.types.enums import JobStatus

        _make_txt_doc(
            self.user,
            self.corpus,
            title="Ruling",
            path="/HQ/H920002.txt",
            body=DOC2_BODY,
        )
        with mock.patch.object(
            EnrichmentWriter,
            "reconcile_document_graph",
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(RuntimeError):
                self._run()

        analysis = Analysis.objects.filter(
            analyzer_id="customs-ruling-citation-enrichment"
        ).latest("id")
        assert analysis.status == JobStatus.FAILED.value

    def test_prefetch_workers_explicit_setting_wins(self):
        from django.test import override_settings

        with override_settings(CUSTOMS_ENRICHMENT_PREFETCH_WORKERS=4):
            assert CustomsRulingCitationService._prefetch_workers() == 4
        with override_settings(CUSTOMS_ENRICHMENT_PREFETCH_WORKERS=0):
            # Floor of 1: a zero-size pool would deadlock the executor.
            assert CustomsRulingCitationService._prefetch_workers() == 1

    def test_third_claimant_keeps_number_ambiguous(self):
        for folder in ("HQ", "NY", "PD"):
            _make_txt_doc(
                self.user,
                self.corpus,
                title=f"{folder} twin",
                path=f"/{folder}/H930002.txt",
                body=f"{folder} twin body.",
            )
        _make_txt_doc(
            self.user,
            self.corpus,
            title="Source",
            path="/HQ/H930001.txt",
            body="HQ H930001\n\nSee HQ H930002.",
        )

        res = self._run()

        assert res["canonical_id_collisions"] == 1
        ref = self._references().get()
        assert ref.resolution_status == C.STATUS_UNRESOLVED

    def test_hts_match_failing_normalization_is_skipped(self):
        # 9 digits (1234.56.789) is not a valid 4/6/8/10-digit HTS shape.
        matches = CustomsRulingCitationService._find_hts_matches(
            "Classified under 1234.56.789 as discussed."
        )
        assert matches == []

    def test_pdf_projection_failure_skips_hts_without_crashing(self):
        import json as jsonlib
        from unittest import mock

        from plasmapdf.models.PdfDataLayer import build_translation_layer

        from opencontractserver.tests.test_extraction_grounding import (
            _build_pawls_for_text,
        )

        pawls_json = _build_pawls_for_text(
            ["Classified under subheading 8703.23.01, HTSUS."]
        )
        layer = build_translation_layer(jsonlib.loads(pawls_json))
        pdf_doc = Document.objects.create(
            title="PDF ruling",
            creator=self.user,
            file_type="application/pdf",
        )
        pdf_doc.pawls_parse_file.save(
            "doc.pawls", ContentFile(pawls_json.encode("utf-8"))
        )
        pdf_doc.txt_extract_file.save(
            "doc.txt", ContentFile(layer.doc_text.encode("utf-8"))
        )
        DocumentPath.objects.create(
            document=pdf_doc,
            corpus=self.corpus,
            path="/HQ/H940001.pdf",
            version_number=1,
            creator=self.user,
        )

        with mock.patch(
            "opencontractserver.enrichment.services."
            "customs_ruling_citation_service.project_span_to_token_annotation",
            side_effect=ValueError("no page"),
        ):
            res = self._run()

        assert res["hts_codes_created"] == 0
        assert res["documents_skipped_unanchorable"] == 0


class RelationshipImportDedupeTests(_CustomsEnrichmentTestBase):
    """create_relationships_from_parsed is idempotent (get_or_create)."""

    def test_reimport_skips_existing_edges(self):
        import logging

        from opencontractserver.tasks.import_tasks import (
            create_relationships_from_parsed,
        )
        from opencontractserver.utils.relationship_file_parser import (
            ParsedRelationship,
        )

        doc1 = _make_txt_doc(
            self.user,
            self.corpus,
            title="A",
            path="/HQ/H950001.txt",
            body="body",
        )
        doc2 = _make_txt_doc(
            self.user,
            self.corpus,
            title="B",
            path="/HQ/H950002.txt",
            body="body",
        )
        path_map = {"/HQ/H950001.txt": doc1, "/HQ/H950002.txt": doc2}
        rels = [
            ParsedRelationship(
                source_path="/HQ/H950001.txt",
                target_path="/HQ/H950002.txt",
                label="CITES",
            )
        ]
        logger = logging.getLogger(__name__)

        first = create_relationships_from_parsed(
            self.corpus, self.user, path_map, rels, logger
        )
        second = create_relationships_from_parsed(
            self.corpus, self.user, path_map, rels, logger
        )

        assert first["relationships_created"] == 1
        assert second["relationships_created"] == 0
        assert second["relationships_skipped"] == 1
        assert self._edges().count() == 1


class LabelTypeCoercionTests(_CustomsEnrichmentTestBase):
    """ensure_labels_and_labelset stringifies non-str, non-enum label types."""

    def test_non_string_label_type_is_coerced(self):
        label = self.corpus.ensure_labels_and_labelset(
            label_data={"X": {"text": "X", "label_type": 123}},
            creator_id=self.user.id,
        )["X"]
        assert label.label_type == "123"
