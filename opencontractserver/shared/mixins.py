import logging
from typing import Any, Optional

from pgvector.django import CosineDistance

from opencontractserver.constants.search import (
    DIM_TO_FIELD_MAP,
    HNSW_MAX_INDEXED_DIM,
)

_logger = logging.getLogger(__name__)


class VectorSearchViaEmbeddingMixin:
    """
    A mixin to enable vector similarity searches on a model that does NOT
    itself hold the embedding columns, but instead has a *reverse* relationship
    to an Embedding model.
    Specifically, we assume the model's related name is "embeddings", pointing
    from Embedding -> e.g. document/annotation/note.

    In usage:
      class DocumentQuerySet(QuerySet, VectorSearchViaEmbeddingMixin):
          EMBEDDING_RELATED_NAME = "embeddings"

      Then you can call:
          Document.objects.search_by_embedding([...], "some-embedder", top_k=10)
    """

    # If your reverse relationship is not named "embeddings", override below in your subclass
    EMBEDDING_RELATED_NAME: str = "embedding_set"

    def _dimension_to_field(self, dimension: int) -> str:
        """
        Given the dimension of the query vector, return the appropriate field
        on the Embedding model (vector_384, vector_768, etc.).
        """
        field_name = DIM_TO_FIELD_MAP.get(dimension)
        if not field_name:
            raise ValueError(f"Unsupported embedding dimension: {dimension}")
        return f"{self.EMBEDDING_RELATED_NAME}__{field_name}"

    def search_by_embedding(
        self,
        query_vector: list[float],
        embedder_path: str,
        top_k: int = 10,
    ) -> list[Any]:
        """
        Vector search for records of this model by embeddings stored in
        a reverse relation to Embedding (embedding->document, for instance).

        - dimension is inferred from len(query_vector)
        - filters on embedder_path
        - excludes cases where the chosen vector field is null
        - adds an annotation '_cosine_distance' via CosineDistance
        - PostgreSQL handles ORDER BY + LIMIT using HNSW index (O(log n))
        - converts distance to similarity_score

        With HNSW indexes on the Embedding vector columns, PostgreSQL uses
        approximate nearest neighbor search instead of sequential scan.
        With pgvector 0.8+ iterative scans (set via init.sql), the
        embedder_path WHERE filter is handled efficiently without
        result loss.

        The unique constraint per (embedder_path, parent) from migration 0059
        guarantees at most one Embedding per parent object per embedder, so
        no DISTINCT ON deduplication is needed.

        Returns a **list** (not a QuerySet) of model instances annotated
        with 'similarity_score'. Do not chain QuerySet methods on the result.
        """
        dimension = len(query_vector)
        if dimension > HNSW_MAX_INDEXED_DIM:
            _logger.warning(
                "Embedding dimension %d exceeds highest HNSW-indexed dim (%d); "
                "query will use sequential scan instead of HNSW index.",
                dimension,
                HNSW_MAX_INDEXED_DIM,
            )
        vector_field = self._dimension_to_field(dimension)

        # JOIN to Embedding rows matching the embedder and non-null vector.
        # ``self.filter`` is provided by the QuerySet that this mixin is
        # combined with at the concrete subclass level.
        base_qs = self.filter(  # type: ignore[attr-defined]
            **{
                f"{self.EMBEDDING_RELATED_NAME}__embedder_path": embedder_path,
                f"{vector_field}__isnull": False,
            }
        )

        # Annotate with cosine distance and let PostgreSQL handle ORDER BY + LIMIT.
        # With HNSW indexes this is O(log n) instead of O(n) sequential scan.
        # CosineDistance returns 0 (identical) to 2 (opposite).
        base_qs = base_qs.annotate(
            _cosine_distance=CosineDistance(vector_field, query_vector)
        )

        # Let PostgreSQL sort and limit — HNSW index drives the scan.
        # Only top_k rows are materialized into Python, not the full table.
        results = list(base_qs.order_by("_cosine_distance")[:top_k])

        # Convert distance to similarity score for each result
        # similarity = 1 - distance (clamped to 0-1 range)
        for obj in results:
            distance = getattr(obj, "_cosine_distance", 0)
            obj.similarity_score = max(0.0, min(1.0, 1.0 - distance))

        return results


class HasEmbeddingMixin:
    """
    Mixin that provides helper methods for creating/updating embeddings on any model
    that references Embedding via (document_id, annotation_id, or note_id).

    The only requirement is that the model must implement:
        def get_embedding_reference_kwargs(self) -> dict[str, Any]

    Example usage for a subclass:
        class Document(BaseOCModel, HasEmbeddingMixin):
            def get_embedding_reference_kwargs(self) -> dict[str, Any]:
                return {"document_id": self.pk}
    """

    def get_embedding_reference_kwargs(self) -> dict[str, Any]:
        """
        Must be overridden by the subclass.
        Return a dictionary like {"document_id": self.pk} or {"annotation_id": self.pk}, etc.
        """
        raise NotImplementedError(
            "Subclass must implement get_embedding_reference_kwargs()"
        )

    def get_embedding(self, embedder_path: str, dimension: int) -> list[float] | None:
        """
        Retrieve the embedding vector for this object with the specified embedder and dimension.

        Args:
            embedder_path (str): Identifier of the embedding model ("openai/ada" etc.)
            dimension (int): Vector dimension (384, 768, 1536, or 3072)

        Returns:
            List[float] | None: The embedding vector or None if not found
        """
        # Late import to avoid circular import (Embedding defined in annotations.models
        # which itself uses this mixin)
        from opencontractserver.annotations.models import Embedding

        vector_field = DIM_TO_FIELD_MAP.get(dimension)
        if not vector_field:
            raise ValueError(f"Unsupported embedding dimension: {dimension}")

        kwargs = self.get_embedding_reference_kwargs()  # e.g. {"document_id": self.pk}

        try:
            embedding = Embedding.objects.get(embedder_path=embedder_path, **kwargs)
            vector = getattr(embedding, vector_field, None)
            return vector if vector is not None else None
        except Embedding.DoesNotExist:
            return None

    async def aget_embedding(
        self, embedder_path: str, dimension: int
    ) -> list[float] | None:
        """
        Async version of get_embedding() - retrieve the embedding vector for this object
        with the specified embedder and dimension.

        Args:
            embedder_path (str): Identifier of the embedding model ("openai/ada" etc.)
            dimension (int): Vector dimension (384, 768, 1536, or 3072)

        Returns:
            List[float] | None: The embedding vector or None if not found
        """
        from channels.db import database_sync_to_async

        return await database_sync_to_async(self.get_embedding)(
            embedder_path, dimension
        )

    def add_embedding(
        self, embedder_path: str, vector: list[float] | None
    ) -> Optional[Any]:
        """
        Creates or updates an Embedding for this object (Document, Annotation, Note, etc.)
        with the given embedder and vector.

        Args:
            embedder_path (str): Identifier of the embedding model ("openai/ada" etc.)
            vector (List[float]): Embedding values as a list of floats, e.g., dimension=384

        Returns:
            Embedding: The created or updated Embedding instance
        """
        # Late import to avoid circular import at the module level
        from opencontractserver.annotations.models import Embedding

        if vector is None:
            return None

        dimension = len(vector)
        kwargs = (
            self.get_embedding_reference_kwargs()
        )  # e.g. {"document_id": self.pk} for Documents
        return Embedding.objects.store_embedding(
            creator=self.creator,  # type: ignore[attr-defined]
            dimension=dimension,
            vector=vector,
            embedder_path=embedder_path,
            **kwargs,
        )

    def add_embeddings(
        self, embedder_path: str, vectors: list[list[float]]
    ) -> list[Any]:
        """
        Creates or updates multiple Embedding records for this object, given a collection of
        vectors (all presumably from the same embedder).

        Args:
            embedder_path (str): Name/identifier for the embedding model used.
            vectors (List[List[float]]): A list of lists of floats, each representing one embedding.

        Returns:
            List[Embedding]: A list of created/updated Embedding objects.
        """
        from opencontractserver.annotations.models import Embedding

        embedding_objects = []
        for vec in vectors:
            dimension = len(vec)
            kwargs = self.get_embedding_reference_kwargs()
            emb = Embedding.objects.store_embedding(
                creator=self.creator,  # type: ignore[attr-defined]
                dimension=dimension,
                vector=vec,
                embedder_path=embedder_path,
                **kwargs,
            )
            embedding_objects.append(emb)
        return embedding_objects
