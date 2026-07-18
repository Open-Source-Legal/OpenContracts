"""Customs/trade grammar family (CBP CROSS-style corpora).

Unit tests for the two Tier-2a customs grammars in
``opencontractserver/enrichment/grammars.py`` (regex shapes ported from
crossfeed's golden-tested CROSS-rulings extractor):

* HTS tariff codes -> ``htsus:<code>`` REF_LAW candidates, gated on a
  document-level HTSUS cue;
* CBP ruling-number citations -> REF_DOCUMENT candidates, gated on the
  corpus's titles being identifier-shaped and resolved against sibling
  document titles by ``ReferenceResolver``.

Plus integration coverage that the family runs through the standard
``EnrichmentService.apply`` path (and therefore through every existing
enrichment trigger — the analyzer task, the ADD_DOCUMENT corpus action,
GraphQL, and the agent tools) with no bespoke service or command.
"""

from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import SimpleTestCase, TestCase

from opencontractserver.annotations.models import Annotation, CorpusReference
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentRelationship
from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.extractor import Candidate
from opencontractserver.enrichment.grammars import (
    _CONF_HTS_ANCHORED,
    _CONF_HTS_CONTEXTUAL,
    GenericCitationExtractor,
    _document_identifier_citations,
    _normalize_hts,
)
from opencontractserver.enrichment.resolver import ReferenceResolver
from opencontractserver.enrichment.services import EnrichmentService

User = get_user_model()


def _fake_docs(*titles):
    """Title-only document stand-ins for the extractor's corpus-shape gate."""
    return [SimpleNamespace(id=i + 1, title=t) for i, t in enumerate(titles)]


RULING_TITLES = ("A83482.doc", "H022844.PDF", "N301234")


class NormalizeHtsTests(SimpleTestCase):
    def test_heading_subheading_passthrough(self):
        assert _normalize_hts("7113.19") == "7113.19"

    def test_ten_digit_statistical_redotted(self):
        assert _normalize_hts("3924.90.5650") == "3924.90.56.50"

    def test_eight_digit_tariff(self):
        assert _normalize_hts("8703.23.01") == "8703.23.01"

    def test_rejects_five_digits(self):
        assert _normalize_hts("12345") is None

    def test_rejects_non_digit_garbage(self):
        assert _normalize_hts("abc") is None


class HtsGrammarTests(SimpleTestCase):
    def setUp(self):
        self.ex = GenericCitationExtractor()

    def _hts(self, text):
        return [
            c
            for c in self.ex.extract(text, reference_types={C.REF_LAW})
            if (c.canonical_key or "").startswith(f"{C.HTSUS_PREFIX}:")
        ]

    def test_anchored_code_is_high_confidence(self):
        text = "The applicable subheading will be 3924.90.5650, HTSUS."
        cands = self._hts(text)
        assert len(cands) == 1
        c = cands[0]
        assert c.canonical_key == "htsus:3924.90.56.50"
        assert c.reference_type == C.REF_LAW
        assert c.jurisdiction == C.JURISDICTION_US_FEDERAL
        assert c.authority_type == C.AUTHORITY_TYPE_STATUTE
        assert c.detection_tier == C.DETECTION_TIER_GRAMMAR
        assert c.detection_confidence == _CONF_HTS_ANCHORED
        assert c.normalized_data["section"] == "3924.90.56.50"

    def test_unanchored_code_in_cue_bearing_document_is_contextual(self):
        text = (
            "The Harmonized Tariff Schedule of the United States is referenced "
            "in this agreement. Import duties were reconciled during the audit "
            "and the parties agreed on totals. The ledger shows a value of "
            "1234.56 for the period."
        )
        cands = self._hts(text)
        assert len(cands) == 1
        assert cands[0].detection_confidence == _CONF_HTS_CONTEXTUAL

    def test_no_document_cue_emits_nothing(self):
        # Dotted decimals in ordinary prose never become HTS citations.
        assert self._hts("The price was 1234.56 dollars per unit.") == []

    def test_bare_hts_acronym_does_not_open_the_document_gate(self):
        # "HTS" collides with unrelated acronyms (e.g. high-throughput
        # screening) so it is deliberately not a document-level cue.
        assert self._hts("HTS assays cost 1234.56 per plate.") == []

    def test_bare_year_never_matches(self):
        assert self._hts("In 2010, the HTSUS was amended.") == []

    def test_odd_digit_grouping_rejected_by_normalization(self):
        # The text shape's middle group allows 2-4 digits, so a 9-digit token
        # like "1234.56.789" matches the regex but fails _normalize_hts's
        # 4/6/8/10-digit rule — the candidate must be skipped, not emitted
        # with a malformed key.
        assert self._hts("Under the HTSUS, item 1234.56.789 was listed.") == []

    def test_type_filter_excludes_hts(self):
        text = "The applicable subheading will be 3924.90.5650, HTSUS."
        cands = self.ex.extract(text, reference_types={C.REF_DOCUMENT})
        assert all(
            not (c.canonical_key or "").startswith(f"{C.HTSUS_PREFIX}:") for c in cands
        )


class RulingCitationGrammarTests(SimpleTestCase):
    def _extract(self, text, titles):
        ex = GenericCitationExtractor(documents=_fake_docs(*titles))
        return ex.extract(text, reference_types={C.REF_DOCUMENT})

    def test_gate_open_emits_identifier_candidates(self):
        cands = self._extract(
            "In HQ H022844 and NY R03632, Customs classified similar goods.",
            RULING_TITLES,
        )
        idents = [c.normalized_data[C.KEY_DOCUMENT_IDENTIFIER] for c in cands]
        assert idents == ["H022844", "R03632"]
        for c in cands:
            assert c.reference_type == C.REF_DOCUMENT
            assert c.canonical_key is None
            assert c.detection_tier == C.DETECTION_TIER_GRAMMAR

    def test_bare_six_digit_legacy_number_not_mined(self):
        # Documented false-positive guard (ported from crossfeed): dollar
        # amounts, statute numbers, and ZIP codes collide with bare 6-digit
        # legacy ruling numbers.
        cands = self._extract(
            "Headquarters Ruling Letter 562035 addressed the issue.",
            RULING_TITLES,
        )
        assert cands == []

    def test_state_plus_zip_not_mined(self):
        assert self._extract("Our office is at NY 10022.", RULING_TITLES) == []

    def test_gate_closed_without_documents(self):
        ex = GenericCitationExtractor()
        assert ex.extract("See HQ H022844.", reference_types={C.REF_DOCUMENT}) == []

    def test_gate_closed_for_non_identifier_titles(self):
        cands = self._extract(
            "See HQ H022844.",
            ("Acme S-1 (2024-09-30) - primary document", "Exhibit 10.1"),
        )
        assert cands == []

    def test_gate_closed_below_fraction(self):
        # 2 identifier-shaped titles out of 6 — enough documents, but the
        # corpus as a whole does not speak the identifier vocabulary;
        # incidental identifier titles must not activate the grammar.
        cands = self._extract(
            "See HQ H022844.",
            (
                "A83482.doc",
                "H555555.doc",
                "Alpha Agreement",
                "Beta Agreement",
                "Gamma Lease",
                "Delta SOW",
            ),
        )
        assert cands == []

    def test_gate_closed_below_min_docs(self):
        # A single identifier-titled document is not a rulings corpus.
        cands = self._extract("See HQ H022844.", ("A83482.doc",))
        assert cands == []

    def test_gate_open_at_thresholds(self):
        # Exactly MIN_DOCS identifier titles and >= FRACTION of the titles.
        cands = self._extract(
            "See HQ H022844.", ("A83482.doc", "N301234.doc", "Alpha Agreement")
        )
        assert len(cands) == 1


class DocumentIdentifierTitleTests(SimpleTestCase):
    """Titles are materialized filenames on some ingest paths — the index key
    must be the bare identifier or every citation into the document silently
    reads as unresolved (regression: extension-carrying CROSS titles)."""

    def test_strips_doc_extension(self):
        assert C.document_identifier_from_title("A83482.doc") == "A83482"

    def test_strips_uppercase_extension(self):
        assert C.document_identifier_from_title("H022844.PDF") == "H022844"

    def test_bare_title_unchanged(self):
        assert C.document_identifier_from_title("A83482") == "A83482"

    def test_none_title(self):
        assert C.document_identifier_from_title(None) == ""

    def test_path_like_title_is_returned_whole(self):
        # Titles are user-editable; a path-like title is not a materialized
        # filename, so its leading segments must not be silently discarded
        # (which would make it LOOK identifier-titled). The whole string
        # fails the identifier fullmatch and stays out of the gate/index.
        assert C.document_identifier_from_title("Reports/N301234") == "REPORTS/N301234"
        assert not C.DOC_IDENTIFIER_RE.fullmatch(
            C.document_identifier_from_title("Reports/N301234")
        )


class IdentifierResolverTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u", password="p")
        self.citing = Document.objects.create(title="N301234.doc", creator=self.user)
        # Extension-carrying title — must still be indexed under the bare
        # identifier the citation grammar extracts.
        self.target = Document.objects.create(title="A83482.doc", creator=self.user)
        self.resolver = ReferenceResolver([self.citing, self.target])

    def _cand(self, ident):
        return Candidate(
            reference_type=C.REF_DOCUMENT,
            start=0,
            end=len(ident),
            raw_text=ident,
            normalized_data={C.KEY_DOCUMENT_IDENTIFIER: ident},
        )

    def test_resolves_identifier_to_sibling_despite_title_extension(self):
        r = self.resolver.resolve_document(
            self._cand("A83482"), source_doc_id=self.citing.id
        )
        assert r is not None
        assert r.resolution_status == C.STATUS_RESOLVED
        assert r.target_document_id == self.target.id

    def test_unknown_identifier_is_unresolved(self):
        r = self.resolver.resolve_document(
            self._cand("K999999"), source_doc_id=self.citing.id
        )
        assert r is not None
        assert r.resolution_status == C.STATUS_UNRESOLVED
        assert r.target_document_id is None

    def test_self_mention_is_dropped(self):
        # A ruling states its own number in headers/footers — never persisted.
        r = self.resolver.resolve_document(
            self._cand("N301234"), source_doc_id=self.citing.id
        )
        assert r is None

    def test_duplicate_title_self_mentions_both_dropped(self):
        # The same ruling ingested twice (e.g. as .doc and .pdf): BOTH copies'
        # self-identifying header mentions must drop.
        duplicate = Document.objects.create(title="A83482.pdf", creator=self.user)
        resolver = ReferenceResolver([self.citing, self.target, duplicate])
        for doc in (self.target, duplicate):
            r = resolver.resolve_document(self._cand("A83482"), source_doc_id=doc.id)
            assert r is None
        # A third document citing the shared identifier stays UNRESOLVED:
        # two documents claiming one identity is AMBIGUITY, reported and left
        # unresolved rather than resolved to whichever copy happened to claim
        # the index slot first. (Expectation updated with the PR 2153 identity
        # port — previously first-writer-wins; the resolver cannot know
        # whether duplicates are the same content or two documents wrongly
        # sharing an identity, and a wrong link is worse than no link. The
        # writer's forward-only heal resolves the row once the duplicate is
        # removed and enrichment re-applies.)
        r = resolver.resolve_document(
            self._cand("A83482"), source_doc_id=self.citing.id
        )
        assert r is not None
        assert r.resolution_status == C.STATUS_UNRESOLVED
        assert r.target_document_id is None

    def test_exhibit_resolution_unaffected(self):
        exhibit = Document.objects.create(
            title="Acme S-1 (2024-09-30) - Exhibit 1.1: EX-1.1", creator=self.user
        )
        resolver = ReferenceResolver([self.citing, exhibit])
        cand = Candidate(
            reference_type=C.REF_DOCUMENT,
            start=0,
            end=11,
            raw_text="Exhibit 1.1",
            normalized_data={"exhibit_number": "1.1"},
        )
        r = resolver.resolve_document(cand, source_doc_id=self.citing.id)
        assert r is not None
        assert r.resolution_status == C.STATUS_RESOLVED
        assert r.target_document_id == exhibit.id


H022844_TEXT = (
    "HQ H022844\n"
    "The classification approach in NY A83482 controls here, while HQ "
    "K999999 is distinguishable. The applicable subheading for the jewelry "
    "will be 7113.19.5000, Harmonized Tariff Schedule of the United States "
    "(HTSUS)."
)
A83482_TEXT = "NY A83482\nThe merchandise is classifiable under 7113.19, HTSUS."


class CustomsEnrichmentIntegrationTests(TestCase):
    """End-to-end: the customs grammars run inside the standard apply()."""

    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="p")
        self.corpus = Corpus.objects.create(title="CROSS Rulings", creator=self.user)
        self.h_doc = Document.objects.create(title="H022844.doc", creator=self.user)
        self.h_doc.txt_extract_file.save(
            "h.txt", ContentFile(H022844_TEXT.encode("utf-8"))
        )
        self.a_doc = Document.objects.create(title="A83482.doc", creator=self.user)
        self.a_doc.txt_extract_file.save(
            "a.txt", ContentFile(A83482_TEXT.encode("utf-8"))
        )
        # add_document creates corpus-isolated copies; enrichment operates on
        # (and resolves to) those copies, not the originals.
        self.h_in_corpus, _, _ = self.corpus.add_document(
            document=self.h_doc, user=self.user
        )
        self.a_in_corpus, _, _ = self.corpus.add_document(
            document=self.a_doc, user=self.user
        )

    def _apply(self):
        return EnrichmentService().apply(
            corpus_id=self.corpus.id, creator_id=self.user.id
        )

    def test_apply_persists_hts_law_references(self):
        self._apply()
        ref = CorpusReference.objects.get(
            corpus=self.corpus,
            reference_type=C.REF_LAW,
            canonical_key="htsus:7113.19.50.00",
        )
        assert ref.resolution_status == C.STATUS_EXTERNAL
        assert ref.jurisdiction == C.JURISDICTION_US_FEDERAL
        assert ref.authority_type == C.AUTHORITY_TYPE_STATUTE
        assert ref.detection_tier == C.DETECTION_TIER_GRAMMAR
        mention = ref.source_annotation
        assert mention is not None and mention.annotation_label is not None
        assert mention.annotation_label.text == C.LABEL_REF_LAW
        assert mention.data is not None
        assert mention.data["canonical_key"] == "htsus:7113.19.50.00"

    def test_apply_resolves_ruling_citation_to_sibling(self):
        self._apply()
        resolved = CorpusReference.objects.get(
            corpus=self.corpus,
            reference_type=C.REF_DOCUMENT,
            normalized_data__document_identifier="A83482",
        )
        assert resolved.resolution_status == C.STATUS_RESOLVED
        assert resolved.target_document_id == self.a_in_corpus.id
        mention = resolved.source_annotation
        assert mention is not None and mention.annotation_label is not None
        assert mention.annotation_label.text == C.LABEL_REF_DOC

    def test_apply_records_unresolved_citation_to_absent_ruling(self):
        self._apply()
        unresolved = CorpusReference.objects.get(
            corpus=self.corpus,
            reference_type=C.REF_DOCUMENT,
            normalized_data__document_identifier="K999999",
        )
        assert unresolved.resolution_status == C.STATUS_UNRESOLVED
        assert unresolved.target_document_id is None

    def test_self_mentions_never_persisted(self):
        self._apply()
        # H022844's own header states its number; A83482's does too.
        assert not CorpusReference.objects.filter(
            corpus=self.corpus,
            source_annotation__document_id=self.h_in_corpus.id,
            normalized_data__document_identifier="H022844",
        ).exists()
        assert not Annotation.objects.filter(
            corpus=self.corpus,
            document_id=self.a_in_corpus.id,
            annotation_label__text=C.LABEL_REF_DOC,
            raw_text="A83482",
        ).exists()

    def test_resolved_citation_rolls_up_to_document_relationship(self):
        self._apply()
        assert DocumentRelationship.objects.filter(
            corpus=self.corpus,
            source_document_id=self.h_in_corpus.id,
            target_document_id=self.a_in_corpus.id,
            relationship_type=C.DOC_REL_RELATIONSHIP,
        ).exists()

    def test_apply_is_idempotent(self):
        self._apply()
        before = CorpusReference.objects.filter(corpus=self.corpus).count()
        out = self._apply()
        assert CorpusReference.objects.filter(corpus=self.corpus).count() == before
        assert out["references_created"] == 0

    def test_hts_keys_surface_in_discover(self):
        inventory = EnrichmentService().discover(
            corpus_id=self.corpus.id, creator_id=self.user.id
        )
        assert "htsus:7113.19.50.00" in inventory["by_key"]

    def test_sibling_ingested_later_heals_unresolved_citation(self):
        self._apply()
        k_doc = Document.objects.create(title="K999999.doc", creator=self.user)
        k_doc.txt_extract_file.save(
            "k.txt", ContentFile(b"HQ K999999\nClassification ruling body.")
        )
        k_in_corpus, _, _ = self.corpus.add_document(document=k_doc, user=self.user)
        out = self._apply()
        healed = CorpusReference.objects.get(
            corpus=self.corpus,
            reference_type=C.REF_DOCUMENT,
            normalized_data__document_identifier="K999999",
        )
        assert healed.resolution_status == C.STATUS_RESOLVED
        assert healed.target_document_id == k_in_corpus.id
        assert out["references_resolved"] == 1


class NonRulingCorpusGateTests(TestCase):
    """An ordinary corpus never mines identifier-shaped tokens as citations."""

    def setUp(self):
        self.user = User.objects.create_user(username="owner2", password="p")
        self.corpus = Corpus.objects.create(title="Agreements", creator=self.user)
        doc = Document.objects.create(title="Alpha Supply Agreement", creator=self.user)
        doc.txt_extract_file.save(
            "alpha.txt",
            ContentFile(b"Purchase order N123456 and serial A99999 are noted."),
        )
        other = Document.objects.create(title="Beta Services MSA", creator=self.user)
        other.txt_extract_file.save("beta.txt", ContentFile(b"Beta body."))
        self.corpus.add_document(document=doc, user=self.user)
        self.corpus.add_document(document=other, user=self.user)

    def test_no_document_identifier_references_created(self):
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)
        assert not CorpusReference.objects.filter(
            corpus=self.corpus,
            reference_type=C.REF_DOCUMENT,
            normalized_data__document_identifier__isnull=False,
        ).exists()


# --------------------------------------------------------------------------- #
# PR 2153 port: series-token legacy citations + path/external_id identity
# --------------------------------------------------------------------------- #


class LegacyCitationGrammarTests(SimpleTestCase):
    """Series-token legacy citations ("HQ 084665", "HRL 087392") — the bulk
    of pre-2000 rulings have BARE numeric identities the prefixed shape
    cannot see (74% of the true reference graph on the real 10K
    official-export benchmark)."""

    def test_mines_series_token_citation(self):
        text = "Upon further consideration, HRL 087392 is deemed correct."
        matches = [m.group(1) for m in C.LEGACY_DOC_IDENTIFIER_CITE_RE.finditer(text)]
        assert matches == ["087392"]

    def test_mines_across_hard_line_wrap(self):
        text = "October 27, 1987, has been modified by HRL\n081374 dated"
        matches = [m.group(1) for m in C.LEGACY_DOC_IDENTIFIER_CITE_RE.finditer(text)]
        assert matches == ["081374"]

    def test_never_mines_new_york_zip_codes(self):
        """5 digits after "NY" is a ZIP (148/149 sampled), and ZIP+4 never
        forms a 6-digit run — the grammar requires exactly six digits."""
        text = "375 Fifth Avenue, New York, NY  10176 and NY 10001-3060."
        assert list(C.LEGACY_DOC_IDENTIFIER_CITE_RE.finditer(text)) == []

    def test_never_mines_bare_number_without_series_token(self):
        text = "Headquarters Ruling Letter 562035, dated June 22, 2001."
        assert list(C.LEGACY_DOC_IDENTIFIER_CITE_RE.finditer(text)) == []

    def test_grammar_emits_canonical_keys_for_both_shapes(self):
        cands = list(
            _document_identifier_citations(
                "See H022844 and also HRL 087392 for the analysis."
            )
        )
        keys = {c.normalized_data[C.KEY_DOCUMENT_IDENTIFIER] for c in cands}
        assert keys == {"H022844", "87392"}
        raws = {c.raw_text for c in cands}
        assert "HRL 087392" in raws  # the series token is part of the mention

    def test_canonical_document_identifier_namespaces(self):
        assert C.canonical_document_identifier("H022844") == "H022844"
        assert C.canonical_document_identifier("r03632") == "R03632"
        assert C.canonical_document_identifier("084665") == "84665"
        assert C.canonical_document_identifier("84665") == "84665"
        assert C.canonical_document_identifier("Plastic trays") is None
        assert C.canonical_document_identifier("1466") is None
        assert C.canonical_document_identifier("") is None


LEGACY_SRC_TEXT = (
    "HQ 084665\n\n"
    "375 Fifth Avenue, New York, NY  10176\n\n"
    "Upon further consideration, HRL 087392 is deemed correct and "
    "HQ 555555 does not control."
)
LEGACY_TGT_TEXT = "HQ 087392\n\nDecision text."


def _make_corpus_txt_doc(user, corpus, *, title, path, body, external_id=""):
    """A text/plain corpus member with an explicit DocumentPath — the official
    export's shape: subject title, identifier-bearing path."""
    from opencontractserver.documents.models import DocumentPath

    doc = Document.objects.create(title=title, creator=user, file_type="text/plain")
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


class LegacyIdentityIntegrationTests(TestCase):
    """End-to-end on the official export's real shape: subject titles, bare
    zero-padded numeric ruling numbers in paths, series-token citations."""

    def setUp(self):
        self.user = User.objects.create_user(username="legacy-owner", password="p")
        self.corpus = Corpus.objects.create(title="CROSS Legacy", creator=self.user)
        self.src = _make_corpus_txt_doc(
            self.user,
            self.corpus,
            title="Gasket material classification",  # subject, NOT the number
            path="/HQ/084665.txt",
            body=LEGACY_SRC_TEXT,
        )
        self.tgt = _make_corpus_txt_doc(
            self.user,
            self.corpus,
            title="Reconsideration of gasket ruling",
            path="/HQ/087392.txt",
            body=LEGACY_TGT_TEXT,
        )

    def _apply(self):
        return EnrichmentService().apply(
            corpus_id=self.corpus.id, creator_id=self.user.id
        )

    def _doc_refs(self):
        return CorpusReference.objects.filter(
            corpus=self.corpus, reference_type=C.REF_DOCUMENT
        )

    def test_series_token_citation_resolves_via_path_identity(self):
        self._apply()

        resolved = self._doc_refs().get(resolution_status=C.STATUS_RESOLVED)
        assert resolved.target_document_id == self.tgt.id
        assert resolved.normalized_data[C.KEY_DOCUMENT_IDENTIFIER] == "87392"
        mention = resolved.source_annotation
        assert mention.raw_text == "HRL 087392"
        # Canonical text-span shape: page 0 sentinel + anchored text.
        assert mention.page == 0
        assert mention.json["text"] == "HRL 087392"

        unresolved = self._doc_refs().get(resolution_status=C.STATUS_UNRESOLVED)
        assert unresolved.normalized_data[C.KEY_DOCUMENT_IDENTIFIER] == "555555"

        # The ZIP code and the document's own header number are not mined /
        # not persisted: exactly the two references above exist.
        assert self._doc_refs().count() == 2

        edge = DocumentRelationship.objects.get(
            corpus=self.corpus, relationship_type=C.DOC_REL_RELATIONSHIP
        )
        assert edge.source_document_id == self.src.id
        assert edge.target_document_id == self.tgt.id

    def test_external_id_outranks_path_case_insensitively(self):
        renamed = _make_corpus_txt_doc(
            self.user,
            self.corpus,
            title="Renamed after import",
            path="/HQ/opaque-name.txt",  # basename no longer the number
            body="HQ 099001\n\nOriginal decision text.",
            external_id="CROSS:099001",  # producer used uppercase namespace
        )
        _make_corpus_txt_doc(
            self.user,
            self.corpus,
            title="Citing ruling",
            path="/HQ/099002.txt",
            body="HQ 099002\n\nWe follow HQ 099001 here.",
        )

        self._apply()

        ref = self._doc_refs().get(normalized_data__document_identifier="99001")
        assert ref.resolution_status == C.STATUS_RESOLVED
        assert ref.target_document_id == renamed.id

    def test_duplicate_path_identity_reported_not_silently_chosen(self):
        _make_corpus_txt_doc(
            self.user,
            self.corpus,
            title="First twin",
            path="/HQ/H730002.txt",
            body="First twin body.",
        )
        _make_corpus_txt_doc(
            self.user,
            self.corpus,
            title="Second twin",
            path="/NY/H730002.txt",
            body="Second twin body.",
        )
        _make_corpus_txt_doc(
            self.user,
            self.corpus,
            title="Citing ruling",
            path="/HQ/099003.txt",
            body="HQ 099003\n\nSee H730002.",
        )

        self._apply()

        ref = self._doc_refs().get(normalized_data__document_identifier="H730002")
        assert ref.resolution_status == C.STATUS_UNRESOLVED
        assert ref.target_document_id is None

    def test_reapply_heals_prefix_shaped_span_mention(self):
        """Pre-fix span mentions carried page=1 and no ``text`` anchor;
        re-applying enrichment converges them on the canonical shape IN
        PLACE (same row — CorpusReference FKs survive)."""
        self._apply()
        mention = (
            self._doc_refs().get(resolution_status=C.STATUS_RESOLVED).source_annotation
        )
        ref_id = self._doc_refs().get(resolution_status=C.STATUS_RESOLVED).id
        Annotation.objects.filter(pk=mention.pk).update(
            page=1,
            json={"start": mention.json["start"], "end": mention.json["end"]},
        )

        self._apply()

        mention.refresh_from_db()
        assert mention.page == 0
        assert mention.json["text"] == "HRL 087392"
        assert self._doc_refs().get(resolution_status=C.STATUS_RESOLVED).id == ref_id

    def test_reapply_is_idempotent(self):
        self._apply()
        before = (
            self._doc_refs().count(),
            Annotation.objects.filter(corpus=self.corpus).count(),
            DocumentRelationship.objects.filter(corpus=self.corpus).count(),
        )

        self._apply()

        after = (
            self._doc_refs().count(),
            Annotation.objects.filter(corpus=self.corpus).count(),
            DocumentRelationship.objects.filter(corpus=self.corpus).count(),
        )
        assert before == after
