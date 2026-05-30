"""Serializers for the multipart document import REST endpoints."""

from __future__ import annotations

from rest_framework import serializers

from opencontractserver.document_imports.models import ChunkedUploadKind


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


class ChunkedUploadStartSerializer(serializers.Serializer):
    """
    Validates the ``start`` step of a chunked upload.

    ``metadata`` carries the same parameters the non-chunked endpoints
    take as form fields (title, description, target corpus id, ...); its
    required shape depends on ``kind`` and is validated in the service
    layer so the per-kind rules live next to the import logic.
    """

    kind = serializers.ChoiceField(choices=ChunkedUploadKind.choices)
    filename = serializers.CharField(max_length=512)
    total_size = serializers.IntegerField(min_value=1)
    chunk_size = serializers.IntegerField(min_value=1)
    total_chunks = serializers.IntegerField(min_value=1)
    metadata = serializers.JSONField(required=False, default=dict)


class ChunkedUploadPartSerializer(serializers.Serializer):
    """Validates a single uploaded part (the part index comes from the URL)."""

    file = serializers.FileField(required=True)
