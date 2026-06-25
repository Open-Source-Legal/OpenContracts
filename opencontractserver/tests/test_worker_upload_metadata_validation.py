"""Worker-upload metadata validation (no DB).

Two fail-fast surfaces guard the metadata a remote worker ships alongside a
faithful document:

* ``WorkerDocumentUploadSerializer.validate_metadata`` rejects a malformed
  ``custom_meta`` / ``metadata`` block at the API boundary, and
* ``MetadataService.upsert_document_metadata`` rejects an unknown ``data_type``
  before it touches the database.

Both raise before any persistence, so these run as ``SimpleTestCase``.
"""

from __future__ import annotations

import json

from django.test import SimpleTestCase
from rest_framework import serializers as drf_serializers

from opencontractserver.extracts.services.metadata import MetadataService
from opencontractserver.worker_uploads.serializers import (
    WorkerDocumentUploadSerializer,
)

# The four required keys validate_metadata checks before reaching the
# custom_meta / metadata blocks under test.
_BASE = {
    "title": "T",
    "content": "C",
    "page_count": 1,
    "pawls_file_content": [],
}


class ValidateMetadataBlockTests(SimpleTestCase):
    @staticmethod
    def _validate(payload: dict):
        return WorkerDocumentUploadSerializer().validate_metadata(json.dumps(payload))

    def test_valid_payload_returns_parsed_dict(self):
        out = self._validate({**_BASE, "custom_meta": {"k": "v"}})
        self.assertEqual(out["title"], "T")
        self.assertEqual(out["custom_meta"], {"k": "v"})

    def test_custom_meta_must_be_object(self):
        with self.assertRaisesMessage(
            drf_serializers.ValidationError, "custom_meta must be a JSON object"
        ):
            self._validate({**_BASE, "custom_meta": ["not", "an", "object"]})

    def test_metadata_must_be_a_list(self):
        with self.assertRaisesMessage(
            drf_serializers.ValidationError, "metadata must be a list"
        ):
            self._validate({**_BASE, "metadata": "scalar"})

    def test_metadata_entry_must_be_an_object(self):
        with self.assertRaisesMessage(
            drf_serializers.ValidationError, "must be a JSON object"
        ):
            self._validate({**_BASE, "metadata": [123]})

    def test_metadata_entry_requires_column_name(self):
        with self.assertRaisesMessage(
            drf_serializers.ValidationError, "column_name is required"
        ):
            self._validate({**_BASE, "metadata": [{"data_type": "STRING"}]})

    def test_metadata_entry_rejects_unknown_data_type(self):
        with self.assertRaisesMessage(
            drf_serializers.ValidationError, "data_type must be one of"
        ):
            self._validate(
                {**_BASE, "metadata": [{"column_name": "c", "data_type": "BOGUS"}]}
            )


class UpsertDocumentMetadataDataTypeTests(SimpleTestCase):
    def test_unknown_data_type_rejected_before_db_access(self):
        # The data_type guard fires before any corpus/document/fieldset access,
        # so dummy (None) args are sufficient to exercise it.
        with self.assertRaisesMessage(ValueError, "Invalid metadata data_type"):
            MetadataService.upsert_document_metadata(
                corpus=None,
                document=None,
                user=None,
                column_name="c",
                data_type="BOGUS",
                value="x",
            )
