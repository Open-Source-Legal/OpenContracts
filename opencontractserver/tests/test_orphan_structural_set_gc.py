"""Regression tests for the orphan StructuralAnnotationSet GC signal.

A StructuralAnnotationSet is shared by every Document with the same
content_hash. The reverse FK uses ``on_delete=PROTECT`` so the set
cannot be deleted while a Document references it, but Django doesn't
trigger any cascade in the *other* direction — deleting the last
Document referencing a set silently orphans the set and its
annotations.

Without GC, repeated Document churn (benchmark harness restarts,
bulk re-imports, …) leaks structural sets indefinitely. The vector
store sees the orphans and returns them on retrieval, double-counting
spans and breaking metrics — see PR #1380 audit thread for the
incident this regression test is locking down.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from django.utils import timezone

from opencontractserver.annotations.models import (
    Annotation,
    StructuralAnnotationSet,
)
from opencontractserver.documents.models import Document

User = get_user_model()


class OrphanStructuralSetGCTests(TransactionTestCase):
    """The post_delete signal must clean up sets with zero remaining refs."""

    def setUp(self) -> None:
        self.user = User.objects.create(username="orphan-gc-user")

    def _make_set_with_annotation(self, content_hash: str) -> StructuralAnnotationSet:
        ss = StructuralAnnotationSet.objects.create(
            content_hash=content_hash,
            parser_name="test",
            creator=self.user,
        )
        Annotation.objects.create(
            structural_set=ss,
            structural=True,
            json={"start": 0, "end": 10},
            raw_text="abc",
            creator=self.user,
        )
        return ss

    def _make_doc(self, ss: StructuralAnnotationSet, *, title: str) -> Document:
        # ``processing_started`` short-circuits the
        # ``process_doc_on_create_atomic`` post_save handler, which would
        # otherwise eagerly chain a celery PDF-ingest task that fails on
        # this file-less test fixture and aborts the whole class. Same
        # pattern documented for ``test_pydantic_ai_agents.py`` /
        # ``test_structural_annotation_portability.py``.
        return Document.objects.create(
            title=title,
            description="",
            structural_annotation_set=ss,
            creator=self.user,
            processing_started=timezone.now(),
        )

    def test_last_document_delete_gcs_orphan_set(self) -> None:
        ss = self._make_set_with_annotation("hash_solo")
        doc = self._make_doc(ss, title="solo")
        ss_id = ss.id

        doc.delete()

        self.assertFalse(
            StructuralAnnotationSet.objects.filter(pk=ss_id).exists(),
            "Set should be GC'd when its last referencing Document is deleted",
        )
        self.assertFalse(
            Annotation.objects.filter(structural_set_id=ss_id).exists(),
            "Set's structural annotations should cascade-delete with the set",
        )

    def test_set_survives_while_other_document_references_it(self) -> None:
        ss = self._make_set_with_annotation("hash_shared")
        doc_a = self._make_doc(ss, title="shared-a")
        self._make_doc(ss, title="shared-b")  # second Document keeps ss alive

        doc_a.delete()

        self.assertTrue(
            StructuralAnnotationSet.objects.filter(pk=ss.id).exists(),
            "Set must remain alive while another Document still references it",
        )
        self.assertEqual(
            Annotation.objects.filter(structural_set_id=ss.id).count(),
            1,
            "Set's annotations must remain intact while any Document references it",
        )

    def test_documents_without_structural_set_are_safe_to_delete(self) -> None:
        # ``structural_annotation_set`` is nullable; deleting a Document
        # that never had one must not crash the GC signal.
        doc = Document.objects.create(
            title="bare",
            description="",
            creator=self.user,
            processing_started=timezone.now(),
        )
        doc.delete()  # must not raise


class CleanupCommandTests(TransactionTestCase):
    """Backfill command for the existing-orphans case."""

    def setUp(self) -> None:
        self.user = User.objects.create(username="cleanup-cmd-user")

    def test_command_deletes_only_orphans(self) -> None:
        # One orphan, one alive
        orphan = StructuralAnnotationSet.objects.create(
            content_hash="orphan_a", parser_name="t", creator=self.user
        )
        alive = StructuralAnnotationSet.objects.create(
            content_hash="alive_a", parser_name="t", creator=self.user
        )
        Document.objects.create(
            title="alive-doc",
            description="",
            structural_annotation_set=alive,
            creator=self.user,
            processing_started=timezone.now(),
        )

        from django.core.management import call_command

        call_command("cleanup_orphan_structural_sets")

        self.assertFalse(StructuralAnnotationSet.objects.filter(pk=orphan.id).exists())
        self.assertTrue(StructuralAnnotationSet.objects.filter(pk=alive.id).exists())

    def test_command_dry_run_makes_no_changes(self) -> None:
        orphan = StructuralAnnotationSet.objects.create(
            content_hash="dry_orphan", parser_name="t", creator=self.user
        )
        from django.core.management import call_command

        call_command("cleanup_orphan_structural_sets", "--dry-run")

        self.assertTrue(
            StructuralAnnotationSet.objects.filter(pk=orphan.id).exists(),
            "--dry-run must not delete anything",
        )
