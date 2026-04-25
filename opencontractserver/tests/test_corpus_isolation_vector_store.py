"""
Regression tests for cross-corpus structural-annotation leak in
``CoreAnnotationVectorStore``.

Background
----------
Annotations created by parsers (paragraph/sentence/sliding-window chunks) live
in ``StructuralAnnotationSet`` rows with ``Annotation.document_id = NULL`` and
``Annotation.corpus_id = NULL``. Their corpus membership is only knowable
through ``structural_set → Document.structural_annotation_set (reverse FK) →
DocumentPath.corpus_id``.

Before the fix, ``CoreAnnotationVectorStore._build_base_queryset()`` had two
collaborating defects in the corpus-only path (``corpus_id`` set,
``document_id`` is None):

1. The ``check_corpus_deletion`` block applied ``Q(document_id__in=active)``
   which silently excludes structural annotations (NULL ``document_id``).
2. The corpus-only branch applied ``Q(structural=True)`` with **no corpus
   constraint at all** — so when the deletion filter was bypassed, structural
   annotations from every corpus in the database leaked through.

These tests mount evidence for both behaviours.
"""

from __future__ import annotations

import hashlib

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
    StructuralAnnotationSet,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.llms.vector_stores.core_vector_stores import (
    CoreAnnotationVectorStore,
    VectorSearchQuery,
)
from opencontractserver.pipeline.utils import get_default_embedder_path

User = get_user_model()


def _constant_vector(dimension: int = 384, value: float = 0.5) -> list[float]:
    """Generate a deterministic constant vector of the given dimension."""
    return [value] * dimension


class CrossCorpusStructuralLeakTests(TestCase):
    """Reproductions of the cross-corpus structural-annotation leak bug.

    Each test sets up two corpora (A and B), each owning its own
    ``StructuralAnnotationSet`` and structural annotations with embeddings,
    then queries ``CoreAnnotationVectorStore`` scoped to corpus A and
    asserts that no row from corpus B appears.
    """

    def setUp(self) -> None:  # noqa: D401 - test fixture
        self.user = User.objects.create_user(
            username="cross_corpus_tester",
            password="testpass",
            email="cross_corpus_tester@example.com",
        )

        self.label = AnnotationLabel.objects.create(text="Paragraph", creator=self.user)

        self.corpus_a = Corpus.objects.create(
            title="Corpus A", creator=self.user, is_public=True
        )
        self.corpus_b = Corpus.objects.create(
            title="Corpus B", creator=self.user, is_public=True
        )

        # Each corpus gets its own structural set + document. We deliberately
        # create separate sets (different content_hash) to mirror the bug
        # scenario where two corpora's parsers produced disjoint sets.
        self.set_a = StructuralAnnotationSet.objects.create(
            content_hash=hashlib.sha256(b"corpus-a-content").hexdigest(),
            creator=self.user,
            parser_name="TestParser",
            parser_version="1.0",
        )
        self.set_b = StructuralAnnotationSet.objects.create(
            content_hash=hashlib.sha256(b"corpus-b-content").hexdigest(),
            creator=self.user,
            parser_name="TestParser",
            parser_version="1.0",
        )

        self.doc_a = Document.objects.create(
            title="Doc A",
            creator=self.user,
            is_public=True,
            structural_annotation_set=self.set_a,
        )
        self.doc_b = Document.objects.create(
            title="Doc B",
            creator=self.user,
            is_public=True,
            structural_annotation_set=self.set_b,
        )

        # DocumentPath links each document to its respective corpus. Active
        # paths so the deletion-aware filter in the vector store doesn't
        # exclude them on grounds of deletion.
        DocumentPath.objects.create(
            document=self.doc_a,
            corpus=self.corpus_a,
            path="/doc_a.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )
        DocumentPath.objects.create(
            document=self.doc_b,
            corpus=self.corpus_b,
            path="/doc_b.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )

        # Structural annotations on each set. document_id is NULL — this is
        # the parser-produced shape that the bug applies to.
        self.struct_a = Annotation.objects.create(
            structural_set=self.set_a,
            annotation_label=self.label,
            creator=self.user,
            raw_text="Corpus A structural paragraph",
            structural=True,
            page=1,
        )
        self.struct_b = Annotation.objects.create(
            structural_set=self.set_b,
            annotation_label=self.label,
            creator=self.user,
            raw_text="Corpus B structural paragraph",
            structural=True,
            page=1,
        )

        # Equip both with embeddings for the default embedder so they are
        # candidates for vector retrieval.
        embedder_path = get_default_embedder_path()
        self.struct_a.add_embedding(embedder_path, _constant_vector(384, 0.10))
        self.struct_b.add_embedding(embedder_path, _constant_vector(384, 0.20))

    # ------------------------------------------------------------------ #
    # Corpus-only retrieval (the hot path for the bug)
    # ------------------------------------------------------------------ #

    def test_corpus_wide_search_excludes_other_corpus_structural(self) -> None:
        """corpus_id=A + document_id=None must NOT return corpus B's annotations.

        This is the core leak. With ``check_corpus_deletion=False`` the
        corpus-only branch is the *only* corpus enforcement, so failure here
        is a direct demonstration of the bug.
        """
        store = CoreAnnotationVectorStore(
            user_id=self.user.id,
            corpus_id=self.corpus_a.id,
            document_id=None,
            check_corpus_deletion=False,
        )
        query = VectorSearchQuery(
            query_embedding=_constant_vector(384, 0.5), similarity_top_k=10
        )
        results = store.search(query)
        returned_ids = {r.annotation.id for r in results}

        self.assertNotIn(
            self.struct_b.id,
            returned_ids,
            "Corpus B structural annotation leaked into corpus-A scoped search",
        )

    def test_corpus_wide_search_returns_own_corpus_structural(self) -> None:
        """The deletion-aware filter must not silently drop structural rows.

        With ``check_corpus_deletion=True`` (the production default) the
        previous code applied ``Q(document_id__in=active)`` which never
        matches NULL ``document_id``, dropping every parser-produced
        structural annotation. The fix must keep them visible.
        """
        store = CoreAnnotationVectorStore(
            user_id=self.user.id,
            corpus_id=self.corpus_a.id,
            document_id=None,
            check_corpus_deletion=True,
        )
        query = VectorSearchQuery(
            query_embedding=_constant_vector(384, 0.5), similarity_top_k=10
        )
        results = store.search(query)
        returned_ids = {r.annotation.id for r in results}

        self.assertIn(
            self.struct_a.id,
            returned_ids,
            "Corpus A structural annotation was silently dropped by "
            "deletion-aware filter",
        )
        self.assertNotIn(
            self.struct_b.id,
            returned_ids,
            "Corpus B structural annotation leaked through deletion-aware path",
        )

    def test_corpus_wide_search_excludes_orphan_structural_set(self) -> None:
        """Structural sets not linked to ANY document in this corpus are out.

        Sets shared by zero corpora (e.g. sets whose documents were all
        purged or never imported) must not appear in corpus-scoped results.
        """
        orphan_set = StructuralAnnotationSet.objects.create(
            content_hash=hashlib.sha256(b"orphan-content").hexdigest(),
            creator=self.user,
            parser_name="TestParser",
            parser_version="1.0",
        )
        orphan_anno = Annotation.objects.create(
            structural_set=orphan_set,
            annotation_label=self.label,
            creator=self.user,
            raw_text="Orphan structural paragraph",
            structural=True,
            page=1,
        )
        orphan_anno.add_embedding(
            get_default_embedder_path(), _constant_vector(384, 0.30)
        )

        store = CoreAnnotationVectorStore(
            user_id=self.user.id,
            corpus_id=self.corpus_a.id,
            document_id=None,
            check_corpus_deletion=False,
        )
        query = VectorSearchQuery(
            query_embedding=_constant_vector(384, 0.5), similarity_top_k=10
        )
        results = store.search(query)
        returned_ids = {r.annotation.id for r in results}

        self.assertNotIn(
            orphan_anno.id,
            returned_ids,
            "Orphan structural annotation (set linked to no document in any "
            "corpus) leaked into corpus-A scoped search",
        )

    # ------------------------------------------------------------------ #
    # Document-scoped retrieval — must continue to work post-fix
    # ------------------------------------------------------------------ #

    def test_deletion_aware_path_excludes_deleted_document_structural(self) -> None:
        """Structural rows whose only ``DocumentPath`` is deleted are dropped.

        Covers the deletion side of ``check_corpus_deletion=True``: the
        ``DocumentPath`` row for ``doc_a`` is flipped to ``is_deleted=True``,
        so ``active_doc_ids`` in
        ``CoreAnnotationVectorStore._build_base_queryset`` becomes empty and
        the corpus-only branch must short-circuit to no results — the
        document's structural annotation must NOT come back, even though the
        annotation row itself is otherwise unchanged.
        """
        DocumentPath.objects.filter(document=self.doc_a, corpus=self.corpus_a).update(
            is_deleted=True
        )

        store = CoreAnnotationVectorStore(
            user_id=self.user.id,
            corpus_id=self.corpus_a.id,
            document_id=None,
            check_corpus_deletion=True,
        )
        query = VectorSearchQuery(
            query_embedding=_constant_vector(384, 0.5), similarity_top_k=10
        )
        results = store.search(query)
        returned_ids = {r.annotation.id for r in results}

        self.assertNotIn(
            self.struct_a.id,
            returned_ids,
            "Structural annotation whose only DocumentPath is deleted "
            "leaked through the deletion-aware corpus-only path",
        )

    def test_deletion_aware_path_partial_deletion_keeps_active_drops_deleted(
        self,
    ) -> None:
        """Partial deletion: with two docs in one corpus, only the active stays.

        The previous test stresses the early-exit branch (every doc deleted
        → ``has_active_docs`` is False → ``Annotation.none()``). This test
        stresses the actual subquery filter:

            active_filters &= Q(document_id__in=active_doc_ids_qs) | Q(
                structural=True, structural_set_id__in=active_struct_set_ids
            )

        With one active document and one deleted document in the same
        corpus, ``active_doc_ids_qs`` is non-empty but partial. The
        deleted document's structural annotation must be excluded while
        the active document's must come through. This is the scenario
        most likely to regress silently if the OR clause is rebuilt or
        the subquery is rewritten incorrectly.
        """
        # Add a second document to corpus_a with its own structural set,
        # then mark its DocumentPath deleted while doc_a's stays active.
        deleted_set = StructuralAnnotationSet.objects.create(
            content_hash=hashlib.sha256(b"corpus-a-deleted-doc").hexdigest(),
            creator=self.user,
            parser_name="TestParser",
            parser_version="1.0",
        )
        deleted_doc = Document.objects.create(
            title="Doc A2 (deleted)",
            creator=self.user,
            is_public=True,
            structural_annotation_set=deleted_set,
        )
        DocumentPath.objects.create(
            document=deleted_doc,
            corpus=self.corpus_a,
            path="/doc_a2.pdf",
            version_number=1,
            is_current=True,
            is_deleted=True,
            creator=self.user,
        )
        deleted_struct = Annotation.objects.create(
            structural_set=deleted_set,
            annotation_label=self.label,
            creator=self.user,
            raw_text="Deleted-doc structural paragraph",
            structural=True,
            page=1,
        )
        deleted_struct.add_embedding(
            get_default_embedder_path(), _constant_vector(384, 0.15)
        )

        store = CoreAnnotationVectorStore(
            user_id=self.user.id,
            corpus_id=self.corpus_a.id,
            document_id=None,
            check_corpus_deletion=True,
        )
        query = VectorSearchQuery(
            query_embedding=_constant_vector(384, 0.5), similarity_top_k=10
        )
        results = store.search(query)
        returned_ids = {r.annotation.id for r in results}

        self.assertIn(
            self.struct_a.id,
            returned_ids,
            "Active document's structural annotation was excluded by the "
            "partial-deletion subquery filter",
        )
        self.assertNotIn(
            deleted_struct.id,
            returned_ids,
            "Deleted document's structural annotation leaked through the "
            "partial-deletion subquery filter",
        )

    def test_document_scoped_search_still_returns_structural(self) -> None:
        """Document-scoped retrieval is the existing well-tested path.

        We assert it remains unaffected by the corpus-only fix.
        """
        store = CoreAnnotationVectorStore(
            user_id=self.user.id,
            corpus_id=self.corpus_a.id,
            document_id=self.doc_a.id,
        )
        query = VectorSearchQuery(
            query_embedding=_constant_vector(384, 0.5), similarity_top_k=10
        )
        results = store.search(query)
        returned_ids = {r.annotation.id for r in results}

        self.assertIn(
            self.struct_a.id,
            returned_ids,
            "Document-scoped search lost its structural annotation",
        )
        self.assertNotIn(
            self.struct_b.id,
            returned_ids,
            "Document-scoped search returned a different document's structural",
        )


class StructuralAnnotationVisibilityTests(TestCase):
    """Verify structural annotations respect per-document visibility.

    A user with permission on a public corpus must not be served structural
    annotations from a *private* document in that corpus. Before the fix the
    vector store applied ``Q(structural=True)`` with no permission constraint
    at all — only an upfront IDOR check on the requested ``corpus_id``,
    leaving structural rows of inaccessible documents reachable.
    """

    def setUp(self) -> None:  # noqa: D401 - test fixture
        self.creator = User.objects.create_user(
            username="struct_visibility_creator",
            password="testpass",
            email="struct_visibility_creator@example.com",
        )
        self.viewer = User.objects.create_user(
            username="struct_visibility_viewer",
            password="testpass",
            email="struct_visibility_viewer@example.com",
        )

        self.label = AnnotationLabel.objects.create(
            text="Paragraph", creator=self.creator
        )

        # Public corpus — the viewer can see the corpus itself (passes the
        # vector store's IDOR check) but has no permission on its private
        # document.
        self.corpus = Corpus.objects.create(
            title="Public Corpus With Private Doc",
            creator=self.creator,
            is_public=True,
        )

        # Private document inside the public corpus.
        self.private_set = StructuralAnnotationSet.objects.create(
            content_hash=hashlib.sha256(b"private-doc-content").hexdigest(),
            creator=self.creator,
            parser_name="TestParser",
            parser_version="1.0",
        )
        self.private_doc = Document.objects.create(
            title="Private Doc",
            creator=self.creator,
            is_public=False,
            structural_annotation_set=self.private_set,
        )
        DocumentPath.objects.create(
            document=self.private_doc,
            corpus=self.corpus,
            path="/private.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.creator,
        )

        self.private_struct = Annotation.objects.create(
            structural_set=self.private_set,
            annotation_label=self.label,
            creator=self.creator,
            raw_text="Private structural paragraph",
            structural=True,
            page=1,
        )
        self.private_struct.add_embedding(
            get_default_embedder_path(), _constant_vector(384, 0.40)
        )

    def test_viewer_excluded_from_private_doc_structural(self) -> None:
        """Viewer with corpus access but no doc access must not see the row."""
        store = CoreAnnotationVectorStore(
            user_id=self.viewer.id,
            corpus_id=self.corpus.id,
            document_id=None,
            check_corpus_deletion=False,
        )
        query = VectorSearchQuery(
            query_embedding=_constant_vector(384, 0.5), similarity_top_k=10
        )
        results = store.search(query)
        returned_ids = {r.annotation.id for r in results}

        self.assertNotIn(
            self.private_struct.id,
            returned_ids,
            "Viewer was served a structural annotation from a private "
            "document they have no permission on",
        )

    def test_creator_still_sees_own_structural(self) -> None:
        """Sanity check: the document creator still gets their own row.

        This guards against a fix that over-restricts and breaks the legitimate
        path.
        """
        store = CoreAnnotationVectorStore(
            user_id=self.creator.id,
            corpus_id=self.corpus.id,
            document_id=None,
            check_corpus_deletion=False,
        )
        query = VectorSearchQuery(
            query_embedding=_constant_vector(384, 0.5), similarity_top_k=10
        )
        results = store.search(query)
        returned_ids = {r.annotation.id for r in results}

        self.assertIn(
            self.private_struct.id,
            returned_ids,
            "Document creator lost access to their own structural annotation",
        )
