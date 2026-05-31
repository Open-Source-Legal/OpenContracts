"""
Tests for ``utils/caml_rewrite.py`` and its integration with the V2 corpus
importer.

Bulk-import zips can include a corpus README (CAML) that references
documents and annotations in the same zip via ``oc-import://`` placeholder
URLs.  These tests cover:

- Pure unit tests of ``rewrite_oc_import_links`` for the supported syntax,
  edge cases, and unresolved-reference behaviour.
- Integration with ``import_md_description_revisions`` so the importer
  actually applies the rewrite when the maps are passed through.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.annotations.models import (
    TOKEN_LABEL,
    Annotation,
    AnnotationLabel,
    LabelSet,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.utils.caml_rewrite import rewrite_oc_import_links
from opencontractserver.utils.import_v2 import import_md_description_revisions

User = get_user_model()


class TestCamlRewriteUnit(TestCase):
    """Unit tests for ``rewrite_oc_import_links``."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="caml_user",
            password="testpass",
            slug="caml-user",
        )

        self.labelset = LabelSet.objects.create(
            title="LS",
            creator=self.user,
        )
        self.label = AnnotationLabel.objects.create(
            text="Clause",
            label_type=TOKEN_LABEL,
            creator=self.user,
        )

        self.corpus = Corpus.objects.create(
            title="My Corpus",
            label_set=self.labelset,
            creator=self.user,
            slug="my-corpus",
        )

        self.doc = Document.objects.create(
            title="Lease",
            creator=self.user,
            page_count=1,
            slug="lease",
        )

        self.annotation = Annotation.objects.create(
            document=self.doc,
            corpus=self.corpus,
            annotation_label=self.label,
            raw_text="Important clause",
            creator=self.user,
        )

    def test_rewrites_document_reference_to_slug_url(self):
        content = (
            "See [the lease](oc-import://document/documents/lease.pdf) " "for context."
        )

        rewritten, stats = rewrite_oc_import_links(
            content=content,
            corpus=self.corpus,
            doc_filename_to_doc={"documents/lease.pdf": self.doc},
            annot_old_id_to_new_pk={},
        )

        self.assertIn("[the lease](/d/caml-user/my-corpus/lease)", rewritten)
        self.assertEqual(stats["documents_resolved"], 1)
        self.assertEqual(stats["documents_unresolved"], 0)

    def test_rewrites_annotation_reference_with_query_param(self):
        content = (
            "See [this clause]"
            "(oc-import://annotation/old-42) for the operative text."
        )

        rewritten, stats = rewrite_oc_import_links(
            content=content,
            corpus=self.corpus,
            doc_filename_to_doc={},
            annot_old_id_to_new_pk={"old-42": self.annotation.pk},
        )

        expected_url = f"/d/caml-user/my-corpus/lease?ann={self.annotation.pk}"
        self.assertIn(f"[this clause]({expected_url})", rewritten)
        self.assertEqual(stats["annotations_resolved"], 1)

    def test_accepts_int_keys_in_annotation_map(self):
        # The export side emits ``"id": f"{annot.id}"`` (string), but the
        # caller may pre-cast to int.  We must accept both.
        content = "[c](oc-import://annotation/7)"

        rewritten, stats = rewrite_oc_import_links(
            content=content,
            corpus=self.corpus,
            doc_filename_to_doc={},
            annot_old_id_to_new_pk={7: self.annotation.pk},
        )

        self.assertIn(f"?ann={self.annotation.pk})", rewritten)
        self.assertEqual(stats["annotations_resolved"], 1)

    def test_unresolved_document_ref_is_left_unchanged(self):
        content = "[ghost](oc-import://document/missing.pdf) tail"

        rewritten, stats = rewrite_oc_import_links(
            content=content,
            corpus=self.corpus,
            doc_filename_to_doc={},
            annot_old_id_to_new_pk={},
        )

        self.assertIn("oc-import://document/missing.pdf", rewritten)
        self.assertEqual(stats["documents_unresolved"], 1)
        self.assertEqual(stats["documents_resolved"], 0)

    def test_unresolved_annotation_ref_is_left_unchanged(self):
        content = "[ghost](oc-import://annotation/9999)"

        rewritten, stats = rewrite_oc_import_links(
            content=content,
            corpus=self.corpus,
            doc_filename_to_doc={},
            annot_old_id_to_new_pk={},
        )

        self.assertIn("oc-import://annotation/9999", rewritten)
        self.assertEqual(stats["annotations_unresolved"], 1)

    def test_annotation_pk_in_map_but_row_missing_is_left_unchanged(self):
        # The id map points at a PK whose Annotation row no longer exists
        # (e.g., deleted between import and rewrite).  The reference must
        # be left intact and counted as unresolved rather than blowing up.
        missing_pk = self.annotation.pk + 999_999
        content = "[orphan](oc-import://annotation/old-99)"

        rewritten, stats = rewrite_oc_import_links(
            content=content,
            corpus=self.corpus,
            doc_filename_to_doc={},
            annot_old_id_to_new_pk={"old-99": missing_pk},
        )

        self.assertIn("oc-import://annotation/old-99", rewritten)
        self.assertEqual(stats["annotations_unresolved"], 1)
        self.assertEqual(stats["annotations_resolved"], 0)

    def test_non_oc_import_links_are_passthrough(self):
        content = (
            "Plain [external](https://example.com/foo) "
            "and [inline](#anchor) — both should survive."
        )

        rewritten, stats = rewrite_oc_import_links(
            content=content,
            corpus=self.corpus,
            doc_filename_to_doc={"documents/lease.pdf": self.doc},
            annot_old_id_to_new_pk={"7": self.annotation.pk},
        )

        self.assertEqual(rewritten, content)
        self.assertEqual(stats["documents_resolved"], 0)
        self.assertEqual(stats["annotations_resolved"], 0)

    def test_handles_leading_dot_slash_in_doc_ref(self):
        content = "[a](oc-import://document/./documents/lease.pdf)"

        rewritten, stats = rewrite_oc_import_links(
            content=content,
            corpus=self.corpus,
            doc_filename_to_doc={"documents/lease.pdf": self.doc},
            annot_old_id_to_new_pk={},
        )

        self.assertIn("/d/caml-user/my-corpus/lease", rewritten)
        self.assertEqual(stats["documents_resolved"], 1)

    def test_empty_content_returns_empty(self):
        rewritten, stats = rewrite_oc_import_links(
            content="",
            corpus=self.corpus,
            doc_filename_to_doc={},
            annot_old_id_to_new_pk={},
        )
        self.assertEqual(rewritten, "")
        self.assertEqual(stats["documents_resolved"], 0)

    def test_mixed_document_and_annotation_refs_in_one_doc(self):
        content = (
            "Intro paragraph.\n\n"
            "Full text: [contract](oc-import://document/documents/lease.pdf).\n"
            "Key clause: [clause](oc-import://annotation/old-42).\n"
        )

        rewritten, stats = rewrite_oc_import_links(
            content=content,
            corpus=self.corpus,
            doc_filename_to_doc={"documents/lease.pdf": self.doc},
            annot_old_id_to_new_pk={"old-42": self.annotation.pk},
        )

        self.assertIn("/d/caml-user/my-corpus/lease)", rewritten)
        self.assertIn(f"?ann={self.annotation.pk})", rewritten)
        self.assertEqual(stats["documents_resolved"], 1)
        self.assertEqual(stats["annotations_resolved"], 1)


class TestImportMdDescriptionRewriteIntegration(TestCase):
    """``import_md_description_revisions`` should apply the rewrite when the
    maps are supplied (the bulk-import path)."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="caml_user2",
            password="testpass",
            slug="caml-user2",
        )
        self.labelset = LabelSet.objects.create(title="LS2", creator=self.user)
        self.label = AnnotationLabel.objects.create(
            text="Clause",
            label_type=TOKEN_LABEL,
            creator=self.user,
        )
        self.corpus = Corpus.objects.create(
            title="C2",
            label_set=self.labelset,
            creator=self.user,
            slug="c2",
        )
        self.doc = Document.objects.create(
            title="Lease",
            creator=self.user,
            page_count=1,
            slug="lease2",
        )
        self.annot = Annotation.objects.create(
            document=self.doc,
            corpus=self.corpus,
            annotation_label=self.label,
            raw_text="Operative",
            creator=self.user,
        )

    def test_rewrite_applied_when_maps_supplied(self):
        """Maps supplied → ``oc-import://`` URLs rewritten before the
        Readme.CAML Document is synthesized."""
        from opencontractserver.corpuses.services.description_cache import (
            read_caml_body,
        )

        md = (
            "# README\n\n"
            "[doc](oc-import://document/documents/lease.pdf)\n"
            "[ann](oc-import://annotation/123)\n"
        )

        import_md_description_revisions(
            md_description=md,
            revisions_data=[],
            corpus=self.corpus,
            user_obj=self.user,
            doc_filename_to_doc={"documents/lease.pdf": self.doc},
            annot_old_id_to_new_pk={"123": self.annot.pk},
        )

        # Post-Task 14 the canonical body lives on the synthesized
        # Readme.CAML Document, not on the legacy ``md_description``
        # FileField.
        self.corpus.refresh_from_db()
        head = self.corpus.readme_caml_document
        self.assertIsNotNone(head)
        saved = read_caml_body(head)

        self.assertIn("/d/caml-user2/c2/lease2", saved)
        self.assertIn(f"?ann={self.annot.pk}", saved)
        self.assertNotIn("oc-import://", saved)

    def test_rewrite_skipped_when_maps_omitted(self):
        """No maps passed → content lands verbatim on the synthesized
        Readme.CAML body (no rewrite step runs)."""
        from opencontractserver.corpuses.services.description_cache import (
            read_caml_body,
        )

        md = "# README\n\n" "[doc](oc-import://document/documents/lease.pdf)\n"

        import_md_description_revisions(
            md_description=md,
            revisions_data=[],
            corpus=self.corpus,
            user_obj=self.user,
        )

        self.corpus.refresh_from_db()
        head = self.corpus.readme_caml_document
        self.assertIsNotNone(head)
        saved = read_caml_body(head)
        self.assertEqual(saved, md)
