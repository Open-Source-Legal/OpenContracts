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

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.utils import timezone
from graphene.test import Client
from graphql_relay import from_global_id, to_global_id

from config.graphql.schema import schema
from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
    StructuralAnnotationSet,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
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

        # A single content hash → a single StructuralAnnotationSet shared by
        # the source document and every corpus copy of it.
        content_hash = hashlib.sha256(b"shared structural content").hexdigest()
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
            corpus_id=self.corpus_a.id, document_id=self.doc_b.id
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
