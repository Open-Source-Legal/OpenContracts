"""Serializers for the multipart document import REST endpoints."""

from __future__ import annotations

from rest_framework import serializers


class DocumentImportSerializer(serializers.Serializer):
    """
    Validates a single-document multipart/form-data import.

    The ``file`` field is the binary document payload; all other fields
    are textual metadata. Empty strings are coerced to None / defaults
    on the view side so the frontend can submit ``FormData`` without
    juggling optional-field omission semantics.
    """

    file = serializers.FileField(required=True)
    filename = serializers.CharField(required=False, allow_blank=True, max_length=512)
    title = serializers.CharField(required=True, max_length=512)
    description = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )
    slug = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=255
    )
    add_to_corpus_id = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )
    add_to_folder_id = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )
    make_public = serializers.BooleanField(required=False, default=False)
    custom_meta = serializers.JSONField(required=False, default=dict)


class DocumentsZipImportSerializer(serializers.Serializer):
    """Validates a bulk zip import (one ``.zip`` file + a few flags)."""

    file = serializers.FileField(required=True)
    title_prefix = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=255
    )
    description = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )
    add_to_corpus_id = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )
    make_public = serializers.BooleanField(required=False, default=False)
    custom_meta = serializers.JSONField(required=False, default=dict)
