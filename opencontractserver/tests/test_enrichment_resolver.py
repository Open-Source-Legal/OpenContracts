"""Unit tests for ReferenceResolver (document-title + heading resolution)."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.documents.models import Document
from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.extractor import Candidate
from opencontractserver.enrichment.resolver import ReferenceResolver, SectionAnno

User = get_user_model()


class ResolverTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u", password="p")
        self.primary = Document.objects.create(title="Primary S-1", creator=self.user)
        self.exhibit = Document.objects.create(
            title="Acme S-1 (2024-09-30) - Exhibit 1.1: EX-1.1", creator=self.user
        )
        self.resolver = ReferenceResolver([self.primary, self.exhibit])

    def test_resolves_exhibit_number_to_target_document(self):
        cand = Candidate(
            reference_type=C.REF_DOCUMENT,
            start=0,
            end=11,
            raw_text="Exhibit 1.1",
            normalized_data={"exhibit_number": "1.1"},
        )
        r = self.resolver.resolve_document(cand, source_doc_id=self.primary.id)
        assert r is not None
        assert r.resolution_status == C.STATUS_RESOLVED
        assert r.target_document_id == self.exhibit.id

    def test_unknown_exhibit_is_unresolved(self):
        cand = Candidate(
            reference_type=C.REF_DOCUMENT,
            start=0,
            end=12,
            raw_text="Exhibit 99.9",
            normalized_data={"exhibit_number": "99.9"},
        )
        r = self.resolver.resolve_document(cand, source_doc_id=self.primary.id)
        assert r is not None
        assert r.resolution_status == C.STATUS_UNRESOLVED
        assert r.target_document_id is None

    def test_law_candidate_is_external(self):
        cand = Candidate(
            reference_type=C.REF_LAW,
            start=0,
            end=5,
            raw_text="x",
            canonical_key="dgcl:145",
            normalized_data={"authority": "dgcl", "section": "145"},
        )
        r = self.resolver.resolve(cand, source_doc_id=self.primary.id, doc_text="x")
        assert r is not None
        assert r.resolution_status == C.STATUS_EXTERNAL
        assert r.canonical_key == "dgcl:145"
        assert r.source_document_id == self.primary.id

    def test_section_matches_oc_section_annotation(self):
        cand = Candidate(
            reference_type=C.REF_SECTION,
            start=20,
            end=34,
            raw_text='see "Risk Factors"',
            normalized_data={"heading": "Risk Factors"},
        )
        sections = [SectionAnno(id=42, raw_text="Risk Factors")]
        r = self.resolver.resolve_section(
            cand, self.primary.id, doc_text="...", sections=sections
        )
        assert r.resolution_status == C.STATUS_RESOLVED
        assert r.target_annotation_id == 42

    def test_section_falls_back_to_heading_text_offset(self):
        text = "intro... Risk Factors\nThe following risks..."
        cand = Candidate(
            reference_type=C.REF_SECTION,
            start=0,
            end=5,
            raw_text='see "Risk Factors"',
            normalized_data={"heading": "Risk Factors"},
        )
        r = self.resolver.resolve_section(
            cand, self.primary.id, doc_text=text, sections=[]
        )
        assert r.resolution_status == C.STATUS_RESOLVED
        assert r.target_annotation_id is None
        assert r.target_offset == text.find("Risk Factors")
