"""Integration tests for EnrichmentWriter + EnrichmentService (DB writes)."""

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase
from graphene.test import Client

from opencontractserver.annotations.models import (
    RELATIONSHIP_LABEL,
    SPAN_LABEL,
    Annotation,
    CorpusReference,
    Relationship,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentRelationship
from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.services import (
    CorpusReferenceService,
    EnrichmentService,
)

User = get_user_model()


class _GQLContext:
    """Minimal info.context stand-in for graphene.test.Client."""

    def __init__(self, user):
        self.user = user


PRIMARY_TEXT = (
    "We are subject to Section 203 of the Delaware General Corporation Law. "
    "Indemnification is governed by Section 145 of the Delaware General "
    "Corporation Law. Shares were issued pursuant to Section 4(a)(2) of the "
    'Securities Act. For details, see "Risk Factors" beginning on page 20. '
    "Risk Factors\nThe following risks are material to our business. "
    "The underwriting agreement is filed as Exhibit 1.1 hereto."
)


class EnrichmentWriterTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="p")
        self.corpus = Corpus.objects.create(title="S-1 Corpus", creator=self.user)
        self.primary = Document.objects.create(
            title="Acme S-1 (2024-09-30) - primary document", creator=self.user
        )
        self.primary.txt_extract_file.save(
            "primary.txt", ContentFile(PRIMARY_TEXT.encode("utf-8"))
        )
        self.exhibit = Document.objects.create(
            title="Acme S-1 (2024-09-30) - Exhibit 1.1: EX-1.1", creator=self.user
        )
        self.exhibit.txt_extract_file.save(
            "ex.txt", ContentFile(b"Underwriting agreement body.")
        )
        # add_document creates corpus-isolated copies; enrichment operates on
        # (and resolves to) those copies, not the originals.
        self.primary_in_corpus, _, _ = self.corpus.add_document(
            document=self.primary, user=self.user
        )
        self.exhibit_in_corpus, _, _ = self.corpus.add_document(
            document=self.exhibit, user=self.user
        )

    def test_apply_creates_law_annotation_and_external_reference(self):
        out = EnrichmentService().apply(
            corpus_id=self.corpus.id, creator_id=self.user.id
        )
        assert out["annotations_created"] > 0

        law_anns = Annotation.objects.filter(
            corpus=self.corpus, annotation_label__text=C.LABEL_REF_LAW
        )
        keys = {a.data.get("canonical_key") for a in law_anns if a.data}
        assert "dgcl:145" in keys
        assert "dgcl:203" in keys
        assert "securities-act:4(a)(2)" in keys

        ext = CorpusReference.objects.filter(
            corpus=self.corpus, reference_type=C.REF_LAW, canonical_key="dgcl:145"
        ).first()
        assert ext is not None
        assert ext.resolution_status == C.STATUS_EXTERNAL

    def test_registry_reference_persists_classification(self):
        # Registry-tier candidates carry no jurisdiction/authority_type; the
        # writer backfills the taxonomy at PERSIST time (AuthorityNamespace ->
        # classify_prefix) so the stored row matches discover() (gap-4) instead
        # of being silently (None, None).
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)
        ref = CorpusReference.objects.get(
            corpus=self.corpus, reference_type=C.REF_LAW, canonical_key="dgcl:145"
        )
        assert ref.detection_tier == C.DETECTION_TIER_REGISTRY
        assert ref.jurisdiction == "us-de"
        assert ref.authority_type == C.AUTHORITY_TYPE_STATUTE

    def test_apply_heals_unclassified_reference_on_rerun(self):
        # A row persisted before classification existed converges on re-apply.
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)
        ref = CorpusReference.objects.get(
            corpus=self.corpus, reference_type=C.REF_LAW, canonical_key="dgcl:145"
        )
        CorpusReference.objects.filter(pk=ref.pk).update(
            jurisdiction=None, authority_type=None
        )
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)
        ref.refresh_from_db()
        assert ref.jurisdiction == "us-de"
        assert ref.authority_type == C.AUTHORITY_TYPE_STATUTE

    def test_apply_heals_unresolved_document_reference_on_rerun(self):
        # get_or_create's lookup key (source_annotation, reference_type,
        # canonical_key) doesn't include the resolution outcome, so a row
        # persisted as UNRESOLVED before its target could be found (a sibling
        # document ingested later, or a resolution-logic bug fixed after the
        # fact) would otherwise never be touched by a later run that DOES
        # find the target — the run's in-memory resolved-count would
        # over-report what actually persisted. Converges on re-apply, like
        # the jurisdiction/authority_type heal above.
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)
        ref = CorpusReference.objects.get(
            corpus=self.corpus, reference_type=C.REF_DOCUMENT
        )
        CorpusReference.objects.filter(pk=ref.pk).update(
            resolution_status=C.STATUS_UNRESOLVED,
            target_document_id=None,
            target_annotation_id=None,
        )

        out = EnrichmentService().apply(
            corpus_id=self.corpus.id, creator_id=self.user.id
        )

        ref.refresh_from_db()
        assert ref.resolution_status == C.STATUS_RESOLVED
        assert ref.target_document_id == self.exhibit_in_corpus.id
        assert out["references_resolved"] == 1
        # An already-RESOLVED row must never be counted again on a run that
        # finds nothing new to heal.
        out2 = EnrichmentService().apply(
            corpus_id=self.corpus.id, creator_id=self.user.id
        )
        assert out2["references_resolved"] == 0

    def test_apply_links_exhibit_reference_to_target_document(self):
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)
        doc_ref = CorpusReference.objects.filter(
            corpus=self.corpus, reference_type=C.REF_DOCUMENT
        ).first()
        assert doc_ref is not None
        assert doc_ref.target_document_id == self.exhibit_in_corpus.id
        # The mention annotation carries the canonical in-app document path
        # (the slug shape the frontend router actually serves — see
        # frontend/src/App.tsx /d/:userIdent/:corpusIdent/:docIdent).
        self.corpus.refresh_from_db()
        self.exhibit_in_corpus.refresh_from_db()
        assert doc_ref.source_annotation.link_url == (
            f"/d/{self.corpus.creator.slug}/{self.corpus.slug}"
            f"/{self.exhibit_in_corpus.slug}"
        )

    def test_section_reference_creates_relationship_or_external_ref(self):
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)
        # No OC_SECTION annotations exist, so the section ref resolves via the
        # heading-text fallback and is stored as a SECTION CorpusReference.
        sec_ref = CorpusReference.objects.filter(
            corpus=self.corpus, reference_type=C.REF_SECTION
        ).first()
        assert sec_ref is not None
        assert sec_ref.resolution_status == C.STATUS_RESOLVED

    def test_section_reference_with_oc_section_creates_relationship(self):
        # Seed an OC_SECTION annotation on the in-corpus primary doc whose text
        # matches the `see "Risk Factors"` heading, so the resolver links to it.
        oc_label = self.corpus.ensure_label_and_labelset(
            label_text="OC_SECTION", creator_id=self.user.id, label_type=SPAN_LABEL
        )
        section = Annotation.objects.create(
            raw_text="Risk Factors",
            page=1,
            json={"start": 0, "end": 12},
            annotation_label=oc_label,
            document_id=self.primary_in_corpus.id,
            corpus=self.corpus,
            creator=self.user,
            annotation_type=SPAN_LABEL,
        )

        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)

        rel = Relationship.objects.filter(
            corpus=self.corpus,
            relationship_label__text=C.LABEL_RELATIONSHIP,
            target_annotations=section,
        ).first()
        assert rel is not None
        source = rel.source_annotations.first()
        assert source is not None
        label = source.annotation_label
        assert label is not None
        assert label.text == C.LABEL_REF_SECTION

    def test_document_reference_creates_document_relationship(self):
        """Resolved exhibit refs roll up to a document-level edge.

        DocumentRelationship rows are what the corpus document graph renders
        (documents = nodes, relationships = edges), so enrichment must emit
        them alongside the annotation-level CorpusReference.
        """
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)

        rel = DocumentRelationship.objects.filter(
            corpus=self.corpus,
            source_document_id=self.primary_in_corpus.id,
            target_document_id=self.exhibit_in_corpus.id,
            annotation_label__text=C.LABEL_RELATIONSHIP,
        ).first()
        assert rel is not None
        assert rel.relationship_type == C.DOC_REL_RELATIONSHIP

    def test_orphan_enrichment_rollup_is_pruned_on_rerun(self):
        """DocumentRelationship rollups are a derived projection of
        CorpusReference — an enrichment-owned edge (data.analysis_id marker)
        with no backing resolved doc reference must be pruned by the next
        apply(), while legitimate rollups survive."""
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)
        rel_label = self.corpus.ensure_label_and_labelset(
            label_text=C.LABEL_RELATIONSHIP,
            creator_id=self.user.id,
            label_type=RELATIONSHIP_LABEL,
        )
        orphan = DocumentRelationship.objects.create(
            source_document_id=self.exhibit_in_corpus.id,
            target_document_id=self.primary_in_corpus.id,
            annotation_label=rel_label,
            relationship_type=C.DOC_REL_RELATIONSHIP,
            corpus=self.corpus,
            creator=self.user,
            data={"analysis_id": 424242},  # enrichment-owned, no backing ref
        )

        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)

        assert not DocumentRelationship.objects.filter(pk=orphan.pk).exists()
        # The legitimate primary -> exhibit rollup is still there.
        assert DocumentRelationship.objects.filter(
            corpus=self.corpus,
            source_document_id=self.primary_in_corpus.id,
            target_document_id=self.exhibit_in_corpus.id,
        ).exists()

    def test_user_created_document_relationships_never_pruned(self):
        """Rows without the data.analysis_id marker are user-authored — the
        reconcile pass must not delete or duplicate them."""
        rel_label = self.corpus.ensure_label_and_labelset(
            label_text=C.LABEL_RELATIONSHIP,
            creator_id=self.user.id,
            label_type=RELATIONSHIP_LABEL,
        )
        user_rel = DocumentRelationship.objects.create(
            source_document_id=self.exhibit_in_corpus.id,
            target_document_id=self.primary_in_corpus.id,
            annotation_label=rel_label,
            relationship_type=C.DOC_REL_RELATIONSHIP,
            corpus=self.corpus,
            creator=self.user,
            data={},  # no marker -> user-authored
        )

        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)

        assert DocumentRelationship.objects.filter(pk=user_rel.pk).exists()

    def test_user_row_for_same_pair_not_duplicated_by_rollup(self):
        """A user-authored edge for the same (source, target, label) pair
        satisfies the projection — reconcile must not add a second row."""
        rel_label = self.corpus.ensure_label_and_labelset(
            label_text=C.LABEL_RELATIONSHIP,
            creator_id=self.user.id,
            label_type=RELATIONSHIP_LABEL,
        )
        DocumentRelationship.objects.create(
            source_document_id=self.primary_in_corpus.id,
            target_document_id=self.exhibit_in_corpus.id,
            annotation_label=rel_label,
            relationship_type=C.DOC_REL_RELATIONSHIP,
            corpus=self.corpus,
            creator=self.user,
            data={},
        )

        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)

        assert (
            DocumentRelationship.objects.filter(
                corpus=self.corpus,
                source_document_id=self.primary_in_corpus.id,
                target_document_id=self.exhibit_in_corpus.id,
            ).count()
            == 1
        )

    def test_document_relationship_rollup_is_idempotent(self):
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)
        count = DocumentRelationship.objects.filter(corpus=self.corpus).count()
        assert count == 1

        out = EnrichmentService().apply(
            corpus_id=self.corpus.id, creator_id=self.user.id
        )
        assert DocumentRelationship.objects.filter(corpus=self.corpus).count() == count
        assert out["document_relationships_created"] == 0

    def test_link_pass_repairs_stale_exhibit_link_urls(self):
        """Same-corpus DOCUMENT (exhibit) mention links are repaired by the
        linking pass when the corpus slug changes after stamping."""
        from opencontractserver.annotations.models import CorpusReference as CR

        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)
        self.corpus.refresh_from_db()
        self.corpus.slug = "renamed-s1-corpus"
        self.corpus.save()

        EnrichmentService().link_external_references(
            corpus_id=self.corpus.id, creator_id=self.user.id
        )

        doc_ref = CR.objects.get(corpus=self.corpus, reference_type=C.REF_DOCUMENT)
        self.exhibit_in_corpus.refresh_from_db()
        assert doc_ref.source_annotation.link_url == (
            f"/d/{self.corpus.creator.slug}/renamed-s1-corpus"
            f"/{self.exhibit_in_corpus.slug}"
        )

    def test_defined_terms_opt_in_only(self):
        # Default apply excludes DEFINED_TERM.
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)
        assert (
            Annotation.objects.filter(
                corpus=self.corpus, annotation_label__text=C.LABEL_REF_TERM
            ).count()
            == 0
        )

    def test_defined_terms_create_mentions_only(self):
        """Definition sites are mention-only: the OC_REF_TERM annotation
        already carries ``term:<slug>`` in its data, so no CorpusReference
        row is written until usage->definition linking exists (a definition
        site has no target — it IS the target)."""
        # PRIMARY_TEXT has no parenthetical definition; add a doc that does.
        doc = Document.objects.create(title="Defs", creator=self.user)
        doc.txt_extract_file.save(
            "defs.txt",
            ContentFile(
                b'Fervo Energy, Inc. (the "Company"). "Change of Control" means a sale.'
            ),
        )
        self.corpus.add_document(document=doc, user=self.user)

        EnrichmentService().apply(
            corpus_id=self.corpus.id,
            creator_id=self.user.id,
            types=list(C.ALL_REFERENCE_TYPES),
        )
        term_anns = Annotation.objects.filter(
            corpus=self.corpus, annotation_label__text=C.LABEL_REF_TERM
        )
        keys = {a.data.get("canonical_key") for a in term_anns if a.data}
        assert "term:company" in keys
        assert "term:change-of-control" in keys
        assert (
            CorpusReference.objects.filter(
                corpus=self.corpus, reference_type=C.REF_DEFINED_TERM
            ).count()
            == 0
        )

    def test_longer_alias_match_does_not_duplicate_mention(self):
        """Growing the alias registry lengthens law-citation spans; the
        mention dedup must match on span start, not the exact span."""
        from opencontractserver.enrichment.authorities import (
            AuthorityCorpusBootstrapper,
            AuthoritySection,
        )

        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)
        law_count = Annotation.objects.filter(
            corpus=self.corpus, annotation_label__text=C.LABEL_REF_LAW
        ).count()

        # Declare a longer alias that now wins longest-first matching for the
        # same citations ("...Delaware General Corporation Law" is unchanged,
        # but make the point with an alias extension).
        AuthorityCorpusBootstrapper().bootstrap(
            creator_id=self.user.id,
            corpus_title="Delaware General Corporation Law",
            aliases=["Delaware General Corporation Law, as amended"],
            sections=[
                AuthoritySection(key="dgcl:145", heading="DGCL § 145", text="...")
            ],
        )

        out = EnrichmentService().apply(
            corpus_id=self.corpus.id, creator_id=self.user.id
        )
        assert out["annotations_created"] == 0
        assert (
            Annotation.objects.filter(
                corpus=self.corpus, annotation_label__text=C.LABEL_REF_LAW
            ).count()
            == law_count
        )

    def test_apply_is_idempotent(self):
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)
        ann_count = Annotation.objects.filter(corpus=self.corpus).count()
        ref_count = CorpusReference.objects.filter(corpus=self.corpus).count()

        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)
        assert Annotation.objects.filter(corpus=self.corpus).count() == ann_count
        assert CorpusReference.objects.filter(corpus=self.corpus).count() == ref_count

    def test_scan_writes_nothing(self):
        before = CorpusReference.objects.count()
        out = EnrichmentService().scan(
            corpus_id=self.corpus.id, creator_id=self.user.id
        )
        assert out["total_candidates"] > 0
        assert CorpusReference.objects.count() == before
        assert Annotation.objects.filter(corpus=self.corpus).count() == 0

    def test_reference_visibility_scoped_to_corpus(self):
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)
        other = User.objects.create_user(username="stranger", password="p")
        visible = CorpusReferenceService.for_corpus(other, self.corpus.id)
        assert visible.count() == 0
        mine = CorpusReferenceService.for_corpus(self.user, self.corpus.id)
        assert mine.count() > 0


class CorpusReferencesResolverGuardTests(TestCase):
    """Fix 1: malformed relay-ID guard in resolve_corpus_references.

    A non-relay / non-numeric corpus_id must return an empty result set
    (not raise a 500 / ValueError).
    """

    def setUp(self):
        self.user = User.objects.create_user(username="gql-guard", password="p")

    def _execute(self, corpus_id_value: str):
        # Lazy import: building the graphene schema at module import time trips
        # a graphene-django field-resolution error under coverage instrumentation
        # (collection-time), which silently drops this file's coverage. Importing
        # inside the method defers the build to runtime. Mirrors the pattern in
        # test_enrichment_tools.py / test_governance_graph.py.
        from config.graphql.schema import schema

        client = Client(schema)
        query = """
            query CorpusRefs($corpusId: ID!) {
              corpusReferences(corpusId: $corpusId) {
                edges { node { id } }
              }
            }
        """
        return client.execute(
            query,
            variable_values={"corpusId": corpus_id_value},
            context_value=_GQLContext(self.user),
        )

    def test_malformed_relay_id_returns_empty_no_error(self):
        """A non-relay string must not raise a 500 — should return empty edges."""
        result = self._execute("not-a-real-id")
        self.assertNotIn("errors", result)
        self.assertEqual(result["data"]["corpusReferences"]["edges"], [])

    def test_non_numeric_decoded_pk_returns_empty_no_error(self):
        """A base64-encoded type:pk where pk is non-numeric must return empty."""
        import base64

        # Encodes to CorpusType:abc — decodes fine but pk "abc" is not a digit.
        relay_id = base64.b64encode(b"CorpusType:abc").decode()
        result = self._execute(relay_id)
        self.assertNotIn("errors", result)
        self.assertEqual(result["data"]["corpusReferences"]["edges"], [])


class PdfTokenMentionTests(TestCase):
    """Mention annotations on PDF documents are projected onto PAWLs tokens.

    The enrichment extractor works in char offsets against
    ``txt_extract_file``; for PDFs that text IS the PlasmaPDF translation
    layer's ``doc_text`` (the parser saves it that way), so the writer can
    project each mention onto token bounding boxes losslessly — the same
    machinery datacell grounding uses. TXT documents keep span mentions.
    """

    # Two pages so the page projection is observable (legacy writer
    # hardcoded page=1 for everything).
    PAGES = [
        "We are subject to Section 203 of the Delaware General Corporation "
        + "Law and related provisions thereof. "
        + "See “Risk Factors” for important considerations.",
        "Risk Factors are described here. "
        + "Indemnification is governed by Section 145 of the Delaware General "
        + "Corporation Law as amended.",
    ]

    def setUp(self):
        import json as jsonlib

        from plasmapdf.models.PdfDataLayer import build_translation_layer

        from opencontractserver.tests.test_extraction_grounding import (
            _build_pawls_for_text,
        )

        self.user = User.objects.create_user(username="pdf-owner", password="p")
        self.corpus = Corpus.objects.create(title="PDF Corpus", creator=self.user)

        pawls_json = _build_pawls_for_text(self.PAGES)
        layer = build_translation_layer(jsonlib.loads(pawls_json))
        self.doc_text = layer.doc_text

        self.pdf_doc = Document.objects.create(
            title="Acme S-1 (2024-09-30) - primary document",
            creator=self.user,
            file_type="application/pdf",
        )
        self.pdf_doc.pawls_parse_file.save(
            "doc.pawls", ContentFile(pawls_json.encode("utf-8"))
        )
        # Mirrors the parser: txt extract is the translation layer's text.
        self.pdf_doc.txt_extract_file.save(
            "doc.txt", ContentFile(self.doc_text.encode("utf-8"))
        )
        self.in_corpus, _, _ = self.corpus.add_document(
            document=self.pdf_doc, user=self.user
        )

    def _law_mentions(self):
        return Annotation.objects.filter(
            document=self.in_corpus,
            corpus=self.corpus,
            annotation_label__text=C.LABEL_REF_LAW,
        )

    def test_pdf_mentions_are_token_annotations_with_real_pages(self):
        from opencontractserver.annotations.models import TOKEN_LABEL

        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)

        mentions = list(self._law_mentions())
        assert len(mentions) >= 2, [m.raw_text for m in mentions]
        for m in mentions:
            assert m.annotation_type == TOKEN_LABEL, m.raw_text
            # Token payload: page-keyed dict (v1 or v2 compact), NOT a span.
            assert isinstance(m.json, dict)
            assert "start" not in m.json, m.json
            # The char span survives as data so dedupe/converge can key on it.
            assert isinstance(m.data.get("char_span"), dict), m.data
            assert isinstance(m.data["char_span"]["start"], int)
            assert m.annotation_label.label_type == TOKEN_LABEL

        # The §145 mention is on the second page — the legacy hardcoded
        # page=1 would flunk this.
        pages = {m.page for m in mentions}
        assert len(pages) >= 2, pages

        # See-quoted-heading SECTION refs anchor their span at the quoted
        # heading while raw_text includes the "See " prefix (raw extends LEFT
        # of the span start) — the projection must handle that shape too.
        section_mentions = list(
            Annotation.objects.filter(
                document=self.in_corpus,
                corpus=self.corpus,
                annotation_label__text=C.LABEL_REF_SECTION,
                raw_text__icontains="Risk Factors",
            )
        )
        assert section_mentions, "expected the see-quoted section mention"
        from opencontractserver.annotations.models import TOKEN_LABEL as _TL

        for m in section_mentions:
            assert m.annotation_type == _TL, (m.raw_text, m.json)

        # CorpusReference rows still hang off the token mentions.
        assert (
            CorpusReference.objects.filter(
                corpus=self.corpus, reference_type=C.REF_LAW
            ).count()
            >= 2
        )

    def test_reapply_is_idempotent_for_token_mentions(self):
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)
        before = self._law_mentions().count()
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)
        assert self._law_mentions().count() == before

    def test_reapply_skips_projection_for_existing_token_mentions(self):
        """A converged PDF mention must not be rebuilt on every rerun."""
        from unittest.mock import patch

        from opencontractserver.enrichment.writer import EnrichmentWriter

        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)

        with patch.object(
            EnrichmentWriter,
            "_project_mention",
            side_effect=AssertionError("existing token mentions must not reproject"),
        ):
            out = EnrichmentService().apply(
                corpus_id=self.corpus.id, creator_id=self.user.id
            )

        assert out["annotations_created"] == 0

    def test_legacy_span_mention_is_upgraded_in_place(self):
        """Re-running enrichment converges pre-fix span mentions to token
        mentions without duplicating them or breaking CorpusReference FKs."""
        from opencontractserver.annotations.models import TOKEN_LABEL

        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)
        mention = self._law_mentions().first()
        assert mention is not None
        ref_ids = set(
            CorpusReference.objects.filter(source_annotation=mention).values_list(
                "id", flat=True
            )
        )

        # Downgrade to the exact legacy shape the old writer produced.
        span_label = self.corpus.ensure_label_and_labelset(
            label_text=C.LABEL_REF_LAW,
            creator_id=self.user.id,
            label_type=SPAN_LABEL,
        )
        char_span = dict(mention.data["char_span"])
        legacy_data = {
            k: v for k, v in (mention.data or {}).items() if k != "char_span"
        }
        Annotation.objects.filter(pk=mention.pk).update(
            json={"start": char_span["start"], "end": char_span["end"]},
            annotation_type=SPAN_LABEL,
            annotation_label=span_label,
            page=1,
            data=legacy_data or None,
        )

        before = self._law_mentions().count()
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)
        assert self._law_mentions().count() == before  # no duplicate

        mention.refresh_from_db()
        assert mention.annotation_type == TOKEN_LABEL
        assert "start" not in mention.json
        assert mention.data["char_span"] == char_span
        assert mention.annotation_label.label_type == TOKEN_LABEL
        # The reference rows still point at the same (upgraded) annotation.
        assert (
            set(
                CorpusReference.objects.filter(source_annotation=mention).values_list(
                    "id", flat=True
                )
            )
            == ref_ids
        )

    def test_drifted_offsets_are_remapped_by_occurrence(self):
        """Real ingests routinely have whitespace-level drift between
        ``txt_extract_file`` and the PAWLs-derived text (e.g. page
        separators). Offsets then disagree, but each mention's raw text still
        occurs in the same order in both — the writer remaps by ordinal
        occurrence so PDF mentions keep their token representation."""
        from opencontractserver.annotations.models import TOKEN_LABEL

        # Shift everything: extra prefix + doubled whitespace mimic a parser
        # that joined pages/sentences differently from PlasmaPDF; the
        # line-wrapped citation mimics the hard-wrap drift seen on real
        # EDGAR ingests (raw_text carries '\n' where PAWLs text has ' ').
        drifted = "FORM S-1 COVER\n\n" + self.doc_text.replace(
            "Section 145 of the Delaware", "Section 145 of\nthe Delaware"
        ).replace(" Section 203", "  Section 203")
        self.in_corpus.txt_extract_file.save(
            "drifted.txt", ContentFile(drifted.encode("utf-8"))
        )

        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)

        mentions = list(self._law_mentions())
        assert len(mentions) >= 2
        for m in mentions:
            assert m.annotation_type == TOKEN_LABEL, (m.raw_text, m.json)
        assert len({m.page for m in mentions}) >= 2

    def test_unfindable_mention_falls_back_to_span(self):
        """A mention whose raw text does not exist in the PAWLs-derived text
        at all (txt extract materially diverged) cannot be projected — keep
        the trustworthy span representation rather than painting tokens in
        the wrong place."""
        ghost = (
            self.doc_text
            + " Plus a ghost citation: Section 999 of the Investment Company Act."
        )
        self.in_corpus.txt_extract_file.save(
            "ghost.txt", ContentFile(ghost.encode("utf-8"))
        )

        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)

        ghost_mentions = [
            m for m in self._law_mentions() if "999" in (m.raw_text or "")
        ]
        assert ghost_mentions, "expected the ghost citation to be extracted"
        for m in ghost_mentions:
            assert m.annotation_type == SPAN_LABEL, m.raw_text
            assert "start" in m.json


class WriterClassificationStampTests(TestCase):
    """The writer copies a grammar candidate's classification onto the row."""

    def setUp(self):
        from django.contrib.auth import get_user_model

        self.user = get_user_model().objects.create_user(username="w", password="p")
        self.corpus = Corpus.objects.create(title="C", creator=self.user)
        self.doc = Document.objects.create(title="D", creator=self.user)

    def test_grammar_candidate_classification_persisted(self):
        from opencontractserver.enrichment import constants as C
        from opencontractserver.enrichment.extractor import Candidate
        from opencontractserver.enrichment.resolver import Resolution
        from opencontractserver.enrichment.writer import EnrichmentWriter

        cand = Candidate(
            reference_type=C.REF_LAW,
            start=0,
            end=18,
            raw_text="15 U.S.C. § 78j(b)",
            canonical_key="usc-15:78j(b)",
            jurisdiction="us-federal",
            authority_type="statute",
            detection_tier="grammar",
            detection_confidence=0.9,
        )
        res = Resolution(
            candidate=cand,
            source_document_id=self.doc.id,
            resolution_status=C.STATUS_EXTERNAL,
            canonical_key="usc-15:78j(b)",
            normalized_data=dict(cand.normalized_data),
        )
        writer = EnrichmentWriter(self.corpus, self.user.id, analysis=None)
        writer.write([res])

        from opencontractserver.annotations.models import CorpusReference

        ref = CorpusReference.objects.get(canonical_key="usc-15:78j(b)")
        assert ref.jurisdiction == "us-federal"
        assert ref.authority_type == "statute"
        assert ref.detection_tier == "grammar"
        assert ref.detection_confidence == 0.9
