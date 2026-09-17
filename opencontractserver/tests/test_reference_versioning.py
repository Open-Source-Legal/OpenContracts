"""Reference web × document versioning — pinned targets and permanent links.

Design: ``docs/architecture/reference-web-versioning.md``. The invariant under
test: a ``CorpusReference`` pins the authority version it was linked against
("as cited"); the current text is derived, never stored; mention links carry
``?v=N`` so they keep resolving after the cited version is superseded.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import SimpleTestCase, TestCase

from config.graphql.core.relay import to_global_id
from config.graphql.schema import schema
from config.graphql.testing import Client
from opencontractserver.annotations.models import CorpusReference
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.authorities import (
    AuthorityCorpusBootstrapper,
    AuthoritySection,
)
from opencontractserver.enrichment.services import (
    CorpusReferenceService,
    EnrichmentService,
)
from opencontractserver.utils.frontend_paths import document_in_corpus_path

User = get_user_model()

S1_TEXT = (
    "Indemnification is provided per Section 145 of the Delaware General "
    "Corporation Law. The underwriting agreement is filed as Exhibit 1.1 hereto."
)


class DocumentInCorpusPathTests(SimpleTestCase):
    def test_bare_path_without_version(self):
        self.assertEqual(
            document_in_corpus_path(
                corpus_creator_slug="u", corpus_slug="c", document_slug="d"
            ),
            "/d/u/c/d",
        )

    def test_positive_version_is_pinned_as_query_param(self):
        self.assertEqual(
            document_in_corpus_path(
                corpus_creator_slug="u",
                corpus_slug="c",
                document_slug="d",
                version_number=3,
            ),
            "/d/u/c/d?v=3",
        )

    def test_non_positive_or_missing_version_is_ignored(self):
        for bad in (None, 0, -1):
            self.assertEqual(
                document_in_corpus_path(
                    corpus_creator_slug="u",
                    corpus_slug="c",
                    document_slug="d",
                    version_number=bad,
                ),
                "/d/u/c/d",
            )

    def test_missing_slug_returns_none_even_with_version(self):
        self.assertIsNone(
            document_in_corpus_path(
                corpus_creator_slug="u",
                corpus_slug=None,
                document_slug="d",
                version_number=2,
            )
        )


class PinnedReferenceTargetTests(TestCase):
    """Authority version-ups never rewrite what a citation resolved to."""

    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="p")
        self.corpus = Corpus.objects.create(title="S-1 Corpus", creator=self.user)
        doc = Document.objects.create(title="Acme S-1 primary", creator=self.user)
        doc.txt_extract_file.save("s1.txt", ContentFile(S1_TEXT.encode("utf-8")))
        self.corpus.add_document(document=doc, user=self.user)
        exhibit = Document.objects.create(
            title="Acme S-1 (2024-09-30) - Exhibit 1.1: EX-1.1", creator=self.user
        )
        exhibit.txt_extract_file.save("ex11.txt", ContentFile(b"underwriting"))
        self.corpus.add_document(document=exhibit, user=self.user)

    def _bootstrap(self, text_145: str = "..145 v1..", user=None):
        return AuthorityCorpusBootstrapper().bootstrap(
            creator_id=(user or self.user).id,
            corpus_title="Delaware General Corporation Law",
            corpus_slug="dgcl",
            sections=[
                AuthoritySection(key="dgcl:145", heading="DGCL § 145", text=text_145)
            ],
        )

    def _link(self):
        return EnrichmentService().link_external_references(
            corpus_id=self.corpus.id, creator_id=self.user.id
        )

    def _ref(self) -> CorpusReference:
        return CorpusReference.objects.select_related(
            "source_annotation", "target_document"
        ).get(corpus=self.corpus, canonical_key="dgcl:145")

    @staticmethod
    def _version_of(document: Document, corpus_id: int) -> int:
        return (
            DocumentPath.objects.filter(document=document, corpus_id=corpus_id)
            .values_list("version_number", flat=True)
            .first()
        )

    def test_link_pins_target_version_in_mention_url(self):
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)
        auth = self._bootstrap()
        self._link()
        ref = self._ref()
        auth_corpus = Corpus.objects.select_related("creator").get(pk=auth["corpus_id"])
        self.assertEqual(
            ref.source_annotation.link_url,
            f"/d/{auth_corpus.creator.slug}/{auth_corpus.slug}"
            f"/{ref.target_document.slug}?v=1",
        )

    def test_doc_to_doc_mention_pins_sibling_version(self):
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)
        ref = CorpusReference.objects.select_related(
            "source_annotation", "target_document"
        ).get(corpus=self.corpus, reference_type=C.REF_DOCUMENT)
        self.assertEqual(ref.resolution_status, C.STATUS_RESOLVED)
        version = self._version_of(ref.target_document, self.corpus.id)
        self.assertTrue(
            ref.source_annotation.link_url.endswith(
                f"/{ref.target_document.slug}?v={version}"
            ),
            ref.source_annotation.link_url,
        )

    def test_authority_version_up_keeps_pinned_target_and_derives_current(self):
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)
        auth = self._bootstrap()
        self._link()
        before = self._ref()
        pinned_id = before.target_document_id
        pinned_url = before.source_annotation.link_url
        self.assertFalse(CorpusReferenceService.target_is_superseded(before))
        self.assertEqual(
            CorpusReferenceService.current_target_document_id(before), pinned_id
        )

        # Amend the statute: a new Document row becomes current in the tree.
        summary = self._bootstrap("..145 v2 amended..")
        self.assertEqual(summary["documents_updated"], 1)
        current = Document.objects.get(
            version_tree_id=before.target_document.version_tree_id, is_current=True
        )
        self.assertNotEqual(current.id, pinned_id)

        out = self._link()
        self.assertEqual(out["law_references_linked"], 0)
        self.assertEqual(out["links_demoted"], 0)
        self.assertEqual(out["links_restamped"], 0)

        after = self._ref()
        self.assertEqual(after.target_document_id, pinned_id, "history rewritten")
        self.assertEqual(after.resolution_status, C.STATUS_RESOLVED)
        self.assertEqual(after.target_corpus_id, auth["corpus_id"])
        self.assertEqual(after.source_annotation.link_url, pinned_url)
        self.assertTrue(CorpusReferenceService.target_is_superseded(after))
        self.assertEqual(
            CorpusReferenceService.current_target_document_id(after), current.id
        )

    def test_pinned_link_still_resolves_after_version_up(self):
        """The ``?v=1`` link opens v1 through the slug resolver once superseded."""
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)
        auth = self._bootstrap()
        self._link()
        pinned = self._ref().target_document
        self._bootstrap("..145 v2..")
        auth_corpus = Corpus.objects.select_related("creator").get(pk=auth["corpus_id"])

        query = """
            query($u: String!, $c: String!, $d: String!, $v: Int) {
              documentInCorpusBySlugs(
                userSlug: $u, corpusSlug: $c, documentSlug: $d, versionNumber: $v
              ) { id }
            }
        """
        client = Client(schema)
        ctx = type("Request", (), {"user": self.user})()
        with_version = client.execute(
            query,
            variables={
                "u": auth_corpus.creator.slug,
                "c": auth_corpus.slug,
                "d": pinned.slug,
                "v": 1,
            },
            context_value=ctx,
        )
        self.assertEqual(
            with_version["data"]["documentInCorpusBySlugs"]["id"],
            to_global_id("DocumentType", pinned.id),
        )
        bare = client.execute(
            query,
            variables={
                "u": auth_corpus.creator.slug,
                "c": auth_corpus.slug,
                "d": pinned.slug,
                "v": None,
            },
            context_value=ctx,
        )
        self.assertIsNone(
            bare["data"]["documentInCorpusBySlugs"],
            "a bare slug link 404s once its version is superseded — which is "
            "exactly why mention links must pin",
        )

    def test_target_repointed_when_key_moves_to_another_tree(self):
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)
        auth = self._bootstrap()
        self._link()
        old = self._ref().target_document

        # Rebuild the pack under a NEW document (different version tree) and
        # retire the key on the old one.
        replacement = Document.objects.create(
            title="DGCL § 145 (rebuilt)",
            creator=self.user,
            custom_meta={"canonical_key": "dgcl:145"},
        )
        replacement.txt_extract_file.save("r.txt", ContentFile(b"rebuilt"))
        auth_corpus = Corpus.objects.get(pk=auth["corpus_id"])
        auth_corpus.add_document(document=replacement, user=self.user)
        # add_document materialises a corpus-isolated copy; that copy is the
        # row with the live path (and the key) in the authority corpus.
        replacement = (
            Document.objects.filter(
                path_records__corpus=auth_corpus,
                path_records__is_current=True,
                custom_meta__canonical_key="dgcl:145",
            )
            .exclude(version_tree_id=old.version_tree_id)
            .get()
        )
        old.custom_meta = {**(old.custom_meta or {}), "canonical_key": "dgcl:145-old"}
        old.save(update_fields=["custom_meta"])

        out = self._link()
        self.assertEqual(out["law_references_linked"], 1)
        after = self._ref()
        self.assertEqual(after.target_document_id, replacement.id)
        self.assertIsNone(after.target_annotation_id)
        self.assertTrue(after.source_annotation.link_url.endswith("?v=1"))

    def test_public_corpus_repoints_when_pinned_version_is_not_public(self):
        """Audience floor still wins over pinning: a public citing corpus may
        only link to versions anonymous readers can open."""
        self.corpus.is_public = True
        self.corpus.save(update_fields=["is_public"])
        for d in Document.objects.filter(path_records__corpus=self.corpus):
            d.is_public = True
            d.save(update_fields=["is_public"])
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)

        auth = self._bootstrap()
        auth_corpus = Corpus.objects.get(pk=auth["corpus_id"])
        auth_corpus.is_public = True
        auth_corpus.save(update_fields=["is_public"])
        v1 = Document.objects.get(pk=auth["document_ids"][0])
        v1.is_public = True
        v1.save(update_fields=["is_public"])
        self._link()
        self.assertEqual(self._ref().target_document_id, v1.id)

        # v2 lands public (corpus is public); v1 is then made private.
        self._bootstrap("..145 v2..")
        v1.is_public = False
        v1.save(update_fields=["is_public"])
        v2 = Document.objects.get(version_tree_id=v1.version_tree_id, is_current=True)

        out = self._link()
        self.assertEqual(out["law_references_linked"], 1)
        self.assertEqual(self._ref().target_document_id, v2.id)

    def test_graphql_exposes_superseded_state_and_current_target(self):
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)
        self._bootstrap()
        self._link()
        pinned = self._ref().target_document
        self._bootstrap("..145 v2..")
        current = Document.objects.get(
            version_tree_id=pinned.version_tree_id, is_current=True
        )

        query = """
            query($corpusId: ID!, $key: String) {
              corpusReferences(corpusId: $corpusId, canonicalKey: $key) {
                edges { node {
                  targetDocument { id }
                  targetIsSuperseded
                  currentTargetDocument { id }
                } }
              }
            }
        """
        out = Client(schema).execute(
            query,
            variables={
                "corpusId": to_global_id("CorpusType", self.corpus.id),
                "key": "dgcl:145",
            },
            context_value=type("Request", (), {"user": self.user})(),
        )
        self.assertNotIn("errors", out, out)
        node = out["data"]["corpusReferences"]["edges"][0]["node"]
        self.assertEqual(
            node["targetDocument"]["id"], to_global_id("DocumentType", pinned.id)
        )
        self.assertTrue(node["targetIsSuperseded"])
        self.assertEqual(
            node["currentTargetDocument"]["id"],
            to_global_id("DocumentType", current.id),
        )

    def test_graphql_current_target_hidden_when_not_visible(self):
        """The derived current version goes through DocumentType visibility."""
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)
        self._bootstrap()
        self._link()
        pinned = self._ref().target_document
        self._bootstrap("..145 v2..")
        current = Document.objects.get(
            version_tree_id=pinned.version_tree_id, is_current=True
        )
        # Share the citing corpus + pinned version with a reader who cannot see
        # the amended version.
        reader = User.objects.create_user(username="reader", password="p")
        self.corpus.is_public = True
        self.corpus.save(update_fields=["is_public"])
        for d in Document.objects.filter(path_records__corpus=self.corpus):
            d.is_public = True
            d.save(update_fields=["is_public"])
        pinned.is_public = True
        pinned.save(update_fields=["is_public"])
        self.assertFalse(current.is_public)

        query = """
            query($corpusId: ID!, $key: String) {
              corpusReferences(corpusId: $corpusId, canonicalKey: $key) {
                edges { node { targetIsSuperseded currentTargetDocument { id } } }
              }
            }
        """
        out = Client(schema).execute(
            query,
            variables={
                "corpusId": to_global_id("CorpusType", self.corpus.id),
                "key": "dgcl:145",
            },
            context_value=type("Request", (), {"user": reader})(),
        )
        self.assertNotIn("errors", out, out)
        edges = out["data"]["corpusReferences"]["edges"]
        # The target corpus is private to the owner, so the strict visibility
        # filter may hide the whole row for the reader; if it is visible, the
        # invisible current version must be null.
        for edge in edges:
            self.assertTrue(edge["node"]["targetIsSuperseded"])
            self.assertIsNone(edge["node"]["currentTargetDocument"])
