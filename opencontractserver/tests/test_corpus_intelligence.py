"""Tests for the Corpus Intelligence GraphQL resolvers.

Covers the two resolvers that power the Corpus Intelligence home:

* ``corpusDocumentGraph`` — the document-relationship graph (nodes = documents,
  edges = DocumentRelationships), ranked by degree and capped via ``limit``.
* ``corpusIntelligenceAggregates`` — label distribution + summary coverage.

Both must respect the permission model (a user without corpus/document access
sees an empty graph and empty aggregates).
"""

import hashlib
import uuid

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase
from graphene.test import Client
from graphql_relay import from_global_id, to_global_id

from config.graphql.schema import schema
from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
    StructuralAnnotationSet,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentRelationship

User = get_user_model()


class TestContext:
    def __init__(self, user):
        self.user = user


class CorpusIntelligenceResolverTestCase(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="pw")
        self.stranger = User.objects.create_user(username="stranger", password="pw")

        self.owner_client = Client(schema, context_value=TestContext(self.owner))
        self.stranger_client = Client(schema, context_value=TestContext(self.stranger))

        # Private corpus owned by ``owner`` — stranger has no access.
        self.corpus = Corpus.objects.create(
            title="Intelligence Corpus", creator=self.owner, is_public=False
        )
        self.corpus_gid = to_global_id("CorpusType", self.corpus.id)

        # Three documents added via the corpus helper (handles DocumentPath).
        self.docs = []
        for i in range(3):
            doc = Document.objects.create(title=f"Doc {i}", creator=self.owner)
            doc, _, _ = self.corpus.add_document(document=doc, user=self.owner)
            self.docs.append(doc)

        # A markdown summary on exactly one document → 1/3 coverage.
        self.docs[0].md_summary_file.save(
            "summary.md", ContentFile(b"# Summary"), save=True
        )

        # Annotation label + annotations for the label-distribution panel.
        self.token_label = AnnotationLabel.objects.create(
            text="Risk Factor",
            label_type="TOKEN_LABEL",
            color="#ff0000",
            creator=self.owner,
        )
        for doc in self.docs:
            Annotation.objects.create(
                document=doc,
                corpus=self.corpus,
                annotation_label=self.token_label,
                raw_text="risk",
                creator=self.owner,
            )

        # Relationship label + two doc→doc edges:
        #   doc0 --RELATIONSHIP--> doc1
        #   doc1 --NOTES--------->  doc2
        # => degrees: doc1=2, doc0=1, doc2=1
        self.rel_label = AnnotationLabel.objects.create(
            text="Cites", label_type="DOC_RELATIONSHIP_LABEL", creator=self.owner
        )
        DocumentRelationship.objects.create(
            source_document=self.docs[0],
            target_document=self.docs[1],
            relationship_type="RELATIONSHIP",
            annotation_label=self.rel_label,
            corpus=self.corpus,
            creator=self.owner,
        )
        DocumentRelationship.objects.create(
            source_document=self.docs[1],
            target_document=self.docs[2],
            relationship_type="NOTES",
            corpus=self.corpus,
            creator=self.owner,
        )

    # ----------------------------- graph -----------------------------

    GRAPH_QUERY = """
        query ($corpusId: ID!, $limit: Int) {
            corpusDocumentGraph(corpusId: $corpusId, limit: $limit) {
                nodes { id title degree }
                edges { id source target label relationshipType }
                totalNodeCount
                totalEdgeCount
                truncated
            }
        }
    """

    def test_graph_returns_nodes_edges_and_degrees(self):
        result = self.owner_client.execute(
            self.GRAPH_QUERY, variables={"corpusId": self.corpus_gid}
        )
        self.assertIsNone(result.get("errors"), result.get("errors"))
        graph = result["data"]["corpusDocumentGraph"]

        self.assertEqual(graph["totalNodeCount"], 3)
        self.assertEqual(graph["totalEdgeCount"], 2)
        self.assertFalse(graph["truncated"])
        self.assertEqual(len(graph["nodes"]), 3)
        self.assertEqual(len(graph["edges"]), 2)

        # Degree map keyed by django pk (decoded from the global id).
        degree_by_pk = {
            int(from_global_id(n["id"])[1]): n["degree"] for n in graph["nodes"]
        }
        self.assertEqual(degree_by_pk[self.docs[1].id], 2)
        self.assertEqual(degree_by_pk[self.docs[0].id], 1)
        self.assertEqual(degree_by_pk[self.docs[2].id], 1)

        # Edge endpoints are navigable global ids; the RELATIONSHIP edge carries
        # its label, the NOTES edge does not.
        rel_edge = next(
            e for e in graph["edges"] if e["relationshipType"] == "RELATIONSHIP"
        )
        self.assertEqual(rel_edge["label"], "Cites")
        self.assertEqual(int(from_global_id(rel_edge["source"])[1]), self.docs[0].id)
        self.assertEqual(int(from_global_id(rel_edge["target"])[1]), self.docs[1].id)

    def test_graph_limit_truncates_to_highest_degree(self):
        result = self.owner_client.execute(
            self.GRAPH_QUERY, variables={"corpusId": self.corpus_gid, "limit": 2}
        )
        self.assertIsNone(result.get("errors"), result.get("errors"))
        graph = result["data"]["corpusDocumentGraph"]

        # Total counts reflect the full graph; rendered nodes are capped.
        self.assertEqual(graph["totalNodeCount"], 3)
        self.assertTrue(graph["truncated"])
        self.assertLessEqual(len(graph["nodes"]), 2)
        # The highest-degree document (doc1) must survive the cap.
        kept_pks = {int(from_global_id(n["id"])[1]) for n in graph["nodes"]}
        self.assertIn(self.docs[1].id, kept_pks)

    def test_graph_nodes_ordered_by_degree(self):
        """Nodes arrive degree-ranked (the documented API contract).

        The highest-degree document must come first; ties may arrive in any
        order, so only the descending-degree invariant is asserted.
        """
        result = self.owner_client.execute(
            self.GRAPH_QUERY, variables={"corpusId": self.corpus_gid}
        )
        self.assertIsNone(result.get("errors"), result.get("errors"))
        degrees = [n["degree"] for n in result["data"]["corpusDocumentGraph"]["nodes"]]
        self.assertEqual(degrees, sorted(degrees, reverse=True))
        self.assertEqual(degrees[0], 2)  # doc1 leads

    def test_graph_hidden_from_unauthorized_user(self):
        result = self.stranger_client.execute(
            self.GRAPH_QUERY, variables={"corpusId": self.corpus_gid}
        )
        self.assertIsNone(result.get("errors"), result.get("errors"))
        graph = result["data"]["corpusDocumentGraph"]
        self.assertEqual(graph["nodes"], [])
        self.assertEqual(graph["edges"], [])
        self.assertEqual(graph["totalNodeCount"], 0)
        self.assertEqual(graph["totalEdgeCount"], 0)

    def test_graph_returns_empty_for_malformed_corpus_id(self):
        # A non-numeric/garbage global id must decode to an empty graph rather
        # than raising (the resolver guards on ``isdigit()``).
        result = self.owner_client.execute(
            self.GRAPH_QUERY, variables={"corpusId": "not-a-valid-id"}
        )
        self.assertIsNone(result.get("errors"), result.get("errors"))
        graph = result["data"]["corpusDocumentGraph"]
        self.assertEqual(graph["nodes"], [])
        self.assertEqual(graph["edges"], [])
        self.assertEqual(graph["totalNodeCount"], 0)
        self.assertEqual(graph["totalEdgeCount"], 0)
        self.assertFalse(graph["truncated"])

    # --------------------------- aggregates --------------------------

    AGG_QUERY = """
        query ($corpusId: ID!) {
            corpusIntelligenceAggregates(corpusId: $corpusId) {
                labelDistribution { label color count }
                documentsWithSummary
                totalDocuments
            }
        }
    """

    def test_aggregates_label_distribution_and_coverage(self):
        result = self.owner_client.execute(
            self.AGG_QUERY, variables={"corpusId": self.corpus_gid}
        )
        self.assertIsNone(result.get("errors"), result.get("errors"))
        agg = result["data"]["corpusIntelligenceAggregates"]

        self.assertEqual(agg["totalDocuments"], 3)
        self.assertEqual(agg["documentsWithSummary"], 1)

        labels = {row["label"]: row for row in agg["labelDistribution"]}
        self.assertIn("Risk Factor", labels)
        self.assertEqual(labels["Risk Factor"]["count"], 3)
        self.assertEqual(labels["Risk Factor"]["color"], "#ff0000")

    def test_aggregates_hidden_from_unauthorized_user(self):
        result = self.stranger_client.execute(
            self.AGG_QUERY, variables={"corpusId": self.corpus_gid}
        )
        self.assertIsNone(result.get("errors"), result.get("errors"))
        agg = result["data"]["corpusIntelligenceAggregates"]
        self.assertEqual(agg["labelDistribution"], [])
        self.assertEqual(agg["documentsWithSummary"], 0)
        self.assertEqual(agg["totalDocuments"], 0)

    def test_aggregates_returns_empty_for_malformed_corpus_id(self):
        result = self.owner_client.execute(
            self.AGG_QUERY, variables={"corpusId": "not-a-valid-id"}
        )
        self.assertIsNone(result.get("errors"), result.get("errors"))
        agg = result["data"]["corpusIntelligenceAggregates"]
        self.assertEqual(agg["labelDistribution"], [])
        self.assertEqual(agg["documentsWithSummary"], 0)
        self.assertEqual(agg["totalDocuments"], 0)

    def test_aggregates_structural_label_counted_once_across_shared_docs(self):
        """A structural annotation shared by N visible docs counts once.

        The label-distribution query OR-joins structural annotations via
        ``structural_set__documents`` (an annotation has no ``document`` of its
        own). That reverse-FK join fans the annotation out to one row per
        referencing document, so the count MUST use ``distinct=True`` — without
        it a structural label would be inflated by the number of docs sharing
        the set. Here two corpus docs share one structural set holding a single
        structural annotation, so the expected count is 1, not 2.
        """
        struct_set = StructuralAnnotationSet.objects.create(
            content_hash=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
            parser_name="TestParser",
            creator=self.owner,
        )
        for i in range(2):
            shared = Document.objects.create(
                title=f"Shared structural doc {i}",
                creator=self.owner,
                structural_annotation_set=struct_set,
            )
            self.corpus.add_document(document=shared, user=self.owner)

        structural_label = AnnotationLabel.objects.create(
            text="Section Header",
            label_type="TOKEN_LABEL",
            color="#00ff00",
            creator=self.owner,
        )
        Annotation.objects.create(
            corpus=self.corpus,
            structural_set=struct_set,
            structural=True,
            annotation_label=structural_label,
            raw_text="header",
            creator=self.owner,
        )

        result = self.owner_client.execute(
            self.AGG_QUERY, variables={"corpusId": self.corpus_gid}
        )
        self.assertIsNone(result.get("errors"), result.get("errors"))
        agg = result["data"]["corpusIntelligenceAggregates"]
        labels = {row["label"]: row["count"] for row in agg["labelDistribution"]}
        self.assertIn("Section Header", labels)
        self.assertEqual(labels["Section Header"], 1)

    def test_aggregates_excludes_oc_reserved_labels(self):
        """OC_-prefixed platform labels are scaffolding, not user insight.

        Labels in the reserved OC_ namespace (OC_SECTION, OC_URL, …) are
        emitted by the pipeline to drive built-in features; surfacing them in
        the user-facing "dominant labels" insight reads as jargon. They must be
        excluded, while ordinary (and even non-OC structural) labels remain.
        """
        oc_label = AnnotationLabel.objects.create(
            text="OC_SECTION", label_type="TOKEN_LABEL", creator=self.owner
        )
        for doc in self.docs:
            Annotation.objects.create(
                document=doc,
                corpus=self.corpus,
                annotation_label=oc_label,
                raw_text="section",
                creator=self.owner,
            )

        result = self.owner_client.execute(
            self.AGG_QUERY, variables={"corpusId": self.corpus_gid}
        )
        self.assertIsNone(result.get("errors"), result.get("errors"))
        agg = result["data"]["corpusIntelligenceAggregates"]
        labels = {row["label"] for row in agg["labelDistribution"]}
        self.assertNotIn("OC_SECTION", labels)
        # The ordinary label created in setUp is unaffected.
        self.assertIn("Risk Factor", labels)
