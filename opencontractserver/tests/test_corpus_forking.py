import base64
import pathlib
import uuid

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import transaction
from django.test import TestCase, TransactionTestCase

from opencontractserver.annotations.models import Annotation, Relationship
from opencontractserver.corpuses.models import Corpus, TemporaryFileHandle
from opencontractserver.documents.models import Document
from opencontractserver.tasks import import_corpus
from opencontractserver.tasks.utils import package_zip_into_base64
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.corpus_forking import build_fork_corpus_task
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class CorpusForkTestCase(TestCase):
    """Test suite for corpus forking data integrity.

    Uses ``setUp`` (instance method) to run an import+fork cycle before each
    test.  ``TransactionTestCase`` runs ``_fixture_teardown()`` (a full
    database FLUSH) before every test method, so data created in
    ``setUpClass`` would be wiped before test 1 even starts.  Each test
    method therefore gets its own fresh import+fork cycle.

    All tests are read-only against the forked data, so there is no
    write-isolation concern beyond the flush semantics.
    """

    fixtures_path = pathlib.Path(__file__).parent / "fixtures"

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(username="bob", password="12345678")
        original_corpus, forked_corpus = self._import_and_fork_corpus()
        self.original_corpus_id = original_corpus.id
        self.forked_corpus_id = forked_corpus.id
        self._label_map_cache = {}

    def _import_and_fork_corpus(self):
        """Import a test corpus and fork it. Returns (original_corpus, forked_corpus)."""
        export_zip_base64_file_string = package_zip_into_base64(
            self.fixtures_path / "Test_Corpus_EXPORT.zip"
        )
        original_corpus = Corpus.objects.create(
            title="New Import", creator=self.user, backend_lock=False
        )
        set_permissions_for_obj_to_user(
            self.user, original_corpus, [PermissionTypes.ALL]
        )

        base64_img_bytes = export_zip_base64_file_string.encode("utf-8")
        decoded_file_data = base64.decodebytes(base64_img_bytes)

        with transaction.atomic():
            temporary_file = TemporaryFileHandle.objects.create()
            temporary_file.file.save(
                f"corpus_import_{uuid.uuid4()}.pdf", ContentFile(decoded_file_data)
            )

        import_task = import_corpus.s(
            temporary_file.id, self.user.id, original_corpus.id
        )
        import_task.apply().get()
        original_corpus.refresh_from_db()

        fork_task = build_fork_corpus_task(
            corpus_pk_to_fork=original_corpus.id, user=self.user
        )
        task_results = fork_task.apply().get()
        forked_corpus = Corpus.objects.get(id=task_results)
        forked_corpus.refresh_from_db()

        return original_corpus, forked_corpus

    def _load_corpuses(self):
        """Retrieve fresh Corpus instances from stored IDs."""
        original = Corpus.objects.get(id=self.original_corpus_id)
        forked = Corpus.objects.get(id=self.forked_corpus_id)
        return original, forked

    def test_corpus_forking(self):
        """Test that forking preserves object counts."""
        original_corpus, forked_corpus = self._load_corpuses()

        self.assertIsInstance(forked_corpus, Corpus)
        self.assertIsInstance(forked_corpus.parent, Corpus)
        self.assertEqual(forked_corpus.parent_id, original_corpus.id)

        # Annotation count
        forked_annotation_count = Annotation.objects.filter(
            corpus=forked_corpus, analysis__isnull=True
        ).count()
        original_annotation_count = Annotation.objects.filter(
            corpus=original_corpus, analysis__isnull=True
        ).count()
        self.assertEqual(forked_annotation_count, original_annotation_count)

        # Document count
        self.assertEqual(
            forked_corpus._get_active_documents().count(),
            original_corpus._get_active_documents().count(),
        )

        # Label count
        original_labelset_labels = original_corpus.label_set.annotation_labels.all()
        forked_labelset_labels = forked_corpus.label_set.annotation_labels.all()
        self.assertEqual(
            forked_labelset_labels.count(), original_labelset_labels.count()
        )

    def _build_label_map(self, original_corpus, forked_corpus):
        """Build a mapping from original label IDs to forked label IDs by
        matching on label text.

        The result is cached by (original_corpus.id, forked_corpus.id) so
        multiple test helpers can share the same label map without redundant
        queries.  Each setUp creates fresh data and a fresh cache dict.

        Note: if multiple labels share the same ``text``, only the last one
        wins in the dict comprehension (silently dropped).  The assertions
        below guard against this in the test fixture.
        """
        cache_key = (original_corpus.id, forked_corpus.id)
        if cache_key in self._label_map_cache:
            return self._label_map_cache[cache_key]

        original_labels = list(original_corpus.label_set.annotation_labels.all())
        forked_labels = list(forked_corpus.label_set.annotation_labels.all())

        original_label_by_text = {lbl.text: lbl.id for lbl in original_labels}
        self.assertEqual(
            len(original_label_by_text),
            len(original_labels),
            "Original corpus has duplicate label texts -- label_map would silently drop entries",
        )

        forked_label_by_text = {lbl.text: lbl.id for lbl in forked_labels}
        self.assertEqual(
            len(forked_label_by_text),
            len(forked_labels),
            "Forked corpus has duplicate label texts -- label_map would silently drop entries",
        )

        label_map = {}
        for text, orig_id in original_label_by_text.items():
            if text in forked_label_by_text:
                label_map[orig_id] = forked_label_by_text[text]

        # Ensure every original label has a mapping entry
        original_label_ids = set(original_label_by_text.values())
        missing = original_label_ids - set(label_map.keys())
        self.assertEqual(missing, set(), f"Labels dropped during fork: {missing}")

        self._label_map_cache[cache_key] = label_map
        return label_map

    def test_forked_label_properties(self):
        """Verify that label properties (color, description, icon, text, label_type)
        transfer correctly during cloning."""
        original_corpus, forked_corpus = self._load_corpuses()

        original_labels = list(
            original_corpus.label_set.annotation_labels.order_by("text").values(
                "text", "color", "description", "icon", "label_type"
            )
        )
        forked_labels = list(
            forked_corpus.label_set.annotation_labels.order_by("text").values(
                "text", "color", "description", "icon", "label_type"
            )
        )

        self.assertGreater(len(original_labels), 0, "Fixture should contain labels")
        self.assertEqual(len(forked_labels), len(original_labels))

        for orig, forked in zip(original_labels, forked_labels):
            self.assertEqual(forked["text"], orig["text"])
            self.assertEqual(forked["color"], orig["color"])
            self.assertEqual(forked["description"], orig["description"])
            self.assertEqual(forked["icon"], orig["icon"])
            self.assertEqual(forked["label_type"], orig["label_type"])

    def test_forked_labels_are_independent_copies(self):
        """Forked labels must be new DB rows, not references to the originals."""
        original_corpus, forked_corpus = self._load_corpuses()

        original_label_ids = set(
            original_corpus.label_set.annotation_labels.values_list("id", flat=True)
        )
        forked_label_ids = set(
            forked_corpus.label_set.annotation_labels.values_list("id", flat=True)
        )

        self.assertGreater(len(original_label_ids), 0, "Fixture should contain labels")
        self.assertTrue(
            original_label_ids.isdisjoint(forked_label_ids),
            "Forked labels should be new rows with different PKs",
        )

    def test_forked_labelset_metadata(self):
        """Verify the forked LabelSet has the [FORK] title prefix and preserves description."""
        original_corpus, forked_corpus = self._load_corpuses()

        original_ls = original_corpus.label_set
        forked_ls = forked_corpus.label_set

        self.assertNotEqual(original_ls.id, forked_ls.id)
        self.assertEqual(forked_ls.title, f"[FORK] {original_ls.title}")
        self.assertEqual(forked_ls.description, original_ls.description)

    def test_forked_document_field_integrity(self):
        """Verify that forked documents have correct titles, provenance, creator,
        and share the same underlying file blobs as the originals."""
        original_corpus, forked_corpus = self._load_corpuses()

        original_docs = list(original_corpus._get_active_documents())
        forked_docs = list(forked_corpus._get_active_documents())

        self.assertGreater(len(original_docs), 0, "Fixture should contain documents")
        self.assertEqual(len(forked_docs), len(original_docs))

        # Join forked documents by source_document_id for robust matching
        forked_by_source: dict[int, Document] = {}
        for d in forked_docs:
            self.assertNotIn(
                d.source_document_id,
                forked_by_source,
                f"Forked corpus has duplicate source_document_id: {d.source_document_id}",
            )
            forked_by_source[d.source_document_id] = d

        for orig_doc in original_docs:
            forked_doc = forked_by_source.get(orig_doc.id)
            self.assertIsNotNone(
                forked_doc,
                f"No forked document found with source_document_id={orig_doc.id}",
            )
            assert forked_doc is not None

            # Title should have [FORK] prefix
            self.assertEqual(forked_doc.title, f"[FORK] {orig_doc.title}")

            # Forked doc should reference original as source_document
            self.assertEqual(forked_doc.source_document_id, orig_doc.id)

            # Forked doc must have a new PK
            self.assertNotEqual(forked_doc.id, orig_doc.id)

            # Creator should propagate
            self.assertEqual(
                forked_doc.creator_id,
                self.user.id,
                "Forked document creator should match the forking user",
            )

            # File blobs should be shared (same underlying file path)
            if orig_doc.pdf_file:
                self.assertEqual(
                    forked_doc.pdf_file.name,
                    orig_doc.pdf_file.name,
                    "Forked doc should share the same PDF file blob",
                )
            if orig_doc.txt_extract_file:
                self.assertEqual(
                    forked_doc.txt_extract_file.name,
                    orig_doc.txt_extract_file.name,
                    "Forked doc should share the same text extract file blob",
                )
            if orig_doc.pawls_parse_file:
                self.assertEqual(
                    forked_doc.pawls_parse_file.name,
                    orig_doc.pawls_parse_file.name,
                    "Forked doc should share the same PAWLs parse file blob",
                )

    def test_forked_annotation_field_integrity(self):
        """Verify that forked annotations preserve page, raw_text,
        json payload, annotation_type, and creator."""
        original_corpus, forked_corpus = self._load_corpuses()

        original_annots = list(
            Annotation.objects.filter(
                corpus=original_corpus, analysis__isnull=True
            ).order_by("raw_text", "page")
        )
        forked_annots = list(
            Annotation.objects.filter(
                corpus=forked_corpus, analysis__isnull=True
            ).order_by("raw_text", "page")
        )

        self.assertGreater(
            len(original_annots), 0, "Fixture should contain annotations"
        )
        self.assertEqual(len(forked_annots), len(original_annots))

        # Guard: ensure original annotations have unambiguous (raw_text, page) keys
        original_by_key: dict[tuple[str, int], Annotation] = {}
        for annot in original_annots:
            key = (annot.raw_text, annot.page)
            self.assertNotIn(
                key,
                original_by_key,
                f"Original corpus has duplicate (raw_text, page) pair: {key}",
            )
            original_by_key[key] = annot

        # Build dict-based lookup for forked annotations by (raw_text, page)
        forked_by_key: dict[tuple[str, int], Annotation] = {}
        for annot in forked_annots:
            key = (annot.raw_text, annot.page)
            self.assertNotIn(
                key,
                forked_by_key,
                f"Forked corpus has duplicate (raw_text, page) pair: {key}",
            )
            forked_by_key[key] = annot

        label_map = self._build_label_map(original_corpus, forked_corpus)

        for key, orig in original_by_key.items():
            forked = forked_by_key.get(key)
            self.assertIsNotNone(
                forked,
                f"No forked annotation found for (raw_text={orig.raw_text!r}, "
                f"page={orig.page})",
            )
            assert forked is not None

            # Must be different DB rows
            self.assertNotEqual(forked.id, orig.id)

            # Core data fields must match
            self.assertEqual(forked.page, orig.page)
            self.assertEqual(forked.raw_text, orig.raw_text)
            # Forked annotations are saved through Annotation.save(), which
            # auto-compacts v1 PAWLs JSON to v2 (issue: lazy migration, see
            # compact_annotation_json). Compare both sides in compact form so
            # the test is format-agnostic.
            from opencontractserver.annotations.compact_json import (
                compact_annotation_json,
            )

            self.assertEqual(
                compact_annotation_json(forked.json),
                compact_annotation_json(orig.json),
            )
            self.assertEqual(forked.annotation_type, orig.annotation_type)

            # Creator should propagate
            self.assertEqual(
                forked.creator_id,
                self.user.id,
                f"Forked annotation creator should match the forking user "
                f"(raw_text='{orig.raw_text}')",
            )

            # Label should be remapped to the forked copy
            if orig.annotation_label_id:
                expected_label_id = label_map.get(orig.annotation_label_id)
                self.assertEqual(
                    forked.annotation_label_id,
                    expected_label_id,
                    f"Annotation label not correctly remapped for annotation "
                    f"with raw_text='{orig.raw_text}'",
                )

            # Corpus reference should point to the forked corpus
            self.assertEqual(forked.corpus_id, forked_corpus.id)

    def test_forked_relationship_integrity(self):
        """Verify forked relationships maintain correct source/target annotation
        references and preserve label mappings."""
        original_corpus, forked_corpus = self._load_corpuses()

        original_rels = list(
            Relationship.objects.filter(
                corpus=original_corpus, analysis__isnull=True
            ).prefetch_related("source_annotations", "target_annotations")
        )
        forked_rels = list(
            Relationship.objects.filter(
                corpus=forked_corpus, analysis__isnull=True
            ).prefetch_related("source_annotations", "target_annotations")
        )

        # Fixture must contain relationships for this test to be meaningful
        if len(original_rels) == 0:
            self.skipTest("Fixture has no relationships -- nothing to verify")

        # Count check (after skipTest for clarity)
        self.assertEqual(len(forked_rels), len(original_rels))

        # Build annotation id -> content key maps for both corpuses.
        original_annots = list(
            Annotation.objects.filter(corpus=original_corpus, analysis__isnull=True)
        )
        original_annot_key_to_id = {(a.raw_text, a.page): a.id for a in original_annots}

        # Guard: ensure (raw_text, page) is unambiguous for originals
        self.assertEqual(
            len(original_annot_key_to_id),
            len(original_annots),
            "Fixture has duplicate (raw_text, page) pairs -- annotation key is ambiguous",
        )

        # Reverse map: original annotation id -> content key
        orig_id_to_key = {v: k for k, v in original_annot_key_to_id.items()}

        # Build forked annotation id -> content key in a single query.
        forked_annots = list(
            Annotation.objects.filter(corpus=forked_corpus, analysis__isnull=True)
        )
        forked_annot_by_id = {a.id: (a.raw_text, a.page) for a in forked_annots}

        # Guard: ensure forked annotations also have unambiguous keys
        self.assertEqual(
            len(forked_annot_by_id),
            len(forked_annots),
            "Forked corpus has duplicate (raw_text, page) pairs -- annotation key is ambiguous",
        )

        # Pre-compute source/target id sets per relationship from the
        # prefetch cache (iterating .all() hits the cache; .values_list()
        # bypasses it and issues a new query each time).
        orig_rel_annot_ids = {}
        for rel in original_rels:
            orig_rel_annot_ids[rel.id] = (
                {a.id for a in rel.source_annotations.all()},
                {a.id for a in rel.target_annotations.all()},
            )

        forked_rel_annot_ids = {}
        for rel in forked_rels:
            forked_rel_annot_ids[rel.id] = (
                {a.id for a in rel.source_annotations.all()},
                {a.id for a in rel.target_annotations.all()},
            )

        # Index forked relationships by (label_text, source_keys, target_keys)
        # for O(1) lookup.  Including the label text in the key prevents
        # collisions when two relationships have empty M2M sets.
        forked_rel_by_key: dict[tuple, Relationship] = {}
        for rel in forked_rels:
            src_ids, tgt_ids = forked_rel_annot_ids[rel.id]
            src_keys = frozenset(
                forked_annot_by_id[aid] for aid in src_ids if aid in forked_annot_by_id
            )
            tgt_keys = frozenset(
                forked_annot_by_id[aid] for aid in tgt_ids if aid in forked_annot_by_id
            )
            rel_label_text = (
                rel.relationship_label.text if rel.relationship_label else None
            )
            composite_key = (rel_label_text, src_keys, tgt_keys)
            self.assertNotIn(
                composite_key,
                forked_rel_by_key,
                f"Forked corpus has duplicate relationship key: {composite_key}",
            )
            forked_rel_by_key[composite_key] = rel

        label_map = self._build_label_map(original_corpus, forked_corpus)

        for orig_rel in original_rels:
            # Convert original annotation IDs to content keys
            orig_source_ids, orig_target_ids = orig_rel_annot_ids[orig_rel.id]
            orig_source_keys = frozenset(
                orig_id_to_key[aid] for aid in orig_source_ids if aid in orig_id_to_key
            )
            orig_target_keys = frozenset(
                orig_id_to_key[aid] for aid in orig_target_ids if aid in orig_id_to_key
            )

            # Use the original label text for lookup (label text is preserved
            # across fork, only the PK changes).
            orig_label_text = (
                orig_rel.relationship_label.text
                if orig_rel.relationship_label
                else None
            )

            # O(1) lookup by (label_text, source_keys, target_keys)
            matched_forked = forked_rel_by_key.get(
                (orig_label_text, orig_source_keys, orig_target_keys)
            )

            self.assertIsNotNone(
                matched_forked,
                f"No matching forked relationship found for original {orig_rel.id}",
            )
            assert matched_forked is not None

            # Verify the relationship points to the forked corpus
            self.assertEqual(matched_forked.corpus_id, forked_corpus.id)

            # Verify label mapping
            if orig_rel.relationship_label_id:
                expected_label = label_map.get(orig_rel.relationship_label_id)
                self.assertEqual(
                    matched_forked.relationship_label_id,
                    expected_label,
                    "Relationship label not correctly remapped",
                )

            # Verify source/target annotations reference forked corpus annotations
            matched_src_ids, matched_tgt_ids = forked_rel_annot_ids[matched_forked.id]
            for annot_id in matched_src_ids | matched_tgt_ids:
                self.assertIn(
                    annot_id,
                    forked_annot_by_id,
                    f"Forked relationship references annotation {annot_id} "
                    "not in the forked corpus",
                )

    def test_forked_corpus_metadata(self):
        """Verify the forked corpus has correct title prefix, parent reference,
        and is unlocked after fork completes."""
        original_corpus, forked_corpus = self._load_corpuses()

        self.assertEqual(forked_corpus.title, f"[FORK] {original_corpus.title}")
        self.assertEqual(forked_corpus.parent_id, original_corpus.id)
        self.assertFalse(
            forked_corpus.backend_lock,
            "Forked corpus should be unlocked after fork completes",
        )
        self.assertEqual(forked_corpus.creator_id, self.user.id)


class CorpusForkErrorHandlingTest(TestCase):
    """Cleanup-on-failure paths for the fork task.

    The fork code path now flows through V2 export+import, but it still owns
    a handful of cleanup branches: ``source_pk is None``, missing shell or
    user, and any exception thrown by export/import while the shell is
    backend-locked.  These are easy to regress when refactoring the task,
    so verify the shell is left unlocked and flagged ``error=True`` in each
    case.
    """

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(username="alice", password="12345678")

    def _apply_fork(self, shell_id: int):
        """Apply ``fork_corpus`` with the historical positional-arg signature.

        The arg list is retained for backward compatibility with queued tasks
        but ignored by the export-driven body.  All ``*_ids`` lists are empty
        because the task no longer consumes them.
        """
        from opencontractserver.tasks.fork_tasks import fork_corpus

        return fork_corpus.apply(
            args=(
                shell_id,  # new_corpus_id
                [],  # doc_ids
                "",  # label_set_id
                [],  # annotation_ids
                [],  # folder_ids
                [],  # relationship_ids
                self.user.id,  # user_id
            )
        ).get()

    def test_fork_with_no_parent_id_marks_shell_error_and_unlocks(self):
        """Shell with ``parent_id=None`` cannot identify a source corpus —
        fork_corpus should mark the shell ``error=True`` and clear the
        ``backend_lock`` rather than leave it hung."""
        shell = Corpus.objects.create(
            title="orphan_shell",
            creator=self.user,
            backend_lock=True,
            parent=None,
        )

        result = self._apply_fork(shell.id)

        self.assertIsNone(result)
        shell.refresh_from_db()
        self.assertTrue(shell.error)
        self.assertFalse(shell.backend_lock)

    def test_fork_with_export_exception_marks_shell_error_and_unlocks(self):
        """When ``build_corpus_v2_zip`` raises, the shell should be flagged
        ``error=True`` and unlocked so the user can retry rather than
        observing a permanently-locked corpus."""
        from unittest.mock import patch

        source = Corpus.objects.create(
            title="source", creator=self.user, backend_lock=False
        )
        shell = Corpus.objects.create(
            title="shell",
            creator=self.user,
            backend_lock=True,
            parent=source,
        )

        with patch(
            "opencontractserver.tasks.fork_tasks.build_corpus_v2_zip",
            side_effect=RuntimeError("simulated export failure"),
        ):
            result = self._apply_fork(shell.id)

        self.assertIsNone(result)
        shell.refresh_from_db()
        self.assertTrue(shell.error)
        self.assertFalse(shell.backend_lock)


class CorpusForkOrphanedBlobGCTest(TransactionTestCase):
    """Verify that the V2-import blob orphaned by fork's file-blob
    repointing is deleted via ``transaction.on_commit`` rather than left
    behind as storage leakage (addresses #1638 follow-up)."""

    fixtures_path = pathlib.Path(__file__).parent / "fixtures"

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(username="gc_user", password="12345678")

    def test_fork_gcs_orphaned_v2_import_blobs(self):
        """End-to-end: forking an imported corpus deletes the V2-import
        blob path on commit because the doc was repointed at the source.

        We capture ``default_storage.delete`` calls during the fork
        and assert at least one call targeted a path that no longer
        appears on any forked document.
        """
        from unittest.mock import patch

        export_zip_base64_file_string = package_zip_into_base64(
            self.fixtures_path / "Test_Corpus_EXPORT.zip"
        )
        source = Corpus.objects.create(
            title="gc_source", creator=self.user, backend_lock=False
        )
        set_permissions_for_obj_to_user(self.user, source, [PermissionTypes.ALL])

        base64_img_bytes = export_zip_base64_file_string.encode("utf-8")
        decoded_file_data = base64.decodebytes(base64_img_bytes)
        with transaction.atomic():
            temporary_file = TemporaryFileHandle.objects.create()
            temporary_file.file.save(
                f"corpus_import_{uuid.uuid4()}.pdf", ContentFile(decoded_file_data)
            )
        import_corpus.s(temporary_file.id, self.user.id, source.id).apply().get()
        source.refresh_from_db()

        # Capture the storage paths default_storage.delete is asked to
        # remove during the fork.  We patch the binding in fork_tasks so
        # only the fork-driven GC is observed (test fixture writes go
        # through the live ``default_storage``).
        deleted_paths: list[str] = []

        def _capture_delete(path: str) -> None:
            deleted_paths.append(path)

        with patch(
            "opencontractserver.tasks.fork_tasks.default_storage.delete",
            side_effect=_capture_delete,
        ):
            fork_task = build_fork_corpus_task(
                corpus_pk_to_fork=source.id, user=self.user
            )
            forked_id = fork_task.apply().get()

        self.assertIsNotNone(forked_id, "fork task should succeed")
        # At least one V2-import blob should have been collected for GC.
        # We don't assert an exact count because that depends on the
        # number of file-blob fields populated on the fixture documents.
        self.assertTrue(
            deleted_paths,
            "fork_corpus should schedule deletion of orphaned V2-import blobs",
        )

        # The deleted paths must not be referenced by any forked document —
        # otherwise the GC would have removed a live blob.
        forked = Corpus.objects.get(pk=forked_id)
        live_paths: set[str] = set()
        for dp in forked.document_paths.filter(is_current=True, is_deleted=False):
            doc = dp.document
            for field_name in (
                "pdf_file",
                "pawls_parse_file",
                "txt_extract_file",
                "icon",
                "md_summary_file",
            ):
                blob = getattr(doc, field_name)
                if blob and blob.name:
                    live_paths.add(blob.name)
        leaked = set(deleted_paths) & live_paths
        self.assertFalse(
            leaked,
            f"GC deleted live blob references still in use: {leaked}",
        )

    def test_fork_gc_tolerates_storage_delete_failures(self):
        """If ``default_storage.delete`` raises for one blob path, the GC
        must log and continue rather than crashing the post-commit callback
        (which would leak the rest of the orphans and surface as an
        unrelated error in Celery worker logs)."""
        from unittest.mock import patch

        export_zip_base64_file_string = package_zip_into_base64(
            self.fixtures_path / "Test_Corpus_EXPORT.zip"
        )
        source = Corpus.objects.create(
            title="gc_fail_source", creator=self.user, backend_lock=False
        )
        set_permissions_for_obj_to_user(self.user, source, [PermissionTypes.ALL])

        base64_img_bytes = export_zip_base64_file_string.encode("utf-8")
        decoded_file_data = base64.decodebytes(base64_img_bytes)
        with transaction.atomic():
            temporary_file = TemporaryFileHandle.objects.create()
            temporary_file.file.save(
                f"corpus_import_{uuid.uuid4()}.pdf", ContentFile(decoded_file_data)
            )
        import_corpus.s(temporary_file.id, self.user.id, source.id).apply().get()
        source.refresh_from_db()

        attempted_paths: list[str] = []

        def _failing_delete(path: str) -> None:
            attempted_paths.append(path)
            # Fail every delete to make sure ``_gc_orphaned_blobs`` does
            # not abort on the first failure.
            raise OSError(f"simulated storage failure for {path}")

        with patch(
            "opencontractserver.tasks.fork_tasks.default_storage.delete",
            side_effect=_failing_delete,
        ):
            fork_task = build_fork_corpus_task(
                corpus_pk_to_fork=source.id, user=self.user
            )
            forked_id = fork_task.apply().get()

        # The fork itself should still succeed; GC failures are non-fatal.
        self.assertIsNotNone(
            forked_id,
            "fork must succeed even when blob GC fails; GC is best-effort",
        )
        # Every orphan path should have been attempted (not short-circuited
        # by the first OSError).
        self.assertTrue(
            len(attempted_paths) >= 1,
            "GC must attempt to delete every orphan path even on failure",
        )
