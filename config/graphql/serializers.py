from typing import Any

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import URLValidator
from drf_extra_fields.fields import Base64ImageField
from rest_framework import serializers

from opencontractserver.annotations.models import Annotation, AnnotationLabel, LabelSet
from opencontractserver.corpuses.models import Corpus, CorpusCategory
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
    categories = serializers.PrimaryKeyRelatedField(
        many=True, required=False, queryset=CorpusCategory.objects.all()
    )

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
            "created_with_embedder",
            "corpus_agent_instructions",
            "document_agent_instructions",
            "categories",
            "license",
            "license_link",
        ]
        # NOTE: is_public is read-only - use SetCorpusVisibility mutation to change it
        # This prevents bypassing permission checks via serializer updates.
        # created_with_embedder is set automatically at creation and never changes.
        read_only_fields = ["id", "is_public", "created_with_embedder"]

    def validate(self, attrs) -> Any:
        attrs = super().validate(attrs)

        # Resolve effective values for partial updates by merging with instance.
        license_val = attrs.get(
            "license", getattr(self.instance, "license", "") if self.instance else ""
        )
        license_link = attrs.get(
            "license_link",
            getattr(self.instance, "license_link", "") if self.instance else "",
        )

        # Validate license against the allowlist.
        # Django choices on CharField are not enforced at the DB level,
        # and DRFMutation does not call model.full_clean(), so this
        # serializer is the only active enforcement point for API mutations.
        from opencontractserver.constants.licenses import LICENSE_CHOICES

        valid_license_values = {choice[0] for choice in LICENSE_CHOICES}
        if license_val and license_val not in valid_license_values:
            raise serializers.ValidationError({"license": "Invalid license value."})

        # CUSTOM license requires a license_link URL.
        if license_val == "CUSTOM" and not license_link:
            raise serializers.ValidationError(
                {"license_link": "A URL is required when using a custom license."}
            )

        # Clear stale license_link when switching away from CUSTOM.
        if license_val != "CUSTOM" and "license" in attrs:
            attrs["license_link"] = ""

        # Reject license_link when the effective license is not CUSTOM.
        # Prevents orphaned URLs from being stored alongside standard licenses.
        if license_val != "CUSTOM" and attrs.get("license_link"):
            raise serializers.ValidationError(
                {"license_link": "license_link can only be set when license is CUSTOM."}
            )

        # Validate URL scheme on any license_link being written.
        final_link = attrs.get("license_link")
        if final_link:
            validator = URLValidator(schemes=["http", "https"])
            try:
                validator(final_link)
            except DjangoValidationError:
                raise serializers.ValidationError(
                    {"license_link": "Only http and https URLs are allowed."}
                )

        return attrs


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
            "profile_headline",
            "profile_about_markdown",
            "profile_links_markdown",
        ]
        read_only_fields: list[str] = []


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
            "long_description",
            "annotation_json",
            "annotation_label",
            "is_public",
            "creator",
            "creator_id",
            "parent",
            "parent_id",
            "link_url",
        ]
        read_only_fields = ["id", "creator", "parent"]

    def validate_link_url(self, value: str | None) -> str | None:
        """Normalise empty strings to None and reject unsafe schemes.

        The frontend sends `link_url=""` to clear an existing URL; convert
        that to None so the column ends up NULL.  All non-empty values flow
        through ``Annotation.validate_link_url`` to block ``javascript:``
        and other dangerous schemes before reaching persistence.
        """
        from opencontractserver.annotations.models import validate_link_url as _validate

        if not value:
            return None
        _validate(value)
        return value

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

    def to_representation(self, instance) -> Any:
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
