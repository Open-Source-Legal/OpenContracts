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


class SupersededSourceVisibilityTests(TestCase):
    """A citing document's version-up must not leak history into current views."""

    def setUp(self):
        self.user = User.objects.create_user(username="owner2", password="p")
        self.corpus = Corpus.objects.create(title="Filings", creator=self.user)
        doc = Document.objects.create(title="Acme S-1 primary", creator=self.user)
        doc.txt_extract_file.save("s1.txt", ContentFile(S1_TEXT.encode("utf-8")))
        self.corpus.add_document(document=doc, user=self.user)
        exhibit = Document.objects.create(
            title="Acme S-1 (2024-09-30) - Exhibit 1.1: EX-1.1", creator=self.user
        )
        exhibit.txt_extract_file.save("ex11.txt", ContentFile(b"underwriting"))
        self.corpus.add_document(document=exhibit, user=self.user)
        self.v1 = Document.objects.get(
            path_records__corpus=self.corpus, title="Acme S-1 primary"
        )
        self.auth = AuthorityCorpusBootstrapper().bootstrap(
            creator_id=self.user.id,
            corpus_title="Delaware General Corporation Law",
            corpus_slug="dgcl2",
            sections=[
                AuthoritySection(key="dgcl:145", heading="DGCL § 145", text="..145..")
            ],
        )
        self.authority_doc = Document.objects.get(pk=self.auth["document_ids"][0])
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)

    def _reupload_primary(self) -> Document:
        from opencontractserver.documents.versioning import import_document

        path = DocumentPath.objects.get(
            document=self.v1, corpus=self.corpus, is_current=True
        ).path
        v2, status, _ = import_document(
            corpus=self.corpus,
            path=path,
            content=(S1_TEXT + " Amended.").encode("utf-8"),
            user=self.user,
            file_type="text/plain",
        )
        self.assertEqual(status, "updated")
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)
        return v2

    def _ctx(self, user=None):
        return type("Request", (), {"user": user or self.user})()

    def test_history_is_kept_on_the_superseded_version(self):
        v2 = self._reupload_primary()
        on_v1 = CorpusReference.objects.filter(
            source_annotation__document=self.v1, canonical_key="dgcl:145"
        )
        on_v2 = CorpusReference.objects.filter(
            source_annotation__document=v2, canonical_key="dgcl:145"
        )
        self.assertEqual(on_v1.count(), 1)
        self.assertEqual(on_v2.count(), 1)
        self.assertEqual(on_v1.get().target_document_id, self.authority_doc.id)

    def test_service_hides_superseded_sources_by_default(self):
        v2 = self._reupload_primary()
        default_sources = set(
            CorpusReferenceService.for_corpus(self.user, self.corpus.id)
            .filter(canonical_key="dgcl:145")
            .values_list("source_annotation__document_id", flat=True)
        )
        self.assertEqual(default_sources, {v2.id})
        historical_sources = set(
            CorpusReferenceService.for_corpus(
                self.user, self.corpus.id, include_historical=True
            )
            .filter(canonical_key="dgcl:145")
            .values_list("source_annotation__document_id", flat=True)
        )
        self.assertEqual(historical_sources, {self.v1.id, v2.id})

    def test_soft_deleted_source_documents_are_hidden_by_default(self):
        from opencontractserver.documents.versioning import delete_document

        path = DocumentPath.objects.get(
            document=self.v1, corpus=self.corpus, is_current=True
        ).path
        delete_document(corpus=self.corpus, path=path, user=self.user)
        self.assertFalse(
            CorpusReferenceService.for_corpus(self.user, self.corpus.id)
            .filter(canonical_key="dgcl:145")
            .exists()
        )
        self.assertTrue(
            CorpusReferenceService.for_corpus(
                self.user, self.corpus.id, include_historical=True
            )
            .filter(canonical_key="dgcl:145")
            .exists()
        )

    def test_graphql_corpus_references_and_inbound_default_to_current(self):
        v2 = self._reupload_primary()
        query = """
            query($corpusId: ID!, $docId: ID!, $hist: Boolean) {
              corpusReferences(
                corpusId: $corpusId, canonicalKey: "dgcl:145", includeHistorical: $hist
              ) { edges { node { sourceAnnotation { document { id } } } } }
              document(id: $docId) {
                inboundReferences(includeHistorical: $hist) {
                  edges { node { sourceAnnotation { document { id } } } }
                }
              }
            }
        """
        variables = {
            "corpusId": to_global_id("CorpusType", self.corpus.id),
            "docId": to_global_id("DocumentType", self.authority_doc.id),
        }
        client = Client(schema)

        def sources(payload, key):
            return {
                e["node"]["sourceAnnotation"]["document"]["id"]
                for e in payload[key]["edges"]
            }

        out = client.execute(
            query, variables={**variables, "hist": False}, context_value=self._ctx()
        )
        self.assertNotIn("errors", out, out)
        v2_gid = {to_global_id("DocumentType", v2.id)}
        self.assertEqual(sources(out["data"], "corpusReferences"), v2_gid)
        self.assertEqual(sources(out["data"]["document"], "inboundReferences"), v2_gid)

        out = client.execute(
            query, variables={**variables, "hist": True}, context_value=self._ctx()
        )
        self.assertNotIn("errors", out, out)
        both = {to_global_id("DocumentType", d) for d in (self.v1.id, v2.id)}
        self.assertEqual(sources(out["data"], "corpusReferences"), both)
        self.assertEqual(sources(out["data"]["document"], "inboundReferences"), both)

    def test_document_graph_projection_ignores_superseded_sources(self):
        from opencontractserver.documents.models import DocumentRelationship
        from opencontractserver.documents.services.relationships import (
            DocumentRelationshipService,
        )

        exhibit = Document.objects.get(
            path_records__corpus=self.corpus, title__startswith="Acme S-1 (2024"
        )
        self.assertTrue(
            DocumentRelationship.objects.filter(
                source_document=self.v1, target_document=exhibit
            ).exists()
        )
        v2 = self._reupload_primary()
        # Projection rebuilt from current sources only.
        self.assertFalse(
            DocumentRelationship.objects.filter(source_document=self.v1).exists()
        )
        self.assertTrue(
            DocumentRelationship.objects.filter(
                source_document=v2, target_document=exhibit
            ).exists()
        )
        visible = DocumentRelationshipService.get_visible_relationships(
            self.user, corpus_id=self.corpus.id
        )
        self.assertEqual(
            set(visible.values_list("source_document_id", flat=True)), {v2.id}
        )

    def test_document_graph_projects_onto_current_target_version(self):
        """Re-uploading the cited exhibit: the pinned reference keeps v1, the
        graph edge points at the exhibit's current version."""
        from opencontractserver.documents.models import DocumentRelationship
        from opencontractserver.documents.versioning import import_document

        exhibit_v1 = Document.objects.get(
            path_records__corpus=self.corpus, title__startswith="Acme S-1 (2024"
        )
        path = DocumentPath.objects.get(
            document=exhibit_v1, corpus=self.corpus, is_current=True
        ).path
        exhibit_v2, status, _ = import_document(
            corpus=self.corpus,
            path=path,
            content=b"underwriting agreement, amended",
            user=self.user,
            file_type="text/plain",
        )
        self.assertEqual(status, "updated")
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)

        ref = CorpusReference.objects.get(
            corpus=self.corpus,
            reference_type=C.REF_DOCUMENT,
            source_annotation__document=self.v1,
        )
        self.assertEqual(ref.target_document_id, exhibit_v1.id)
        self.assertTrue(CorpusReferenceService.target_is_superseded(ref))
        self.assertTrue(
            DocumentRelationship.objects.filter(
                source_document=self.v1, target_document=exhibit_v2
            ).exists()
        )
        self.assertFalse(
            DocumentRelationship.objects.filter(
                source_document=self.v1, target_document=exhibit_v1
            ).exists()
        )

    def test_user_authored_relationship_to_superseded_version_is_hidden(self):
        from opencontractserver.documents.models import DocumentRelationship
        from opencontractserver.documents.services.relationships import (
            DocumentRelationshipService,
        )

        exhibit = Document.objects.get(
            path_records__corpus=self.corpus, title__startswith="Acme S-1 (2024"
        )
        DocumentRelationship.objects.create(
            source_document=self.v1,
            target_document=exhibit,
            relationship_type="NOTES",
            corpus=self.corpus,
            creator=self.user,
            data={"note": "hand made"},
        )
        self._reupload_primary()
        visible = DocumentRelationshipService.get_visible_relationships(
            self.user, corpus_id=self.corpus.id, relationship_type="NOTES"
        )
        self.assertFalse(visible.filter(source_document=self.v1).exists())
