"""Relationship-targeted vector store (issue #1645).

Mirrors :class:`CoreAnnotationVectorStore` but searches the polymorphic
``Embedding.relationship`` slot populated by
``calculate_embeddings_for_relationship_batch``. Today this only surfaces
``OC_SUBTREE_GROUP`` rows materialised by
``opencontractserver/utils/subtree_groups.py``; the store is structured so
adding a second relationship label (e.g. an analyzer-emitted cross-doc
link) only requires extending the visibility filter.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
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
from opencontractserver.tasks.embeddings_task import join_block_text_parts
from opencontractserver.utils.embeddings import (
    agenerate_embeddings_from_text,
    generate_embeddings_from_text,
    get_embedder,
)

User = get_user_model()
_logger = logging.getLogger(__name__)


@dataclass
class RelationshipVectorSearchQuery:
    """Framework-agnostic relationship vector search query.

    Mirrors :class:`VectorSearchQuery` so callers that already construct
    one shape can swap in this one with a renamed type only.
    """

    query_text: str | None = None
    query_embedding: list[float] | None = None
    similarity_top_k: int = 50
    # Filter to specific relationship labels. Defaults to
    # ``OC_SUBTREE_GROUP`` because that's the only relationship type
    # the embedding pipeline produces today; the field is exposed so a
    # future analyzer-emitted relationship can opt in without a wider
    # schema change.
    label_texts: list[str] = field(
        default_factory=lambda: [OC_SUBTREE_GROUP_LABEL_NAME]
    )


@dataclass
class RelationshipVectorSearchResult:
    """One hit from :meth:`CoreRelationshipVectorStore.search`.

    ``block_text`` is the same string the embedder saw — bounded by
    ``SUBTREE_GROUP_BLOCK_TEXT_MAX_CHARS`` — so GraphQL clients can
    render a snippet without re-fetching annotations.
    """

    relationship: Relationship
    similarity_score: float = 1.0
    source_annotation_id: int | None = None
    target_annotation_ids: list[int] = field(default_factory=list)
    block_text: str = ""
    label_text: str | None = None
    document_id: int | None = None
    corpus_id: int | None = None


class CoreRelationshipVectorStore:
    """Vector search over ``Relationship`` rows via the polymorphic Embedding FK.

    The store mirrors ``CoreAnnotationVectorStore``'s permissioning model:
    an upfront IDOR check on ``document_id``/``corpus_id`` (deny by
    returning ``[]``), then a queryset built off
    ``Relationship.objects.visible_to_user(user)`` so corpus/document
    permission inheritance is enforced consistently.

    Embedding lookup is done with a JOIN to ``Embedding`` filtered on the
    embedder path and the dim-specific vector column, ranked by cosine
    distance. The same approach as the ``VectorSearchViaEmbeddingMixin``
    used by annotations/documents/notes, but inlined here because
    ``RelationshipManager`` is not built from a queryset class today and
    we don't want to refactor that for this issue.
    """

    def __init__(
        self,
        user_id: str | int | None = None,
        corpus_id: str | int | None = None,
        document_id: str | int | None = None,
        embedder_path: str | None = None,
        embed_dim: int = 768,
    ) -> None:
        if embedder_path is None and corpus_id is None:
            raise ValueError(
                "CoreRelationshipVectorStore requires either 'corpus_id' "
                "to derive an embedder or an explicit 'embedder_path' override."
            )
        self.user_id = user_id
        self.corpus_id = corpus_id
        self.document_id = document_id
        self.embed_dim = embed_dim

        if embedder_path is not None:
            embedder_class, detected_embedder_path = get_embedder(
                embedder_path=embedder_path
            )
        else:
            # The constructor-level guard above rules out
            # ``corpus_id is None`` here.
            embedder_class, detected_embedder_path = get_embedder(
                corpus_id=corpus_id,
            )
        if detected_embedder_path is None:
            raise ValueError(
                "get_embedder() resolved no embedder_path for relationship "
                "search; check corpus.preferred_embedder or the global default."
            )
        self.embedder_path: str = detected_embedder_path

        if self.embed_dim not in VALID_EMBEDDING_DIMS:
            self.embed_dim = getattr(embedder_class, "vector_size", 768)

    # ------------------------------------------------------------------ #
    # Base queryset construction
    # ------------------------------------------------------------------ #
    def _build_visible_relationship_qs(
        self, label_texts: list[str]
    ) -> Any:  # Returns QuerySet[Relationship]
        """Build the visibility-filtered Relationship queryset.

        Returns an empty queryset for any of:
        - User not found (treat as anonymous → no visibility).
        - document_id / corpus_id provided but not visible to the user
          (IDOR prevention; same "empty result" pattern used by
          ``CoreAnnotationVectorStore._build_base_queryset``).
        """
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.documents.models import Document

        user = None
        if self.user_id:
            try:
                user = User.objects.get(id=self.user_id)
            except User.DoesNotExist:
                _logger.warning(f"User ID {self.user_id} not found")
                return Relationship.objects.none()

        # IDOR: deny by empty result on missing-or-denied document/corpus.
        if self.document_id is not None:
            if (
                not Document.objects.visible_to_user(user)
                .filter(id=self.document_id)
                .exists()
            ):
                _logger.warning(
                    "User %s denied access to document %s in relationship "
                    "vector search (not found or no permission)",
                    self.user_id,
                    self.document_id,
                )
                return Relationship.objects.none()

        if self.corpus_id is not None:
            if (
                not Corpus.objects.visible_to_user(user)
                .filter(id=self.corpus_id)
                .exists()
            ):
                _logger.warning(
                    "User %s denied access to corpus %s in relationship "
                    "vector search (not found or no permission)",
                    self.user_id,
                    self.corpus_id,
                )
                return Relationship.objects.none()

        qs = Relationship.objects.visible_to_user(user).filter(
            relationship_label__text__in=label_texts
        )

        # Scope by document / corpus. Structural relationships live on
        # ``structural_set`` with ``document=NULL``; non-structural rows
        # carry ``document``/``corpus`` FKs directly. The Q-OR below
        # handles both shapes uniformly — identical reasoning to the
        # corresponding block in ``CoreAnnotationVectorStore``.
        if self.document_id is not None:
            doc_filter = Q(document_id=self.document_id)
            # Structural relationships are anchored via
            # StructuralAnnotationSet — look up the doc's set so we can
            # include them. Fetching only the FK keeps this a single
            # 1-row SELECT.
            structural_set_id = (
                Document.objects.filter(pk=self.document_id)
                .values_list("structural_annotation_set_id", flat=True)
                .first()
            )
            if structural_set_id is not None:
                doc_filter |= Q(structural=True, structural_set_id=structural_set_id)
            qs = qs.filter(doc_filter)
        elif self.corpus_id is not None:
            # Lazy subqueries — same rationale as the annotation store
            # (avoid materialising tens of thousands of IDs into Python
            # for the IN clause).
            from opencontractserver.documents.models import DocumentPath

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

        # ``visible_to_user`` already deduplicates, but the doc/corpus
        # OR-filter above can multiply rows when a relationship hits
        # multiple branches — distinct() is cheap on the small final set.
        return qs.distinct()

    # ------------------------------------------------------------------ #
    # Embedding generation
    # ------------------------------------------------------------------ #
    def _generate_query_embedding(self, query_text: str) -> list[float] | None:
        embedder_path, vector = generate_embeddings_from_text(
            query_text, embedder_path=self.embedder_path
        )
        if vector is None:
            _logger.warning(
                "Failed to generate query embedding for relationship search "
                "(embedder=%s, query='%s...')",
                embedder_path,
                query_text[:50],
            )
        return vector

    async def _agenerate_query_embedding(self, query_text: str) -> list[float] | None:
        embedder_path, vector = await agenerate_embeddings_from_text(
            query_text, embedder_path=self.embedder_path
        )
        if vector is None:
            _logger.warning(
                "Failed to generate async query embedding for relationship "
                "search (embedder=%s, query='%s...')",
                embedder_path,
                query_text[:50],
            )
        return vector

    # ------------------------------------------------------------------ #
    # Search core
    # ------------------------------------------------------------------ #
    def _run_vector_search(
        self,
        visible_qs: Any,
        query_vector: list[float],
        top_k: int,
    ) -> list[Relationship]:
        """Rank visible relationships by cosine distance.

        Implementation matches ``VectorSearchViaEmbeddingMixin`` but inlined
        so we don't need to refactor RelationshipManager away from
        ``BaseVisibilityManager`` into a from_queryset(...) shape.
        """
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

        # JOIN through the Embedding reverse FK (``embedding_set``).
        # ``related_name`` was set on the FK so ``Relationship.embedding_set``
        # is the M2O reverse manager.
        rel_field_path = f"embedding_set__{vector_field_name}"
        # The filter ensures we only score relationships that actually
        # have an embedding for the requested embedder path AND the
        # requested vector dimension — so a partially-embedded corpus
        # doesn't surface NULL-vector rows ranked at the bottom.
        scored_qs = (
            visible_qs.filter(
                embedding_set__embedder_path=self.embedder_path,
                **{f"{rel_field_path}__isnull": False},
            )
            .annotate(_cosine_distance=CosineDistance(rel_field_path, query_vector))
            .order_by("_cosine_distance")
        )
        # Materialise the top-k slice and convert distance → similarity.
        # ``select_related`` for label (label.text is surfaced in results)
        # plus prefetch for sources/targets — both are tiny per row.
        rows = list(
            scored_qs.select_related("relationship_label").prefetch_related(
                "source_annotations", "target_annotations"
            )[:top_k]
        )
        for r in rows:
            distance = getattr(r, "_cosine_distance", 0) or 0
            r.similarity_score = max(0.0, min(1.0, 1.0 - distance))
        return rows

    def _shape_results(
        self, rows: list[Relationship]
    ) -> list[RelationshipVectorSearchResult]:
        """Convert raw Relationship rows into the result dataclass."""
        results: list[RelationshipVectorSearchResult] = []
        for r in rows:
            sources = list(r.source_annotations.all())
            targets = list(r.target_annotations.all())
            source_id = sources[0].id if sources else None
            target_ids = sorted(t.id for t in targets)
            # Order: source(s) first then targets by id — matches
            # ``synthesize_relationship_block_text`` so the surfaced
            # block_text mirrors what the embedder saw exactly.
            ann_text = {ann.id: (ann.raw_text or "") for ann in [*sources, *targets]}
            ordered_ids = ([source_id] if source_id is not None else []) + target_ids
            block_text = join_block_text_parts(
                [ann_text.get(aid, "") or "" for aid in ordered_ids]
            )

            # ``corpus_id`` may be NULL on structural relationships; we
            # do a best-effort lookup via the structural set so corpus-
            # scoped clients can still associate the hit with a corpus
            # for breadcrumbs / deep-link routing.
            corpus_id: int | None = r.corpus_id
            document_id: int | None = r.document_id
            if corpus_id is None and self.corpus_id is not None:
                corpus_id = int(self.corpus_id)
            if document_id is None and self.document_id is not None:
                document_id = int(self.document_id)

            results.append(
                RelationshipVectorSearchResult(
                    relationship=r,
                    similarity_score=r.similarity_score,  # type: ignore[attr-defined]
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

        Falls back to an empty result list when no vector can be derived
        from the query (consistent with the annotation store's behaviour
        for the same condition). FTS/hybrid is intentionally not wired
        in for relationships today — the block text is already a
        synthesis of constituent annotation texts, so a separate full-
        text arm would mostly duplicate the vector arm.
        """
        # Embedding embeddings are joined on ``Embedding.embedder_path``
        # so the visible-Relationship queryset doesn't need to know
        # which embedder we're searching. ``_build_visible_relationship_qs``
        # already returns ``Relationship.objects.none()`` for every
        # denial branch, so ``_run_vector_search`` will yield an empty
        # list without us needing a separate COUNT.
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
        """Async wrapper around :meth:`search`.

        The hot path is dominated by the cosine-distance SQL — a single
        ``sync_to_async`` around the whole pipeline is simpler than
        threading async through every layer and avoids the
        ``SynchronousOnlyOperation`` traps from
        ``CoreAnnotationVectorStore`` (PipelineSettings, etc.).
        """
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
