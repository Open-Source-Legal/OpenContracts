"""Tests for the corpus-scoped governanceGraph GraphQL query.

The governance graph is the in-app surface of the reference web: nodes are
documents (filing primaries, exhibits, statute sections) plus "ghost" nodes
for still-EXTERNAL law citations; edges are resolved LAW links (possibly
cross-corpus), EXTERNAL law citations, ``DocumentRelationship`` rows, and
verified canonical-key ``AuthorityRelationship`` rows — weighted by mention
count. Mirrors ``demo/export_governance_graph.py``, visibility-enforced through
the service layer.
"""

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase
from graphql_relay import to_global_id

from opencontractserver.annotations.models import AuthorityRelationship
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.documents.versioning import import_document
from opencontractserver.enrichment.authorities import (
    AuthorityCorpusBootstrapper,
    AuthoritySection,
)
from opencontractserver.enrichment.services import EnrichmentService

User = get_user_model()

S1_TEXT = (
    "Indemnification is provided under Section 145 of the Delaware General "
    "Corporation Law. As permitted by Section 145 of the Delaware General "
    "Corporation Law, our charter limits liability. We are also governed by "
    "Section 203 of the Delaware General Corporation Law. The form of "
    "underwriting agreement is filed as Exhibit 1.1 hereto."
)

GRAPH_QUERY = """
    query ($cid: ID!) {
      governanceGraph(corpusId: $cid) {
        corpora { id title kind }
        nodes { id documentId title kind corpusId authority degree }
        edges { source target edgeType weight }
        documentCount
        externalKeyCount
        edgeCount
        mentionCount
        truncated
      }
    }
"""

GRAPH_QUERY_WITH_REGIME = """
    query ($cid: ID!) {
      governanceGraph(corpusId: $cid) {
        nodes {
          id
          title
          kind
          authority
          jurisdiction
          authorityType
          discoveryState
          degree
        }
      }
    }
"""


class _Ctx:
    def __init__(self, user):
        self.user = user


def _run_graph(user, corpus_pk):
    from config.graphql.schema import schema
    from config.graphql.testing import Client

    return Client(schema, context_value=_Ctx(user)).execute(
        GRAPH_QUERY, variables={"cid": to_global_id("CorpusType", corpus_pk)}
    )


REFS_QUERY = """
    query ($cid: ID!, $did: ID!) {
      corpusReferences(corpusId: $cid, documentId: $did) {
        edges { node { id referenceType } }
      }
    }
"""


def _run_refs(user, corpus_pk, document_gid):
    from config.graphql.schema import schema
    from config.graphql.testing import Client

    return Client(schema, context_value=_Ctx(user)).execute(
        REFS_QUERY,
        variables={
            "cid": to_global_id("CorpusType", corpus_pk),
            "did": document_gid,
        },
    )


class GovernanceGraphTests(TestCase):
    """Happy-path graph composition for a filing corpus with a linked authority."""

    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="p")
        self.corpus = Corpus.objects.create(title="S-1 Corpus", creator=self.user)
        self.primary = Document.objects.create(
            title="Acme Inc. S-1 (2026-01-01)", creator=self.user
        )
        self.primary.txt_extract_file.save(
            "s1.txt", ContentFile(S1_TEXT.encode("utf-8"))
        )
        self.exhibit = Document.objects.create(
            title="Acme Inc. S-1 (2026-01-01) - Exhibit 1.1: EX-1.1",
            creator=self.user,
        )
        self.exhibit.txt_extract_file.save("ex.txt", ContentFile(b"Underwriting."))
        self.corpus.add_document(document=self.primary, user=self.user)
        self.corpus.add_document(document=self.exhibit, user=self.user)
        # `add_document` creates corpus-local copies — enrichment resolves to
        # those, so the graph must be asserted against the in-corpus ids.
        self.primary_id, self.exhibit_id = (
            self.corpus.document_paths.filter(
                is_current=True, document__title=t
            ).values_list("document_id", flat=True)[0]
            for t in (self.primary.title, self.exhibit.title)
        )

        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)
        # Authority covers § 145 only — § 203 stays an EXTERNAL ghost.
        auth = AuthorityCorpusBootstrapper().bootstrap(
            creator_id=self.user.id,
            corpus_title="Delaware General Corporation Law",
            sections=[
                AuthoritySection(
                    key="dgcl:145", heading="DGCL § 145", text="Indemnification."
                ),
            ],
        )
        self.auth_corpus_id = auth["corpus_id"]
        EnrichmentService().link_external_references(
            corpus_id=self.corpus.id, creator_id=self.user.id
        )
        self.statute_id = (
            Corpus.objects.get(pk=self.auth_corpus_id)
            .document_paths.filter(is_current=True)
            .values_list("document_id", flat=True)[0]
        )

    def _graph(self):
        result = _run_graph(self.user, self.corpus.id)
        assert result.get("errors") is None, result.get("errors")
        return result["data"]["governanceGraph"]

    def _node_by_id(self, graph, node_id):
        return next(n for n in graph["nodes"] if n["id"] == node_id)

    def test_nodes_cover_documents_and_external_ghosts(self):
        graph = self._graph()
        primary_gid = to_global_id("DocumentType", self.primary_id)
        exhibit_gid = to_global_id("DocumentType", self.exhibit_id)
        statute_gid = to_global_id("DocumentType", self.statute_id)

        primary = self._node_by_id(graph, primary_gid)
        assert primary["kind"] == "primary"
        assert primary["documentId"] == primary_gid
        assert primary["corpusId"] == to_global_id("CorpusType", self.corpus.id)

        assert self._node_by_id(graph, exhibit_gid)["kind"] == "exhibit"

        statute = self._node_by_id(graph, statute_gid)
        assert statute["kind"] == "statute"
        assert statute["authority"] == "dgcl"
        assert statute["corpusId"] == to_global_id("CorpusType", self.auth_corpus_id)

        ghost = self._node_by_id(graph, "key:dgcl:203")
        assert ghost["kind"] == "external"
        assert ghost["documentId"] is None
        assert ghost["authority"] == "dgcl"
        assert ghost["title"] == "dgcl:203"

    def test_edges_weighted_by_mention_count(self):
        graph = self._graph()
        primary_gid = to_global_id("DocumentType", self.primary_id)
        statute_gid = to_global_id("DocumentType", self.statute_id)
        exhibit_gid = to_global_id("DocumentType", self.exhibit_id)

        by_key = {(e["source"], e["target"], e["edgeType"]): e for e in graph["edges"]}
        law = by_key[(primary_gid, statute_gid, "LAW")]
        assert law["weight"] == 2  # § 145 cited twice
        external = by_key[(primary_gid, "key:dgcl:203", "LAW_EXTERNAL")]
        assert external["weight"] == 1
        assert (primary_gid, exhibit_gid, "DOCUMENT") in by_key

        # Degree = sum of weights touching the node.
        primary = self._node_by_id(graph, primary_gid)
        doc_weight = by_key[(primary_gid, exhibit_gid, "DOCUMENT")]["weight"]
        assert primary["degree"] == 2 + 1 + doc_weight

    def test_corpora_classified_filing_vs_authority(self):
        graph = self._graph()
        kinds = {c["id"]: c["kind"] for c in graph["corpora"]}
        assert kinds[to_global_id("CorpusType", self.corpus.id)] == "filing"
        assert kinds[to_global_id("CorpusType", self.auth_corpus_id)] == "authority"

    def test_stats(self):
        graph = self._graph()
        assert graph["documentCount"] == 3  # primary, exhibit, statute
        assert graph["externalKeyCount"] == 1  # dgcl:203
        assert graph["edgeCount"] == len(graph["edges"])
        assert graph["mentionCount"] == sum(e["weight"] for e in graph["edges"])
        assert graph["truncated"] is False

    def test_invisible_corpus_returns_empty_graph(self):
        stranger = User.objects.create_user(username="stranger", password="p")
        result = _run_graph(stranger, self.corpus.id)
        assert result.get("errors") is None, result.get("errors")
        graph = result["data"]["governanceGraph"]
        assert graph["nodes"] == []
        assert graph["edges"] == []
        assert graph["documentCount"] == 0

    def test_invisible_authority_target_degrades_to_external_ghost(self):
        # A reader of the (public) filing corpus who cannot see the private
        # authority corpus must get a ghost node — not the statute document.
        reader = User.objects.create_user(username="reader", password="p")
        self.corpus.is_public = True
        self.corpus.save()
        Document.objects.filter(id__in=[self.primary_id, self.exhibit_id]).update(
            is_public=True
        )

        result = _run_graph(reader, self.corpus.id)
        assert result.get("errors") is None, result.get("errors")
        graph = result["data"]["governanceGraph"]

        statute_gid = to_global_id("DocumentType", self.statute_id)
        node_ids = {n["id"] for n in graph["nodes"]}
        assert statute_gid not in node_ids
        assert "key:dgcl:145" in node_ids  # degraded to ghost, rolled to root
        edge_types = {(e["source"], e["target"]): e["edgeType"] for e in graph["edges"]}
        primary_gid = to_global_id("DocumentType", self.primary_id)
        assert edge_types[(primary_gid, "key:dgcl:145")] == "LAW_EXTERNAL"
        # The private authority corpus must not be listed.
        corpus_ids = {c["id"] for c in graph["corpora"]}
        assert to_global_id("CorpusType", self.auth_corpus_id) not in corpus_ids

    def test_corpus_references_document_id_idor_guard(self):
        """A corpus reader cannot probe references by a document they can't see.

        The ``corpusReferences(documentId:)`` filter validates that the supplied
        document is READ-visible before filtering by it. The statute section
        lives in the private authority corpus and is a LAW target of this
        corpus's references — so without the guard, a reader of the (public)
        filing corpus could supply the statute's id and learn it has references.
        The guard returns the same empty result as a document with none.
        """
        primary_gid = to_global_id("DocumentType", self.primary_id)
        statute_gid = to_global_id("DocumentType", self.statute_id)

        # Owner sees both documents — a positive control proving each id genuinely
        # has references in the corpus (so the reader's empties below are the
        # guard at work, not an absence of data).
        owner_primary = _run_refs(self.user, self.corpus.id, primary_gid)
        assert owner_primary.get("errors") is None, owner_primary.get("errors")
        assert owner_primary["data"]["corpusReferences"][
            "edges"
        ], "expected the primary's outbound references"
        owner_statute = _run_refs(self.user, self.corpus.id, statute_gid)
        assert owner_statute["data"]["corpusReferences"][
            "edges"
        ], "expected inbound references targeting the statute section"

        # Reader can READ the filing corpus (public) but NOT the private statute.
        reader = User.objects.create_user(username="refs-reader", password="p")
        self.corpus.is_public = True
        self.corpus.save()
        Document.objects.filter(id__in=[self.primary_id, self.exhibit_id]).update(
            is_public=True
        )

        # Visible document → references flow through.
        reader_primary = _run_refs(reader, self.corpus.id, primary_gid)
        assert reader_primary.get("errors") is None, reader_primary.get("errors")
        assert reader_primary["data"]["corpusReferences"]["edges"]

        # Invisible document → IDOR guard returns empty (statute has refs, but the
        # reader cannot see it, so cannot probe by its id).
        reader_statute = _run_refs(reader, self.corpus.id, statute_gid)
        assert reader_statute.get("errors") is None, reader_statute.get("errors")
        assert reader_statute["data"]["corpusReferences"]["edges"] == []


class GovernanceGraphAuthorityRelationshipTests(TestCase):
    """Verified canonical authority edges reuse the production graph rail."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username="authority-graph-owner", password="p"
        )
        self.source_corpus = Corpus.objects.create(
            title="PUCT Orders", creator=self.owner
        )
        self.target_corpus = Corpus.objects.create(
            title="ERCOT Revision History", creator=self.owner
        )
        self.source_key = "puct-order:project-123:final"
        self.target_key = "ercot-pgrr:145"
        self.source_document, _, _ = import_document(
            corpus=self.source_corpus,
            path="/documents/final-order.txt",
            content=b"Final order text.",
            user=self.owner,
            file_type="text/plain",
            title="PUCT Final Order",
            custom_meta={
                "canonical_key": self.source_key,
                "authority": "puct-order",
            },
        )
        self.target_document, _, _ = import_document(
            corpus=self.target_corpus,
            path="/documents/pgrr-145.txt",
            content=b"Revision request text.",
            user=self.owner,
            file_type="text/plain",
            title="PGRR 145 Private Title",
            custom_meta={
                "canonical_key": self.target_key,
                "authority": "ercot-pgrr",
            },
        )

    def _create_relationship(self, *, verified: bool) -> AuthorityRelationship:
        return AuthorityRelationship.objects.create(
            source_key=self.source_key,
            relationship_type="IMPLEMENTS",
            target_key=self.target_key,
            source="manual",
            origin="governance-graph-test",
            verified=verified,
        )

    @staticmethod
    def _graph(user, corpus_pk):
        result = _run_graph(user, corpus_pk)
        assert result.get("errors") is None, result.get("errors")
        return result["data"]["governanceGraph"]

    def test_verified_cross_corpus_relationship_preserves_target_corpus(self):
        self._create_relationship(verified=True)

        graph = self._graph(self.owner, self.source_corpus.pk)
        source_gid = to_global_id("DocumentType", self.source_document.pk)
        target_gid = to_global_id("DocumentType", self.target_document.pk)
        target_corpus_gid = to_global_id("CorpusType", self.target_corpus.pk)

        assert {
            "source": source_gid,
            "target": target_gid,
            "edgeType": "IMPLEMENTS",
            "weight": 1,
        } in graph["edges"]
        target_node = next(node for node in graph["nodes"] if node["id"] == target_gid)
        assert target_node["corpusId"] == target_corpus_gid
        target_corpus = next(
            corpus for corpus in graph["corpora"] if corpus["id"] == target_corpus_gid
        )
        assert target_corpus["kind"] == "authority"

    def test_independent_installs_resolve_their_own_visible_current_copies(self):
        second_owner = User.objects.create_user(
            username="authority-graph-second-owner", password="p"
        )
        second_source_corpus = Corpus.objects.create(
            title="Second PUCT Orders", creator=second_owner
        )
        second_target_corpus = Corpus.objects.create(
            title="Second ERCOT Revision History", creator=second_owner
        )
        second_source_document, _, _ = import_document(
            corpus=second_source_corpus,
            path="/documents/final-order.txt",
            content=b"Independent final order copy.",
            user=second_owner,
            file_type="text/plain",
            title="Second PUCT Final Order",
            custom_meta={
                "canonical_key": self.source_key,
                "authority": "puct-order",
            },
        )
        second_target_document, _, _ = import_document(
            corpus=second_target_corpus,
            path="/documents/pgrr-145.txt",
            content=b"Independent revision request copy.",
            user=second_owner,
            file_type="text/plain",
            title="Second PGRR 145",
            custom_meta={
                "canonical_key": self.target_key,
                "authority": "ercot-pgrr",
            },
        )
        self._create_relationship(verified=True)

        first_current_source, _, _ = import_document(
            corpus=self.source_corpus,
            path="/documents/final-order.txt",
            content=b"Current final order text.",
            user=self.owner,
            file_type="text/plain",
            title="Current PUCT Final Order",
            custom_meta={
                "canonical_key": self.source_key,
                "authority": "puct-order",
            },
        )
        first_current_target, _, _ = import_document(
            corpus=self.target_corpus,
            path="/documents/pgrr-145.txt",
            content=b"Current revision request text.",
            user=self.owner,
            file_type="text/plain",
            title="Current PGRR 145",
            custom_meta={
                "canonical_key": self.target_key,
                "authority": "ercot-pgrr",
            },
        )
        second_current_source, _, _ = import_document(
            corpus=second_source_corpus,
            path="/documents/final-order.txt",
            content=b"Second current final order text.",
            user=second_owner,
            file_type="text/plain",
            title="Second Current PUCT Final Order",
            custom_meta={
                "canonical_key": self.source_key,
                "authority": "puct-order",
            },
        )
        second_current_target, _, _ = import_document(
            corpus=second_target_corpus,
            path="/documents/pgrr-145.txt",
            content=b"Second current revision request text.",
            user=second_owner,
            file_type="text/plain",
            title="Second Current PGRR 145",
            custom_meta={
                "canonical_key": self.target_key,
                "authority": "ercot-pgrr",
            },
        )

        first_graph = self._graph(self.owner, self.source_corpus.pk)
        second_graph = self._graph(second_owner, second_source_corpus.pk)
        first_source_gid = to_global_id("DocumentType", first_current_source.pk)
        first_target_gid = to_global_id("DocumentType", first_current_target.pk)
        second_source_gid = to_global_id("DocumentType", second_current_source.pk)
        second_target_gid = to_global_id("DocumentType", second_current_target.pk)

        assert {
            "source": first_source_gid,
            "target": first_target_gid,
            "edgeType": "IMPLEMENTS",
            "weight": 1,
        } in first_graph["edges"]
        assert {
            "source": second_source_gid,
            "target": second_target_gid,
            "edgeType": "IMPLEMENTS",
            "weight": 1,
        } in second_graph["edges"]

        first_node_ids = {node["id"] for node in first_graph["nodes"]}
        second_node_ids = {node["id"] for node in second_graph["nodes"]}
        assert second_source_gid not in first_node_ids
        assert second_target_gid not in first_node_ids
        assert first_source_gid not in second_node_ids
        assert first_target_gid not in second_node_ids
        historical_gids = {
            to_global_id("DocumentType", document.pk)
            for document in (
                self.source_document,
                self.target_document,
                second_source_document,
                second_target_document,
            )
        }
        assert historical_gids.isdisjoint(first_node_ids)
        assert historical_gids.isdisjoint(second_node_ids)
        assert to_global_id("CorpusType", second_target_corpus.pk) not in {
            corpus["id"] for corpus in first_graph["corpora"]
        }
        assert to_global_id("CorpusType", self.target_corpus.pk) not in {
            corpus["id"] for corpus in second_graph["corpora"]
        }

    def test_unverified_relationship_is_excluded(self):
        self._create_relationship(verified=False)

        graph = self._graph(self.owner, self.source_corpus.pk)

        assert graph["edges"] == []
        assert graph["nodes"] == []

    def test_invisible_target_degrades_without_title_or_corpus_leak(self):
        self._create_relationship(verified=True)
        self.source_corpus.is_public = True
        self.source_corpus.save(update_fields=["is_public"])
        self.source_document.is_public = True
        self.source_document.save(update_fields=["is_public"])
        reader = User.objects.create_user(
            username="authority-graph-reader", password="p"
        )

        graph = self._graph(reader, self.source_corpus.pk)
        source_gid = to_global_id("DocumentType", self.source_document.pk)
        target_gid = to_global_id("DocumentType", self.target_document.pk)
        target_corpus_gid = to_global_id("CorpusType", self.target_corpus.pk)
        ghost_id = f"key:{self.target_key}"

        assert {
            "source": source_gid,
            "target": ghost_id,
            "edgeType": "IMPLEMENTS",
            "weight": 1,
        } in graph["edges"]
        node_ids = {node["id"] for node in graph["nodes"]}
        assert ghost_id in node_ids
        assert target_gid not in node_ids
        ghost = next(node for node in graph["nodes"] if node["id"] == ghost_id)
        assert ghost["title"] == self.target_key
        assert "PGRR 145 Private Title" not in {
            node["title"] for node in graph["nodes"]
        }
        assert target_corpus_gid not in {corpus["id"] for corpus in graph["corpora"]}


class GovernanceGraphRegimeFieldTests(TestCase):
    """Phase 5: jurisdiction / authority_type / discovery_state on graph nodes.

    Verifies that:
    - A statute doc_node derives jurisdiction/authority_type from its authority prefix.
    - A ghost node for a key that has an AuthorityFrontier row carries that row's
      discovery_state (and jurisdiction/authority_type from the frontier when set).
    - A ghost node without a frontier row still returns jurisdiction/authority_type
      from classify_prefix and discovery_state=None.
    """

    def setUp(self):
        from opencontractserver.enrichment.services import EnrichmentService

        self.user = User.objects.create_user(username="regime-owner", password="p")
        self.corpus = Corpus.objects.create(title="Regime S-1", creator=self.user)
        primary = Document.objects.create(
            title="Acme S-1 regime test", creator=self.user
        )
        # Cites DGCL § 145 (registered prefix → jurisdiction us-de, statute) and
        # DGCL § 203 (will become a ghost since we only bootstrap § 145).
        primary.txt_extract_file.save(
            "s1r.txt",
            ContentFile(
                b"Governed by Section 145 of the Delaware General Corporation Law. "
                b"Also under Section 203 of the Delaware General Corporation Law."
            ),
        )
        self.corpus.add_document(document=primary, user=self.user)
        self.primary_id = self.corpus.document_paths.filter(
            is_current=True, document__title=primary.title
        ).values_list("document_id", flat=True)[0]

        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)

        from opencontractserver.enrichment.authorities import (
            AuthorityCorpusBootstrapper,
            AuthoritySection,
        )

        auth = AuthorityCorpusBootstrapper().bootstrap(
            creator_id=self.user.id,
            corpus_title="Delaware General Corporation Law (regime test)",
            sections=[
                AuthoritySection(
                    key="dgcl:145", heading="DGCL § 145", text="Indemnification."
                ),
            ],
        )
        self.auth_corpus_id = auth["corpus_id"]
        EnrichmentService().link_external_references(
            corpus_id=self.corpus.id, creator_id=self.user.id
        )
        self.statute_id = (
            Corpus.objects.get(pk=self.auth_corpus_id)
            .document_paths.filter(is_current=True)
            .values_list("document_id", flat=True)[0]
        )

    def _graph_with_regime(self):
        from config.graphql.schema import schema
        from config.graphql.testing import Client

        result = Client(schema, context_value=_Ctx(self.user)).execute(
            GRAPH_QUERY_WITH_REGIME,
            variables={"cid": to_global_id("CorpusType", self.corpus.id)},
        )
        assert result.get("errors") is None, result.get("errors")
        return result["data"]["governanceGraph"]["nodes"]

    def test_statute_doc_node_carries_jurisdiction_and_authority_type(self):
        """A statute document node (has canonical_key in custom_meta) derives
        jurisdiction/authority_type from its authority prefix via classify_prefix.
        """
        nodes = self._graph_with_regime()
        statute_gid = to_global_id("DocumentType", self.statute_id)
        statute = next((n for n in nodes if n["id"] == statute_gid), None)
        assert statute is not None, "statute node missing from graph"
        assert statute["kind"] == "statute"
        assert statute["authority"] == "dgcl"
        # dgcl is in PREFIX_CLASSIFICATION → ("us-de", "statute")
        assert statute["jurisdiction"] == "us-de"
        assert statute["authorityType"] == "statute"
        # doc nodes are always ingested — discoveryState is null
        assert statute["discoveryState"] is None

    def test_ghost_node_without_frontier_row_gets_classify_prefix_fallback(self):
        """A ghost key with no AuthorityFrontier row still resolves jurisdiction
        and authority_type from classify_prefix, and discovery_state is null.
        """
        from opencontractserver.annotations.models import AuthorityFrontier

        # Ensure there's no frontier row for dgcl:203
        AuthorityFrontier.objects.filter(canonical_key="dgcl:203").delete()

        nodes = self._graph_with_regime()
        ghost = next((n for n in nodes if n["id"] == "key:dgcl:203"), None)
        assert ghost is not None, "dgcl:203 ghost node missing"
        assert ghost["kind"] == "external"
        assert ghost["authority"] == "dgcl"
        assert ghost["jurisdiction"] == "us-de"
        assert ghost["authorityType"] == "statute"
        assert ghost["discoveryState"] is None

    def test_ghost_node_with_frontier_row_carries_discovery_state(self):
        """A ghost key that has an AuthorityFrontier row carries its discovery_state,
        jurisdiction, and authority_type from the row (not just classify_prefix).
        """
        from opencontractserver.annotations.models import AuthorityFrontier

        # Create a frontier row for the ghost key with explicit state.
        frontier_row, _ = AuthorityFrontier.objects.get_or_create(
            canonical_key="dgcl:203",
            defaults={
                "authority": "dgcl",
                "jurisdiction": "us-de",
                "authority_type": "statute",
                "mention_count": 1,
                "discovery_state": "queued",
            },
        )
        frontier_row.discovery_state = "pending_approval"
        frontier_row.save(update_fields=["discovery_state", "modified"])

        nodes = self._graph_with_regime()
        ghost = next((n for n in nodes if n["id"] == "key:dgcl:203"), None)
        assert ghost is not None, "dgcl:203 ghost node missing"
        assert ghost["discoveryState"] == "pending_approval"
        assert ghost["jurisdiction"] == "us-de"
        assert ghost["authorityType"] == "statute"
