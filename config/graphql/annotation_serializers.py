"""
Serializers related to annotations to avoid circular imports.
"""

from django.contrib.auth import get_user_model
from rest_framework import serializers

from opencontractserver.annotations.models import AnnotationLabel

User = get_user_model()


# Placed here (not in serializers.py) to avoid a circular import between
# the annotations app and the graphql config module.
class AnnotationLabelSerializer(serializers.ModelSerializer):
    creator_id = serializers.IntegerField(write_only=True)
    description = serializers.CharField(allow_blank=True, default="")

    class Meta:
        model = AnnotationLabel
        fields = [
            "id",
            "creator",
            "label_type",
            "color",
            "description",
            "icon",
            "text",
            "creator_id",
            "read_only",
        ]
        read_only_fields = ["id", "creator"]

    def create(self, validated_data):
        creator_id = validated_data.pop("creator_id", None)
        if creator_id:
            try:
                validated_data["creator"] = get_user_model().objects.get(pk=creator_id)
            except get_user_model().DoesNotExist:
                raise serializers.ValidationError({"creator_id": "Invalid creator ID"})
        return super().create(validated_data)
