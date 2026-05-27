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


class ZipToCorpusImportSerializer(serializers.Serializer):
    """
    Validates a bulk zip import that **preserves folder structure** into
    a specific corpus. Distinct from :class:`DocumentsZipImportSerializer`
    in that ``corpus_id`` is required and ``target_folder_id`` may be
    supplied to root the import under an existing folder.
    """

    file = serializers.FileField(required=True)
    corpus_id = serializers.CharField(required=True)
    target_folder_id = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )
    title_prefix = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=255
    )
    description = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )
    # Deliberately relaxed from the legacy GraphQL ImportZipToCorpus
    # contract (which required make_public). The UI always supplies it,
    # and treating omission as "private" is the safer default for API
    # callers who omit it.
    make_public = serializers.BooleanField(required=False, default=False)
    custom_meta = serializers.JSONField(required=False, default=dict)


class CorpusExportImportSerializer(serializers.Serializer):
    """
    Validates an OpenContracts corpus-export zip import. The export ZIP
    produced by ``StartCorpusExport`` is the only supported input —
    permission gating + corpus creation happens in the service layer.
    """

    file = serializers.FileField(required=True)
