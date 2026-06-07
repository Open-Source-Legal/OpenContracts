"""Regression tests for corpus annotation-card deep links.

Structural annotations carry ``document_id=NULL`` and reach their document
only through the shared ``StructuralAnnotationSet``. Because that set is
deduplicated by content hash, the SAME set is shared across the standalone
import source AND every corpus-isolated copy (potentially in different
corpuses). ``AnnotationType.resolve_document`` previously returned an
*unscoped*, non-deterministic member of the set
(``structural_set.documents.first()``), so the corpus "Annotations" tab
rendered cards pointing at the wrong document (or no navigable document at
all) and the deep links broke.

The fix scopes the structural-set document resolution to the corpus (or
document) actually being queried — see
``AnnotationService.structural_document_prefetch`` and
``config/graphql/annotation_queries.py::resolve_annotations``. These tests
prove a structural annotation surfaced in corpus A's cards resolves to
corpus A's copy, and the same annotation in corpus B's cards resolves to
corpus B's copy.
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

        # Structural annotations live ONLY on the shared set (document=NULL).
        label = AnnotationLabel.objects.create(text="text", creator=self.user)
        self.struct_annotations = [
            Annotation.objects.create(
                structural_set=self.structural_set,
                annotation_label=label,
                creator=self.user,
                raw_text=f"Section {i}",
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
            annotations(corpusId: $corpusId, structural: true) {
                totalCount
                edges {
                    node {
                        id
                        structural
                        corpus { id }
                        document { id slug title }
                    }
                }
            }
        }
    """

    def _resolved_documents(self, corpus):
        result = self._client().execute(
            self._QUERY,
            variables={"corpusId": to_global_id("CorpusType", corpus.id)},
        )
        self.assertIsNone(
            result.get("errors"), f"GraphQL errors: {result.get('errors')}"
        )
        return [edge["node"] for edge in result["data"]["annotations"]["edges"]]

    def test_structural_cards_resolve_to_corpus_local_document(self):
        """A structural annotation in corpus A's cards resolves to A's copy."""
        nodes = self._resolved_documents(self.corpus_a)

        # All three structural annotations surface in the corpus cards.
        self.assertEqual(len(nodes), len(self.struct_annotations))

        expected_doc_gid = to_global_id("DocumentType", self.doc_a.id)
        for node in nodes:
            self.assertTrue(node["structural"])
            # Structural annotations are corpus-agnostic → corpus is null; the
            # resolved document must still be present and navigable.
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
        nodes = self._resolved_documents(self.corpus_b)
        self.assertEqual(len(nodes), len(self.struct_annotations))

        expected_doc_gid = to_global_id("DocumentType", self.doc_b.id)
        for node in nodes:
            self.assertEqual(node["document"]["id"], expected_doc_gid)

    def test_resolved_document_has_path_in_queried_corpus(self):
        """Resolved doc is never the source/other-corpus copy (no path here)."""
        nodes = self._resolved_documents(self.corpus_a)
        foreign_doc_ids = {self.source_doc.id, self.doc_b.id}
        for node in nodes:
            resolved_pk = int(from_global_id(node["document"]["id"])[1])
            self.assertNotIn(
                resolved_pk,
                foreign_doc_ids,
                "resolve_document returned a document with no path in corpus A",
            )
