"""Tool-registry + tool-function tests for corpus reference enrichment."""

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase

from opencontractserver.annotations.models import Annotation, CorpusReference
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.llms.tools.core_tools import (
    apply_corpus_reference_enrichment,
    scan_corpus_references,
)
from opencontractserver.llms.tools.tool_registry import AVAILABLE_TOOLS

User = get_user_model()

TEXT = (
    "Indemnification under Section 145 of the Delaware General Corporation Law. "
    "Issued per Section 4(a)(2) of the Securities Act."
)


class EnrichmentToolRegistryTests(TestCase):
    def test_both_tools_are_registered(self):
        names = {t.name for t in AVAILABLE_TOOLS}
        assert "scan_corpus_references" in names
        assert "apply_corpus_reference_enrichment" in names

    def test_apply_tool_requires_approval_and_write(self):
        td = next(
            t for t in AVAILABLE_TOOLS if t.name == "apply_corpus_reference_enrichment"
        )
        assert td.requires_corpus is True
        assert td.requires_approval is True
        assert td.requires_write_permission is True


class EnrichmentToolFunctionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="p")
        self.corpus = Corpus.objects.create(title="C", creator=self.user)
        doc = Document.objects.create(title="S-1 primary document", creator=self.user)
        doc.txt_extract_file.save("d.txt", ContentFile(TEXT.encode("utf-8")))
        self.corpus.add_document(document=doc, user=self.user)

    def test_scan_writes_nothing_and_reports(self):
        out = scan_corpus_references(corpus_id=self.corpus.id, creator_id=self.user.id)
        assert out["total_candidates"] >= 2
        assert Annotation.objects.filter(corpus=self.corpus).count() == 0

    def test_apply_creates_references(self):
        out = apply_corpus_reference_enrichment(
            corpus_id=self.corpus.id, creator_id=self.user.id
        )
        assert out["references_created"] >= 2
        keys = set(
            CorpusReference.objects.filter(corpus=self.corpus).values_list(
                "canonical_key", flat=True
            )
        )
        assert "dgcl:145" in keys
        assert "securities-act:4(a)(2)" in keys


class _Ctx:
    def __init__(self, user):
        self.user = user


class EnrichmentGraphQLTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="p")
        self.corpus = Corpus.objects.create(title="C", creator=self.user)
        doc = Document.objects.create(title="S-1 primary document", creator=self.user)
        doc.txt_extract_file.save("d.txt", ContentFile(TEXT.encode("utf-8")))
        self.corpus.add_document(document=doc, user=self.user)
        apply_corpus_reference_enrichment(
            corpus_id=self.corpus.id, creator_id=self.user.id
        )

    def _run(self, user):
        from graphene.test import Client
        from graphql_relay import to_global_id

        from config.graphql.schema import schema

        gid = to_global_id("CorpusType", self.corpus.id)
        query = """
            query ($cid: ID!) {
              corpusReferences(corpusId: $cid, referenceType: "LAW") {
                edges { node { canonicalKey resolutionStatus } }
              }
            }
        """
        return Client(schema, context_value=_Ctx(user)).execute(
            query, variables={"cid": gid}
        )

    def test_owner_sees_law_references(self):
        result = self._run(self.user)
        edges = result["data"]["corpusReferences"]["edges"]
        keys = {e["node"]["canonicalKey"] for e in edges}
        assert "dgcl:145" in keys
        assert all(e["node"]["resolutionStatus"] == "EXTERNAL" for e in edges)

    def test_stranger_sees_nothing(self):
        stranger = User.objects.create_user(username="stranger", password="p")
        result = self._run(stranger)
        assert result["data"]["corpusReferences"]["edges"] == []
