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

from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase

from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.enrichment import constants as C
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

    def test_unresolvable_document_id_returns_error(self):
        """A document_id that doesn't resolve must error, not silently succeed.

        Regression: an agent confused a corpus_id for a document_id and got a
        well-formed empty (outbound_count=0, inbound_count=0) envelope back,
        then confidently told the user "no such citation exists" — when the
        pk simply didn't identify a real/visible document at all. A wrong-but-
        colliding pk (e.g. some unrelated document with no references) must
        surface the same error, not a false-empty success.
        """
        res = get_document_references(
            corpus_id=self.corpus.id,
            user_id=self.user.id,
            document_id=999999999,
        )
        self.assertIn("error", res)
        self.assertEqual(res["outbound"], [])
        self.assertEqual(res["inbound"], [])

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

    def test_find_documents_citing_by_subsection_key_falls_back_to_root(self):
        """A subsection key not present verbatim still finds root-key citers.

        The fixture's CorpusReference rows only carry "dgcl:145" (no
        subsection). Anchoring on "dgcl:145(a)" must still surface the primary
        filing — proving find_documents_citing now routes through
        candidate_keys()'s subsection-root fallback instead of doing a bare
        exact-match filter.
        """
        res = find_documents_citing(
            corpus_id=self.corpus.id,
            user_id=self.user.id,
            canonical_key="dgcl:145(a)",
        )
        docs = {d["document_id"] for d in res["citing_documents"]}
        self.assertIn(self.primary_id, docs)

    def test_find_documents_citing_requires_anchor(self):
        res = find_documents_citing(corpus_id=self.corpus.id, user_id=self.user.id)
        self.assertIn("error", res)

    def test_find_documents_citing_unresolvable_document_id_errors(self):
        """A document_id anchor that doesn't resolve must error, not false-empty.

        Mirrors get_document_references: an agent passing a corpus_id (or any
        bad/invisible pk) where a document_id belongs must be told the id is
        unknown, not handed a well-formed 'nobody cites this' result.
        """
        res = find_documents_citing(
            corpus_id=self.corpus.id,
            user_id=self.user.id,
            document_id=999999999,
        )
        self.assertIn("error", res)
        self.assertEqual(res["citing_documents"], [])
        self.assertEqual(res["citing_document_count"], 0)

    def test_find_documents_citing_corpus_id_survives_sample_truncation(self):
        """corpus_id comes from the ranked aggregate, not the capped sample scan.

        Regression: corpus_id was populated in the bounded citing-clause sample
        scan (capped at NAV_CITING_SAMPLE_SCAN, ordered by document_id), so a
        top-ranked document whose id sorted past the budget got a null
        corpus_id. With the scan budget forced to 0 the snippets are empty but
        corpus_id (a DB aggregate on the ranked query) must still be populated.
        """
        with mock.patch.object(C, "NAV_CITING_SAMPLE_SCAN", 0):
            res = find_documents_citing(
                corpus_id=self.corpus.id,
                user_id=self.user.id,
                canonical_key="dgcl:145",
            )
        doc = next(
            d for d in res["citing_documents"] if d["document_id"] == self.primary_id
        )
        self.assertIsNotNone(doc["corpus_id"])
        self.assertEqual(doc["sample_citations"], [])

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

    def test_neighborhood_focus_low_degree_survives_truncation(self):
        """A low-degree focus must be found even when node_cap < corpus nodes.

        Regression: GovernanceGraphService.build() truncates its output to the
        top node_cap nodes by GLOBAL degree. With node_cap=2, a whole-corpus
        build would drop the exhibit (lowest degree) before any focus/BFS
        restriction — so focusing on it must build the full graph first.
        """
        res = get_reference_neighborhood(
            corpus_id=self.corpus.id,
            user_id=self.user.id,
            focus_document_id=self.exhibit_id,
            depth=1,
            node_cap=2,
        )
        self.assertTrue(res["focus_in_graph"])
        doc_ids = {n["doc_pk"] for n in res["doc_nodes"]}
        self.assertIn(self.exhibit_id, doc_ids)

    def test_neighborhood_focus_survives_cap_eviction(self):
        """The cap must never evict the focus doc for a higher-degree neighbour.

        focus=exhibit (low global degree) is adjacent to primary (higher degree)
        via the DOCUMENT edge. The restricted neighbourhood {exhibit, primary}
        exceeds node_cap=1, so the degree ranking alone would keep primary and
        drop the exhibit — the tool must force-keep the focus, respect node_cap,
        and report focus_in_graph against the FINAL node set.
        """
        res = get_reference_neighborhood(
            corpus_id=self.corpus.id,
            user_id=self.user.id,
            focus_document_id=self.exhibit_id,
            depth=1,
            node_cap=1,
        )
        doc_ids = {n["doc_pk"] for n in res["doc_nodes"]}
        self.assertIn(self.exhibit_id, doc_ids)
        self.assertTrue(res["focus_in_graph"])
        # node_cap honoured: exactly one node total, and it is the focus.
        self.assertEqual(len(res["doc_nodes"]) + len(res["ghost_nodes"]), 1)

    def test_neighborhood_focus_with_no_references_is_honest(self):
        """A focus document with no references yields focus_in_graph=False."""
        loner = Document.objects.create(title="Unconnected Memo", creator=self.user)
        loner.txt_extract_file.save("m.txt", ContentFile(b"No citations here."))
        self.corpus.add_document(document=loner, user=self.user)
        loner_id = self.corpus.document_paths.filter(
            is_current=True, document__title=loner.title
        ).values_list("document_id", flat=True)[0]
        res = get_reference_neighborhood(
            corpus_id=self.corpus.id,
            user_id=self.user.id,
            focus_document_id=loner_id,
        )
        self.assertFalse(res["focus_in_graph"])

    # ---- input validation branches ------------------------------------ #
    def test_read_reference_target_requires_an_anchor(self):
        res = read_reference_target(corpus_id=self.corpus.id, user_id=self.user.id)
        self.assertFalse(res["resolved"])
        self.assertIn("error", res)

    def test_get_document_references_invalid_direction_defaults_to_both(self):
        res = get_document_references(
            corpus_id=self.corpus.id,
            user_id=self.user.id,
            document_id=self.primary_id,
            direction="sideways",
        )
        self.assertEqual(res["direction"], "both")
        self.assertGreater(res["outbound_count"], 0)

    def test_missing_document_id_error_envelope_matches_happy_path(self):
        res = get_document_references(corpus_id=self.corpus.id, user_id=self.user.id)
        # Error envelope carries the same context keys the happy path returns.
        for key in ("corpus_id", "direction", "outbound", "inbound"):
            self.assertIn(key, res)

    def test_error_envelope_reports_normalized_direction(self):
        # A bad direction on an error path reports the normalized "both", not
        # the raw LLM-supplied value — matching the happy-path envelope.
        res = get_document_references(
            corpus_id=self.corpus.id,
            user_id=self.user.id,
            document_id=999999999,
            direction="sideways",
        )
        self.assertIn("error", res)
        self.assertEqual(res["direction"], "both")

    # ---- abuse-resistance clamps -------------------------------------- #
    def test_reference_limit_is_clamped(self):
        # A huge limit is clamped to NAV_MAX_REFERENCES, not passed through raw.
        res = get_document_references(
            corpus_id=self.corpus.id,
            user_id=self.user.id,
            document_id=self.primary_id,
            limit=100000,
        )
        self.assertLessEqual(res["outbound_count"], C.NAV_MAX_REFERENCES)

    def test_neighborhood_depth_is_clamped(self):
        res = get_reference_neighborhood(
            corpus_id=self.corpus.id,
            user_id=self.user.id,
            focus_document_id=self.primary_id,
            depth=99,
        )
        self.assertEqual(res["depth"], C.NAV_NEIGHBORHOOD_MAX_DEPTH)

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
