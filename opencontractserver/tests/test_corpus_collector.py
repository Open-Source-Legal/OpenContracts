from django.test import TestCase

from opencontractserver.analyzer.models import Analysis, Analyzer
from opencontractserver.annotations.models import Annotation, LabelSet, Relationship
from opencontractserver.corpuses.models import Corpus, CorpusFolder
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.extracts.models import Column, Datacell, Fieldset
from opencontractserver.users.models import User
from opencontractserver.utils.corpus_collector import (
    CorpusObjectCollection,
    collect_corpus_objects,
)


class TestCollectCorpusObjects(TestCase):
    """Tests for the shared collect_corpus_objects utility."""

    user: User

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="collector_user", password="pass")

    def _make_corpus(self, title="Test Corpus", with_label_set=True):
        """Create a corpus, optionally with a label set."""
        label_set = None
        if with_label_set:
            label_set = LabelSet.objects.create(
                title=f"LS for {title}", creator=self.user
            )
        return Corpus.objects.create(
            title=title, creator=self.user, label_set=label_set
        )

    def _add_document(self, corpus, title="Doc", path="/doc"):
        """Create a document and attach it to the corpus via DocumentPath."""
        doc = Document.objects.create(title=title, creator=self.user)
        DocumentPath.objects.create(
            document=doc,
            corpus=corpus,
            path=path,
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )
        return doc

    def test_empty_corpus(self):
        """An empty corpus should return empty collections."""
        corpus = self._make_corpus("Empty Corpus", with_label_set=False)
        result = collect_corpus_objects(corpus)

        self.assertIsInstance(result, CorpusObjectCollection)
        self.assertEqual(result.document_ids, [])
        self.assertEqual(result.annotation_ids, [])
        self.assertIsNone(result.label_set_id)
        self.assertEqual(result.folder_ids, [])
        self.assertEqual(result.relationship_ids, [])
        self.assertEqual(result.metadata_column_ids, [])
        self.assertEqual(result.metadata_datacell_ids, [])

    def test_collects_active_documents(self):
        """Active (is_current=True, is_deleted=False) documents are collected."""
        corpus = self._make_corpus()
        doc1 = self._add_document(corpus, "Doc1", "/doc1")
        doc2 = self._add_document(corpus, "Doc2", "/doc2")

        # Deleted document should NOT appear
        deleted_doc = Document.objects.create(title="Deleted", creator=self.user)
        DocumentPath.objects.create(
            document=deleted_doc,
            corpus=corpus,
            path="/deleted",
            version_number=1,
            is_current=True,
            is_deleted=True,
            creator=self.user,
        )

        # Historical (non-current) should NOT appear
        historical_doc = Document.objects.create(title="Historical", creator=self.user)
        DocumentPath.objects.create(
            document=historical_doc,
            corpus=corpus,
            path="/historical",
            version_number=1,
            is_current=False,
            is_deleted=False,
            creator=self.user,
        )

        result = collect_corpus_objects(corpus)
        self.assertCountEqual(result.document_ids, [doc1.id, doc2.id])

    def test_document_ids_are_distinct(self):
        """Defensive coverage for data integrity bugs upstream.

        Multiple active DocumentPaths for the same document should still
        produce a single ID in the collected results.
        """
        corpus = self._make_corpus()
        doc = Document.objects.create(title="Shared Doc", creator=self.user)

        # Two is_current=True DocumentPath records for the same document is not
        # a normal application state; this is defensive coverage for data
        # integrity bugs upstream to ensure collect_corpus_objects de-duplicates.
        DocumentPath.objects.create(
            document=doc,
            corpus=corpus,
            path="/path-a",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )
        DocumentPath.objects.create(
            document=doc,
            corpus=corpus,
            path="/path-b",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )

        result = collect_corpus_objects(corpus)
        self.assertEqual(result.document_ids, [doc.id])

    def test_excludes_analysis_annotations(self):
        """Only user-created annotations (analysis=NULL) are collected."""
        corpus = self._make_corpus()
        doc = self._add_document(corpus)

        # User-created annotation
        user_annot = Annotation.objects.create(
            corpus=corpus,
            document=doc,
            raw_text="user annotation",
            creator=self.user,
            analysis=None,
        )

        # Analysis-generated annotation
        analyzer = Analyzer.objects.create(
            id="test-analyzer",
            description="Test",
            creator=self.user,
            task_name="test_task_annot",
        )
        analysis = Analysis.objects.create(
            analyzer=analyzer,
            analyzed_corpus=corpus,
            creator=self.user,
        )
        Annotation.objects.create(
            corpus=corpus,
            document=doc,
            raw_text="analysis annotation",
            creator=self.user,
            analysis=analysis,
        )

        result = collect_corpus_objects(corpus)
        self.assertEqual(result.annotation_ids, [user_annot.id])

    def test_excludes_analysis_relationships(self):
        """Only user-created relationships (analysis=NULL) are collected."""
        corpus = self._make_corpus()
        doc = self._add_document(corpus)

        # User relationship
        user_rel = Relationship.objects.create(
            corpus=corpus,
            document=doc,
            creator=self.user,
            analysis=None,
        )

        # Analysis relationship
        analyzer = Analyzer.objects.create(
            id="test-analyzer-rel",
            description="Test",
            creator=self.user,
            task_name="test_task_rel",
        )
        analysis = Analysis.objects.create(
            analyzer=analyzer,
            analyzed_corpus=corpus,
            creator=self.user,
        )
        Relationship.objects.create(
            corpus=corpus,
            document=doc,
            creator=self.user,
            analysis=analysis,
        )

        result = collect_corpus_objects(corpus)
        self.assertEqual(result.relationship_ids, [user_rel.id])

    def test_collects_label_set_id(self):
        """The label set ID is captured when present."""
        corpus = self._make_corpus()
        result = collect_corpus_objects(corpus)
        self.assertEqual(result.label_set_id, corpus.label_set.pk)

    def test_no_label_set(self):
        """label_set_id is None when corpus has no label set."""
        corpus = self._make_corpus(with_label_set=False)
        result = collect_corpus_objects(corpus)
        self.assertIsNone(result.label_set_id)

    def test_collects_folders(self):
        """Folders belonging to the corpus are collected."""
        corpus = self._make_corpus()
        folder = CorpusFolder.objects.create(
            name="Folder A", corpus=corpus, creator=self.user
        )

        result = collect_corpus_objects(corpus)
        self.assertEqual(result.folder_ids, [folder.id])

    def test_folder_tree_ordering_parents_before_children(self):
        """with_tree_fields() ensures parents come before children in folder_ids."""
        corpus = self._make_corpus()
        parent = CorpusFolder.objects.create(
            name="Parent", corpus=corpus, creator=self.user
        )
        child = CorpusFolder.objects.create(
            name="Child", corpus=corpus, creator=self.user, parent=parent
        )

        result = collect_corpus_objects(corpus)
        self.assertEqual(result.folder_ids, [parent.id, child.id])

    def test_include_metadata_false_skips_metadata(self):
        """When include_metadata=False (default), metadata fields stay empty."""
        corpus = self._make_corpus()
        self._add_document(corpus)

        result = collect_corpus_objects(corpus)
        self.assertEqual(result.metadata_column_ids, [])
        self.assertEqual(result.metadata_datacell_ids, [])

    def test_include_metadata_true_collects_manual_columns(self):
        """When include_metadata=True, manual metadata columns are collected."""
        corpus = self._make_corpus()
        doc = self._add_document(corpus)

        # Create metadata schema (fieldset) linked to the corpus
        fieldset = Fieldset.objects.create(
            name="Metadata Schema",
            description="",
            creator=self.user,
            corpus=corpus,
        )

        manual_col = Column.objects.create(
            fieldset=fieldset,
            name="Manual Col",
            query="manual query",
            creator=self.user,
            is_manual_entry=True,
            data_type="TEXT",
            output_type="str",
        )
        Column.objects.create(
            fieldset=fieldset,
            name="Auto Col",
            query="auto query",
            creator=self.user,
            is_manual_entry=False,
        )

        # Create a manual datacell
        datacell = Datacell.objects.create(
            column=manual_col,
            document=doc,
            creator=self.user,
            extract=None,
            data_definition="manual metadata entry",
        )

        result = collect_corpus_objects(corpus, include_metadata=True)
        self.assertEqual(result.metadata_column_ids, [manual_col.id])
        self.assertEqual(result.metadata_datacell_ids, [datacell.id])

    def test_does_not_collect_other_corpus_objects(self):
        """Objects from a different corpus are not included."""
        corpus_a = self._make_corpus("Corpus A")
        corpus_b = self._make_corpus("Corpus B")

        doc_a = self._add_document(corpus_a, "Doc A", "/a")
        self._add_document(corpus_b, "Doc B", "/b")

        Annotation.objects.create(
            corpus=corpus_a,
            document=doc_a,
            raw_text="annot A",
            creator=self.user,
        )

        result = collect_corpus_objects(corpus_b)
        # corpus_b has one doc but no annotations
        self.assertEqual(len(result.document_ids), 1)
        self.assertEqual(result.annotation_ids, [])
