"""Tests for the OC_SUBTREE_GROUP → vector-search wiring (issue #1645).

Covers two layers:

1. ``CoreAnnotationVectorStore`` attaches a ``BlockContext`` to annotation
   hits whose annotation participates in a materialised OC_SUBTREE_GROUP,
   picking the smallest enclosing group when several nest.
2. ``CoreRelationshipVectorStore`` returns embedded OC_SUBTREE_GROUP rows
   ranked by cosine similarity against the same embedding store, scoped by
   ``visible_to_user`` / corpus / document for IDOR safety.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase

from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
    Relationship,
)
from opencontractserver.constants.annotations import (
    OC_SUBTREE_GROUP_LABEL_NAME,
    SUBTREE_GROUP_BLOCK_TEXT_MAX_CHARS,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.llms.vector_stores.core_relationship_vector_store import (
    CoreRelationshipVectorStore,
    RelationshipVectorSearchQuery,
)
from opencontractserver.llms.vector_stores.core_vector_stores import (
    BlockContext,
    CoreAnnotationVectorStore,
)
from opencontractserver.pipeline.utils import get_default_embedder_path
from opencontractserver.utils.embeddings import (
    synthesize_relationship_block_text,
)
from opencontractserver.utils.subtree_groups import (
    build_subtree_groups_for_document,
)

if TYPE_CHECKING:
    from opencontractserver.users.models import User as UserModel

User = get_user_model()


def constant_vector(dim: int, value: float) -> list[float]:
    return [value] * dim


class BlockContextAttachTestCase(TestCase):
    """Annotation-hit block_context augmentation."""

    user: UserModel
    corpus: Corpus
    document: Document
    label_struct: AnnotationLabel
    root: Annotation
    section: Annotation
    para: Annotation
    leaf: Annotation

    @classmethod
    def setUpTestData(cls) -> None:
        with transaction.atomic():
            cls.user = User.objects.create_user(
                username="block-context-user",
                password="pw",
            )
            cls.corpus = Corpus.objects.create(
                title="BlockContext Corpus",
                creator=cls.user,
                is_public=True,
            )
            cls.document = Document.objects.create(
                title="BlockContext Doc",
                creator=cls.user,
                is_public=True,
            )
            DocumentPath.objects.create(
                document=cls.document,
                corpus=cls.corpus,
                path="/blockctx.pdf",
                version_number=1,
                is_current=True,
                is_deleted=False,
                creator=cls.user,
            )

            cls.label_struct = AnnotationLabel.objects.create(
                text="Structural", creator=cls.user
            )

            # Tree:  ROOT  →  SECTION  →  PARA  →  LEAF
            # Two nested groups (ROOT and SECTION) both contain LEAF;
            # SECTION is the smaller — the helper must surface SECTION.
            cls.root = Annotation.objects.create(
                document=cls.document,
                annotation_label=cls.label_struct,
                raw_text="ROOT-text",
                structural=True,
                creator=cls.user,
                is_public=True,
            )
            cls.section = Annotation.objects.create(
                document=cls.document,
                annotation_label=cls.label_struct,
                raw_text="SECTION-text",
                structural=True,
                creator=cls.user,
                parent=cls.root,
                is_public=True,
            )
            cls.para = Annotation.objects.create(
                document=cls.document,
                annotation_label=cls.label_struct,
                raw_text="PARA-text",
                structural=True,
                creator=cls.user,
                parent=cls.section,
                is_public=True,
            )
            cls.leaf = Annotation.objects.create(
                document=cls.document,
                annotation_label=cls.label_struct,
                raw_text="LEAF-text",
                structural=True,
                creator=cls.user,
                parent=cls.para,
                is_public=True,
            )

        # Materialise OC_SUBTREE_GROUP rows (root, section, para). Para
        # is a non-leaf with one descendant (leaf), so three groups total.
        created = build_subtree_groups_for_document(cls.document, cls.user.id)
        assert created == 3, f"expected 3 subtree groups, got {created}"

    def test_smallest_enclosing_block_is_surfaced(self) -> None:
        """Hit on LEAF surfaces PARA (smallest), not SECTION or ROOT."""
        results = CoreAnnotationVectorStore._attach_block_context_sync(
            [_fake_result(self.leaf)]
        )
        self.assertIsNotNone(results[0].block_context)
        bc: BlockContext = results[0].block_context  # type: ignore[assignment]
        # PARA's descendant set is {LEAF}, so it has the fewest descendants
        # and wins over SECTION ({PARA, LEAF}) and ROOT ({SECTION, PARA, LEAF}).
        self.assertEqual(bc.source_annotation_id, self.para.id)
        self.assertEqual(bc.target_annotation_ids, [self.leaf.id])
        self.assertEqual(bc.source_text, "PARA-text")
        # block_text should be "source\ntarget" — the join uses newlines.
        self.assertIn("PARA-text", bc.block_text)
        self.assertIn("LEAF-text", bc.block_text)
        self.assertLessEqual(len(bc.block_text), SUBTREE_GROUP_BLOCK_TEXT_MAX_CHARS)

    def test_no_block_context_for_root_level_hit(self) -> None:
        """ROOT has no enclosing subtree — block_context stays None."""
        results = CoreAnnotationVectorStore._attach_block_context_sync(
            [_fake_result(self.root)]
        )
        self.assertIsNone(results[0].block_context)

    def test_empty_results_pass_through(self) -> None:
        """Helper is safe to call with an empty list."""
        out = CoreAnnotationVectorStore._attach_block_context_sync([])
        self.assertEqual(out, [])

    def test_block_text_is_bounded(self) -> None:
        """Block text truncates at the cap regardless of underlying length."""
        # Inflate the LEAF text so concatenation exceeds the cap. We
        # mutate a fresh DB-refreshed instance so the shared
        # ``cls.leaf`` in-memory object isn't dirtied for sibling tests.
        # The TestCase transaction rolls back the DB write at teardown.
        big = "x" * (SUBTREE_GROUP_BLOCK_TEXT_MAX_CHARS + 100)
        leaf = Annotation.objects.get(pk=self.leaf.pk)
        leaf.raw_text = big
        leaf.save(update_fields=["raw_text"])
        results = CoreAnnotationVectorStore._attach_block_context_sync(
            [_fake_result(leaf)]
        )
        bc = results[0].block_context
        self.assertIsNotNone(bc)
        assert bc is not None  # appease type checker
        self.assertLessEqual(len(bc.block_text), SUBTREE_GROUP_BLOCK_TEXT_MAX_CHARS)

    def test_non_structural_group_relationship_is_ignored(self) -> None:
        """Only ``structural=True`` OC_SUBTREE_GROUP rows contribute context.

        Guards against an analyzer (or any other writer) copying the
        OC_SUBTREE_GROUP label onto a non-structural relationship and
        polluting block_context. The filter in
        ``_attach_block_context_sync`` pins ``structural=True`` alongside
        the label name; this test removes the genuine structural group
        for LEAF and replaces it with a non-structural look-alike — the
        helper must return ``block_context=None`` rather than fall back
        to the imposter.
        """
        subtree_label = AnnotationLabel.objects.get(text=OC_SUBTREE_GROUP_LABEL_NAME)

        # Drop every materialised group that covers LEAF so the structural
        # path can't satisfy the request, leaving only the non-structural
        # decoy as a candidate.
        Relationship.objects.filter(
            relationship_label=subtree_label,
            structural=True,
            target_annotations=self.leaf,
        ).delete()

        decoy = Relationship.objects.create(
            relationship_label=subtree_label,
            document=self.document,
            structural=False,  # the bit the filter must enforce
            creator=self.user,
        )
        decoy.source_annotations.add(self.para)
        decoy.target_annotations.add(self.leaf)

        results = CoreAnnotationVectorStore._attach_block_context_sync(
            [_fake_result(self.leaf)]
        )
        self.assertIsNone(results[0].block_context)


class RelationshipVectorStoreTestCase(TestCase):
    """End-to-end: embed a subtree group and retrieve it via vector search."""

    user: UserModel
    corpus: Corpus
    document: Document
    label_struct: AnnotationLabel
    parent: Annotation
    child_a: Annotation
    child_b: Annotation
    subtree_rel: Relationship

    @classmethod
    def setUpTestData(cls) -> None:
        with transaction.atomic():
            cls.user = User.objects.create_user(
                username="rel-search-user", password="pw"
            )
            cls.corpus = Corpus.objects.create(
                title="Rel Search Corpus",
                creator=cls.user,
                is_public=True,
            )
            cls.document = Document.objects.create(
                title="Rel Search Doc",
                creator=cls.user,
                is_public=True,
            )
            DocumentPath.objects.create(
                document=cls.document,
                corpus=cls.corpus,
                path="/rel.pdf",
                version_number=1,
                is_current=True,
                is_deleted=False,
                creator=cls.user,
            )

            cls.label_struct = AnnotationLabel.objects.create(
                text="Structural", creator=cls.user
            )
            cls.parent = Annotation.objects.create(
                document=cls.document,
                annotation_label=cls.label_struct,
                raw_text="parent-block",
                structural=True,
                creator=cls.user,
                is_public=True,
            )
            cls.child_a = Annotation.objects.create(
                document=cls.document,
                annotation_label=cls.label_struct,
                raw_text="child-A",
                structural=True,
                creator=cls.user,
                parent=cls.parent,
                is_public=True,
            )
            cls.child_b = Annotation.objects.create(
                document=cls.document,
                annotation_label=cls.label_struct,
                raw_text="child-B",
                structural=True,
                creator=cls.user,
                parent=cls.parent,
                is_public=True,
            )

        build_subtree_groups_for_document(cls.document, cls.user.id)
        cls.subtree_rel = Relationship.objects.filter(
            relationship_label__text=OC_SUBTREE_GROUP_LABEL_NAME,
            source_annotations=cls.parent,
        ).get()

        # Hand-embed the relationship: we don't want to invoke the Celery
        # task in tests, so write the vector directly. This still
        # exercises the manager / FK / partial-unique path.
        embedder_path = get_default_embedder_path()
        cls.subtree_rel.add_embedding(embedder_path, constant_vector(384, 0.4))

    def test_vector_hit_returns_block_metadata(self) -> None:
        """A search query whose vector aligns with the embedding returns it."""
        store = CoreRelationshipVectorStore(
            user_id=self.user.id,
            corpus_id=self.corpus.id,
            embedder_path=get_default_embedder_path(),
        )
        # Use the same vector we stored so cosine-distance == 0.
        results = store.search(
            RelationshipVectorSearchQuery(
                query_embedding=constant_vector(384, 0.4),
                similarity_top_k=5,
            )
        )
        self.assertEqual(len(results), 1)
        hit = results[0]
        self.assertEqual(hit.relationship.id, self.subtree_rel.id)
        self.assertEqual(hit.source_annotation_id, self.parent.id)
        self.assertEqual(
            set(hit.target_annotation_ids), {self.child_a.id, self.child_b.id}
        )
        self.assertEqual(hit.label_text, OC_SUBTREE_GROUP_LABEL_NAME)
        # block_text mirrors what the embedder would have seen.
        embed_text = synthesize_relationship_block_text(self.subtree_rel)
        self.assertEqual(hit.block_text, embed_text)
        # Similarity is cosine-distance-derived; near-identical vector
        # should score very high (≥ 0.99 after the 1-distance flip).
        self.assertGreater(hit.similarity_score, 0.99)

    def test_idor_corpus_denied(self) -> None:
        """A user lacking corpus visibility gets an empty list, not an error."""
        other_user = User.objects.create_user(username="rel-other", password="pw")
        private_corpus = Corpus.objects.create(
            title="Private Corpus",
            creator=self.user,  # belongs to first user
            is_public=False,
        )
        # ``other_user`` cannot see ``private_corpus``. The store must
        # return [] without leaking anything from the embedded subtree.
        store = CoreRelationshipVectorStore(
            user_id=other_user.id,
            corpus_id=private_corpus.id,
            embedder_path=get_default_embedder_path(),
        )
        results = store.search(
            RelationshipVectorSearchQuery(
                query_embedding=constant_vector(384, 0.4),
                similarity_top_k=5,
            )
        )
        self.assertEqual(results, [])

    def test_async_search_delegates_to_sync_search(self) -> None:
        """``async_search`` is a thin ``sync_to_async`` wrapper over
        ``search``; pinning its delegation contract so any future
        divergence (e.g. an async-specific code path that drops a
        field) surfaces immediately. We mock ``search`` rather than
        exercise the DB because ``TestCase`` + ``sync_to_async``
        threads see a different connection than the test
        transaction, so an end-to-end async DB query would
        false-negative under TestCase. The DB happy path is already
        pinned by ``test_vector_hit_returns_block_metadata``."""
        import asyncio
        from unittest.mock import patch

        store = CoreRelationshipVectorStore(
            user_id=self.user.id,
            corpus_id=self.corpus.id,
            embedder_path=get_default_embedder_path(),
        )
        query = RelationshipVectorSearchQuery(
            query_embedding=constant_vector(384, 0.4),
            similarity_top_k=5,
        )
        sentinel: list = ["sentinel-result"]
        with patch.object(store, "search", return_value=sentinel) as mock_search:
            result = asyncio.run(store.async_search(query))
        mock_search.assert_called_once_with(query)
        self.assertIs(result, sentinel)

    def test_async_search_regenerates_query_embedding_for_text_only(self) -> None:
        """When only ``query_text`` is supplied, ``async_search`` runs
        the async embedding regeneration before delegating to
        ``search``. Pinning that the regenerated vector flows through
        on the rebuilt query keeps the text-only path honest."""
        import asyncio
        from unittest.mock import patch

        store = CoreRelationshipVectorStore(
            user_id=self.user.id,
            corpus_id=self.corpus.id,
            embedder_path=get_default_embedder_path(),
        )
        query = RelationshipVectorSearchQuery(
            query_text="hello world",
            similarity_top_k=3,
        )
        regenerated = constant_vector(384, 0.42)

        async def _fake_embed(_text: str) -> list[float]:
            return regenerated

        with patch.object(
            store, "_agenerate_query_embedding", side_effect=_fake_embed
        ), patch.object(store, "search", return_value=[]) as mock_search:
            asyncio.run(store.async_search(query))
        # ``search`` is called with a rebuilt query carrying the
        # regenerated embedding — not the original text-only query.
        forwarded = mock_search.call_args.args[0]
        self.assertEqual(forwarded.query_embedding, regenerated)
        self.assertEqual(forwarded.query_text, "hello world")
        self.assertEqual(forwarded.similarity_top_k, 3)


def _fake_result(annotation: Annotation):
    """Build a VectorSearchResult for the attach helper to consume."""
    from opencontractserver.llms.vector_stores.core_vector_stores import (
        VectorSearchResult,
    )

    return VectorSearchResult(annotation=annotation, similarity_score=1.0)


# ----------------------------------------------------------------------------
# Helper-text synthesis
# ----------------------------------------------------------------------------


class SynthesizeBlockTextTestCase(TestCase):
    """Stress the bounded-concat behaviour without DB churn."""

    user: UserModel
    label: AnnotationLabel
    document: Document
    src: Annotation
    t1: Annotation
    t2: Annotation
    rel: Relationship

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = User.objects.create_user(username="synth-user", password="pw")
        cls.label = AnnotationLabel.objects.create(text="Structural", creator=cls.user)
        cls.document = Document.objects.create(title="Synth", creator=cls.user)
        cls.src = Annotation.objects.create(
            document=cls.document,
            annotation_label=cls.label,
            raw_text="HEAD",
            structural=True,
            creator=cls.user,
        )
        cls.t1 = Annotation.objects.create(
            document=cls.document,
            annotation_label=cls.label,
            raw_text="T1",
            structural=True,
            creator=cls.user,
        )
        cls.t2 = Annotation.objects.create(
            document=cls.document,
            annotation_label=cls.label,
            raw_text="T2",
            structural=True,
            creator=cls.user,
        )
        rel_label = AnnotationLabel.objects.create(
            text=OC_SUBTREE_GROUP_LABEL_NAME, creator=cls.user
        )
        cls.rel = Relationship.objects.create(
            relationship_label=rel_label,
            document=cls.document,
            creator=cls.user,
            structural=True,
        )
        cls.rel.source_annotations.add(cls.src)
        cls.rel.target_annotations.add(cls.t1, cls.t2)

    def test_synthesize_joins_source_and_targets_in_id_order(self) -> None:
        text = synthesize_relationship_block_text(self.rel)
        self.assertEqual(text, "HEAD\nT1\nT2")

    def test_synthesize_truncates_at_cap(self) -> None:
        # Bloat HEAD so source alone exceeds the cap. Mutate a refetched
        # row so the shared in-memory ``cls.src`` isn't dirtied — the
        # TestCase transaction rolls the DB change back at teardown.
        src = Annotation.objects.get(pk=self.src.pk)
        src.raw_text = "x" * (SUBTREE_GROUP_BLOCK_TEXT_MAX_CHARS + 50)
        src.save(update_fields=["raw_text"])
        text = synthesize_relationship_block_text(self.rel)
        self.assertLessEqual(len(text), SUBTREE_GROUP_BLOCK_TEXT_MAX_CHARS)

    def test_synthesize_skips_empty_components(self) -> None:
        # Empty raw_text on T1 should be dropped (no blank line).
        # Mutate a refetched row so ``cls.t1`` isn't dirtied.
        t1 = Annotation.objects.get(pk=self.t1.pk)
        t1.raw_text = ""
        t1.save(update_fields=["raw_text"])
        text = synthesize_relationship_block_text(self.rel)
        self.assertEqual(text, "HEAD\nT2")
