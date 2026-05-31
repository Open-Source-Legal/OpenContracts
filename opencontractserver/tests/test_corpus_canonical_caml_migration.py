"""Post-migration invariants for the Canonical-CAML description refactor.

Originally this module exercised migration 0052's ``backfill_all`` by
staging legacy ``Corpus.md_description`` files and
``CorpusDescriptionRevision`` rows through the live ORM and then
invoking the backfill against the live model registry. Migration 0053
removes both the FileField and the revision model, so the staging path
is no longer expressible against the post-0053 schema — the
``CanonicalCamlBackfillMigrationTest`` class has been retired.

What survives here is the structural verification that the legacy
storage is gone and that the new canonical write path (Document signal
handler refreshing ``Corpus.description_preview``) is the only thing
populating the cache columns. End-to-end backfill behavior is covered
by ``test_corpus_export_import_v2`` and ``test_v2_import_back_compat``
which round-trip V2 archives through the synthesized Readme.CAML
Document path (Task 14 + signal handler from Task 3).

Spec: docs/superpowers/specs/2026-05-27-canonical-caml-description-refactor-design.md §4.9
"""

from __future__ import annotations

import types
from importlib import import_module
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import SimpleTestCase, TestCase

from opencontractserver.corpuses.models import Corpus

# The backfill migration module name starts with a digit, so it cannot be a
# normal ``import``; ``import_module`` with the dotted string works.
_BACKFILL_MIGRATION = import_module(
    "opencontractserver.corpuses.migrations.0054_canonical_caml_backfill"
)


class _BytesOrStrBackedField:
    """Minimal stand-in for a ``FieldFile`` whose text-mode read returns the
    configured payload.

    Cloud storage backends (S3Boto3Storage / GoogleCloudStorage via
    django-storages #382) return ``bytes`` from a ``"r"``-mode read without
    raising; local ``FileSystemStorage`` returns ``str``. This fake lets the
    suite exercise both on machines that only have local storage.
    """

    def __init__(self, payload, name: str = "Readme.CAML.md"):
        self._payload = payload
        self.name = name

    def __bool__(self) -> bool:
        return True

    def open(self, mode: str = "r"):
        return self

    def read(self):
        return self._payload

    def close(self) -> None:
        pass


class CanonicalCamlBackfillBytesReadTest(SimpleTestCase):
    """Regression for the production ``migrate`` crash at 0054.

    On cloud storage the backfill's readers received ``bytes`` (text mode is
    silently ignored, no exception, so the ``except``-guarded binary fallback
    never fired). The ``bytes`` then reached ``body.encode("utf-8")`` in
    ``_create_caml_doc`` →
    ``AttributeError: 'bytes' object has no attribute 'encode'``. The readers
    must normalise to ``str``.
    """

    def test_coerce_to_text_decodes_bytes(self):
        self.assertEqual(_BACKFILL_MIGRATION._coerce_to_text(b"caf\xc3\xa9"), "café")

    def test_coerce_to_text_passes_str_through(self):
        self.assertEqual(_BACKFILL_MIGRATION._coerce_to_text("café"), "café")

    def test_read_md_description_normalises_bytes_to_str(self):
        corpus = types.SimpleNamespace(
            md_description=_BytesOrStrBackedField("café ✓".encode())
        )
        body = _BACKFILL_MIGRATION._read_md_description(corpus)
        self.assertIsInstance(body, str)
        self.assertEqual(body, "café ✓")
        # The exact downstream operation that crashed in production.
        body.encode("utf-8")

    def test_read_md_description_str_backend_unaffected(self):
        corpus = types.SimpleNamespace(
            md_description=_BytesOrStrBackedField("plain body")
        )
        self.assertEqual(_BACKFILL_MIGRATION._read_md_description(corpus), "plain body")

    def test_read_caml_doc_body_normalises_bytes_to_str(self):
        doc = types.SimpleNamespace(
            txt_extract_file=_BytesOrStrBackedField(b"# Readme")
        )
        body = _BACKFILL_MIGRATION._read_caml_doc_body(doc)
        self.assertIsInstance(body, str)
        self.assertEqual(body, "# Readme")


class ReadCamlBodyBytesTest(TestCase):
    """``read_caml_body`` must decode bytes from cloud storage to ``str``.

    Same django-storages #382 root cause as the backfill crash: the live
    cache-refresh signal handler and GraphQL ``descriptionRevisions`` facade
    both read CAML bodies through this helper, and a ``bytes`` leak there
    breaks ``markdown_to_plain_text`` (``re`` on a bytes-like object).
    """

    def test_read_caml_body_decodes_bytes_from_storage(self):
        from opencontractserver.corpuses.services.description_cache import (
            read_caml_body,
        )
        from opencontractserver.documents.models import Document

        User = get_user_model()
        user = User.objects.create_user(username="caml-bytes", password="x")
        doc = Document.objects.create(
            title="Readme.CAML", file_type="text/markdown", creator=user
        )
        doc.txt_extract_file.save(
            "Readme.CAML.md", ContentFile(b"placeholder"), save=True
        )

        payload = "# Heading café ✓"
        raw = payload.encode()
        # Patch ``open`` on the FieldFile *class* (resolved on the class, not
        # the instance ``__dict__``) to mimic a cloud backend yielding bytes.
        with patch.object(type(doc.txt_extract_file), "open") as mock_open:
            mock_open.return_value.__enter__ = lambda s: BytesIO(raw)
            mock_open.return_value.__exit__ = lambda s, *a: None
            body = read_caml_body(doc)

        self.assertIsInstance(body, str)
        self.assertEqual(body, payload)


class LegacyStorageDroppedTest(TestCase):
    """After migration 0053, the legacy field / model class are gone."""

    def test_corpus_has_no_md_description_attr(self):
        self.assertFalse(
            hasattr(Corpus, "md_description"),
            "Corpus.md_description still exists — migration 0053 didn't run?",
        )

    def test_no_corpus_description_revision_model(self):
        from django.apps import apps

        with self.assertRaises(LookupError):
            apps.get_model("corpuses", "CorpusDescriptionRevision")

    def test_description_preview_save_override_no_longer_present(self):
        """Confirms the Corpus.save() override branch is gone — cache writes
        only flow through the Document signal handler now."""
        from opencontractserver.corpuses.services.corpus_service import (
            CorpusService,
        )

        User = get_user_model()
        u = User.objects.create_user(username="legacy-drop", password="x")
        corpus = Corpus.objects.create(title="C", creator=u)
        with self.captureOnCommitCallbacks(execute=True):
            CorpusService.update_description(u, corpus, "Body via CAML.")
        corpus.refresh_from_db()
        self.assertEqual(corpus.description_preview, "Body via CAML.")
