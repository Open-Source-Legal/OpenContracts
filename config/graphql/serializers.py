from typing import Any

from django.contrib.auth import get_user_model
from drf_extra_fields.fields import Base64ImageField
from rest_framework import serializers

from opencontractserver.annotations.models import Annotation, AnnotationLabel, LabelSet
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.extracts.models import Column, Extract
from opencontractserver.shared.fields import PDFBase64File

User = get_user_model()


class DocumentSerializer(serializers.ModelSerializer):
    pdf_file = PDFBase64File(required=False)

    class Meta:
        model = Document
        fields = [
            "id",
            "title",
            "description",
            "slug",
            "custom_meta",
            "pdf_file",
        ]
        read_only_fields = ["id"]


class CorpusSerializer(serializers.ModelSerializer):
    icon = Base64ImageField(required=False)

    class Meta:
        model = Corpus
        fields = [
            "id",
            "title",
            "description",
            "is_public",
            "slug",
            "icon",
            "label_set",
            "creator",
            "creator_id",
            "preferred_embedder",
            "corpus_agent_instructions",
            "document_agent_instructions",
        ]
        read_only_fields = ["id"]


class ExtractSerializer(serializers.ModelSerializer):
    class Meta:
        model = Extract
        fields = [
            "id",
            "corpus",
            "name",
            "fieldset",
            "creator",
            "creator_id",
            "created",
            "started",
            "finished",
        ]
        read_only_fields = ["id", "created"]


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "name",
            "first_name",
            "last_name",
            "phone",
            "slug",
            "is_profile_public",  # Issue #611
        ]
        read_only_fields = []


class ColumnSerializer(serializers.ModelSerializer):
    class Meta:
        model = Column
        fields = [
            "id",
            "name",
            "fieldset",
            "fieldset_id",
            "language_model",
            "language_model_id",
            "query",
            "match_text",
            "output_type",
            "limit_to_label",
            "instructions",
            "language_model_id",
            "extract_is_list",
            "must_contain_text",
        ]
        read_only_fields = ["id", "created"]


class LabelsetSerializer(serializers.ModelSerializer):
    icon = Base64ImageField(required=False)

    class Meta:
        model = LabelSet
        fields = ["id", "title", "description", "icon", "creator", "creator_id"]
        read_only_fields = ["id"]


class AnnotationSerializer(serializers.ModelSerializer):
    """
    Serializer for the `Annotation` model. Maps the model's `json` field to `annotation_json`
    in the serialized representation to avoid issues with pydantic handling a field named 'json'.
    """

    annotation_json = serializers.JSONField(source="json")
    tokens_json = serializers.JSONField()

    annotation_label = serializers.PrimaryKeyRelatedField(
        many=False, queryset=AnnotationLabel.objects.all()
    )
    creator_id = serializers.IntegerField(write_only=True)
    parent_id = serializers.IntegerField(
        write_only=True, required=False, allow_null=True
    )

    class Meta:
        model = Annotation
        fields = [
            "id",
            "page",
            "raw_text",
            "tokens_json",
            "bounding_box",
            "annotation_json",
            "annotation_label",
            "is_public",
            "creator",
            "creator_id",
            "parent",
            "parent_id",
        ]
        read_only_fields = ["id", "creator", "parent"]

    def create(self, validated_data: dict) -> Annotation:
        """
        Create a new `Annotation` instance, mapping `creator_id` and `parent_id` to their respective
        related objects.
        """
        creator_id = validated_data.pop("creator_id", None)
        parent_id = validated_data.pop("parent_id", None)

        if creator_id:
            try:
                validated_data["creator"] = get_user_model().objects.get(pk=creator_id)
            except get_user_model().DoesNotExist:
                raise serializers.ValidationError({"creator_id": "Invalid creator ID"})
        else:
            raise serializers.ValidationError({"creator_id": "This field is required."})

        if parent_id:
            try:
                validated_data["parent"] = Annotation.objects.get(pk=parent_id)
            except Annotation.DoesNotExist:
                raise serializers.ValidationError({"parent_id": "Invalid parent ID"})
        else:
            validated_data["parent"] = None

        return super().create(validated_data)

    def validate_annotation_json(self, value: Any) -> Any:
        """
        Validate the 'annotation_json' field. If the data appears to conform to
        `dict[Union[int, str], OpenContractsSinglePageAnnotationType]`, ensure that
        any `BoundingBoxPythonType` values with floats are converted to ints.
        """
        if isinstance(value, dict):
            # Check if value conforms to OpenContractsSinglePageAnnotationType
            is_single_page_annotation = True
            for key, page_annotation in value.items():
                if (
                    not isinstance(page_annotation, dict)
                    or "bounds" not in page_annotation
                ):
                    is_single_page_annotation = False
                    break

            if is_single_page_annotation:
                # Convert bounds values to integers
                for key, page_annotation in value.items():
                    bounds = page_annotation["bounds"]
                    for coord in ["top", "bottom", "left", "right"]:
                        if coord in bounds and isinstance(bounds[coord], (int, float)):
                            bounds[coord] = int(bounds[coord])

        return value

    def to_representation(self, instance):
        """
        Override to_representation to ensure that bounds values are integers when serializing.
        """
        representation = super().to_representation(instance)
        annotation_json = representation.get("annotation_json")

        if isinstance(annotation_json, dict):
            # Check if annotation_json conforms to OpenContractsSinglePageAnnotationType
            is_single_page_annotation = True
            for key, page_annotation in annotation_json.items():
                if (
                    not isinstance(page_annotation, dict)
                    or "bounds" not in page_annotation
                ):
                    is_single_page_annotation = False
                    break

            if is_single_page_annotation:
                # Convert bounds values to integers
                for key, page_annotation in annotation_json.items():
                    bounds = page_annotation["bounds"]
                    for coord in ["top", "bottom", "left", "right"]:
                        if coord in bounds and isinstance(bounds[coord], (int, float)):
                            bounds[coord] = int(bounds[coord])

        representation["annotation_json"] = annotation_json
        return representation
