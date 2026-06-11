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


class CorpusReferenceTraversalVisibilityTests(TestCase):
    """Nested FK traversal on ``CorpusReferenceType`` must not leak documents.

    ``corpusReferences`` is corpus-as-gate (corpus READ unlocks the rows), but
    ``targetDocument`` resolution goes through graphene-django's FK converter →
    ``DocumentType.get_node`` → ``DocumentType.get_queryset`` (visibility
    filtered). This pins that a reader of a public corpus gets ``null`` for a
    target document they cannot READ, while the owner still resolves it.
    """

    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="p")
        self.reader = User.objects.create_user(username="reader", password="p")
        self.corpus = Corpus.objects.create(
            title="Public C", creator=self.owner, is_public=True
        )
        doc = Document.objects.create(title="S-1 primary document", creator=self.owner)
        doc.txt_extract_file.save("d.txt", ContentFile(TEXT.encode("utf-8")))
        self.corpus.add_document(document=doc, user=self.owner)
        apply_corpus_reference_enrichment(
            corpus_id=self.corpus.id, creator_id=self.owner.id
        )
        # Point one reference at a PRIVATE document (owner-only, no public
        # corpus path) — the cross-corpus law-link shape.
        self.private_doc = Document.objects.create(
            title="Private statute section", creator=self.owner, is_public=False
        )
        ref = CorpusReference.objects.filter(corpus=self.corpus).first()
        assert ref is not None
        ref.target_document = self.private_doc
        ref.save(update_fields=["target_document", "modified"])
        self.ref = ref

    def _run(self, user):
        from graphene.test import Client
        from graphql_relay import to_global_id

        from config.graphql.schema import schema

        gid = to_global_id("CorpusType", self.corpus.id)
        query = """
            query ($cid: ID!) {
              corpusReferences(corpusId: $cid) {
                edges { node { canonicalKey targetDocument { id title } } }
              }
            }
        """
        return Client(schema, context_value=_Ctx(user)).execute(
            query, variables={"cid": gid}
        )

    def test_owner_resolves_target_document(self):
        result = self._run(self.owner)
        nodes = [e["node"] for e in result["data"]["corpusReferences"]["edges"]]
        assert any(
            n["targetDocument"]
            and n["targetDocument"]["title"] == "Private statute section"
            for n in nodes
        )

    def test_corpus_reader_gets_null_for_invisible_target_document(self):
        result = self._run(self.reader)
        edges = result["data"]["corpusReferences"]["edges"]
        # Corpus-as-gate: the reference rows themselves ARE visible...
        assert edges
        # ...but the private target document nulls out for the reader.
        assert all(e["node"]["targetDocument"] is None for e in edges)
