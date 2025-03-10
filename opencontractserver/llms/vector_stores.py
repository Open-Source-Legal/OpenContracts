from typing import Any, Optional

from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import Q, QuerySet
from llama_index.core.schema import BaseNode, TextNode
from llama_index.core.vector_stores.types import (
    BasePydanticVectorStore,
    MetadataFilters,
    VectorStoreQuery,
    VectorStoreQueryMode,
    VectorStoreQueryResult,
)
from pgvector.django import CosineDistance

from opencontractserver.annotations.models import Annotation
from opencontractserver.utils.permissioning import resolve_user

User = get_user_model()


class DjangoAnnotationVectorStore(BasePydanticVectorStore):
    """Django Annotation Vector Store.

    This vector store uses Django's ORM to store and retrieve embeddings and text data
    from the Annotation model. It allows filtering by AnnotationLabel text.

    Args:
        connection_string (str): The Django database connection string.

    Example:
        >>> from opencontractserver.llms.vector_stores import DjangoAnnotationVectorStore
        >>> vector_store = DjangoAnnotationVectorStore()
    """

    stores_text: bool = True
    flat_metadata: bool = False

    user_id: str | int | None
    user: User | None
    corpus_id: str | int | None
    document_id: str | int | None
    must_have_text: str | None

    def __init__(
        self,
        user_id: str | int | None = None,
        corpus_id: str | int | None = None,
        document_id: str | int | None = None,
        must_have_text: str | None = None,
        hybrid_search: bool = False,
        text_search_config: str = "english",
        embed_dim: int = 1536,
        cache_ok: bool = False,
        perform_setup: bool = True,
        debug: bool = False,
        use_jsonb: bool = False,
    ):

        actual_user = resolve_user(user_id)

        super().__init__(
            user_id=user_id,
            user=actual_user,
            corpus_id=corpus_id,
            document_id=document_id,
            must_have_text=must_have_text,
            hybrid_search=hybrid_search,
            text_search_config=text_search_config,
            embed_dim=embed_dim,
            cache_ok=cache_ok,
            perform_setup=perform_setup,
            debug=debug,
            use_jsonb=use_jsonb,
        )

    async def close(self) -> None:
        return

    @classmethod
    def class_name(cls) -> str:
        return "DjangoAnnotationVectorStore"

    @classmethod
    def from_params(
        cls,
        user_id: str | int | None = None,
        corpus_id: str | int | None = None,
        document_id: str | int | None = None,
        must_have_text: str | None = None,
        hybrid_search: bool = False,
        text_search_config: str = "english",
        embed_dim: int = 1536,
        cache_ok: bool = False,
        perform_setup: bool = True,
        debug: bool = False,
        use_jsonb: bool = False,
    ) -> "DjangoAnnotationVectorStore":
        return cls(
            user_id=user_id,
            corpus_id=corpus_id,
            document_id=document_id,
            must_have_text=must_have_text,
            hybrid_search=hybrid_search,
            text_search_config=text_search_config,
            embed_dim=embed_dim,
            cache_ok=cache_ok,
            perform_setup=perform_setup,
            debug=debug,
            use_jsonb=use_jsonb,
        )

    def _get_annotation_queryset(self) -> QuerySet:
        """
        Get the base Annotation queryset with proper permission filtering.

        This handles structural annotations (which are always visible) and
        user-specific permissions using our consistent permission system.
        """
        from opencontractserver.annotations.models import Annotation

        # Get structural annotations which are always visible
        structural_queryset = Annotation.objects.filter(structural=True).distinct()

        # Get annotations the user can see based on permissions
        if self.user_id:
            # Use the model's permission filtering
            user_visible_queryset = Annotation.objects.visible_to_user(
                self.user
            ).distinct()
            queryset = structural_queryset | user_visible_queryset
        else:
            # For anonymous users, only show public and structural annotations
            queryset = (
                structural_queryset
                | Annotation.objects.filter(is_public=True).distinct()
            )

        # Apply additional filters
        if self.corpus_id is not None:
            queryset = queryset.filter(
                Q(corpus_id=self.corpus_id) | Q(document__corpus=self.corpus_id)
            )
        if self.document_id is not None:
            queryset = queryset.filter(document=self.document_id)
        if self.must_have_text is not None:
            queryset = queryset.filter(raw_text__icontains=self.must_have_text)

        return queryset.distinct()

    def _build_filter_query(self, filters: Optional[MetadataFilters]) -> QuerySet:
        """Build the filter query based on the provided metadata filters."""
        queryset = self._get_annotation_queryset()

        # print(f"_build_filter_query: {queryset.count()}")

        if filters is None:
            return queryset

        for filter_ in filters.filters:
            # print(f"_build_filter_query - filter: {filter_}")
            if filter_.key == "label":
                queryset = queryset.filter(annotation_label__text__iexact=filter_.value)
            else:
                raise ValueError(f"Unsupported filter key: {filter_.key}")

        return queryset

    def _db_rows_to_query_result(
        self, rows: list[Annotation]
    ) -> VectorStoreQueryResult:
        """Convert database rows to a VectorStoreQueryResult."""
        nodes = []
        similarities = []
        ids = []

        for row in rows:
            # print(f"Embedding type: {type(row.embedding)} {row.embedding}")
            # print(f"Row id: {row.id}")
            node = TextNode(
                doc_id=str(row.id),
                text=row.raw_text,
                embedding=row.embedding.tolist()
                if getattr(row, "embedding", None) is not None
                else [],
                extra_info={
                    "page": row.page,
                    "json": row.json,
                    "bounding_box": row.bounding_box,
                    "annotation_id": row.id,
                    "label": row.annotation_label.text
                    if row.annotation_label
                    else None,
                    "label_id": row.annotation_label.id
                    if row.annotation_label
                    else None,
                },
            )
            # print(f"Created node: {node}")
            # print(f"Node ref doc: {node.ref_doc_id}")
            # print(f"Node dir: {dir(node)}")
            nodes.append(node)
            similarities.append(row.similarity)
            ids.append(str(row.id))

        return VectorStoreQueryResult(nodes=nodes, similarities=similarities, ids=ids)

    @property
    def client(self) -> None:
        """Return None since the Django ORM is used instead of a separate client."""
        return None

    def add(self, nodes: list[BaseNode], **add_kwargs: Any) -> list[str]:
        """Don't actually want to add entries via LlamaIndex"""
        return []

    async def async_add(self, nodes: list[BaseNode], **kwargs: Any) -> list[str]:
        """Add nodes asynchronously to the vector store."""
        return self.add(nodes, **kwargs)

    def delete(self, doc_id: str, **delete_kwargs: Any):
        """Don't want this to occur through LlamaIndex."""
        pass

    def query(self, query: VectorStoreQuery, **kwargs: Any) -> VectorStoreQueryResult:
        """Query the vector store."""
        queryset = self._build_filter_query(query.filters)

        if query.mode == VectorStoreQueryMode.HYBRID:
            if query.query_str is None:
                raise ValueError("query_str must be provided for hybrid search.")

            if query.alpha is None:
                alpha = 0.5  # Default alpha value for hybrid search
            else:
                alpha = query.alpha

            queryset = queryset.annotate(
                similarity=alpha * CosineDistance("embeddings", query.query_embedding)
                + (1 - alpha)
                * models.functions.TrigramSimilarity("raw_text", query.query_str)
            ).order_by("-similarity")[: query.hybrid_top_k]

        elif query.mode in [
            VectorStoreQueryMode.SPARSE,
            VectorStoreQueryMode.TEXT_SEARCH,
        ]:
            if query.query_str is None:
                raise ValueError("query_str must be provided for text search.")

            queryset = (
                queryset.filter(raw_text__search=query.query_str)
                .annotate(
                    similarity=models.functions.TrigramSimilarity(
                        "raw_text", query.query_str
                    )
                )
                .order_by("-similarity")[: query.sparse_top_k]
            )

        else:  # Default to vector search
            queryset = (
                queryset.order_by(
                    CosineDistance("embedding", query.query_embedding)
                ).annotate(
                    similarity=CosineDistance("embedding", query.query_embedding)
                )
            )[: query.similarity_top_k]

        rows = list(queryset)
        # print(f"Returned rows: {rows}")

        return self._db_rows_to_query_result(rows)

    async def aquery(
        self, query: VectorStoreQuery, **kwargs: Any
    ) -> VectorStoreQueryResult:
        """Query the vector store asynchronously."""
        return await database_sync_to_async(self.query)(query, **kwargs)
