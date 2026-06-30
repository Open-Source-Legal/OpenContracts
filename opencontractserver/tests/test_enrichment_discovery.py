"""Open-vocabulary discovery surfaces non-registry authorities."""

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase

from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.enrichment.services import EnrichmentService

User = get_user_model()

_TEXT = (
    "The issuer is liable under 15 U.S.C. § 78j(b) and must comply with "
    "40 C.F.R. § 261.4. It is also governed by Tex. Bus. Orgs. Code § 21.401 "
    "and Section 145 of the Delaware General Corporation Law."
)


class DiscoveryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="d", password="p")
        self.corpus = Corpus.objects.create(title="C", creator=self.user)
        doc = Document.objects.create(title="D", creator=self.user)
        doc.txt_extract_file.save("d.txt", ContentFile(_TEXT.encode("utf-8")))
        self.corpus.add_document(document=doc, user=self.user)

    def test_registry_only_scan_misses_usc_and_cfr(self):
        out = EnrichmentService().scan(
            corpus_id=self.corpus.id, creator_id=self.user.id
        )
        keys = {s["canonical_key"] for s in out["samples"]}
        assert "dgcl:145" in keys  # registry still works
        assert "usc-15:78j(b)" not in keys  # not detected at registry tier

    def test_grammar_tier_finds_open_vocabulary_authorities(self):
        out = EnrichmentService().discover(
            corpus_id=self.corpus.id, creator_id=self.user.id
        )
        keys = set(out["by_key"])
        assert "usc-15:78j(b)" in keys
        assert "cfr-40:261.4" in keys
        assert "tx-boc:21.401" in keys
        assert "us-tx" in out["by_jurisdiction"]
        assert any(n["prefix"] == "tx-boc" for n in out["new_namespaces"])
        # dgcl is seeded → NOT new. And registry-tier classification is
        # backfilled, so its jurisdiction appears in the rollup (regression #6).
        assert not any(n["prefix"] == "dgcl" for n in out["new_namespaces"])
        assert "us-de" in out["by_jurisdiction"]
        # Unbounded by default: the whole corpus is scanned, nothing truncated.
        assert out["documents_truncated"] is False
        assert out["documents_total_in_corpus"] == 1
        assert out["documents_visible_to_caller"] == 1
        assert out["documents_excluded_by_visibility"] == 0

    def test_max_documents_caps_the_scan_and_flags_truncation(self):
        # Add a second document so the corpus exceeds the cap; max_documents=1
        # scans a single doc and the result advertises the truncation rather
        # than silently dropping coverage.
        doc2 = Document.objects.create(title="D2", creator=self.user)
        doc2.txt_extract_file.save(
            "d2.txt", ContentFile(b"Liability attaches under 15 U.S.C. 78j(b).")
        )
        self.corpus.add_document(document=doc2, user=self.user)

        out = EnrichmentService().discover(
            corpus_id=self.corpus.id, creator_id=self.user.id, max_documents=1
        )
        assert out["documents_total_in_corpus"] == 2
        assert out["documents_visible_to_caller"] == 2
        assert out["documents_scanned"] == 1
        assert out["documents_truncated"] is True
