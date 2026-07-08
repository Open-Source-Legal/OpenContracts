"""Regression tests for corpus annotation-card deep links.

Structural annotations created by the parse-within-corpus pipeline carry
``corpus_id`` set (so they surface in that corpus's "Annotations" tab) but
``document_id=NULL`` — they reach their document only through the shared
``StructuralAnnotationSet`` (``import_annotations`` sets ``corpus`` +
``structural=True``; ``_create_structural_annotation_set`` then nulls
``document`` and moves them onto the set, leaving ``corpus`` intact).

Because a ``StructuralAnnotationSet`` is deduplicated by content hash, the
same set is shared across the standalone import source AND every
corpus-isolated copy (potentially in different corpuses). Two bugs combined
to break the cards. First, ``AnnotationType.resolve_document`` was never run
for the ``document`` field at all: graphene-django's auto-generated FK field
reads the FK straight from ``root.document_id`` (NULL for structural
annotations) and short-circuits, so the field returned ``None`` ("Unknown
Document"). Declaring ``document`` as an explicit ``graphene.Field`` on
``AnnotationType`` makes the custom ``resolve_document`` run. Second, once it
runs, ``resolve_document`` resolved structural annotations via an unscoped,
non-deterministic ``structural_set.documents.first()``. The fix scopes
resolution to the corpus being queried — see
``AnnotationService.structural_document_prefetch`` and
``config/graphql/annotation_queries.py::resolve_annotations``.

These tests prove a structural annotation surfaced in corpus A's cards
resolves to corpus A's copy, and the same shared set resolves to corpus B's
copy when queried via corpus B — never to the standalone source or the other
corpus's copy.
"""

import hashlib
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from graphql_relay import from_global_id, to_global_id

from config.graphql.annotation_types import AnnotationType
from config.graphql.schema import schema
from config.graphql.testing import Client
from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
    StructuralAnnotationSet,
)
from opencontractserver.annotations.services import AnnotationService
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class CorpusCardsStructuralDocumentResolutionTests(TestCase):
    """``annotations(corpusId=...)`` resolves structural docs within the corpus."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="cards_struct_doc_user",
            password="testpass123",
            email="cards_struct_doc@test.com",
        )
        self.other_user = User.objects.create_user(
            username="cards_struct_doc_other_user",
            password="testpass123",
            email="cards_struct_doc_other@test.com",
        )

        # A single content hash → a single StructuralAnnotationSet shared by
        # the source document and every corpus copy of it.
        content_hash = hashlib.sha256(b"shared structural content").hexdigest()
        self.content_hash = content_hash
        self.structural_set = StructuralAnnotationSet.objects.create(
            content_hash=content_hash,
            creator=self.user,
            parser_name="TestParser",
            parser_version="1.0",
        )

        # Standalone import source (NOT added to any corpus) — created first so
        # it has the lowest pk, i.e. the row an unscoped ``.first()`` is most
        # likely to return.
        self.source_doc = Document.objects.create(
            title="Shared S-1 (source)",
            creator=self.user,
            pdf_file_hash=content_hash,
            structural_annotation_set=self.structural_set,
            page_count=3,
            processing_started=timezone.now(),
        )
        set_permissions_for_obj_to_user(
            self.user, self.source_doc, [PermissionTypes.READ]
        )
        # A private document owned by another user that shares the structural
        # set and sorts first in the unscoped structural document prefetch.
        # Resolving through this row would leak another user's DocumentType.
        self.private_doc = Document.objects.create(
            title="Private shared S-1",
            slug="aaa-private-shared-s-1",
            creator=self.other_user,
            pdf_file_hash=content_hash,
            structural_annotation_set=self.structural_set,
            page_count=3,
            processing_started=timezone.now(),
        )

        # Two corpuses, each receiving an isolated copy that SHARES the set.
        self.corpus_a = Corpus.objects.create(
            title="Corpus A", creator=self.user, is_public=True
        )
        self.corpus_b = Corpus.objects.create(
            title="Corpus B", creator=self.user, is_public=True
        )
        for corpus in (self.corpus_a, self.corpus_b):
            set_permissions_for_obj_to_user(self.user, corpus, [PermissionTypes.READ])

        self.doc_a, _, _ = self.corpus_a.add_document(
            document=self.source_doc, user=self.user
        )
        self.doc_b, _, _ = self.corpus_b.add_document(
            document=self.source_doc, user=self.user
        )
        for doc in (self.doc_a, self.doc_b):
            set_permissions_for_obj_to_user(self.user, doc, [PermissionTypes.READ])

        # Sanity: all three documents share the one structural set.
        self.assertEqual(
            self.doc_a.structural_annotation_set_id, self.structural_set.id
        )
        self.assertEqual(
            self.doc_b.structural_annotation_set_id, self.structural_set.id
        )

        self.label = AnnotationLabel.objects.create(text="text", creator=self.user)

    def _make_structural_annotations(self, corpus, prefix):
        """Create structural annotations tagged with ``corpus`` (document NULL).

        Mirrors the parse-within-corpus shape: ``corpus`` set, ``document``
        NULL, linked only through the shared ``structural_set``.
        """
        return [
            Annotation.objects.create(
                corpus=corpus,
                document=None,
                structural_set=self.structural_set,
                annotation_label=self.label,
                creator=self.user,
                raw_text=f"{prefix} Section {i}",
                structural=True,
                page=1,
            )
            for i in range(3)
        ]

    def _client(self):
        request = RequestFactory().get("/graphql")
        request.user = self.user
        return Client(schema, context_value=request)

    _QUERY = """
        query Cards($corpusId: ID!) {
            annotations(corpusId: $corpusId, structural: true, first: 100) {
                edges {
                    node {
                        id
                        structural
                        document { id slug title }
                    }
                }
            }
        }
    """

    _UNSCOPED_QUERY = """
        query Cards {
            annotations(structural: true, first: 100) {
                edges {
                    node {
                        id
                        structural
                        document { id slug title }
                    }
                }
            }
        }
    """

    def _nodes_by_annotation_id(self, corpus):
        """Run the corpus cards query and return ``{annotation_gid: node}``.

        Keyed by annotation id so the assertions test *document resolution*
        (the behaviour this fix changes) independently of connection edge
        cardinality.
        """
        result = self._client().execute(
            self._QUERY,
            variables={"corpusId": to_global_id("CorpusType", corpus.id)},
        )
        self.assertIsNone(
            result.get("errors"), f"GraphQL errors: {result.get('errors')}"
        )
        return {
            edge["node"]["id"]: edge["node"]
            for edge in result["data"]["annotations"]["edges"]
        }

    def test_structural_cards_resolve_to_corpus_local_document(self):
        """Each structural annotation in corpus A's cards resolves to A's copy."""
        annotations = self._make_structural_annotations(self.corpus_a, "A")
        nodes = self._nodes_by_annotation_id(self.corpus_a)

        # Every structural annotation surfaces in the corpus cards.
        self.assertEqual(
            set(nodes),
            {to_global_id("AnnotationType", a.id) for a in annotations},
        )

        expected_doc_gid = to_global_id("DocumentType", self.doc_a.id)
        for node in nodes.values():
            self.assertTrue(node["structural"])
            # Structural annotations resolve their document only via the shared
            # set; it must be present and navigable, not "Unknown Document".
            self.assertIsNotNone(
                node["document"],
                "Structural annotation resolved to no document (Unknown Document)",
            )
            self.assertEqual(
                node["document"]["id"],
                expected_doc_gid,
                "Structural card must resolve to the corpus-A copy, not the "
                "standalone source or another corpus's copy",
            )
            # The corpus-local copy always carries a title — never the
            # frontend's "Unknown Document" fallback.
            self.assertTrue(node["document"]["title"])

    def test_same_structural_set_resolves_per_corpus(self):
        """The same shared set resolves to B's copy when queried via corpus B."""
        annotations = self._make_structural_annotations(self.corpus_b, "B")
        nodes = self._nodes_by_annotation_id(self.corpus_b)

        self.assertEqual(
            set(nodes),
            {to_global_id("AnnotationType", a.id) for a in annotations},
        )

        expected_doc_gid = to_global_id("DocumentType", self.doc_b.id)
        for node in nodes.values():
            self.assertEqual(node["document"]["id"], expected_doc_gid)

    def test_resolved_document_has_path_in_queried_corpus(self):
        """Resolved doc is never the source/other-corpus copy (no path here)."""
        self._make_structural_annotations(self.corpus_a, "A")
        nodes = self._nodes_by_annotation_id(self.corpus_a)
        self.assertTrue(nodes, "expected structural annotations to surface")
        foreign_doc_ids = {self.source_doc.id, self.doc_b.id}
        for node in nodes.values():
            resolved_pk = int(from_global_id(node["document"]["id"])[1])
            self.assertNotIn(
                resolved_pk,
                foreign_doc_ids,
                "resolve_document returned a document with no path in corpus A",
            )

    def test_prefetch_document_id_takes_precedence_over_corpus_id(self):
        """``document_id`` scopes to that exact document, even with a corpus_id.

        The document-knowledge-base view passes both ids; the resolved
        structural document must be the one being viewed, not an arbitrary
        corpus-local copy.
        """
        from opencontractserver.annotations.services import AnnotationService

        annotations = self._make_structural_annotations(self.corpus_a, "A")
        # corpus_id points at A, but document_id pins doc_b — document_id wins.
        prefetch = AnnotationService.structural_document_prefetch(
            user=self.user, corpus_id=self.corpus_a.id, document_id=self.doc_b.id
        )
        fetched = (
            Annotation.objects.filter(id=annotations[0].id)
            .select_related("structural_set")
            .prefetch_related(prefetch)
            .first()
        )
        resolved = list(fetched.structural_set.documents.all())
        self.assertEqual(
            [d.id for d in resolved],
            [self.doc_b.id],
            "document_id must take precedence over corpus_id in the prefetch",
        )

    def test_unscoped_structural_resolution_skips_private_shared_documents(self):
        """Unscoped annotation browsing must not leak a private shared doc."""
        annotations = self._make_structural_annotations(self.corpus_a, "A")
        result = self._client().execute(self._UNSCOPED_QUERY)
        self.assertIsNone(
            result.get("errors"), f"GraphQL errors: {result.get('errors')}"
        )
        nodes = {
            edge["node"]["id"]: edge["node"]
            for edge in result["data"]["annotations"]["edges"]
        }
        expected_annotation_gid = to_global_id("AnnotationType", annotations[0].id)
        self.assertIn(expected_annotation_gid, nodes)

        resolved_doc = nodes[expected_annotation_gid]["document"]
        self.assertIsNotNone(resolved_doc)
        self.assertNotEqual(
            resolved_doc["id"],
            to_global_id("DocumentType", self.private_doc.id),
            "resolve_document returned a private document from the shared set",
        )
        # Positive assertion: the resolved document must be one of the copies
        # the requesting user may READ — excluding the private doc alone would
        # still pass if resolution silently returned the wrong (but visible)
        # member, so pin it to the allowed set.
        allowed_doc_ids = {
            to_global_id("DocumentType", doc.id)
            for doc in (self.source_doc, self.doc_a, self.doc_b)
        }
        self.assertIn(resolved_doc["id"], allowed_doc_ids)

    def test_corpus_scoped_prefetch_skips_private_shared_documents(self):
        """The corpus-scoped *prefetch* path — not just the DB fallback —
        must not leak a private document that shares the structural set and
        has a path inside the queried corpus.

        ``test_unscoped_structural_resolution_skips_private_shared_documents``
        above only exercises the DB fallback (no ``corpusId``/``documentId``
        supplied, so ``AnnotationService.structural_document_prefetch`` scopes
        to nothing but visibility). This test drives the primary production
        path instead: ``annotations(corpusId=...)`` always applies that
        prefetch with ``corpus_id`` set, which is what the corpus annotation
        cards use.

        It also captures the query count for two page sizes of structural
        annotations that all share the ONE structural set, and asserts the
        *delta* stays flat rather than pinning an absolute count (which would
        be brittle against unrelated query-count changes elsewhere in the
        request). A correctly working prefetch issues a single batched query
        for ``structural_set__documents`` regardless of row count; if the
        ``_prefetched_objects_cache`` detection in
        ``AnnotationType.resolve_document`` ever silently breaks (e.g. a
        future Django upgrade renames/restructures that private attribute),
        every row degrades to its own per-row fallback query instead, and the
        delta assertion below catches that.
        """
        # A private, corpus-A-local copy sharing the structural set — built
        # directly (like ``self.private_doc`` in setUp) rather than via
        # ``Corpus.add_document``, which force-sets ``is_public=True`` for
        # any document added to a public corpus (``corpus_a.is_public``) and
        # would defeat this test. Not granted READ to ``self.user``. The
        # "aaa-" slug prefix sorts before ``self.doc_a``'s, so an unfiltered
        # corpus-scoped ``.order_by("slug")`` would pick this one first if
        # the visibility filter silently failed.
        private_doc_in_a = Document.objects.create(
            title="Private shared S-1 (corpus A copy)",
            slug="aaa-private-in-corpus-a",
            creator=self.other_user,
            pdf_file_hash=self.content_hash,
            structural_annotation_set=self.structural_set,
            is_public=False,
            page_count=3,
            processing_started=timezone.now(),
        )
        DocumentPath.objects.create(
            document=private_doc_in_a,
            corpus=self.corpus_a,
            path="/documents/private-in-a",
            version_number=1,
            parent=None,
            is_current=True,
            is_deleted=False,
            creator=self.other_user,
        )

        annotations = self._make_structural_annotations(self.corpus_a, "A")

        with CaptureQueriesContext(connection) as ctx_small:
            nodes = self._nodes_by_annotation_id(self.corpus_a)

        self.assertEqual(
            set(nodes),
            {to_global_id("AnnotationType", a.id) for a in annotations},
        )

        expected_doc_gid = to_global_id("DocumentType", self.doc_a.id)
        private_doc_gid = to_global_id("DocumentType", private_doc_in_a.id)
        for node in nodes.values():
            self.assertNotEqual(
                node["document"]["id"],
                private_doc_gid,
                "corpus-scoped prefetch resolved a private shared document",
            )
            self.assertEqual(
                node["document"]["id"],
                expected_doc_gid,
                "corpus-scoped prefetch must resolve to the corpus-A copy",
            )

        # Triple the structural annotations sharing the same structural_set
        # and re-run the identical query. A correctly batched prefetch issues
        # the same handful of queries regardless of row count; a per-row
        # fallback regression would add roughly one query per extra
        # annotation. Assert the delta stays small rather than pinning an
        # absolute, environment-sensitive query count.
        annotations += self._make_structural_annotations(self.corpus_a, "B")
        annotations += self._make_structural_annotations(self.corpus_a, "C")

        with CaptureQueriesContext(connection) as ctx_large:
            nodes = self._nodes_by_annotation_id(self.corpus_a)

        self.assertEqual(
            set(nodes),
            {to_global_id("AnnotationType", a.id) for a in annotations},
        )
        for node in nodes.values():
            self.assertEqual(node["document"]["id"], expected_doc_gid)

        added_annotations = len(annotations) - 3
        query_delta = len(ctx_large.captured_queries) - len(ctx_small.captured_queries)
        self.assertLess(
            query_delta,
            added_annotations,
            "query count scaled with annotation count (delta "
            f"{query_delta} for {added_annotations} extra annotations) — "
            "the structural document prefetch cache was not used "
            "(N+1 regression)",
        )

    def _info(self, user):
        return SimpleNamespace(context=SimpleNamespace(user=user))

    def test_resolve_document_uncached_fk_uses_permission_gated_fallback(self):
        """When a non-structural ``Annotation`` is fetched WITHOUT
        ``select_related("document")`` (every production query path always
        applies it — see ``resolve_annotations`` / ``resolve_semantic_search``),
        ``AnnotationType.resolve_document`` must re-derive visibility through
        ``AnnotationService.resolve_owned_document`` rather than trusting an
        un-checked FK traversal.
        """
        owned_doc = Document.objects.create(
            title="Directly owned doc",
            creator=self.user,
            page_count=1,
            processing_started=timezone.now(),
        )
        set_permissions_for_obj_to_user(self.user, owned_doc, [PermissionTypes.READ])
        annotation = Annotation.objects.create(
            document=owned_doc,
            annotation_label=self.label,
            creator=self.user,
            raw_text="Clause text",
            page=1,
        )

        fk_uncached = Annotation.objects.get(pk=annotation.id)
        self.assertFalse(
            fk_uncached._meta.get_field("document").is_cached(fk_uncached),
            "test setup must fetch the annotation without select_related",
        )
        resolved = AnnotationType.resolve_document(fk_uncached, self._info(self.user))
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.id, owned_doc.id)

        fk_uncached_again = Annotation.objects.get(pk=annotation.id)
        resolved_for_stranger = AnnotationType.resolve_document(
            fk_uncached_again, self._info(self.other_user)
        )
        self.assertIsNone(
            resolved_for_stranger,
            "resolve_owned_document must not leak a document the requester "
            "cannot READ",
        )

    def test_resolve_owned_document_directly(self):
        """Unit-level coverage of ``AnnotationService.resolve_owned_document``:
        visible documents are returned, invisible ones resolve to ``None``.
        """
        resolved = AnnotationService.resolve_owned_document(
            document_id=self.source_doc.id, user=self.user
        )
        self.assertEqual(resolved.id, self.source_doc.id)

        resolved_for_stranger = AnnotationService.resolve_owned_document(
            document_id=self.source_doc.id, user=self.other_user
        )
        self.assertIsNone(resolved_for_stranger)

    def test_resolve_document_structural_fallback_without_corpus_returns_none(self):
        """The structural DB fallback requires a ``corpus_id`` to scope
        against; a standalone structural annotation (no corpus) resolves to
        ``None`` rather than guessing at an arbitrary shared-set member.
        """
        annotation = Annotation.objects.create(
            corpus=None,
            document=None,
            structural_set=self.structural_set,
            annotation_label=self.label,
            creator=self.user,
            raw_text="Standalone structural annotation",
            structural=True,
            page=1,
        )
        # Fetched without the corpus/document-scoped prefetch, so
        # resolve_document falls through to resolve_structural_document_fallback.
        fresh = Annotation.objects.get(pk=annotation.id)
        resolved = AnnotationType.resolve_document(fresh, self._info(self.user))
        self.assertIsNone(resolved)

    def test_resolve_document_structural_fallback_resolves_corpus_scoped_document(
        self,
    ):
        """With a ``corpus_id`` and no applied prefetch, the DB fallback still
        resolves to the corpus-local, visible copy of the shared structural
        set — mirroring the prefetch-backed resolution exercised elsewhere in
        this file, but through ``AnnotationService.resolve_structural_document_fallback``
        directly.
        """
        annotation = self._make_structural_annotations(self.corpus_a, "A")[0]
        fresh = Annotation.objects.get(pk=annotation.id)
        resolved = AnnotationType.resolve_document(fresh, self._info(self.user))
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.id, self.doc_a.id)

    def test_resolve_structural_document_fallback_directly(self):
        """Unit-level coverage of
        ``AnnotationService.resolve_structural_document_fallback``: no
        ``corpus_id`` short-circuits to ``None``; a valid ``corpus_id``
        resolves the visible, corpus-scoped member of the shared set.
        """
        self.assertIsNone(
            AnnotationService.resolve_structural_document_fallback(
                structural_set_id=self.structural_set.id,
                corpus_id=None,
                user=self.user,
            )
        )

        resolved = AnnotationService.resolve_structural_document_fallback(
            structural_set_id=self.structural_set.id,
            corpus_id=self.corpus_a.id,
            user=self.user,
        )
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.id, self.doc_a.id)
