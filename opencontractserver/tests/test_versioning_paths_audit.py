"""Regression tests for the corpus versioning & path/folder audit fixes.

Each test class targets one finding from the audit and proves the corrected
behaviour. Findings (see the audit report) are referenced by their IDs:

- H1: ``Corpus.add_document`` disambiguates on path collision (no silent
  supersede of an existing document).
- H2: Folder rename / move reconciles ``DocumentPath.path`` strings.
- M1: Single source of truth for lifecycle-action inference
  (``DocumentPath.infer_action``) shared by all three surfaces.
- M2: Folder name collisions return a graceful error, not an HTTP 500.
- M3: Restore disambiguates when the original path was reused while trashed.
- M4: ``version_number`` / ``last_modified`` resolvers share one cached query.
- M5: ``resolve_version_history`` is scoped to ``visible_to_user``.
- L1: ``has_version_history`` uses ``parent_id`` (zero extra queries).
- L2: ``get_document_folder`` tolerates >1 active path (no crash).
- L3: ``get_filesystem_at_time`` is scoped to the corpus.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from graphql_relay import to_global_id

from opencontractserver.corpuses.models import Corpus, CorpusFolder
from opencontractserver.corpuses.services import (
    DocumentLifecycleService,
    FolderCRUDService,
    FolderDocumentService,
)
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.documents.versioning import (
    delete_document,
    get_filesystem_at_time,
    get_path_history,
    import_document,
    move_document,
    restore_document,
)
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


def _fake_info(user):
    """Minimal ``info`` stand-in with a mutable ``context`` carrying ``user``.

    Resolvers stash request-scoped caches via ``setattr`` on ``info.context``;
    a ``SimpleNamespace`` supports that and exposes ``.user``.
    """
    return SimpleNamespace(context=SimpleNamespace(user=user))


def _active_paths(corpus):
    return DocumentPath.objects.filter(corpus=corpus, is_current=True, is_deleted=False)


class AddDocumentDisambiguationTests(TestCase):
    """H1: adding two same-titled documents keeps both (no silent supersede)."""

    def setUp(self):
        self.user = User.objects.create_user(username="h1user", password="pw")
        self.corpus = Corpus.objects.create(title="H1 Corpus", creator=self.user)

    def _make_source(self, title):
        return Document.objects.create(
            title=title, creator=self.user, file_type="application/pdf"
        )

    def test_collision_disambiguates_instead_of_superseding(self):
        src_a = self._make_source("Agreement")
        src_b = self._make_source("Agreement")

        copy_a, status_a, path_a = self.corpus.add_document(
            document=src_a, user=self.user
        )
        copy_b, status_b, path_b = self.corpus.add_document(
            document=src_b, user=self.user
        )

        # Both adds succeed and produce DISTINCT active paths.
        self.assertEqual(status_a, "added")
        self.assertEqual(status_b, "added")
        self.assertNotEqual(path_a.path, path_b.path)
        self.assertEqual(path_a.path, "/documents/Agreement")
        self.assertEqual(path_b.path, "/documents/Agreement_1")

        # The first document was NOT superseded — both paths are still active.
        self.assertTrue(
            DocumentPath.objects.get(pk=path_a.pk).is_current,
            "First document's path must remain active (was silently hidden "
            "before the fix).",
        )
        self.assertTrue(DocumentPath.objects.get(pk=path_b.pk).is_current)

        # Both are independent root content trees (fresh version, parent None).
        self.assertEqual(path_a.version_number, 1)
        self.assertEqual(path_b.version_number, 1)
        self.assertIsNone(path_a.parent_id)
        self.assertIsNone(path_b.parent_id)
        self.assertNotEqual(copy_a.version_tree_id, copy_b.version_tree_id)

        # Both documents are visible/active in the corpus.
        self.assertEqual(self.corpus.document_count(), 2)
        self.assertEqual(_active_paths(self.corpus).count(), 2)

    def test_three_way_collision_chains_suffixes(self):
        paths = []
        for _ in range(3):
            _, _, p = self.corpus.add_document(
                document=self._make_source("Report"), user=self.user
            )
            paths.append(p.path)
        self.assertEqual(
            paths,
            ["/documents/Report", "/documents/Report_1", "/documents/Report_2"],
        )
        self.assertEqual(_active_paths(self.corpus).count(), 3)


class FolderRenameMovePathReconcileTests(TestCase):
    """H2: folder rename / move keeps DocumentPath.path strings consistent."""

    def setUp(self):
        self.user = User.objects.create_user(username="h2user", password="pw")
        self.corpus = Corpus.objects.create(title="H2 Corpus", creator=self.user)
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.ALL])

    def _doc_in_folder(self, title, folder):
        """Create a corpus doc and move it into ``folder`` (folder-derived path)."""
        src = Document.objects.create(
            title=title, creator=self.user, file_type="application/pdf"
        )
        copy, _, _ = self.corpus.add_document(document=src, user=self.user)
        ok, err = FolderDocumentService.move_document_to_folder(
            user=self.user, document=copy, corpus=self.corpus, folder=folder
        )
        self.assertTrue(ok, err)
        return copy

    def _current_path(self, document):
        return _active_paths(self.corpus).get(document=document).path

    def test_rename_folder_rewrites_document_paths(self):
        folder, err = FolderCRUDService.create_folder(
            user=self.user, corpus=self.corpus, name="Legal"
        )
        self.assertEqual(err, "")
        assert folder is not None
        doc = self._doc_in_folder("Contract", folder)
        self.assertEqual(self._current_path(doc), "/Legal/Contract")

        ok, err = FolderCRUDService.update_folder(
            user=self.user, folder=folder, name="Contracts"
        )
        self.assertTrue(ok, err)

        # Path string now reflects the new folder name.
        self.assertEqual(self._current_path(doc), "/Contracts/Contract")
        # Old path is retained as inactive history (immutable node).
        self.assertTrue(
            DocumentPath.objects.filter(
                corpus=self.corpus, path="/Legal/Contract", is_current=False
            ).exists()
        )
        # The reconciliation node is a MOVED event.
        new_node = _active_paths(self.corpus).get(document=doc)
        self.assertEqual(new_node.infer_action(), DocumentPath.ACTION_MOVED)

    def test_rename_rewrites_descendant_folder_documents(self):
        parent, _ = FolderCRUDService.create_folder(
            user=self.user, corpus=self.corpus, name="A"
        )
        assert parent is not None
        child, _ = FolderCRUDService.create_folder(
            user=self.user, corpus=self.corpus, name="B", parent=parent
        )
        assert child is not None
        doc = self._doc_in_folder("Deep", child)
        self.assertEqual(self._current_path(doc), "/A/B/Deep")

        ok, err = FolderCRUDService.update_folder(
            user=self.user, folder=parent, name="Z"
        )
        self.assertTrue(ok, err)
        # Descendant folder's documents are rewritten too.
        self.assertEqual(self._current_path(doc), "/Z/B/Deep")

    def test_move_folder_rewrites_document_paths(self):
        parent, _ = FolderCRUDService.create_folder(
            user=self.user, corpus=self.corpus, name="A"
        )
        assert parent is not None
        child, _ = FolderCRUDService.create_folder(
            user=self.user, corpus=self.corpus, name="B", parent=parent
        )
        assert child is not None
        doc = self._doc_in_folder("Mover", child)
        self.assertEqual(self._current_path(doc), "/A/B/Mover")

        # Move child B to the corpus root.
        ok, err = FolderCRUDService.move_folder(
            user=self.user, folder=child, new_parent=None
        )
        self.assertTrue(ok, err)
        self.assertEqual(self._current_path(doc), "/B/Mover")

    def test_non_folder_derived_paths_untouched(self):
        """An upload-style /documents/<title> path is left alone on rename."""
        folder, _ = FolderCRUDService.create_folder(
            user=self.user, corpus=self.corpus, name="Legal"
        )
        assert folder is not None
        # add_document places the doc in the folder but with a /documents/ path
        # (NOT folder-derived), since add_document doesn't fold the folder into
        # the path.
        src = Document.objects.create(
            title="Loose", creator=self.user, file_type="application/pdf"
        )
        copy, _, path_rec = self.corpus.add_document(
            document=src, user=self.user, folder=folder
        )
        self.assertEqual(path_rec.path, "/documents/Loose")

        ok, err = FolderCRUDService.update_folder(
            user=self.user, folder=folder, name="Renamed"
        )
        self.assertTrue(ok, err)
        # Unchanged — it never reflected the folder location.
        self.assertEqual(self._current_path(copy), "/documents/Loose")


class InferActionConsistencyTests(TestCase):
    """M1: one source of truth for action inference across all surfaces."""

    def setUp(self):
        self.user = User.objects.create_user(username="m1user", password="pw")
        self.corpus = Corpus.objects.create(title="M1 Corpus", creator=self.user)

    def test_lifecycle_action_sequence(self):
        content = b"m1 content"
        _, _, p1 = import_document(
            corpus=self.corpus, path="/a.pdf", content=content, user=self.user
        )
        p2 = move_document(self.corpus, "/a.pdf", "/b.pdf", self.user)
        p3 = delete_document(self.corpus, "/b.pdf", self.user)
        p4 = restore_document(self.corpus, "/b.pdf", self.user)

        # Canonical labels from the single source of truth.
        self.assertEqual(p1.infer_action(None), DocumentPath.ACTION_IMPORTED)
        self.assertEqual(p2.infer_action(), DocumentPath.ACTION_MOVED)
        self.assertEqual(p3.infer_action(), DocumentPath.ACTION_DELETED)
        self.assertEqual(p4.infer_action(), DocumentPath.ACTION_RESTORED)

        # get_path_history shares the same LOGIC but keeps its legacy label
        # vocabulary (IMPORTED -> "CREATED") for backward compatibility.
        history = get_path_history(p4)
        self.assertEqual(
            [e["action"] for e in history],
            ["CREATED", "MOVED", "DELETED", "RESTORED"],
        )

    def test_folder_only_change_is_moved(self):
        """A folder change with the same path string is still MOVED."""
        folder = CorpusFolder.objects.create(
            name="F", corpus=self.corpus, creator=self.user
        )
        _, _, p1 = import_document(
            corpus=self.corpus, path="/x.pdf", content=b"x", user=self.user
        )
        # Same path string, but folder changes None -> folder.
        p2 = move_document(
            self.corpus, "/x.pdf", "/x.pdf", self.user, new_folder=folder
        )
        self.assertEqual(p2.path, p1.path)
        self.assertNotEqual(p2.folder_id, p1.folder_id)
        self.assertEqual(p2.infer_action(p1), DocumentPath.ACTION_MOVED)

    def test_delete_takes_precedence_over_move(self):
        """A node that is both moved AND newly deleted reports DELETED."""
        previous = DocumentPath(path="/a.pdf", folder_id=None, is_deleted=False)
        # Path changed (would be MOVED) but also transitioned into deleted.
        current = DocumentPath(path="/b.pdf", folder_id=None, is_deleted=True)
        self.assertEqual(current.infer_action(previous), DocumentPath.ACTION_DELETED)


class FolderNameCollisionTests(TestCase):
    """M2: folder name collisions surface a clean error, not an exception."""

    def setUp(self):
        self.user = User.objects.create_user(username="m2user", password="pw")
        self.corpus = Corpus.objects.create(title="M2 Corpus", creator=self.user)
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.ALL])

    def test_duplicate_create_returns_error(self):
        f1, err1 = FolderCRUDService.create_folder(
            user=self.user, corpus=self.corpus, name="Dup"
        )
        self.assertIsNotNone(f1)
        self.assertEqual(err1, "")

        f2, err2 = FolderCRUDService.create_folder(
            user=self.user, corpus=self.corpus, name="Dup"
        )
        self.assertIsNone(f2)
        self.assertIn("already exists", err2)

    def test_move_into_colliding_sibling_returns_error(self):
        parent, _ = FolderCRUDService.create_folder(
            user=self.user, corpus=self.corpus, name="Parent"
        )
        # A "C" already lives under Parent.
        FolderCRUDService.create_folder(
            user=self.user, corpus=self.corpus, name="C", parent=parent
        )
        # Another "C" at the root.
        loose_c, _ = FolderCRUDService.create_folder(
            user=self.user, corpus=self.corpus, name="C"
        )
        assert parent is not None
        assert loose_c is not None

        ok, err = FolderCRUDService.move_folder(
            user=self.user, folder=loose_c, new_parent=parent
        )
        self.assertFalse(ok)
        self.assertIn("already exists", err)
        # The loose folder stays where it was (no partial move).
        loose_c.refresh_from_db()
        self.assertIsNone(loose_c.parent_id)

    def test_name_collision_discriminated_from_other_integrity_errors(self):
        """rename/move only report a name collision for the name constraint.

        ``reconcile_paths_after_folder_change`` runs inside the same
        ``transaction.atomic()`` as the folder write; a concurrent import that
        lands on a rewritten ``DocumentPath`` can raise an unrelated
        ``IntegrityError``. That must NOT be reported as a folder-name
        collision.
        """
        from django.db import IntegrityError

        from opencontractserver.corpuses.services.folders import (
            _is_folder_name_collision,
        )

        name_err = IntegrityError(
            "duplicate key value violates unique constraint "
            '"unique_folder_name_per_parent"'
        )
        path_err = IntegrityError(
            "duplicate key value violates unique constraint "
            '"unique_active_path_per_corpus"'
        )
        self.assertTrue(_is_folder_name_collision(name_err))
        self.assertFalse(_is_folder_name_collision(path_err))


class RestoreCollisionTests(TestCase):
    """M3: restoring onto a reused path disambiguates instead of crashing."""

    def setUp(self):
        self.user = User.objects.create_user(username="m3user", password="pw")
        self.corpus = Corpus.objects.create(title="M3 Corpus", creator=self.user)
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.ALL])

    def test_restore_when_path_reused(self):
        # Import, soft-delete, then upload a NEW doc to the same path.
        _, _, p1 = import_document(
            corpus=self.corpus, path="/report.pdf", content=b"v1", user=self.user
        )
        tombstone = delete_document(self.corpus, "/report.pdf", self.user)
        new_doc, status, p_new = import_document(
            corpus=self.corpus, path="/report.pdf", content=b"v2", user=self.user
        )
        self.assertEqual(status, "created")

        # Restoring the trashed doc must not collide — it lands on a fresh path.
        ok, err = DocumentLifecycleService.restore_document(
            user=self.user, document_path=tombstone
        )
        self.assertTrue(ok, err)

        active = set(_active_paths(self.corpus).values_list("path", flat=True))
        self.assertIn("/report.pdf", active)  # the new upload
        self.assertIn("/report_1.pdf", active)  # the restored original
        self.assertEqual(len(active), 2)

    def test_low_level_restore_disambiguates(self):
        _, _, _ = import_document(
            corpus=self.corpus, path="/a.pdf", content=b"v1", user=self.user
        )
        delete_document(self.corpus, "/a.pdf", self.user)
        import_document(
            corpus=self.corpus, path="/a.pdf", content=b"v2", user=self.user
        )
        restored = restore_document(self.corpus, "/a.pdf", self.user)
        self.assertEqual(restored.path, "/a_1.pdf")
        self.assertTrue(restored.is_current)
        self.assertFalse(restored.is_deleted)


class VersionResolverTests(TestCase):
    """M4/M5/L1: version-metadata resolver correctness + query batching."""

    def setUp(self):
        self.user = User.objects.create_user(username="m4user", password="pw")
        self.other = User.objects.create_user(username="m4other", password="pw")
        self.corpus = Corpus.objects.create(title="M4 Corpus", creator=self.user)
        # Two content versions at one path.
        self.doc_v1, _, _ = import_document(
            corpus=self.corpus, path="/doc.pdf", content=b"v1", user=self.user
        )
        self.doc_v2, _, self.path_v2 = import_document(
            corpus=self.corpus, path="/doc.pdf", content=b"v2", user=self.user
        )
        self.corpus_gid = to_global_id("CorpusType", self.corpus.pk)

    def _doc_type(self):
        from config.graphql.document_types import DocumentType

        return DocumentType

    def test_version_number_and_last_modified_share_one_query(self):
        # M4: both resolvers read the same current path; with the request cache
        # they cost a single query total (was 2N before).
        DocumentType = self._doc_type()
        info = _fake_info(self.user)
        with CaptureQueriesContext(connection) as ctx:
            vnum = DocumentType.resolve_version_number(
                self.doc_v2, info, self.corpus_gid
            )
            DocumentType.resolve_last_modified(self.doc_v2, info, self.corpus_gid)
        self.assertEqual(vnum, 2)
        self.assertEqual(len(ctx.captured_queries), 1)

    def test_has_version_history_zero_queries(self):
        # L1: parent_id check must not fetch the parent row.
        DocumentType = self._doc_type()
        info = _fake_info(self.user)
        with CaptureQueriesContext(connection) as ctx:
            has_history = DocumentType.resolve_has_version_history(self.doc_v2, info)
        self.assertTrue(has_history)
        self.assertEqual(len(ctx.captured_queries), 0)

        with CaptureQueriesContext(connection) as ctx:
            no_history = DocumentType.resolve_has_version_history(self.doc_v1, info)
        self.assertFalse(no_history)
        self.assertEqual(len(ctx.captured_queries), 0)

    def test_version_history_scoped_to_visible_user(self):
        # M5: the owner sees both versions; an unauthorised user sees none.
        DocumentType = self._doc_type()

        owner_history = DocumentType.resolve_version_history(
            self.doc_v2, _fake_info(self.user)
        )
        self.assertEqual(len(owner_history["versions"]), 2)

        other_history = DocumentType.resolve_version_history(
            self.doc_v2, _fake_info(self.other)
        )
        self.assertEqual(
            len(other_history["versions"]),
            0,
            "Version metadata must not leak to a user who cannot see the docs.",
        )


class GetDocumentFolderRobustnessTests(TestCase):
    """L2: get_document_folder tolerates >1 active path without crashing."""

    def setUp(self):
        self.user = User.objects.create_user(username="l2user", password="pw")
        self.corpus = Corpus.objects.create(title="L2 Corpus", creator=self.user)
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.ALL])

    def test_two_active_paths_does_not_raise(self):
        folder = CorpusFolder.objects.create(
            name="F", corpus=self.corpus, creator=self.user
        )
        doc, _, p1 = import_document(
            corpus=self.corpus,
            path="/in_folder.pdf",
            content=b"x",
            user=self.user,
            folder=folder,
        )
        # Forge a SECOND active path for the same (corpus, document) at a
        # different path string — allowed by the (corpus, path) unique index.
        DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            folder=None,
            path="/forged_root.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )

        # Must not raise MultipleObjectsReturned.
        result = FolderDocumentService.get_document_folder(
            user=self.user, document=doc, corpus=self.corpus
        )
        # Deterministically returns the newest active path's folder.
        self.assertIn(result, {None, folder})


class FilesystemAtTimeScopingTests(TestCase):
    """L3: get_filesystem_at_time is scoped to the target corpus."""

    def setUp(self):
        self.user = User.objects.create_user(username="l3user", password="pw")
        self.corpus_a = Corpus.objects.create(title="A", creator=self.user)
        self.corpus_b = Corpus.objects.create(title="B", creator=self.user)

    def test_only_target_corpus_paths_returned(self):
        # Same path string in two different corpuses.
        import_document(
            corpus=self.corpus_a, path="/shared.pdf", content=b"a", user=self.user
        )
        import_document(
            corpus=self.corpus_b, path="/shared.pdf", content=b"b", user=self.user
        )
        snapshot = get_filesystem_at_time(
            self.corpus_a, timezone.now() + timedelta(seconds=1)
        )
        rows = list(snapshot)
        self.assertEqual(len(rows), 1)
        self.assertTrue(all(r.corpus_id == self.corpus_a.id for r in rows))
        self.assertEqual(rows[0].path, "/shared.pdf")
