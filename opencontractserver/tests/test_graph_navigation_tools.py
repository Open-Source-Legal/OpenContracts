"""Tests for the read-only graph-navigation agent tools.

These tools (``opencontractserver/llms/tools/core_tools/graph_navigation.py``)
let an agent *walk* the materialised reference graph one hop at a time. The
fixture mirrors ``test_governance_graph.py``: an S-1 filing that cites DGCL
§145 twice (resolved to a bootstrapped authority document), §203 once (an
EXTERNAL ghost), and an exhibit — so every traversal direction has something
real to return.

The load-bearing assertions are the permission ones: a stranger sees nothing,
and a *private* target inside a *public* corpus must not leak through the
reference edge.
"""

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase

from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.enrichment.authorities import (
    AuthorityCorpusBootstrapper,
    AuthoritySection,
)
from opencontractserver.enrichment.services import EnrichmentService
from opencontractserver.llms.tools.core_tools.graph_navigation import (
    find_documents_citing,
    get_document_references,
    get_reference_neighborhood,
    read_reference_target,
)

User = get_user_model()

S1_TEXT = (
    "Indemnification is provided under Section 145 of the Delaware General "
    "Corporation Law. As permitted by Section 145 of the Delaware General "
    "Corporation Law, our charter limits liability. We are also governed by "
    "Section 203 of the Delaware General Corporation Law. The form of "
    "underwriting agreement is filed as Exhibit 1.1 hereto."
)


class GraphNavigationToolTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="p")
        self.corpus = Corpus.objects.create(title="S-1 Corpus", creator=self.user)
        self.primary = Document.objects.create(
            title="Acme Inc. S-1 (2026-01-01)", creator=self.user
        )
        self.primary.txt_extract_file.save("s1.txt", ContentFile(S1_TEXT.encode()))
        self.exhibit = Document.objects.create(
            title="Acme Inc. S-1 (2026-01-01) - Exhibit 1.1: EX-1.1",
            creator=self.user,
        )
        self.exhibit.txt_extract_file.save("ex.txt", ContentFile(b"Underwriting."))
        self.corpus.add_document(document=self.primary, user=self.user)
        self.corpus.add_document(document=self.exhibit, user=self.user)
        # add_document forks corpus-local copies — resolve to the in-corpus ids.
        self.primary_id, self.exhibit_id = (
            self.corpus.document_paths.filter(
                is_current=True, document__title=t
            ).values_list("document_id", flat=True)[0]
            for t in (self.primary.title, self.exhibit.title)
        )

        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)
        auth = AuthorityCorpusBootstrapper().bootstrap(
            creator_id=self.user.id,
            corpus_title="Delaware General Corporation Law",
            sections=[
                AuthoritySection(
                    key="dgcl:145",
                    heading="DGCL § 145",
                    text="Indemnification of directors and officers.",
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

    # ---- get_document_references --------------------------------------- #
    def test_outbound_includes_resolved_and_external(self):
        res = get_document_references(
            corpus_id=self.corpus.id,
            user_id=self.user.id,
            document_id=self.primary_id,
        )
        by_key = {r["canonical_key"]: r for r in res["outbound"] if r["canonical_key"]}
        # § 145 resolved to the authority document.
        self.assertIn("dgcl:145", by_key)
        self.assertEqual(by_key["dgcl:145"]["resolution_status"], "RESOLVED")
        self.assertEqual(by_key["dgcl:145"]["target_document_id"], self.statute_id)
        self.assertTrue(by_key["dgcl:145"]["citing_text"])
        # § 203 stays EXTERNAL (no authority ingested).
        self.assertIn("dgcl:203", by_key)
        self.assertEqual(by_key["dgcl:203"]["resolution_status"], "EXTERNAL")
        self.assertIsNone(by_key["dgcl:203"]["target_document_id"])

    def test_inbound_on_statute_lists_the_citing_filing(self):
        res = get_document_references(
            corpus_id=self.corpus.id,
            user_id=self.user.id,
            document_id=self.statute_id,
            direction="inbound",
        )
        self.assertEqual(res["outbound"], [])
        citing_docs = {r["citing_document_id"] for r in res["inbound"]}
        self.assertIn(self.primary_id, citing_docs)

    def test_direction_filter_outbound_only(self):
        res = get_document_references(
            corpus_id=self.corpus.id,
            user_id=self.user.id,
            document_id=self.primary_id,
            direction="outbound",
        )
        self.assertEqual(res["inbound"], [])
        self.assertGreater(res["outbound_count"], 0)

    def test_missing_document_id_returns_error(self):
        res = get_document_references(corpus_id=self.corpus.id, user_id=self.user.id)
        self.assertIn("error", res)

    # ---- read_reference_target ---------------------------------------- #
    def test_read_reference_target_by_key(self):
        res = read_reference_target(
            corpus_id=self.corpus.id,
            user_id=self.user.id,
            canonical_key="dgcl:145",
        )
        self.assertTrue(res["resolved"])
        self.assertEqual(res["document_id"], self.statute_id)
        self.assertIn("Indemnification", res["text"])
        self.assertEqual(res["canonical_key"], "dgcl:145")

    def test_read_reference_target_unresolved_ghost(self):
        res = read_reference_target(
            corpus_id=self.corpus.id,
            user_id=self.user.id,
            canonical_key="dgcl:203",
        )
        self.assertFalse(res["resolved"])

    def test_read_reference_target_invisible_document_not_read(self):
        """A stranger cannot open a private document via target_document_id."""
        stranger = User.objects.create_user(username="peeker", password="p")
        res = read_reference_target(
            corpus_id=self.corpus.id,
            user_id=stranger.id,
            target_document_id=self.statute_id,
        )
        self.assertFalse(res["resolved"])

    def test_read_reference_target_paging(self):
        res = read_reference_target(
            corpus_id=self.corpus.id,
            user_id=self.user.id,
            target_document_id=self.statute_id,
            char_offset=0,
            max_chars=5,
        )
        self.assertTrue(res["resolved"])
        self.assertEqual(res["returned_chars"], 5)
        self.assertTrue(res["has_more"])

    # ---- find_documents_citing ---------------------------------------- #
    def test_find_documents_citing_by_key(self):
        res = find_documents_citing(
            corpus_id=self.corpus.id,
            user_id=self.user.id,
            canonical_key="dgcl:145",
        )
        docs = {d["document_id"]: d for d in res["citing_documents"]}
        self.assertIn(self.primary_id, docs)
        self.assertEqual(docs[self.primary_id]["mention_count"], 2)

    def test_find_documents_citing_by_document_id(self):
        # Anchor on the statute document itself: the filing cites it.
        res = find_documents_citing(
            corpus_id=self.corpus.id,
            user_id=self.user.id,
            document_id=self.statute_id,
        )
        docs = {d["document_id"] for d in res["citing_documents"]}
        self.assertIn(self.primary_id, docs)

    def test_find_documents_citing_requires_anchor(self):
        res = find_documents_citing(corpus_id=self.corpus.id, user_id=self.user.id)
        self.assertIn("error", res)

    # ---- get_reference_neighborhood ----------------------------------- #
    def test_neighborhood_whole_corpus(self):
        res = get_reference_neighborhood(corpus_id=self.corpus.id, user_id=self.user.id)
        doc_ids = {n["doc_pk"] for n in res["doc_nodes"]}
        self.assertIn(self.primary_id, doc_ids)
        self.assertIn(self.statute_id, doc_ids)
        ghost_keys = {n["key"] for n in res["ghost_nodes"]}
        self.assertIn("dgcl:203", ghost_keys)

    def test_neighborhood_focus_on_document(self):
        res = get_reference_neighborhood(
            corpus_id=self.corpus.id,
            user_id=self.user.id,
            focus_document_id=self.primary_id,
            depth=1,
        )
        self.assertTrue(res["focus_in_graph"])
        doc_ids = {n["doc_pk"] for n in res["doc_nodes"]}
        # 1 hop from the filing reaches the resolved statute + the exhibit.
        self.assertIn(self.statute_id, doc_ids)

    # ---- permissions (load-bearing) ----------------------------------- #
    def test_stranger_sees_no_references(self):
        stranger = User.objects.create_user(username="stranger", password="p")
        res = get_document_references(
            corpus_id=self.corpus.id,
            user_id=stranger.id,
            document_id=self.primary_id,
        )
        self.assertEqual(res["outbound_count"], 0)
        self.assertEqual(res["inbound_count"], 0)

    def test_private_target_not_leaked_through_public_corpus(self):
        """A public filing corpus must not leak a PRIVATE authority target."""
        # Publish the filing corpus + its in-corpus documents, but keep the
        # authority corpus + statute document private (the bootstrap default).
        Corpus.objects.filter(pk=self.corpus.id).update(is_public=True)
        Document.objects.filter(pk__in=[self.primary_id, self.exhibit_id]).update(
            is_public=True
        )

        stranger = User.objects.create_user(username="reader", password="p")
        res = get_document_references(
            corpus_id=self.corpus.id,
            user_id=stranger.id,
            document_id=self.primary_id,
        )
        keys = {r["canonical_key"] for r in res["outbound"]}
        # The § 203 ghost (no target) is fine to surface…
        self.assertIn("dgcl:203", keys)
        # …but § 145's target is the private statute, so the whole edge is hidden.
        self.assertNotIn("dgcl:145", keys)

        # And the stranger cannot open the private authority text directly.
        read = read_reference_target(
            corpus_id=self.corpus.id,
            user_id=stranger.id,
            canonical_key="dgcl:145",
        )
        self.assertFalse(read["resolved"])
