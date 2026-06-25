import json
import logging
from typing import Any

from rest_framework import serializers

from opencontractserver.annotations.models import EMBEDDING_DIMENSIONS
from opencontractserver.extracts.services.metadata import MetadataService
from opencontractserver.worker_uploads.models import WorkerDocumentUpload

logger = logging.getLogger(__name__)

_SUPPORTED_DIMS = frozenset(dim for dim, _ in EMBEDDING_DIMENSIONS)
_METADATA_DATA_TYPES = frozenset(MetadataService.METADATA_DATA_TYPES)


class WorkerDocumentUploadSerializer(serializers.Serializer):
    """
    Serializer for the multipart worker document upload endpoint.

    Expects:
    - file: the document file (PDF, etc.)
    - metadata: JSON string containing the WorkerDocumentUploadMetadataType payload
    """

    file = serializers.FileField(required=True)
    metadata = serializers.CharField(required=True)

    def validate_metadata(self, value: str) -> dict[str, Any]:
        try:
            data = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Invalid JSON in metadata.", exc_info=True)
            raise serializers.ValidationError("Invalid JSON in metadata.")

        if not isinstance(data, dict):
            raise serializers.ValidationError("Metadata must be a JSON object.")

        required_fields = ["title", "content", "page_count", "pawls_file_content"]
        missing = [f for f in required_fields if f not in data]
        if missing:
            raise serializers.ValidationError(
                f"Missing required fields in metadata: {missing}"
            )

        if not isinstance(data["pawls_file_content"], list):
            raise serializers.ValidationError(
                "pawls_file_content must be a list of page objects."
            )

        # Validate embeddings structure if present
        embeddings = data.get("embeddings")
        if embeddings:
            if not isinstance(embeddings, dict):
                raise serializers.ValidationError("embeddings must be a JSON object.")
            if "embedder_path" not in embeddings:
                raise serializers.ValidationError(
                    "embeddings.embedder_path is required when providing embeddings."
                )
            doc_emb = embeddings.get("document_embedding")
            if doc_emb is not None:
                _validate_vector(doc_emb, "embeddings.document_embedding")
            annot_embs = embeddings.get("annotation_embeddings")
            if annot_embs is not None:
                if not isinstance(annot_embs, dict):
                    raise serializers.ValidationError(
                        "embeddings.annotation_embeddings must be a dict."
                    )
                for annot_id, vec in annot_embs.items():
                    _validate_vector(
                        vec,
                        f"embeddings.annotation_embeddings[{annot_id}]",
                    )

        # Structured document metadata, if present, must be a JSON object —
        # it is stored verbatim on Document.custom_meta.
        custom_meta = data.get("custom_meta")
        if custom_meta is not None and not isinstance(custom_meta, dict):
            raise serializers.ValidationError("custom_meta must be a JSON object.")

        # Typed corpus metadata (Column/Datacell): a list of entries, each with a
        # column_name + data_type. Value type is validated server-side against the
        # column on ingestion (Datacell.clean).
        md = data.get("metadata")
        if md is not None:
            if not isinstance(md, list):
                raise serializers.ValidationError("metadata must be a list.")
            for i, entry in enumerate(md):
                if not isinstance(entry, dict):
                    raise serializers.ValidationError(
                        f"metadata[{i}] must be a JSON object."
                    )
                if not entry.get("column_name") or not isinstance(
                    entry.get("column_name"), str
                ):
                    raise serializers.ValidationError(
                        f"metadata[{i}].column_name is required (string)."
                    )
                if entry.get("data_type") not in _METADATA_DATA_TYPES:
                    raise serializers.ValidationError(
                        f"metadata[{i}].data_type must be one of "
                        f"{sorted(_METADATA_DATA_TYPES)}."
                    )

        return data


def _validate_vector(vec: Any, field_name: str) -> None:
    """Validate that a vector is a list of numbers with a supported dimension."""
    if not isinstance(vec, list):
        raise serializers.ValidationError(f"{field_name} must be a list of floats.")
    if not all(isinstance(v, (int, float)) for v in vec):
        raise serializers.ValidationError(
            f"{field_name} must contain only numeric values."
        )
    if len(vec) not in _SUPPORTED_DIMS:
        raise serializers.ValidationError(
            f"{field_name} has unsupported dimension {len(vec)}. "
            f"Supported: {sorted(_SUPPORTED_DIMS)}."
        )


class WorkerDocumentUploadStatusSerializer(serializers.ModelSerializer):
    """Read-only serializer for upload status responses."""

    upload_id = serializers.UUIDField(source="id", read_only=True)
    document_id = serializers.IntegerField(
        source="result_document_id", read_only=True, allow_null=True
    )

    class Meta:
        model = WorkerDocumentUpload
        fields = [
            "upload_id",
            "status",
            "corpus",
            "document_id",
            "error_message",
            "created",
            "processing_started",
            "processing_finished",
        ]
        read_only_fields = fields
