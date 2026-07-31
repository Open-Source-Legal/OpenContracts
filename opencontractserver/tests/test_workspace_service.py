"""Tests for ``WorkspaceService`` — generated artifacts into a user's workspace."""

from __future__ import annotations

from django.test import TestCase

from opencontractserver.corpuses.models import Corpus, CorpusFolder
from opencontractserver.corpuses.services import WorkspaceService
from opencontractserver.documents.models import DocumentPath
from opencontractserver.users.models import User


class WorkspaceServiceTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="workspace-user", password="x")

    # ``_get_active_documents`` defaults to ``include_caml=False`` — markdown is
    # hidden from extractors and analyzers, which must not run over a CAML
    # article. The user-facing listing does the opposite: the GraphQL
    # ``CorpusType.documents`` resolver passes ``include_caml=True``, so a saved
    # report IS visible in the workspace. These assertions mirror the resolver.

    def _read(self, document) -> str:
        document.txt_extract_file.open("rb")
        try:
            return document.txt_extract_file.read().decode("utf-8")
        finally:
            document.txt_extract_file.close()

    def test_saves_into_the_users_personal_corpus(self):
        document = WorkspaceService.save_markdown(
            user=self.user,
            title="Quarterly Note",
            content="# Quarterly Note\n\nBody.",
        )

        personal = Corpus.objects.get(creator=self.user, is_personal=True)
        self.assertIn(
            document.pk,
            personal._get_active_documents(include_caml=True).values_list(
                "pk", flat=True
            ),
        )
        self.assertEqual(document.creator_id, self.user.pk)
        self.assertEqual(document.file_type, "text/markdown")
        self.assertIn("Body.", self._read(document))

    def test_creates_the_personal_corpus_when_absent(self):
        # The user post_save signal provisions one; deleting it proves the
        # service does not depend on that having happened.
        Corpus.objects.filter(creator=self.user, is_personal=True).delete()
        self.assertFalse(
            Corpus.objects.filter(creator=self.user, is_personal=True).exists()
        )

        WorkspaceService.save_markdown(
            user=self.user, title="Recreated", content="text"
        )

        self.assertTrue(
            Corpus.objects.filter(creator=self.user, is_personal=True).exists()
        )

    def test_folder_is_created_once_across_saves(self):
        for title in ("First", "Second"):
            WorkspaceService.save_markdown(
                user=self.user,
                title=title,
                content="text",
                folder_name="Research Reports",
            )

        personal = Corpus.objects.get(creator=self.user, is_personal=True)
        folders = CorpusFolder.objects.filter(
            corpus=personal, name="Research Reports", parent=None
        )
        self.assertEqual(folders.count(), 1)
        self.assertEqual(personal._get_active_documents(include_caml=True).count(), 2)

    def test_second_save_versions_in_place_instead_of_duplicating(self):
        first = WorkspaceService.save_markdown(
            user=self.user,
            title="Living Report",
            content="draft one",
            folder_name="Research Reports",
            filename_stem="living-report",
        )
        second = WorkspaceService.save_markdown(
            user=self.user,
            title="Living Report",
            content="draft two",
            folder_name="Research Reports",
            filename_stem="living-report",
        )

        self.assertNotEqual(first.pk, second.pk)
        # Same version tree, one current head, prior text still retrievable.
        self.assertEqual(first.version_tree_id, second.version_tree_id)
        first.refresh_from_db()
        self.assertFalse(first.is_current)
        self.assertTrue(second.is_current)
        self.assertEqual(self._read(first), "draft one")
        self.assertEqual(self._read(second), "draft two")

        personal = Corpus.objects.get(creator=self.user, is_personal=True)
        current_paths = DocumentPath.objects.filter(
            corpus=personal, is_current=True, is_deleted=False
        )
        self.assertEqual(current_paths.count(), 1)
        self.assertEqual(current_paths.first().version_number, 2)

    def test_titles_with_separators_cannot_invent_folders(self):
        """A generated title must not be able to escape its path segment."""
        document = WorkspaceService.save_markdown(
            user=self.user,
            title="Q3 / Q4: ../../escape attempt",
            content="text",
            folder_name="Research Reports",
        )

        personal = Corpus.objects.get(creator=self.user, is_personal=True)
        path = (
            DocumentPath.objects.filter(document=document, corpus=personal)
            .values_list("path", flat=True)
            .first()
        )
        # Exactly one level below the declared folder, whatever the title said.
        self.assertEqual(path.strip("/").count("/"), 1)
        self.assertTrue(path.strip("/").startswith("Research Reports/"))
        self.assertNotIn("..", path)

    def test_two_users_get_separate_workspaces(self):
        other = User.objects.create_user(username="other-workspace", password="x")

        mine = WorkspaceService.save_markdown(
            user=self.user, title="Shared Name", content="mine"
        )
        theirs = WorkspaceService.save_markdown(
            user=other, title="Shared Name", content="theirs"
        )

        self.assertNotEqual(mine.pk, theirs.pk)
        my_corpus = Corpus.objects.get(creator=self.user, is_personal=True)
        their_corpus = Corpus.objects.get(creator=other, is_personal=True)
        self.assertNotEqual(my_corpus.pk, their_corpus.pk)
        self.assertEqual(my_corpus._get_active_documents(include_caml=True).count(), 1)
        self.assertEqual(
            their_corpus._get_active_documents(include_caml=True).count(), 1
        )


class CorpusDocumentCountTestCase(TestCase):
    """``document_count`` must exclude the CAML article — and nothing else.

    Excluding every markdown document was equivalent while a corpus's only
    markdown was its landing article. Once generated artifacts (saved chat
    answers, research reports) became real documents, a personal workspace
    reported "0 documents" while listing files — the first thing a user sees
    when they open their workspace.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="count-user", password="x")
        self.corpus = Corpus.objects.create(
            title="Counted Corpus", creator=self.user, is_public=False
        )

    def _add(self, title: str, file_type: str = "text/markdown"):
        from opencontractserver.documents.versioning import import_document

        document, _status, _path = import_document(
            corpus=self.corpus,
            path=f"{title}.md" if file_type == "text/markdown" else title,
            content=b"body",
            user=self.user,
            file_type=file_type,
            title=title,
        )
        return document

    def test_saved_markdown_artifacts_are_counted(self):
        self.assertEqual(self.corpus.document_count(), 0)
        self._add("Saved chat answer")
        self.assertEqual(self.corpus.document_count(), 1)

    def test_the_caml_article_is_not_counted(self):
        from opencontractserver.constants.document_processing import (
            CAML_ARTICLE_TITLE,
        )

        self._add(CAML_ARTICLE_TITLE)
        self.assertEqual(self.corpus.document_count(), 0)

        # ...but a saved artifact alongside it still is.
        self._add("Saved chat answer")
        self.assertEqual(self.corpus.document_count(), 1)

    def test_list_annotation_and_model_method_agree(self):
        """The list and detail views must not disagree about the same number.

        ``_corpus_count_subqueries`` (list) and ``Corpus.document_count()``
        (detail) answer the same question through different SQL; they share one
        predicate precisely so they cannot drift apart.
        """
        from django.db.models import Subquery
        from django.db.models.functions import Coalesce

        from config.graphql.corpus_queries import _corpus_count_subqueries
        from opencontractserver.constants.document_processing import (
            CAML_ARTICLE_TITLE,
        )

        self._add(CAML_ARTICLE_TITLE)
        self._add("Saved chat answer")
        self._add("Another saved answer")

        doc_sq, _annot_sq = _corpus_count_subqueries()
        annotated = (
            Corpus.objects.filter(pk=self.corpus.pk)
            .annotate(_document_count=Coalesce(Subquery(doc_sq), 0))
            .first()
        )
        self.assertEqual(annotated._document_count, self.corpus.document_count())
        self.assertEqual(annotated._document_count, 2)
