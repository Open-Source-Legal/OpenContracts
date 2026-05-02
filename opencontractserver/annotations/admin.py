from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib import admin
from django.db.models import Count, QuerySet
from guardian.admin import GuardedModelAdmin

from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
    Embedding,
    LabelSet,
    Note,
    Relationship,
)

if TYPE_CHECKING:
    from django.http import HttpRequest


class ContentModalityFilter(admin.SimpleListFilter):
    """
    Custom filter for content_modalities ArrayField.
    Allows filtering annotations by TEXT, IMAGE, or both modalities.
    """

    title = "content modality"
    parameter_name = "modality"

    def lookups(
        self,
        request: HttpRequest,
        model_admin: admin.ModelAdmin[Any],
    ) -> tuple[tuple[str, str], ...]:
        return (
            ("text", "TEXT only"),
            ("image", "IMAGE only"),
            ("text_and_image", "TEXT and IMAGE"),
            ("has_image", "Has IMAGE"),
            ("has_text", "Has TEXT"),
            ("empty", "No modalities"),
        )

    def queryset(
        self,
        request: HttpRequest,
        queryset: QuerySet[Annotation],
    ) -> QuerySet[Annotation]:
        if self.value() == "text":
            return queryset.filter(content_modalities=["TEXT"])
        if self.value() == "image":
            return queryset.filter(content_modalities=["IMAGE"])
        if self.value() == "text_and_image":
            # Match arrays containing both (order may vary)
            return queryset.filter(content_modalities__contains=["TEXT"]).filter(
                content_modalities__contains=["IMAGE"]
            )
        if self.value() == "has_image":
            return queryset.filter(content_modalities__contains=["IMAGE"])
        if self.value() == "has_text":
            return queryset.filter(content_modalities__contains=["TEXT"])
        if self.value() == "empty":
            return queryset.filter(content_modalities=[])
        return queryset


class AnnotationEmbeddingInline(admin.TabularInline):
    """
    Inline admin for displaying embeddings associated with an annotation.
    """

    model = Embedding
    fk_name = "annotation"
    fields = ("id", "embedder_path", "dimension", "created", "modified")
    readonly_fields = ("id", "embedder_path", "dimension", "created", "modified")
    extra = 0

    def dimension(self, obj: Embedding) -> str:
        """Display which vector dimension is populated."""
        if obj.vector_384 is not None:
            return "384"
        elif obj.vector_768 is not None:
            return "768"
        elif obj.vector_1536 is not None:
            return "1536"
        elif obj.vector_3072 is not None:
            return "3072"
        return "Unknown"

    dimension.short_description = "Dimension"  # type: ignore[attr-defined]


class NoteEmbeddingInline(admin.TabularInline):
    """
    Inline admin for displaying embeddings associated with a note.
    """

    model = Embedding
    fk_name = "note"
    fields = ("id", "embedder_path", "dimension", "created", "modified")
    readonly_fields = ("id", "embedder_path", "dimension", "created", "modified")
    extra = 0

    def dimension(self, obj: Embedding) -> str:
        """Display which vector dimension is populated."""
        if obj.vector_384 is not None:
            return "384"
        elif obj.vector_768 is not None:
            return "768"
        elif obj.vector_1536 is not None:
            return "1536"
        elif obj.vector_3072 is not None:
            return "3072"
        return "Unknown"

    dimension.short_description = "Dimension"  # type: ignore[attr-defined]


@admin.register(Annotation)
class AnnotationAdmin(GuardedModelAdmin):
    list_display = [
        "id",
        "page",
        "raw_text",
        "annotation_label",
        "modality_display",
        "total_embeddings",
    ]
    search_fields = ["id", "raw_text", "annotation_label__text", "document__title"]
    list_filter = (
        ContentModalityFilter,
        "analysis",
        "page",
        "structural",
        "created",
        "modified",
        "is_public",
    )
    raw_id_fields = ("annotation_label", "document", "corpus", "analysis", "creator")
    inlines = [AnnotationEmbeddingInline]

    def get_queryset(self, request: HttpRequest) -> QuerySet[Any]:
        """
        Override queryset to annotate with embedding count.
        """
        qs = super().get_queryset(request)
        return qs.annotate(total_embeddings=Count("embedding_set", distinct=True))

    def total_embeddings(self, obj: Annotation) -> int:
        """
        Display the total number of embeddings for this annotation.
        """
        return obj.total_embeddings  # type: ignore[attr-defined]

    total_embeddings.admin_order_field = "total_embeddings"  # type: ignore[attr-defined]
    total_embeddings.short_description = "Embeddings"  # type: ignore[attr-defined]

    def modality_display(self, obj: Annotation) -> str:
        """
        Display content modalities as a formatted string.
        """
        if obj.content_modalities:
            return ", ".join(obj.content_modalities)
        return "-"

    modality_display.short_description = "Modality"  # type: ignore[attr-defined]


@admin.register(Relationship)
class RelationshipAdmin(GuardedModelAdmin):
    list_display = ["id", "relationship_label"]
    raw_id_fields = (
        "relationship_label",
        "corpus",
        "document",
        "source_annotations",
        "target_annotations",
        "analyzer",
        "creator",
    )


@admin.register(AnnotationLabel)
class AnnotationLabelAdmin(GuardedModelAdmin):
    list_display = ["id", "color", "icon", "text"]


@admin.register(LabelSet)
class LabelSetAdmin(GuardedModelAdmin):
    list_display = ["id", "title", "description"]


@admin.register(Note)
class NoteAdmin(GuardedModelAdmin):
    """Admin interface for Note model"""

    list_display = [
        "id",
        "title",
        "document",
        "creator",
        "created",
        "modified",
        "total_embeddings",
    ]
    search_fields = ["id", "title", "content", "document__title", "creator__username"]
    list_filter = ("is_public", "created", "modified")
    raw_id_fields = ("parent", "document", "annotation", "creator")
    inlines = [NoteEmbeddingInline]

    def get_queryset(self, request: HttpRequest) -> QuerySet[Any]:
        """
        Override queryset to annotate with embedding count.
        """
        qs = super().get_queryset(request)
        return qs.annotate(total_embeddings=Count("embedding_set", distinct=True))

    def total_embeddings(self, obj: Note) -> int:
        """
        Display the total number of embeddings for this note.
        """
        return obj.total_embeddings  # type: ignore[attr-defined]

    total_embeddings.admin_order_field = "total_embeddings"  # type: ignore[attr-defined]
    total_embeddings.short_description = "Embeddings"  # type: ignore[attr-defined]


@admin.register(Embedding)
class EmbeddingAdmin(GuardedModelAdmin):
    """Admin interface for Embedding model"""

    list_display = [
        "id",
        "embedder_path",
        "dimension_info",
        "reference_type",
        "created",
        "modified",
    ]
    list_filter = ("created", "modified", "embedder_path")
    search_fields = ["embedder_path", "id"]
    raw_id_fields = ("document", "annotation", "note", "creator")

    def reference_type(self, obj: Embedding) -> str:
        """Display what type of object this embedding belongs to."""
        if obj.document_id:
            return f"Document #{obj.document_id}"
        elif obj.annotation_id:
            return f"Annotation #{obj.annotation_id}"
        elif obj.note_id:
            return f"Note #{obj.note_id}"
        return "Unknown"

    reference_type.short_description = "Referenced Object"  # type: ignore[attr-defined]

    def dimension_info(self, obj: Embedding) -> str:
        """Display which vector dimension is populated."""
        dimensions: list[str] = []
        if obj.vector_384 is not None:
            dimensions.append("384")
        if obj.vector_768 is not None:
            dimensions.append("768")
        if obj.vector_1536 is not None:
            dimensions.append("1536")
        if obj.vector_3072 is not None:
            dimensions.append("3072")
        return ", ".join(dimensions) if dimensions else "None"

    dimension_info.short_description = "Dimensions"  # type: ignore[attr-defined]
