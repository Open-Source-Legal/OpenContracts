"""Tests for the cross-corpus resolution pass (EXTERNAL law refs -> RESOLVED)."""

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase

from opencontractserver.annotations.models import CorpusReference
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.authorities import (
    AuthorityCorpusBootstrapper,
    AuthoritySection,
)
from opencontractserver.enrichment.service import EnrichmentService

User = get_user_model()

S1_TEXT = (
    "We are governed by Section 203 of the Delaware General Corporation Law. "
    "Indemnification is provided per Section 145 of the Delaware General "
    "Corporation Law. The offering relies on Section 4(a)(2) of the "
    "Securities Act."
)


class CrossCorpusLinkingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="p")
        self.corpus = Corpus.objects.create(title="S-1 Corpus", creator=self.user)
        doc = Document.objects.create(title="Acme S-1 primary", creator=self.user)
        doc.txt_extract_file.save("s1.txt", ContentFile(S1_TEXT.encode("utf-8")))
        self.corpus.add_document(document=doc, user=self.user)

    def _bootstrap_dgcl(self, user=None):
        return AuthorityCorpusBootstrapper().bootstrap(
            creator_id=(user or self.user).id,
            corpus_title="Delaware General Corporation Law",
            sections=[
                AuthoritySection(key="dgcl:145", heading="DGCL § 145", text="..145.."),
                AuthoritySection(key="dgcl:203", heading="DGCL § 203", text="..203.."),
            ],
        )

    def test_link_upgrades_external_law_refs(self):
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)
        auth = self._bootstrap_dgcl()

        out = EnrichmentService().link_external_references(
            corpus_id=self.corpus.id, creator_id=self.user.id
        )
        assert out["law_references_linked"] == 2

        ref = CorpusReference.objects.get(corpus=self.corpus, canonical_key="dgcl:145")
        assert ref.resolution_status == C.STATUS_RESOLVED
        assert ref.target_corpus_id == auth["corpus_id"]
        assert ref.target_document is not None
        assert ref.source_annotation.link_url == (
            f"/corpus/{auth['corpus_id']}/document/{ref.target_document_id}"
        )
        # No DGCL doc for the Securities Act citation -> still external.
        sa = CorpusReference.objects.get(
            corpus=self.corpus, canonical_key="securities-act:4(a)(2)"
        )
        assert sa.resolution_status == C.STATUS_EXTERNAL
        assert sa.target_document is None

    def test_apply_links_automatically_when_authority_exists(self):
        self._bootstrap_dgcl()
        out = EnrichmentService().apply(
            corpus_id=self.corpus.id, creator_id=self.user.id
        )
        assert out["law_references_linked"] == 2

    def test_link_is_idempotent(self):
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)
        self._bootstrap_dgcl()
        EnrichmentService().link_external_references(
            corpus_id=self.corpus.id, creator_id=self.user.id
        )
        again = EnrichmentService().link_external_references(
            corpus_id=self.corpus.id, creator_id=self.user.id
        )
        assert again["law_references_linked"] == 0

    def test_self_referential_statute_corpus_links_internally(self):
        """Enrichment ON an authority corpus: '§ X of this title' citations in
        statute text resolve to sibling sections of the same corpus."""
        auth = AuthorityCorpusBootstrapper().bootstrap(
            creator_id=self.user.id,
            corpus_title="Delaware General Corporation Law",
            sections=[
                AuthoritySection(
                    key="dgcl:251",
                    heading="DGCL § 251",
                    text=(
                        "Any 2 or more corporations may merge into a single "
                        "corporation. Notice shall be given as provided in "
                        "§ 222 of this title."
                    ),
                ),
                AuthoritySection(
                    key="dgcl:222",
                    heading="DGCL § 222",
                    text="Whenever stockholders are required to take action...",
                ),
            ],
        )

        out = EnrichmentService().apply(
            corpus_id=auth["corpus_id"], creator_id=self.user.id
        )
        assert out["law_references_linked"] == 1

        ref = CorpusReference.objects.get(
            corpus_id=auth["corpus_id"], canonical_key="dgcl:222"
        )
        assert ref.resolution_status == C.STATUS_RESOLVED
        assert ref.target_corpus_id == auth["corpus_id"]
        assert ref.target_document is not None
        assert (ref.target_document.custom_meta or {})["canonical_key"] == "dgcl:222"
        assert (ref.normalized_data or {})["relative"] is True

    def test_link_respects_authority_visibility(self):
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)
        other = User.objects.create_user(username="other", password="p")
        self._bootstrap_dgcl(user=other)  # private to `other`

        out = EnrichmentService().link_external_references(
            corpus_id=self.corpus.id, creator_id=self.user.id
        )
        assert out["law_references_linked"] == 0
        ref = CorpusReference.objects.get(corpus=self.corpus, canonical_key="dgcl:145")
        assert ref.resolution_status == C.STATUS_EXTERNAL
