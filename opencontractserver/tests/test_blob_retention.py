"""Regression tests for issue #1464 (blob retention across corpus-
isolated Document copies) and issue #1492 (orphan-blob reclaim at
Document delete-time).

Combined invariant: a file blob (pdf_file, txt_extract_file, etc.) is
alive in storage as long as at least one Document references it; once
the LAST referencing row is deleted, the blob is reclaimed from
storage.

#1464 (PR #1487) added the defensive primitives — ``unique_blob_paths``
and ``safe_delete_field_blob`` — that prevent shared-blob destruction.
#1492 wires the offensive half: ``pre_delete``/``post_delete`` signals
on Document capture blob paths and schedule a Celery task on
``transaction.on_commit`` that reclaims them iff still orphaned at
task time.
"""

from __future__ import annotations

import uuid

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from django.test import TransactionTestCase, override_settings

from opencontractserver.agents.memory import (
    get_or_create_memory_document,
    update_memory_content,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath

User = get_user_model()

# Blob-field-name list lives on the model; using the helper here keeps
# the test file in lock-step with whatever new ``FileField``s land on
# Document without an additional edit here.
DOCUMENT_FILE_FIELDS: tuple[str, ...] = Document.blob_field_names()


class UniqueBlobPathsTestCase(TransactionTestCase):
    """Tests for ``Document.objects.unique_blob_paths(doc)``."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="blob-test-user", password="x")
        self.corpus_a = Corpus.objects.create(title="Corpus A", creator=self.user)

        # Use UUID-prefixed filenames so parallel/sequential test runs never
        # collide on the same storage path (local FileSystemStorage does NOT
        # overwrite; it appends a suffix, which would break name assertions).
        uid = uuid.uuid4().hex

        # Create a source document with real file fields. Use small
        # ContentFile payloads so storage stays fast; assertions check
        # blob NAMES (S3 keys), not content.
        self.source = Document.objects.create(
            title="Source Doc", creator=self.user, file_type="application/pdf"
        )
        self.source.pdf_file.save(
            f"src_{uid}.pdf", ContentFile(b"%PDF-1.4 dummy"), save=True
        )
        self.source.txt_extract_file.save(
            f"src_{uid}.txt", ContentFile(b"hello"), save=True
        )
        self.uid = uid

    def test_solitary_document_all_blobs_unique(self) -> None:
        """A document with no copies owns all of its blobs."""
        unique = Document.objects.unique_blob_paths(self.source)

        self.assertIn(self.source.pdf_file.name, unique)
        self.assertIn(self.source.txt_extract_file.name, unique)

    def test_shared_blob_excluded_for_both(self) -> None:
        """When a corpus copy shares the source blob, neither side
        considers that blob unique to itself."""
        copy, _status, _path = self.corpus_a.add_document(
            document=self.source, user=self.user
        )

        # Sanity: copy and source share the same S3 key
        self.assertEqual(copy.pdf_file.name, self.source.pdf_file.name)

        source_unique = Document.objects.unique_blob_paths(self.source)
        copy_unique = Document.objects.unique_blob_paths(copy)

        self.assertNotIn(self.source.pdf_file.name, source_unique)
        self.assertNotIn(copy.pdf_file.name, copy_unique)

    def test_unshared_field_remains_unique(self) -> None:
        """A field that's NOT shared with the copy is still unique to
        the document that owns it (per-field check, not whole-row)."""
        copy, _status, _path = self.corpus_a.add_document(
            document=self.source, user=self.user
        )

        # Replace the copy's txt_extract_file with a fresh blob so it
        # no longer shares with source.
        copy.txt_extract_file.save(
            f"copy_{self.uid}.txt", ContentFile(b"copy content"), save=True
        )
        # add_document() shares the FieldFile object from source, so saving
        # copy's field mutates the shared FieldFile's .name in memory.
        # Refresh source from DB to get the original path back.
        self.source.refresh_from_db()
        self.assertNotEqual(
            copy.txt_extract_file.name, self.source.txt_extract_file.name
        )

        source_unique = Document.objects.unique_blob_paths(self.source)
        # Source's txt_extract_file is no longer shared, so it IS unique
        self.assertIn(self.source.txt_extract_file.name, source_unique)
        # PDF is still shared, so still NOT unique
        self.assertNotIn(self.source.pdf_file.name, source_unique)

    def test_empty_field_not_in_result(self) -> None:
        """File fields with no blob assigned must not appear in the
        result set (would be an empty string otherwise)."""
        # md_summary_file was never set on self.source
        self.assertFalse(self.source.md_summary_file)

        unique = Document.objects.unique_blob_paths(self.source)

        self.assertNotIn("", unique)
        self.assertFalse(any(p == "" for p in unique))


class SafeDeleteFieldBlobTestCase(TransactionTestCase):
    """Tests for ``Document.safe_delete_field_blob(field_name)`` across
    every ``FileField`` on the model.

    This is the primitive that future blob-deletion code (e.g. issue
    #1492's orphan cleanup) must call instead of ``FieldFile.delete()``
    directly. The contract:

    - Empty field → no-op, returns ``False``.
    - Unique blob path → blob removed from storage, field cleared,
      returns ``True``.
    - Shared blob path → blob retained in storage, field cleared on
      this row only, returns ``False``.

    Tests run for every ``FileField`` on Document so adding a new
    file field is automatically covered.
    """

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="safe-del-user", password="x")
        self.corpus = Corpus.objects.create(title="Origin", creator=self.user)
        self.uid = uuid.uuid4().hex

    def _make_doc_with_blobs(self) -> Document:
        """Create a Document with every FileField populated."""
        doc = Document.objects.create(
            title=f"Doc {self.uid}",
            creator=self.user,
            file_type="application/pdf",
        )
        for field_name in DOCUMENT_FILE_FIELDS:
            file_field = getattr(doc, field_name)
            file_field.save(
                f"{field_name}_{self.uid}.bin",
                ContentFile(f"payload-{field_name}".encode()),
                save=True,
            )
        return doc

    def test_unique_blob_is_deleted_from_storage(self) -> None:
        """For each FileField: when only one Document references the
        blob, ``safe_delete_field_blob`` removes it from storage and
        returns True."""
        doc = self._make_doc_with_blobs()

        for field_name in DOCUMENT_FILE_FIELDS:
            with self.subTest(field=field_name):
                blob_name = getattr(doc, field_name).name
                self.assertTrue(default_storage.exists(blob_name))

                freed = doc.safe_delete_field_blob(field_name)

                self.assertTrue(
                    freed,
                    f"{field_name}: expected primitive to free unique blob",
                )
                self.assertFalse(
                    default_storage.exists(blob_name),
                    f"{field_name}: unique blob {blob_name!r} should have "
                    "been removed from storage",
                )
                self.assertFalse(
                    bool(getattr(doc, field_name)),
                    f"{field_name}: field should be cleared after delete",
                )

    def test_shared_blob_is_preserved_for_sibling(self) -> None:
        """For each FileField: when a sibling Document references the
        same blob, ``safe_delete_field_blob`` clears the field on this
        row but leaves the blob alive for the sibling and returns False."""
        source = self._make_doc_with_blobs()
        copy, _status, _path = self.corpus.add_document(document=source, user=self.user)

        # Each iteration clears one field on ``copy`` (via
        # ``safe_delete_field_blob`` below), so the in-memory
        # ``source``/``copy`` instances diverge from the DB as the loop
        # progresses. The ``refresh_from_db()`` calls at the top of the
        # iteration restore both to the canonical row state, ensuring
        # subsequent subTests see only the *current* field's sharing
        # condition (the source row's blob is never touched).
        for field_name in DOCUMENT_FILE_FIELDS:
            with self.subTest(field=field_name):
                source.refresh_from_db()
                copy.refresh_from_db()

                blob_name = getattr(source, field_name).name
                # Sanity: corpus copy shares this field's blob with source.
                self.assertEqual(
                    getattr(copy, field_name).name,
                    blob_name,
                    f"{field_name}: pre-condition — copy should share "
                    "blob with source",
                )

                freed = copy.safe_delete_field_blob(field_name, save=True)

                self.assertFalse(
                    freed,
                    f"{field_name}: expected primitive to retain shared blob",
                )
                self.assertTrue(
                    default_storage.exists(blob_name),
                    f"{field_name}: shared blob {blob_name!r} was destroyed "
                    "while sibling still references it (issue #1464)",
                )

                copy.refresh_from_db()
                self.assertFalse(
                    bool(getattr(copy, field_name)),
                    f"{field_name}: copy field should be cleared",
                )

                # Source is untouched and can still read its content.
                source.refresh_from_db()
                self.assertEqual(getattr(source, field_name).name, blob_name)
                with getattr(source, field_name).open("rb") as fh:
                    self.assertEqual(
                        fh.read(),
                        f"payload-{field_name}".encode(),
                        f"{field_name}: source content was clobbered",
                    )

    def test_empty_field_is_noop(self) -> None:
        """Calling the primitive on an unset field is a no-op and
        returns False (no exception)."""
        doc = Document.objects.create(
            title="Empty Doc", creator=self.user, file_type="application/pdf"
        )
        for field_name in DOCUMENT_FILE_FIELDS:
            with self.subTest(field=field_name):
                self.assertFalse(bool(getattr(doc, field_name)))
                self.assertFalse(doc.safe_delete_field_blob(field_name))

    def test_invalid_field_name_raises(self) -> None:
        """Typos must fail loud, not silently no-op."""
        doc = self._make_doc_with_blobs()
        with self.assertRaises(ValueError):
            doc.safe_delete_field_blob("not_a_field")

    def test_non_file_field_raises(self) -> None:
        """Pointing the primitive at a non-FileField is a programmer
        error and must raise."""
        doc = self._make_doc_with_blobs()
        # ``title`` is a CharField on Document.
        with self.assertRaises(ValueError):
            doc.safe_delete_field_blob("title")


class MemoryDocumentBlobRetentionTestCase(TransactionTestCase):
    """Regression for issue #1464: ``update_memory_content`` must not
    clobber a ``txt_extract_file`` blob that is still referenced by a
    sibling Document (e.g. a corpus-isolated copy of the memory doc).

    With ``FileSystemStorage`` (used in tests), deleting a blob and then
    saving a new file with the same requested name reuses the same path
    on disk. This means the *name* stays the same but the *content* is
    replaced. The regression is therefore detectable via content, not
    via the blob path.

    The guard (issue #1464 fix) changes the write strategy for a shared
    blob: instead of delete-then-save (which clobbers the shared file),
    it clears the field to ``None`` and lets Django's storage generate a
    new unique path for the updated content (because the original file
    still exists on disk). The sibling's field keeps pointing at the old
    path, which now still contains the original content.
    """

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="memory-blob-user", password="x")
        self.corpus_a = Corpus.objects.create(
            title="Memory Source Corpus", creator=self.user
        )
        self.corpus_b = Corpus.objects.create(
            title="Memory Sibling Corpus", creator=self.user
        )

    def test_update_keeps_blob_when_shared_with_sibling(self) -> None:
        """Updating memory in corpus A must not clobber the blob content
        that sibling in corpus B still references.

        Failure mode (before fix): delete-then-save reuses the same storage
        path, overwriting the shared file. The sibling's field still points
        at the path, but now reads back the NEW content instead of its own.

        Fix behaviour: the old blob is preserved (field is cleared to None
        so storage generates a fresh path for the new content). The sibling
        continues to read the original content.
        """
        new_content = "## New section\nFoo bar baz"

        # Create the memory document in corpus A
        memory_doc = async_to_sync(get_or_create_memory_document)(
            self.corpus_a, self.user
        )
        original_blob_name = memory_doc.txt_extract_file.name
        assert original_blob_name is not None
        self.assertTrue(default_storage.exists(original_blob_name))

        # Record the original content so we can verify sibling is unchanged.
        with memory_doc.txt_extract_file.open("rb") as fh:
            original_content = fh.read()

        # Create a corpus-isolated copy in corpus B that shares the same
        # txt_extract_file blob (this is what Corpus.add_document does).
        sibling, _, _ = self.corpus_b.add_document(document=memory_doc, user=self.user)
        self.assertEqual(
            sibling.txt_extract_file.name,
            original_blob_name,
            "Pre-condition: corpus copy must share blob with source",
        )

        # Update memory content on corpus A.  The OLD blob is still
        # referenced by sibling in corpus B and must not be clobbered.
        async_to_sync(update_memory_content)(self.corpus_a, new_content, self.user)

        # Assert: sibling's blob still holds the ORIGINAL content.
        sibling.refresh_from_db()
        self.assertTrue(
            default_storage.exists(sibling.txt_extract_file.name),
            f"Sibling blob {sibling.txt_extract_file.name!r} was deleted",
        )
        with sibling.txt_extract_file.open("rb") as fh:
            sibling_content = fh.read()
        self.assertEqual(
            sibling_content,
            original_content,
            "Sibling blob was clobbered: it now contains the memory-doc's "
            "updated content instead of its own original content",
        )

        # Memory doc A must reflect the new content.
        memory_doc.refresh_from_db()
        with memory_doc.txt_extract_file.open("rb") as fh:
            updated_content = fh.read()
        self.assertEqual(updated_content, new_content.encode("utf-8"))

    def test_update_deletes_blob_when_unshared(self) -> None:
        """When no sibling references the old blob, the update SHOULD
        write the new content to the memory document.

        (Whether the old path is physically deleted and a new path
        allocated, or the same path is reused, depends on the storage
        backend. What matters is that the memory document's file
        contains the new content after the call.)
        """
        new_content = "## Updated\nSome new text"

        memory_doc = async_to_sync(get_or_create_memory_document)(
            self.corpus_a, self.user
        )

        async_to_sync(update_memory_content)(self.corpus_a, new_content, self.user)

        memory_doc.refresh_from_db()
        with memory_doc.txt_extract_file.open("rb") as fh:
            stored = fh.read()
        self.assertEqual(
            stored,
            new_content.encode("utf-8"),
            "Memory document should contain the updated content after update",
        )


class DocumentDeleteBlobRetentionTestCase(TransactionTestCase):
    """Issue #1464 spec regression: deleting a Document must not destroy
    file blobs that are still referenced by sibling Documents (corpus-
    isolated copies). Currently default ``Model.delete()`` does not
    touch blobs, so these tests pass today; they exist as a tripwire and
    will become the primary contract test once the orphan-cleanup work
    in issue #1492 lands a row-delete blob-removal mechanic.

    Coverage spans every ``FileField`` on Document (parameterized via
    ``DOCUMENT_FILE_FIELDS``) so adding a new file field is automatically
    protected.
    """

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="delete-blob-user", password="x")
        self.corpus_a = Corpus.objects.create(title="Origin", creator=self.user)
        self.uid = uuid.uuid4().hex

    def _make_shared_pair(self) -> tuple[Document, Document, dict[str, str]]:
        """Build a (source, copy) pair where every FileField is shared.

        Returns the pair plus a ``{field_name: blob_name}`` snapshot of
        the shared paths, captured before either row is deleted.
        """
        source = Document.objects.create(
            title=f"Shared Doc {self.uid}",
            creator=self.user,
            file_type="application/pdf",
        )
        for field_name in DOCUMENT_FILE_FIELDS:
            getattr(source, field_name).save(
                f"{field_name}_{self.uid}.bin",
                ContentFile(f"payload-{field_name}".encode()),
                save=True,
            )
        copy, _status, _path = self.corpus_a.add_document(
            document=source, user=self.user
        )
        # Refresh both so we read the canonical names from the DB.
        source.refresh_from_db()
        copy.refresh_from_db()

        shared_blobs: dict[str, str] = {}
        for field_name in DOCUMENT_FILE_FIELDS:
            blob_name = getattr(source, field_name).name
            assert blob_name, f"setUp: {field_name} should be populated"
            self.assertEqual(
                getattr(copy, field_name).name,
                blob_name,
                f"setUp: {field_name} must be shared between source and copy",
            )
            shared_blobs[field_name] = blob_name
        return source, copy, shared_blobs

    def test_deleting_copy_preserves_all_shared_blobs(self) -> None:
        """Deleting one Document must not destroy any blob still
        referenced by another live Document — checked across every
        ``FileField`` on Document."""
        source, copy, shared = self._make_shared_pair()

        # DocumentPath.document uses on_delete=PROTECT; remove paths first.
        DocumentPath.objects.filter(document=copy).delete()
        copy.delete()

        source.refresh_from_db()
        for field_name, blob_name in shared.items():
            with self.subTest(field=field_name):
                self.assertEqual(getattr(source, field_name).name, blob_name)
                self.assertTrue(
                    default_storage.exists(blob_name),
                    f"{field_name}: deleting a corpus copy destroyed the "
                    f"blob {blob_name!r} that the source Document still "
                    "references — issue #1464 regression.",
                )

    def test_deleting_source_preserves_all_shared_blobs(self) -> None:
        """Symmetry: deleting the source must not destroy any blob still
        referenced by a copy. (``source_document`` FK uses SET_NULL, so
        the copy's row survives the source delete.)"""
        source, copy, shared = self._make_shared_pair()

        # DocumentPath.document uses on_delete=PROTECT; remove source paths.
        DocumentPath.objects.filter(document=source).delete()
        source.delete()

        copy.refresh_from_db()
        for field_name, blob_name in shared.items():
            with self.subTest(field=field_name):
                self.assertEqual(getattr(copy, field_name).name, blob_name)
                self.assertTrue(
                    default_storage.exists(blob_name),
                    f"{field_name}: deleting the source destroyed the blob "
                    f"{blob_name!r} that the copy still references — "
                    "issue #1464 regression.",
                )
                with getattr(copy, field_name).open("rb") as fh:
                    self.assertEqual(
                        fh.read(),
                        f"payload-{field_name}".encode(),
                        f"{field_name}: copy content was clobbered",
                    )


# ---------------------------------------------------------------------------
# Issue #1492 — orphan blob reclaim at Document delete-time.
# ---------------------------------------------------------------------------


def _make_doc_with_blobs(
    user, uid: str, label: str = "Doc"
) -> tuple[Document, dict[str, str]]:
    """Create a Document with every FileField populated with a unique
    payload. Returns the Document plus a ``{field: blob_name}`` map.

    Each field gets a unique filename so storage allocates distinct
    paths and we can assert per-field deletion across the parameterized
    field set.
    """
    doc = Document.objects.create(
        title=f"{label} {uid}",
        creator=user,
        file_type="application/pdf",
    )
    blobs: dict[str, str] = {}
    for field_name in DOCUMENT_FILE_FIELDS:
        field_file = getattr(doc, field_name)
        field_file.save(
            f"{label.lower()}_{field_name}_{uid}.bin",
            ContentFile(f"{label}-{field_name}".encode()),
            save=True,
        )
        # ``FieldFile.name`` is set in-memory by ``save(save=True)``; no
        # need to round-trip to the DB just to read it back.
        blobs[field_name] = field_file.name
    return doc, blobs


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class DocumentDeleteOrphanReclaimTestCase(TransactionTestCase):
    """Issue #1492: deleting a Document reclaims its orphan blobs.

    The signal pair on Document captures populated FileField paths
    pre_delete and schedules ``cleanup_orphaned_document_blobs_task`` on
    ``transaction.on_commit``. The task only deletes a path that is no
    longer referenced by any live Document on any FileField — paths
    still referenced by a sibling row (corpus-isolated copy, etc.) are
    left alone.
    """

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="orphan-blob-user", password="x")
        self.corpus = Corpus.objects.create(title="Origin", creator=self.user)
        self.uid = uuid.uuid4().hex

    def test_per_row_delete_solitary_doc_reclaims_every_blob(self) -> None:
        """A solitary Document's blobs are reclaimed from storage when
        the row is deleted via per-instance ``Model.delete()``.

        Coverage spans every FileField on the model so adding a new
        file field is automatically covered."""
        doc, blobs = _make_doc_with_blobs(self.user, self.uid)
        for field_name, blob_name in blobs.items():
            self.assertTrue(default_storage.exists(blob_name))

        doc.delete()

        for field_name, blob_name in blobs.items():
            with self.subTest(field=field_name):
                self.assertFalse(
                    default_storage.exists(blob_name),
                    f"{field_name}: orphaned blob {blob_name!r} should "
                    "have been reclaimed by Document delete (#1492)",
                )

    def test_per_row_delete_with_sibling_retains_every_shared_blob(self) -> None:
        """When a sibling Document still references the blobs, deleting
        one row leaves storage untouched. Re-validates the
        ``unique_blob_paths_for_many`` orphan check at task time."""
        source, blobs = _make_doc_with_blobs(self.user, self.uid, label="Source")
        copy, _, _ = self.corpus.add_document(document=source, user=self.user)
        # Pre-condition: every blob is shared between source and copy.
        copy.refresh_from_db()
        for field_name, blob_name in blobs.items():
            self.assertEqual(getattr(copy, field_name).name, blob_name)

        # Cascade-safe delete: paths first (PROTECT), then row.
        DocumentPath.objects.filter(document=copy).delete()
        copy.delete()

        for field_name, blob_name in blobs.items():
            with self.subTest(field=field_name):
                self.assertTrue(
                    default_storage.exists(blob_name),
                    f"{field_name}: blob {blob_name!r} was reclaimed "
                    "even though source still references it (#1464/#1492)",
                )

    def test_queryset_bulk_delete_solitary_docs_reclaims_every_blob(self) -> None:
        """``QuerySet.delete()`` on a set of solitary Documents reclaims
        every blob — verifies that signals fire per-instance even on
        bulk delete (Django disables fast-delete once listeners are
        connected) and that paths from all instances coalesce into a
        single Celery task via the per-transaction accumulator."""
        docs_blobs = []
        for i in range(3):
            doc, blobs = _make_doc_with_blobs(
                self.user, f"{self.uid}-{i}", label=f"Bulk{i}"
            )
            docs_blobs.append((doc, blobs))

        all_paths: set[str] = set()
        for doc, blobs in docs_blobs:
            all_paths.update(blobs.values())
            self.assertTrue(all(default_storage.exists(p) for p in blobs.values()))

        pks = [doc.pk for doc, _ in docs_blobs]
        Document.objects.filter(pk__in=pks).delete()

        for path in all_paths:
            with self.subTest(path=path):
                self.assertFalse(
                    default_storage.exists(path),
                    f"queryset.delete() left orphan blob {path!r} in storage",
                )

    def test_queryset_bulk_delete_one_of_pair_retains_shared_blob(self) -> None:
        """A queryset delete that targets only one half of a sharing
        pair must NOT reclaim the shared blob — the surviving sibling
        keeps the field intact."""
        source, blobs = _make_doc_with_blobs(self.user, self.uid, label="Source")
        copy, _, _ = self.corpus.add_document(document=source, user=self.user)

        # Bulk-delete only the copy.
        DocumentPath.objects.filter(document=copy).delete()
        Document.objects.filter(pk=copy.pk).delete()

        for field_name, blob_name in blobs.items():
            with self.subTest(field=field_name):
                self.assertTrue(
                    default_storage.exists(blob_name),
                    f"{field_name}: queryset delete of copy reclaimed "
                    f"shared blob {blob_name!r} (#1464 regression via #1492)",
                )

    def test_queryset_bulk_delete_both_halves_reclaims_shared_blob(self) -> None:
        """When the queryset spans BOTH halves of a sharing pair, the
        blob is reclaimed (no surviving reference). Confirms the
        orphan check at task time correctly returns False — the
        ``exclude(pk__in=target_pks)`` semantics apply transitively
        because both rows are gone post-commit."""
        source, blobs = _make_doc_with_blobs(self.user, self.uid, label="Source")
        copy, _, _ = self.corpus.add_document(document=source, user=self.user)

        DocumentPath.objects.filter(document__in=[source, copy]).delete()
        Document.objects.filter(pk__in=[source.pk, copy.pk]).delete()

        for field_name, blob_name in blobs.items():
            with self.subTest(field=field_name):
                self.assertFalse(
                    default_storage.exists(blob_name),
                    f"{field_name}: blob {blob_name!r} survived after "
                    "every referencing row was deleted",
                )

    def test_doc_with_empty_field_does_not_crash(self) -> None:
        """A Document with some ``FileField``s left empty must delete
        cleanly without scheduling spurious cleanup for empty paths."""
        doc = Document.objects.create(
            title=f"Sparse {self.uid}",
            creator=self.user,
            file_type="application/pdf",
        )
        # Populate only one field.
        doc.pdf_file.save(
            f"sparse_{self.uid}.pdf", ContentFile(b"%PDF-1.4 dummy"), save=True
        )
        blob = doc.pdf_file.name
        assert blob is not None
        self.assertTrue(default_storage.exists(blob))

        doc.delete()

        self.assertFalse(default_storage.exists(blob))

    def test_transaction_rollback_preserves_blobs(self) -> None:
        """If the surrounding transaction rolls back, the on_commit
        cleanup callback never fires and storage is untouched.

        We assert directly on storage rather than on the Document row:
        ``transaction.on_commit`` is documented to skip callbacks on
        rollback, which is the property under test. The row's fate
        depends on Django's interaction with FileField pre-save signals
        and is not what this test is here to check.
        """
        doc, blobs = _make_doc_with_blobs(self.user, self.uid, label="Rollback")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                DocumentPath.objects.filter(document=doc).delete()
                doc.delete()
                # Force the atomic block to roll back.
                raise IntegrityError("simulated mid-delete failure")

        # The on_commit callback never fired, so every blob is still
        # alive in storage despite the doc.delete() inside the rolled-
        # back transaction.
        for field_name, blob_name in blobs.items():
            with self.subTest(field=field_name):
                self.assertTrue(
                    default_storage.exists(blob_name),
                    f"{field_name}: blob {blob_name!r} was reclaimed "
                    "despite transaction rollback",
                )

    def test_rollback_then_successful_delete_does_not_corrupt_cleanup(self) -> None:
        """Cross-transaction bleed of the per-connection accumulator.

        The accumulator that batches blob-cleanup paths between
        ``post_delete`` and ``on_commit`` is a Python attribute on the
        Django connection wrapper. ``transaction.on_commit`` skips the
        flush callback on rollback, but Django does not reset attributes
        on the wrapper, so a rolled-back delete leaves its captured paths
        sitting in the accumulator. The next transaction merges its own
        paths with the leftover ones and dispatches the cleanup task on
        the union — the task's orphan re-check is what actually keeps
        the rolled-back row's blobs alive.

        This test pins that contract: after a rollback, the next real
        delete must (a) actually free its own blobs and (b) not destroy
        the rolled-back document's blobs.
        """
        rolled_back_doc, rolled_back_blobs = _make_doc_with_blobs(
            self.user, self.uid, label="RolledBack"
        )
        committed_doc, committed_blobs = _make_doc_with_blobs(
            self.user, self.uid, label="Committed"
        )

        # Transaction A: delete rolled_back_doc, then force a rollback.
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                DocumentPath.objects.filter(document=rolled_back_doc).delete()
                rolled_back_doc.delete()
                raise IntegrityError("simulated mid-delete failure")

        # Transaction B: actually delete committed_doc.
        DocumentPath.objects.filter(document=committed_doc).delete()
        committed_doc.delete()

        # Rolled-back blobs survive — the row was restored by rollback,
        # so the orphan re-check skips its paths even though they bled
        # into transaction B's accumulator.
        for field_name, blob_name in rolled_back_blobs.items():
            with self.subTest(rolled_back=field_name):
                self.assertTrue(
                    default_storage.exists(blob_name),
                    f"{field_name}: rolled-back blob {blob_name!r} was "
                    "reclaimed by a subsequent transaction",
                )

        # Committed-delete blobs ARE reclaimed — the next transaction's
        # cleanup must still work after the rollback bleed.
        for field_name, blob_name in committed_blobs.items():
            with self.subTest(committed=field_name):
                self.assertFalse(
                    default_storage.exists(blob_name),
                    f"{field_name}: committed-delete blob {blob_name!r} "
                    "was NOT reclaimed (rollback poisoned the next "
                    "transaction's cleanup)",
                )

    def test_permanently_delete_corpus_copy_retains_blobs_via_source(self) -> None:
        """Issue #1492 cascade case 1 — permanently delete a corpus copy
        when its source Document still references the same blobs.

        ``Corpus.add_document`` always creates a fresh corpus-isolated
        Document whose FileFields share storage paths with the source
        (Rule I3). Permanently deleting the corpus copy invokes
        ``Document.delete()`` on the copy, which the new signal pair
        treats as a candidate for blob reclaim. The orphan check in the
        Celery task must observe that the source still references those
        paths and therefore leave them alone.
        """
        from opencontractserver.documents.versioning import (
            permanently_delete_document,
        )

        source, blobs = _make_doc_with_blobs(self.user, self.uid, label="Trash")
        # add_document creates a corpus-isolated copy and the
        # DocumentPath points at THAT copy, not at the source.
        copy, _, _ = self.corpus.add_document(document=source, user=self.user)
        DocumentPath.objects.filter(document=copy, corpus=self.corpus).update(
            is_deleted=True
        )

        success, error = permanently_delete_document(self.corpus, copy, self.user)

        self.assertTrue(success, f"permanent delete failed: {error}")
        self.assertFalse(Document.objects.filter(pk=copy.pk).exists())
        # Source still alive → all shared blobs alive.
        self.assertTrue(Document.objects.filter(pk=source.pk).exists())
        for field_name, blob_name in blobs.items():
            with self.subTest(field=field_name):
                self.assertTrue(
                    default_storage.exists(blob_name),
                    f"{field_name}: permanently_delete_document reclaimed "
                    f"shared blob {blob_name!r} despite live source",
                )

    def test_permanently_delete_corpus_copy_then_source_reclaims_blobs(
        self,
    ) -> None:
        """Issue #1492 cascade case 2 — once every Document referencing a
        blob has been deleted, the new mechanic reclaims it.

        Sequence:
        1. ``permanently_delete_document`` removes the corpus copy
           (blobs survive — source still references them).
        2. The standalone source Document (which has no DocumentPath
           because it was never the target of an add_document call —
           ``add_document`` creates the path on the *copy*) is deleted
           directly. With no surviving references, the cleanup task
           reaps every blob.
        """
        from opencontractserver.documents.versioning import (
            permanently_delete_document,
        )

        source, blobs = _make_doc_with_blobs(self.user, self.uid, label="Final")
        copy, _, _ = self.corpus.add_document(document=source, user=self.user)
        DocumentPath.objects.filter(document=copy, corpus=self.corpus).update(
            is_deleted=True
        )

        permanently_delete_document(self.corpus, copy, self.user)
        # Sanity: blobs survived the first delete.
        for blob_name in blobs.values():
            self.assertTrue(default_storage.exists(blob_name))

        source.delete()

        for field_name, blob_name in blobs.items():
            with self.subTest(field=field_name):
                self.assertFalse(
                    default_storage.exists(blob_name),
                    f"{field_name}: orphan blob {blob_name!r} not "
                    "reclaimed after final reference removed",
                )

    def test_permanently_delete_with_sibling_corpus_copy_retains_blobs(
        self,
    ) -> None:
        """When another corpus still hosts a sibling corpus-isolated
        copy of the same source, deleting one copy must not destroy the
        blobs — both the source and the sibling copy still reference
        them."""
        from opencontractserver.documents.versioning import (
            permanently_delete_document,
        )

        source, blobs = _make_doc_with_blobs(self.user, self.uid, label="MultiCorpus")
        copy_a, _, _ = self.corpus.add_document(document=source, user=self.user)
        corpus_b = Corpus.objects.create(title="Other", creator=self.user)
        copy_b, _, _ = corpus_b.add_document(document=source, user=self.user)

        DocumentPath.objects.filter(document=copy_a, corpus=self.corpus).update(
            is_deleted=True
        )

        success, error = permanently_delete_document(self.corpus, copy_a, self.user)

        self.assertTrue(success, f"permanent delete failed: {error}")
        self.assertFalse(Document.objects.filter(pk=copy_a.pk).exists())
        # Source + copy_b survive and still reference every blob.
        self.assertTrue(Document.objects.filter(pk=source.pk).exists())
        self.assertTrue(Document.objects.filter(pk=copy_b.pk).exists())
        for field_name, blob_name in blobs.items():
            with self.subTest(field=field_name):
                self.assertTrue(
                    default_storage.exists(blob_name),
                    f"{field_name}: blob {blob_name!r} reclaimed despite "
                    "live source + sibling corpus copy",
                )

    def test_corpus_delete_protect_holds_and_blobs_remain(self) -> None:
        """Cascade safety check: deleting a Corpus cascades to its
        DocumentPath rows (corpus FK is CASCADE) but does NOT delete the
        underlying Documents (DocumentPath.document FK is PROTECT — wait,
        PROTECT only blocks deletion of the protected row, not the
        cascade *into* the protector). Result: Documents survive corpus
        deletion, and so do their blobs."""
        source, blobs = _make_doc_with_blobs(self.user, self.uid, label="CorpusCascade")
        copy, _, _ = self.corpus.add_document(document=source, user=self.user)
        # Sanity: corpus has a path.
        self.assertTrue(DocumentPath.objects.filter(corpus=self.corpus).exists())

        self.corpus.delete()

        # DocumentPath rows for this corpus are gone.
        self.assertFalse(DocumentPath.objects.filter(corpus_id=self.corpus.pk).exists())
        # Documents survive (corpus delete does not cascade into Document).
        self.assertTrue(Document.objects.filter(pk=source.pk).exists())
        self.assertTrue(Document.objects.filter(pk=copy.pk).exists())
        # Blobs survive too — no Document was deleted, no cleanup ran.
        for field_name, blob_name in blobs.items():
            with self.subTest(field=field_name):
                self.assertTrue(
                    default_storage.exists(blob_name),
                    f"{field_name}: blob {blob_name!r} reclaimed despite "
                    "Documents surviving corpus.delete()",
                )

    def test_documentpath_protect_blocks_naive_delete(self) -> None:
        """Sanity check: ``DocumentPath.document`` is ``on_delete=PROTECT``
        so a Document with live paths cannot be deleted directly. This
        lock guards against the orphan-cleanup mechanic stripping blobs
        while the corpus still has a path pointing at the row."""
        from django.db.models.deletion import ProtectedError

        source, _ = _make_doc_with_blobs(self.user, self.uid, label="Protected")
        copy, _, _ = self.corpus.add_document(document=source, user=self.user)
        copy.refresh_from_db()
        copy_blobs = {
            field_name: getattr(copy, field_name).name
            for field_name in DOCUMENT_FILE_FIELDS
        }
        # Path holds copy in place; deleting copy must raise.
        with self.assertRaises(ProtectedError):
            copy.delete()
        for field_name, blob_name in copy_blobs.items():
            with self.subTest(field=field_name):
                self.assertTrue(
                    default_storage.exists(blob_name),
                    f"{field_name}: PROTECT failed, blob {blob_name!r} "
                    "removed before path cleanup",
                )

    def test_broker_dispatch_failure_is_logged_and_swallowed(self) -> None:
        """Issue #1492 follow-up: when the Celery broker is unavailable
        ``cleanup_orphaned_document_blobs_task.delay`` raises out of the
        ``on_commit`` callback. The signal handler must not crash the
        delete (which has already committed), but it MUST log the path
        list at ERROR level so ops can recover.

        Verifies the dispatch wrapper around ``.delay()`` in
        ``opencontractserver.documents.signals``.
        """
        from unittest.mock import patch

        doc, blobs = _make_doc_with_blobs(self.user, self.uid, label="DispatchFailure")

        broker_error = RuntimeError("broker unreachable")
        with patch(
            "opencontractserver.tasks.cleanup_tasks."
            "cleanup_orphaned_document_blobs_task.delay",
            side_effect=broker_error,
        ) as mocked_delay, self.assertLogs(
            "opencontractserver.documents.signals", level="ERROR"
        ) as log_ctx:
            # Delete must not raise even though the broker is down.
            doc.delete()

        mocked_delay.assert_called_once()
        # The error log must include the orphaned paths so ops can
        # reconcile manually or via the future management command.
        joined = "\n".join(log_ctx.output)
        self.assertIn("Blob cleanup task dispatch failed", joined)
        for blob_name in blobs.values():
            self.assertIn(blob_name, joined)

        # Document row is gone (delete committed before the on_commit
        # callback fired) but blobs are still in storage because dispatch
        # failed — exactly the orphan condition the log warns about.
        self.assertFalse(Document.objects.filter(pk=doc.pk).exists())
        for field_name, blob_name in blobs.items():
            with self.subTest(field=field_name):
                self.assertTrue(
                    default_storage.exists(blob_name),
                    f"{field_name}: blob {blob_name!r} should still be "
                    "in storage when the dispatch failed",
                )

        # Cleanup: remove the now-orphaned blobs ourselves so the test
        # leaves storage in a clean state.
        for blob_name in blobs.values():
            if default_storage.exists(blob_name):
                default_storage.delete(blob_name)

    def test_bulk_delete_registers_single_on_commit_callback(self) -> None:
        """Issue #1572 follow-up #2: ``QuerySet.delete()`` on N rows
        must register at most ONE blob-cleanup ``on_commit`` callback
        for the surrounding atomic context, not one per row.

        Before the fix, every ``post_delete`` registered its own
        ``on_commit`` callback; the first to fire drained the shared
        accumulator and the rest short-circuited on an empty set, but
        the queue still grew O(N) in memory and per-callback dispatch
        cost. Now we register exactly once per atomic context (subject
        to a presence check against the queue) and update the shared
        accumulator on subsequent ``post_delete`` signals.
        """
        import functools as _functools

        from django.db import connections

        from opencontractserver.documents.signals import _FLUSH_CALLBACK_MARKER

        bulk_size = 20
        docs: list[Document] = []
        for i in range(bulk_size):
            doc, _blobs = _make_doc_with_blobs(
                self.user, f"{self.uid}-callback-{i}", label=f"BulkCB{i}"
            )
            docs.append(doc)

        pks = [d.pk for d in docs]
        connection = connections["default"]

        def _count_blob_flush_callbacks() -> int:
            count = 0
            for entry in connection.run_on_commit:
                # entry: (savepoint_ids, callback, robust) on Django 5.x
                callback = entry[1]
                target = (
                    callback.func
                    if isinstance(callback, _functools.partial)
                    else callback
                )
                if getattr(target, _FLUSH_CALLBACK_MARKER, False):
                    count += 1
            return count

        with transaction.atomic():
            before = _count_blob_flush_callbacks()
            Document.objects.filter(pk__in=pks).delete()
            after = _count_blob_flush_callbacks()
            new_callbacks = after - before

        self.assertEqual(
            new_callbacks,
            1,
            f"Bulk delete of {bulk_size} rows registered {new_callbacks} "
            "blob-cleanup on_commit callbacks; expected exactly 1 — "
            "the shared accumulator should coalesce all paths into a "
            "single flush (issue #1572 follow-up #2).",
        )


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class UniqueBlobPathsForManyTestCase(TransactionTestCase):
    """Tests for ``Document.objects.unique_blob_paths_for_many(qs)`` —
    the batched complement to ``unique_blob_paths`` introduced for
    issue #1492's queryset-scale orphan check."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="unique-many-user", password="x")
        self.corpus = Corpus.objects.create(title="Origin", creator=self.user)
        self.uid = uuid.uuid4().hex

    def test_empty_input_returns_empty_set(self) -> None:
        self.assertEqual(
            Document.objects.unique_blob_paths_for_many(Document.objects.none()),
            set(),
        )
        self.assertEqual(Document.objects.unique_blob_paths_for_many([]), set())

    def test_single_solitary_doc_returns_all_its_blobs(self) -> None:
        doc, blobs = _make_doc_with_blobs(self.user, self.uid, label="Solo")
        unique = Document.objects.unique_blob_paths_for_many([doc.pk])
        self.assertEqual(unique, set(blobs.values()))

    def test_shared_pair_excluded_when_only_one_targeted(self) -> None:
        """A blob shared between target and a non-target Document must
        NOT appear in the unique set — that's exactly the case where
        the offensive cleanup must skip the path."""
        source, blobs = _make_doc_with_blobs(self.user, self.uid, label="Source")
        copy, _, _ = self.corpus.add_document(document=source, user=self.user)

        unique = Document.objects.unique_blob_paths_for_many([copy.pk])
        for field_name, blob_name in blobs.items():
            with self.subTest(field=field_name):
                self.assertNotIn(
                    blob_name,
                    unique,
                    f"{field_name}: shared blob {blob_name!r} should not "
                    "be marked unique to the corpus copy",
                )

    def test_shared_pair_included_when_both_targeted(self) -> None:
        """If the input set includes both halves of a sharing pair, the
        blob has no live reference outside the input → it IS unique to
        the input set (and therefore safe to delete if both are removed)."""
        source, blobs = _make_doc_with_blobs(self.user, self.uid, label="Source")
        copy, _, _ = self.corpus.add_document(document=source, user=self.user)

        unique = Document.objects.unique_blob_paths_for_many([source.pk, copy.pk])
        for field_name, blob_name in blobs.items():
            with self.subTest(field=field_name):
                self.assertIn(blob_name, unique)

    def test_accepts_queryset_input(self) -> None:
        doc, blobs = _make_doc_with_blobs(self.user, self.uid, label="QS")
        qs = Document.objects.filter(pk=doc.pk)
        self.assertEqual(
            Document.objects.unique_blob_paths_for_many(qs),
            set(blobs.values()),
        )

    def test_excludes_empty_field_paths(self) -> None:
        """Documents with empty FileFields must not contribute spurious
        empty strings to the unique-paths set."""
        doc = Document.objects.create(
            title=f"Sparse {self.uid}",
            creator=self.user,
            file_type="application/pdf",
        )
        doc.pdf_file.save(f"sparse_{self.uid}.pdf", ContentFile(b"%PDF-1.4"), save=True)
        unique = Document.objects.unique_blob_paths_for_many([doc.pk])
        self.assertEqual(unique, {doc.pdf_file.name})
        self.assertNotIn("", unique)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class CleanupOrphanedDocumentBlobsTaskTestCase(TransactionTestCase):
    """Direct tests for ``cleanup_orphaned_document_blobs_task``. The
    signal handler tests above cover the integrated path; these cases
    pin the task's standalone contract for defensive programming."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="cleanup-task-user", password="x")
        self.uid = uuid.uuid4().hex

    def test_empty_input_is_noop(self) -> None:
        from opencontractserver.tasks.cleanup_tasks import (
            cleanup_orphaned_document_blobs_task,
        )

        self.assertEqual(cleanup_orphaned_document_blobs_task([]), 0)

    def test_skips_paths_still_referenced(self) -> None:
        """If a Document still references the path on any FileField, the
        task must not delete the blob from storage."""
        from opencontractserver.tasks.cleanup_tasks import (
            cleanup_orphaned_document_blobs_task,
        )

        doc, blobs = _make_doc_with_blobs(self.user, self.uid, label="StillReferenced")
        path = blobs["pdf_file"]
        self.assertTrue(default_storage.exists(path))

        deleted = cleanup_orphaned_document_blobs_task([path])

        self.assertEqual(deleted, 0)
        self.assertTrue(
            default_storage.exists(path),
            "task deleted a blob that a Document still references",
        )

    def test_deletes_orphaned_path(self) -> None:
        """A path with no live Document reference is removed."""
        from opencontractserver.tasks.cleanup_tasks import (
            cleanup_orphaned_document_blobs_task,
        )

        # Manually write a payload to storage that is not referenced by
        # any Document — synthetic orphan to test the cleanup in
        # isolation.
        orphan_path = default_storage.save(
            f"synthetic_orphan_{self.uid}.bin", ContentFile(b"orphan")
        )
        self.assertTrue(default_storage.exists(orphan_path))

        deleted = cleanup_orphaned_document_blobs_task([orphan_path])

        self.assertEqual(deleted, 1)
        self.assertFalse(default_storage.exists(orphan_path))

    def test_dedupes_input(self) -> None:
        """Duplicate paths in the input list are processed once."""
        from opencontractserver.tasks.cleanup_tasks import (
            cleanup_orphaned_document_blobs_task,
        )

        orphan_path = default_storage.save(
            f"dup_orphan_{self.uid}.bin", ContentFile(b"orphan")
        )
        deleted = cleanup_orphaned_document_blobs_task(
            [orphan_path, orphan_path, orphan_path]
        )
        self.assertEqual(deleted, 1)
        self.assertFalse(default_storage.exists(orphan_path))

    def test_missing_path_is_tolerated(self) -> None:
        """A path that no longer exists in storage (e.g. because a
        previous run already deleted it, or another process raced us
        to it — issue #1572 follow-up #3) is reported as cleaned and
        does not raise.

        The exact ``deleted_count`` depends on whether the configured
        storage backend raises ``FileNotFoundError`` (counted as 0) or
        is idempotent on missing paths (counted as 1). What we pin
        here is the idempotency contract: storage is left in the
        desired state with no exceptions surfacing to the caller.
        """
        from opencontractserver.tasks.cleanup_tasks import (
            cleanup_orphaned_document_blobs_task,
        )

        nonexistent = f"nonexistent_{self.uid}.bin"
        # Should not raise; storage state must be "absent" after the call.
        cleanup_orphaned_document_blobs_task([nonexistent])
        self.assertFalse(default_storage.exists(nonexistent))
