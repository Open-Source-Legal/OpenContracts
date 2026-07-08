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
        from graphql_relay import to_global_id

        from config.graphql.schema import schema
        from config.graphql.testing import Client

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


class CorpusReferenceDocumentFilterTests(TestCase):
    """``corpusReferences(documentId:)`` returns refs touching EITHER side.

    The document References side-panel fetches one document's inbound +
    outbound references in a single query and splits client-side.
    """

    DOC_TEXT = (
        "Indemnification under Section 145 of the Delaware General Corporation "
        "Law. The underwriting agreement is filed as Exhibit 1.1 hereto."
    )

    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="p")
        self.corpus = Corpus.objects.create(title="C", creator=self.user)
        primary = Document.objects.create(title="Acme S-1 primary", creator=self.user)
        primary.txt_extract_file.save(
            "p.txt", ContentFile(self.DOC_TEXT.encode("utf-8"))
        )
        exhibit = Document.objects.create(
            title="Acme S-1 - Exhibit 1.1: EX-1.1", creator=self.user
        )
        exhibit.txt_extract_file.save("e.txt", ContentFile(b"Underwriting."))
        self.primary_in_corpus, _, _ = self.corpus.add_document(
            document=primary, user=self.user
        )
        self.exhibit_in_corpus, _, _ = self.corpus.add_document(
            document=exhibit, user=self.user
        )
        apply_corpus_reference_enrichment(
            corpus_id=self.corpus.id, creator_id=self.user.id
        )

    def _run(self, document_pk):
        from graphql_relay import to_global_id

        from config.graphql.schema import schema
        from config.graphql.testing import Client

        query = """
            query ($cid: ID!, $did: ID) {
              corpusReferences(corpusId: $cid, documentId: $did) {
                edges { node { referenceType canonicalKey } }
              }
            }
        """
        return Client(schema, context_value=_Ctx(self.user)).execute(
            query,
            variables={
                "cid": to_global_id("CorpusType", self.corpus.id),
                "did": to_global_id("DocumentType", document_pk),
            },
        )

    def test_source_document_returns_its_outbound_references(self):
        result = self._run(self.primary_in_corpus.id)
        assert result.get("errors") is None, result.get("errors")
        types = {
            e["node"]["referenceType"]
            for e in result["data"]["corpusReferences"]["edges"]
        }
        assert "LAW" in types
        assert "DOCUMENT" in types

    def test_target_document_returns_its_inbound_references(self):
        # The exhibit is only ever a TARGET (the primary cites it).
        result = self._run(self.exhibit_in_corpus.id)
        assert result.get("errors") is None, result.get("errors")
        edges = result["data"]["corpusReferences"]["edges"]
        assert edges, "expected the inbound DOCUMENT reference"
        assert {e["node"]["referenceType"] for e in edges} == {"DOCUMENT"}

    def test_unrelated_document_returns_nothing(self):
        other = Document.objects.create(title="Unrelated", creator=self.user)
        result = self._run(other.id)
        assert result.get("errors") is None, result.get("errors")
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
        from graphql_relay import to_global_id

        from config.graphql.schema import schema
        from config.graphql.testing import Client

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

    def test_document_filter_is_idor_safe_for_invisible_doc(self):
        # IDOR: a corpus reader filtering by an INVISIBLE document's id must
        # not learn whether it has references — that would probe the private
        # target. The owner, who can see the document, still gets the row.
        from graphql_relay import to_global_id

        from config.graphql.schema import schema
        from config.graphql.testing import Client

        query = """
            query ($cid: ID!, $did: ID) {
              corpusReferences(corpusId: $cid, documentId: $did) {
                edges { node { canonicalKey } }
              }
            }
        """
        variables = {
            "cid": to_global_id("CorpusType", self.corpus.id),
            "did": to_global_id("DocumentType", self.private_doc.id),
        }
        reader_res = Client(schema, context_value=_Ctx(self.reader)).execute(
            query, variables=variables
        )
        assert reader_res.get("errors") is None, reader_res.get("errors")
        assert reader_res["data"]["corpusReferences"]["edges"] == []

        owner_res = Client(schema, context_value=_Ctx(self.owner)).execute(
            query, variables=variables
        )
        assert owner_res.get("errors") is None, owner_res.get("errors")
        assert owner_res["data"]["corpusReferences"]["edges"]


class BackfillToolRegistryTests(TestCase):
    def test_backfill_tools_are_registered(self):
        names = {t.name for t in AVAILABLE_TOOLS}
        assert "list_wanted_authorities" in names
        assert "bootstrap_authority_corpus" in names

    def test_bootstrap_tool_requires_approval_and_write(self):
        td = next(t for t in AVAILABLE_TOOLS if t.name == "bootstrap_authority_corpus")
        assert td.requires_approval is True
        assert td.requires_write_permission is True

    def test_list_wanted_tool_is_corpus_scoped_read_only(self):
        td = next(t for t in AVAILABLE_TOOLS if t.name == "list_wanted_authorities")
        assert td.requires_corpus is True
        assert td.requires_approval is False
        assert td.requires_write_permission is False


class BackfillToolFunctionTests(TestCase):
    def setUp(self):
        from opencontractserver.llms.tools.core_tools import (
            apply_corpus_reference_enrichment,
        )

        self.user = User.objects.create_user(username="owner2", password="p")
        self.corpus = Corpus.objects.create(title="C2", creator=self.user)
        doc = Document.objects.create(title="S-1 primary document", creator=self.user)
        doc.txt_extract_file.save("d.txt", ContentFile(TEXT.encode("utf-8")))
        self.corpus.add_document(document=doc, user=self.user)
        apply_corpus_reference_enrichment(
            corpus_id=self.corpus.id, creator_id=self.user.id
        )

    def test_list_wanted_authorities_reports_queue(self):
        from opencontractserver.llms.tools.core_tools import list_wanted_authorities

        out = list_wanted_authorities(corpus_id=self.corpus.id, creator_id=self.user.id)
        auths = {w["authority"] for w in out["authorities"]}
        assert "dgcl" in auths

    def test_bootstrap_tool_creates_authority_and_relinks(self):
        from opencontractserver.llms.tools.core_tools import (
            bootstrap_authority_corpus,
        )

        out = bootstrap_authority_corpus(
            creator_id=self.user.id,
            corpus_title="Delaware General Corporation Law",
            sections=[
                {"key": "dgcl:145", "heading": "DGCL § 145", "text": "..145.."},
            ],
        )
        assert out["documents_created"] == 1
        assert out["relink"]["law_references_linked"] == 1
        ref = CorpusReference.objects.get(corpus=self.corpus, canonical_key="dgcl:145")
        assert ref.resolution_status == "RESOLVED"

    def test_bootstrap_tool_async_relink_offloads_to_celery(self):
        # The async agent-tool path threads relink_async=True so the relink
        # sweep is enqueued instead of run inline (no thread-pool slot held for
        # minutes on a large authority set).
        from opencontractserver.llms.tools.core_tools import (
            bootstrap_authority_corpus,
        )

        out = bootstrap_authority_corpus(
            creator_id=self.user.id,
            corpus_title="Delaware General Corporation Law",
            sections=[
                {"key": "dgcl:145", "heading": "DGCL § 145", "text": "..145.."},
            ],
            relink_async=True,
        )
        # Offloaded: the inline summary is replaced by a queued task handle.
        assert out["relink"]["queued"] is True
        assert out["relink"]["task_id"]
        # Celery runs eagerly under test settings, so the citing corpus still
        # converged: the EXTERNAL dgcl:145 reference upgraded to RESOLVED.
        ref = CorpusReference.objects.get(corpus=self.corpus, canonical_key="dgcl:145")
        assert ref.resolution_status == "RESOLVED"

    def test_bootstrap_tool_rejects_malformed_sections(self):
        from opencontractserver.llms.tools.core_tools import (
            bootstrap_authority_corpus,
        )

        with self.assertRaises(ValueError):
            bootstrap_authority_corpus(
                creator_id=self.user.id,
                corpus_title="Broken",
                sections=[{"heading": "missing key and text"}],
            )
        with self.assertRaises(ValueError):
            bootstrap_authority_corpus(
                creator_id=self.user.id, corpus_title="Empty", sections=[]
            )


class DiscoverAuthoritiesToolTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="dt", password="p")
        self.corpus = Corpus.objects.create(title="C", creator=self.user)
        doc = Document.objects.create(title="D", creator=self.user)
        doc.txt_extract_file.save(
            "d.txt",
            ContentFile(b"Liable under 15 U.S.C. 78j(b) and 40 C.F.R. 261.4."),
        )
        self.corpus.add_document(document=doc, user=self.user)

    def test_discover_returns_open_vocab_keys(self):
        from opencontractserver.llms.tools.core_tools.corpus_references import (
            discover_authorities,
        )

        out = discover_authorities(corpus_id=self.corpus.id, creator_id=self.user.id)
        assert "usc-15:78j(b)" in out["by_key"]
        assert out["new_namespaces"]  # usc/cfr prefixes not registered

    def test_discover_tool_is_corpus_scoped_read_only(self):
        td = next(t for t in AVAILABLE_TOOLS if t.name == "discover_authorities")
        assert td.requires_corpus is True
        assert td.requires_approval is False
        assert td.requires_write_permission is False


class CrawlAuthoritiesToolRegistryTests(TestCase):
    """crawl_authorities is registered at all four sites with the correct flags."""

    def test_crawl_authorities_in_available_tools(self):
        names = {t.name for t in AVAILABLE_TOOLS}
        assert "crawl_authorities" in names

    def test_crawl_authorities_flags(self):
        td = next(t for t in AVAILABLE_TOOLS if t.name == "crawl_authorities")
        assert td.requires_corpus is True
        assert td.requires_approval is True
        assert td.requires_write_permission is True

    def test_crawl_authorities_has_expected_parameters(self):
        td = next(t for t in AVAILABLE_TOOLS if t.name == "crawl_authorities")
        param_names = {p[0] for p in td.parameters}
        assert "max_depth" in param_names
        assert "min_demand" in param_names
        assert "max_authorities" in param_names

    def test_crawl_authorities_importable_from_core_tools(self):
        from opencontractserver.llms.tools.core_tools import (  # noqa: F401
            acrawl_authorities,
            crawl_authorities,
        )

    def test_crawl_authorities_in_function_registry(self):
        from opencontractserver.llms.tools.tool_registry import ToolFunctionRegistry

        ToolFunctionRegistry.reset()
        reg = ToolFunctionRegistry.get()
        entry = reg.resolve("crawl_authorities")
        assert entry is not None
        assert entry.definition.requires_approval is True
        assert entry.definition.requires_corpus is True
        assert entry.definition.requires_write_permission is True
