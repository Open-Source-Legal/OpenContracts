"""Relationship-targeted vector store (issue #1645).

Mirrors :class:`CoreAnnotationVectorStore` but searches the polymorphic
``Embedding.relationship`` slot populated by
``calculate_embeddings_for_relationship_batch``. Today it only surfaces
``OC_SUBTREE_GROUP`` rows materialised by ``utils/subtree_groups.py``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from asgiref.sync import sync_to_async
from django.db.models import Q
from pgvector.django import CosineDistance

from opencontractserver.annotations.models import (
    Relationship,
    StructuralAnnotationSet,
)
from opencontractserver.constants.annotations import (
    OC_SUBTREE_GROUP_LABEL_NAME,
)
from opencontractserver.constants.search import (
    DIM_TO_FIELD_MAP,
    HNSW_MAX_INDEXED_DIM,
    VALID_EMBEDDING_DIMS,
)
from opencontractserver.llms.vector_stores.base_vector_store import BaseVectorStore
from opencontractserver.utils.embeddings import join_block_text_parts

_logger = logging.getLogger(__name__)


@dataclass
class RelationshipVectorSearchQuery:
    """Framework-agnostic relationship vector search query."""

    query_text: str | None = None
    query_embedding: list[float] | None = None
    similarity_top_k: int = 50
    # Defaults to ``OC_SUBTREE_GROUP`` because that's the only embedded
    # relationship label today; exposed so a future analyzer-emitted
    # relationship can opt in without a schema change.
    label_texts: list[str] = field(
        default_factory=lambda: [OC_SUBTREE_GROUP_LABEL_NAME]
    )


@dataclass
class RelationshipVectorSearchResult:
    """One hit from :meth:`CoreRelationshipVectorStore.search`."""

    relationship: Relationship
    similarity_score: float = 1.0
    source_annotation_id: int | None = None
    target_annotation_ids: list[int] = field(default_factory=list)
    # Same bounded string the embedder saw, so clients can render a
    # snippet without re-fetching annotations.
    block_text: str = ""
    label_text: str | None = None
    document_id: int | None = None
    corpus_id: int | None = None


class CoreRelationshipVectorStore(BaseVectorStore):
    """Vector search over ``Relationship`` rows via the polymorphic Embedding FK.

    Inherits user resolution, IDOR checks, embedder resolution, and query
    embedding generation from :class:`BaseVectorStore`. Embedding lookup is
    done with a JOIN to ``Embedding`` ranked by cosine distance — same idea
    as ``VectorSearchViaEmbeddingMixin`` but inlined because
    ``RelationshipManager`` isn't a from_queryset(...) shape today.
    """

    # ------------------------------------------------------------------ #
    # Base queryset construction
    # ------------------------------------------------------------------ #
    def _build_visible_relationship_qs(
        self, label_texts: list[str]
    ) -> Any:  # Returns QuerySet[Relationship]
        """Return Relationship qs filtered by visibility, label, and scope.

        Returns ``Relationship.objects.none()`` for any of:
        - User configured but not found.
        - document_id / corpus_id provided but not visible to the user.
        """
        from opencontractserver.documents.models import Document

        user, user_invalid = self._resolve_user_sync()
        if user_invalid or self._check_idor_sync(user):
            return Relationship.objects.none()

        qs = Relationship.objects.visible_to_user(user).filter(
            relationship_label__text__in=label_texts
        )

        # Structural relationships are anchored via StructuralAnnotationSet
        # (document=NULL); non-structural rows carry document/corpus FKs
        # directly. The Q-OR handles both shapes — identical to the
        # corresponding block in CoreAnnotationVectorStore.
        if self.document_id is not None:
            doc_filter = Q(document_id=self.document_id)
            structural_set_id = (
                Document.objects.filter(pk=self.document_id)
                .values_list("structural_annotation_set_id", flat=True)
                .first()
            )
            if structural_set_id is not None:
                doc_filter |= Q(structural=True, structural_set_id=structural_set_id)
            qs = qs.filter(doc_filter)

        # NOTE: both document_id and corpus_id can be set. The two IDOR
        # checks pass independently; we narrow to relationships matching
        # the document AND the corpus by stacking the document filter
        # above with the corpus filter below. If the document isn't in
        # the corpus, the AND collapses to no rows.
        if self.corpus_id is not None:
            from opencontractserver.documents.models import DocumentPath

            # Lazy subqueries — avoid materialising tens of thousands of
            # IDs into Python for the IN clause (same rationale as the
            # annotation store).
            corpus_doc_ids_qs = (
                DocumentPath.objects.filter(
                    corpus_id=self.corpus_id, is_current=True, is_deleted=False
                )
                .values("document_id")
                .distinct()
            )
            visible_corpus_set_ids = (
                StructuralAnnotationSet.objects.filter(documents__in=corpus_doc_ids_qs)
                .values("id")
                .distinct()
            )
            qs = qs.filter(
                Q(corpus_id=self.corpus_id)
                | Q(document_id__in=corpus_doc_ids_qs)
                | Q(
                    structural=True,
                    structural_set_id__in=visible_corpus_set_ids,
                )
            )

        # The OR-filter can multiply rows when a relationship hits
        # multiple branches; distinct() is cheap on the small final set.
        return qs.distinct()

    # ------------------------------------------------------------------ #
    # Search core
    # ------------------------------------------------------------------ #
    def _run_vector_search(
        self,
        visible_qs: Any,
        query_vector: list[float],
        top_k: int,
    ) -> list[tuple[Relationship, float]]:
        """Rank visible relationships by cosine distance."""
        dimension = len(query_vector)
        vector_field_name = DIM_TO_FIELD_MAP.get(dimension)
        if vector_field_name is None:
            _logger.warning(
                "Unsupported embedding dimension for relationship search: %s",
                dimension,
            )
            return []
        if dimension > HNSW_MAX_INDEXED_DIM:
            _logger.warning(
                "Relationship search dim %s exceeds HNSW-indexed max %s; "
                "query falls back to sequential scan",
                dimension,
                HNSW_MAX_INDEXED_DIM,
            )

        # JOIN through the reverse FK (``Relationship.embedding_set``).
        rel_field_path = f"embedding_set__{vector_field_name}"
        # Filter on embedder_path AND non-NULL vector column so a
        # partially-embedded corpus doesn't surface NULL-vector rows at
        # the bottom of the ranking.
        scored_qs = (
            visible_qs.filter(
                embedding_set__embedder_path=self.embedder_path,
                **{f"{rel_field_path}__isnull": False},
            )
            .annotate(_cosine_distance=CosineDistance(rel_field_path, query_vector))
            .order_by("_cosine_distance")
        )
        rows = list(
            scored_qs.select_related("relationship_label").prefetch_related(
                "source_annotations", "target_annotations"
            )[:top_k]
        )
        # Tuple instead of mutating the model — avoids dynamic-attribute
        # leak that previously required ``type: ignore[attr-defined]``.
        return [
            (r, max(0.0, min(1.0, 1.0 - (getattr(r, "_cosine_distance", 0) or 0))))
            for r in rows
        ]

    def _shape_results(
        self, rows: list[tuple[Relationship, float]]
    ) -> list[RelationshipVectorSearchResult]:
        """Convert raw Relationship rows into the result dataclass."""
        results: list[RelationshipVectorSearchResult] = []
        for r, similarity_score in rows:
            # Sort by id so multi-source relationships mirror
            # ``synthesize_relationship_block_text`` exactly (it orders
            # source/target M2Ms by id at the SQL level). Single-source
            # OC_SUBTREE_GROUP rows today are unaffected, but the sort
            # makes the alignment hold for any future multi-source kind.
            sources = sorted(r.source_annotations.all(), key=lambda a: a.id)
            targets = sorted(r.target_annotations.all(), key=lambda a: a.id)
            source_id = sources[0].id if sources else None
            source_ids = [s.id for s in sources]
            target_ids = [t.id for t in targets]
            ann_text = {ann.id: (ann.raw_text or "") for ann in [*sources, *targets]}
            ordered_ids = source_ids + target_ids
            block_text = join_block_text_parts(
                [ann_text.get(aid, "") or "" for aid in ordered_ids]
            )

            # corpus_id is NULL on structural relationships; best-effort
            # fallback to scoping context for breadcrumbs / deep-links
            # (this is a hint, not ground truth — a structural set can be
            # shared across corpora).
            corpus_id: int | None = r.corpus_id
            document_id: int | None = r.document_id
            if corpus_id is None and self.corpus_id is not None:
                corpus_id = int(self.corpus_id)
            if document_id is None and self.document_id is not None:
                document_id = int(self.document_id)

            results.append(
                RelationshipVectorSearchResult(
                    relationship=r,
                    similarity_score=similarity_score,
                    source_annotation_id=source_id,
                    target_annotation_ids=target_ids,
                    block_text=block_text,
                    label_text=(
                        r.relationship_label.text if r.relationship_label else None
                    ),
                    document_id=document_id,
                    corpus_id=corpus_id,
                )
            )
        return results

    def search(
        self, query: RelationshipVectorSearchQuery
    ) -> list[RelationshipVectorSearchResult]:
        """Sync relationship vector search.

        FTS/hybrid is not wired in for relationships — the block text is
        already a synthesis of constituent annotation texts, so a
        separate full-text arm would mostly duplicate the vector arm.
        """
        visible_qs = self._build_visible_relationship_qs(query.label_texts)

        vector = query.query_embedding
        if vector is None and query.query_text is not None:
            vector = self._generate_query_embedding(query.query_text)
        if vector is None or len(vector) not in VALID_EMBEDDING_DIMS:
            _logger.warning(
                "Relationship vector search: no valid query vector; returning empty"
            )
            return []

        rows = self._run_vector_search(visible_qs, vector, query.similarity_top_k)
        return self._shape_results(rows)

    async def async_search(
        self, query: RelationshipVectorSearchQuery
    ) -> list[RelationshipVectorSearchResult]:
        """Async wrapper around :meth:`search`."""
        # One ``sync_to_async`` around the whole pipeline is simpler than
        # threading async through every layer and avoids the
        # SynchronousOnlyOperation traps in CoreAnnotationVectorStore.
        if (
            query.query_embedding is None
            and query.query_text is not None
            and query.query_text.strip()
        ):
            vector = await self._agenerate_query_embedding(query.query_text)
            if vector is None or len(vector) not in VALID_EMBEDDING_DIMS:
                return []
            query = RelationshipVectorSearchQuery(
                query_text=query.query_text,
                query_embedding=vector,
                similarity_top_k=query.similarity_top_k,
                label_texts=list(query.label_texts),
            )
        return await sync_to_async(self.search)(query)
