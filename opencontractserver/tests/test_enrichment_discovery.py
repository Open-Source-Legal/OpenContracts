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
