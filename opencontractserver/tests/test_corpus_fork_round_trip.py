"""
Round-trip tests for corpus forking functionality.

These tests validate that forking is lossless (or intentionally lossy with documented
exclusions) by creating corpuses with known data, forking them through multiple
generations, and comparing data integrity at each step.

Test Philosophy:
    1. Create a corpus with comprehensive test data
    2. Fork it (generation 1)
    3. Compare fork to original
    4. Fork the fork (generation 2)
    5. Compare generation 2 to generation 1
    6. Repeat for N generations and detect degradation

Run with:
    docker compose -f test.yml run django pytest opencontractserver/tests/test_corpus_fork_round_trip.py -v
"""

import logging
from dataclasses import dataclass
from typing import Optional, cast

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase
from django.utils import timezone

from opencontractserver.annotations.models import (
    RELATIONSHIP_LABEL,
    TOKEN_LABEL,
    Annotation,
    AnnotationLabel,
    LabelSet,
    Note,
    Relationship,
    StructuralAnnotationSet,
)
from opencontractserver.corpuses.models import Corpus, CorpusFolder
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.extracts.models import Column, Datacell, Fieldset
from opencontractserver.tasks.fork_tasks import fork_corpus
from opencontractserver.tests._corpus_fixture import _MINIMAL_PDF_BYTES
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()
logger = logging.getLogger(__name__)


@dataclass
class CorpusSnapshot:
    """Captures the state of a corpus for comparison."""

    corpus_id: int
    title: str
    document_count: int
    annotation_count: int
    relationship_count: int
    label_count: int
    folder_count: int
    note_count: int

    # Detailed data for integrity checks
    document_titles: set[str]
    annotation_texts: set[str]
    label_texts: set[str]
    folder_names: set[str]
    note_titles: set[str]
    relationship_label_texts: set[str]

    # Metadata fields
    has_description: bool
    has_icon: bool
    has_label_set: bool

    @classmethod
    def from_corpus(cls, corpus: Corpus) -> "CorpusSnapshot":
        """Create a snapshot from a corpus."""
        # Get documents via get_documents() to respect DocumentPath
        documents = corpus._get_active_documents()

        # Get user annotations (not analysis-generated)
        annotations = Annotation.objects.filter(
            corpus_id=corpus.pk,
            analysis__isnull=True,
        )

        # Get relationships (not analysis-generated)
        relationships = Relationship.objects.filter(
            corpus_id=corpus.pk,
            analysis__isnull=True,
        )

        # Get folders
        folders = CorpusFolder.objects.filter(corpus_id=corpus.pk)

        # Get notes for documents in corpus
        doc_ids = documents.values_list("id", flat=True)
        notes = Note.objects.filter(document_id__in=doc_ids)

        # Get labels if label set exists
        labels = []
        if corpus.label_set:
            labels = corpus.label_set.annotation_labels.all()

        return cls(
            corpus_id=corpus.pk,
            title=corpus.title,
            document_count=documents.count(),
            annotation_count=annotations.count(),
            relationship_count=relationships.count(),
            label_count=len(labels),
            folder_count=folders.count(),
            note_count=notes.count(),
            # Document.title is nullable on the model, but every document in
            # these fork fixtures has a title; cast keeps the snapshot field a
            # plain set[str] without filtering at runtime.
            document_titles=cast(
                "set[str]", set(documents.values_list("title", flat=True))
            ),
            annotation_texts=set(annotations.values_list("raw_text", flat=True)),
            label_texts={label.text for label in labels},
            folder_names=set(folders.values_list("name", flat=True)),
            note_titles=set(notes.values_list("title", flat=True)),
            relationship_label_texts=set(
                relationships.exclude(relationship_label__isnull=True).values_list(
                    "relationship_label__text", flat=True
                )
            ),
            has_description=bool(corpus.description),
            has_icon=bool(corpus.icon and corpus.icon.name),
            has_label_set=corpus.label_set is not None,
        )

    def compare_to(
        self,
        other: "CorpusSnapshot",
        ignore_title_prefix: bool = True,
    ) -> list[str]:
        """
        Compare this snapshot to another and return list of differences.

        Args:
            other: The snapshot to compare against
            ignore_title_prefix: If True, ignore [FORK] prefix when comparing titles

        Returns:
            List of difference descriptions (empty if identical)
        """
        differences = []

        # Document count
        if self.document_count != other.document_count:
            differences.append(
                f"Document count: {self.document_count} vs {other.document_count}"
            )

        # Annotation count
        if self.annotation_count != other.annotation_count:
            differences.append(
                f"Annotation count: {self.annotation_count} vs {other.annotation_count}"
            )

        # Label count
        if self.label_count != other.label_count:
            differences.append(
                f"Label count: {self.label_count} vs {other.label_count}"
            )

        # Document titles (ignoring [FORK] prefix)
        def normalize_title(t: str) -> str:
            if ignore_title_prefix:
                return t.replace("[FORK] ", "")
            return t

        self_doc_titles = {normalize_title(t) for t in self.document_titles}
        other_doc_titles = {normalize_title(t) for t in other.document_titles}
        if self_doc_titles != other_doc_titles:
            missing = self_doc_titles - other_doc_titles
            extra = other_doc_titles - self_doc_titles
            if missing:
                differences.append(f"Missing document titles: {missing}")
            if extra:
                differences.append(f"Extra document titles: {extra}")

        # Annotation texts
        if self.annotation_texts != other.annotation_texts:
            missing = self.annotation_texts - other.annotation_texts
            extra = other.annotation_texts - self.annotation_texts
            if missing:
                differences.append(f"Missing annotation texts: {missing}")
            if extra:
                differences.append(f"Extra annotation texts: {extra}")

        # Label texts
        if self.label_texts != other.label_texts:
            missing = self.label_texts - other.label_texts
            extra = other.label_texts - self.label_texts
            if missing:
                differences.append(f"Missing label texts: {missing}")
            if extra:
                differences.append(f"Extra label texts: {extra}")

        return differences


class CorpusForkRoundTripTestCase(TestCase):
    """
    Round-trip tests for corpus forking.

    Tests validate that forking preserves data integrity across multiple generations.
    """

    def setUp(self):
        """Create test user."""
        self.user = User.objects.create_user(
            username="fork_test_user",
            password="testpass123",
        )

    def _create_test_corpus(
        self,
        title: str = "Test Corpus",
        num_documents: int = 3,
        num_annotations_per_doc: int = 2,
        num_relationships: int = 2,
        num_folders: int = 2,
        num_notes_per_doc: int = 1,
    ) -> Corpus:
        """
        Create a corpus with comprehensive test data.

        This creates a corpus with known data that can be validated after forking.
        """
        # Create label set with labels
        label_set = LabelSet.objects.create(
            title=f"{title} Labels",
            description="Test label set for fork testing",
            creator=self.user,
        )

        # Create token labels
        token_labels = []
        for i in range(3):
            label = AnnotationLabel.objects.create(
                text=f"Token Label {i}",
                label_type=TOKEN_LABEL,
                color=f"#{'0' * i}{'F' * (6-i)}",
                description=f"Test token label {i}",
                creator=self.user,
            )
            label_set.annotation_labels.add(label)
            token_labels.append(label)

        # Create relationship label
        rel_label = AnnotationLabel.objects.create(
            text="Related To",
            label_type=RELATIONSHIP_LABEL,
            color="#FF0000",
            description="Test relationship label",
            creator=self.user,
        )
        label_set.annotation_labels.add(rel_label)

        # Create corpus
        corpus = Corpus.objects.create(
            title=title,
            description=f"Test corpus for fork round-trip testing: {title}",
            label_set=label_set,
            creator=self.user,
            is_public=False,
        )
        set_permissions_for_obj_to_user(self.user, corpus, [PermissionTypes.CRUD])

        # Create folders
        folders = []
        root_folder = None
        for i in range(num_folders):
            folder = CorpusFolder.objects.create(
                name=f"Folder {i}",
                corpus=corpus,
                description=f"Test folder {i}",
                parent=root_folder if i > 0 else None,
                creator=self.user,
            )
            # Note: CorpusFolder inherits permissions from parent Corpus
            # No individual permissions needed
            folders.append(folder)
            if i == 0:
                root_folder = folder

        # Create documents
        documents = []
        # Fork now round-trips through V2 export/import which writes the
        # file into a ZIP and reads it back, so docs need real PDF bytes.
        # Reuses the shared minimal PDF from _corpus_fixture so the literal
        # only lives in one place.
        for i in range(num_documents):
            doc = Document.objects.create(
                title=f"Document {i}",
                description=f"Test document {i} for fork testing",
                pdf_file=ContentFile(_MINIMAL_PDF_BYTES, name=f"doc_{i}.pdf"),
                pdf_file_hash=f"fork_test_hash_{i}",
                file_type="application/pdf",
                page_count=1,
                creator=self.user,
                is_public=False,
                backend_lock=False,
                # processing_started set to bypass the parsing pipeline
                # signal (which would otherwise try to ingest the fake PDF).
                processing_started=timezone.now(),
            )
            set_permissions_for_obj_to_user(self.user, doc, [PermissionTypes.CRUD])

            # Add to corpus with folder assignment
            folder = folders[i % len(folders)] if folders else None

            # Create DocumentPath manually (since add_document has complex logic)
            path = f"/documents/doc_{doc.pk}"
            DocumentPath.objects.create(
                document=doc,
                corpus=corpus,
                folder=folder,
                path=path,
                version_number=1,
                is_current=True,
                is_deleted=False,
                creator=self.user,
            )
            # Document is already linked to corpus via DocumentPath above

            documents.append(doc)

            # Create annotations for this document
            annotations = []
            for j in range(num_annotations_per_doc):
                annotation = Annotation.objects.create(
                    page=1,
                    raw_text=f"Annotation text {i}-{j}",
                    json={
                        "v": 2,
                        "p": {"1": {"b": [0, 0, 1, 1], "t": str(j)}},
                    },
                    annotation_label=token_labels[j % len(token_labels)],
                    document=doc,
                    corpus=corpus,
                    creator=self.user,
                )
                set_permissions_for_obj_to_user(
                    self.user, annotation, [PermissionTypes.CRUD]
                )
                annotations.append(annotation)

            # Create notes for this document
            for k in range(num_notes_per_doc):
                note = Note.objects.create(
                    title=f"Note {i}-{k}",
                    content=f"Note content for document {i}, note {k}",
                    document=doc,
                    corpus=corpus,
                    page=1,
                    creator=self.user,
                )
                set_permissions_for_obj_to_user(self.user, note, [PermissionTypes.CRUD])

        # Create relationships between annotations
        all_annotations = list(
            Annotation.objects.filter(corpus=corpus, analysis__isnull=True)
        )
        for i in range(min(num_relationships, len(all_annotations) - 1)):
            source_ann = all_annotations[i]
            target_ann = all_annotations[i + 1]

            relationship = Relationship.objects.create(
                relationship_label=rel_label,
                corpus=corpus,
                document=source_ann.document,
                creator=self.user,
            )
            relationship.source_annotations.add(source_ann)
            relationship.target_annotations.add(target_ann)
            set_permissions_for_obj_to_user(
                self.user, relationship, [PermissionTypes.CRUD]
            )

        return corpus

    def _execute_fork(self, corpus: Corpus) -> Optional[Corpus]:
        """
        Execute a fork of the given corpus.

        Returns the forked corpus or None if fork failed.
        """
        # Collect fork data (mimicking the mutation logic)
        doc_ids = list(corpus._get_active_documents().values_list("id", flat=True))

        annotation_ids = list(
            Annotation.objects.filter(
                corpus_id=corpus.pk,
                analysis__isnull=True,
            ).values_list("id", flat=True)
        )

        label_set_id = corpus.label_set_id

        # Collect folder IDs (in tree order for proper parent mapping)
        # Note: with_tree_fields() provides default tree_ordering which ensures parents before children
        folder_ids = list(
            CorpusFolder.objects.filter(corpus_id=corpus.pk)
            .with_tree_fields()
            .values_list("id", flat=True)
        )

        # Collect relationship IDs (user relationships only)
        relationship_ids = list(
            Relationship.objects.filter(
                corpus_id=corpus.pk,
                analysis__isnull=True,
            ).values_list("id", flat=True)
        )

        # Create the forked corpus shell
        forked_corpus = Corpus.objects.create(
            title=f"[FORK] {corpus.title}",
            description=corpus.description,
            backend_lock=True,
            creator=self.user,
            parent_id=corpus.pk,
        )
        set_permissions_for_obj_to_user(
            self.user, forked_corpus, [PermissionTypes.CRUD]
        )

        # Execute the fork task synchronously
        result = fork_corpus(
            new_corpus_id=forked_corpus.pk,
            doc_ids=doc_ids,
            label_set_id=label_set_id,
            annotation_ids=annotation_ids,
            folder_ids=folder_ids,
            relationship_ids=relationship_ids,
            user_id=self.user.pk,
        )

        if result is None:
            return None

        # Refresh from database
        forked_corpus.refresh_from_db()
        return forked_corpus

    def test_single_fork_preserves_documents(self):
        """Test that a single fork preserves all documents."""
        original = self._create_test_corpus(
            title="Doc Preservation Test",
            num_documents=5,
            num_annotations_per_doc=0,
            num_relationships=0,
            num_folders=0,
            num_notes_per_doc=0,
        )
        original_snapshot = CorpusSnapshot.from_corpus(original)

        forked = self._execute_fork(original)
        self.assertIsNotNone(forked, "Fork should succeed")
        assert forked is not None

        forked_snapshot = CorpusSnapshot.from_corpus(forked)

        self.assertEqual(
            original_snapshot.document_count,
            forked_snapshot.document_count,
            "Document count should match",
        )

        differences = original_snapshot.compare_to(forked_snapshot)
        # Filter out expected differences (folders, notes, relationships not copied yet)
        doc_related_diffs = [d for d in differences if "document" in d.lower()]
        self.assertEqual(
            doc_related_diffs,
            [],
            f"Document-related differences found: {doc_related_diffs}",
        )

    def test_single_fork_preserves_annotations(self):
        """Test that a single fork preserves all user annotations."""
        original = self._create_test_corpus(
            title="Annotation Preservation Test",
            num_documents=3,
            num_annotations_per_doc=4,
            num_relationships=0,
            num_folders=0,
            num_notes_per_doc=0,
        )
        original_snapshot = CorpusSnapshot.from_corpus(original)

        forked = self._execute_fork(original)
        self.assertIsNotNone(forked, "Fork should succeed")
        assert forked is not None

        forked_snapshot = CorpusSnapshot.from_corpus(forked)

        self.assertEqual(
            original_snapshot.annotation_count,
            forked_snapshot.annotation_count,
            "Annotation count should match",
        )
        self.assertEqual(
            original_snapshot.annotation_texts,
            forked_snapshot.annotation_texts,
            "Annotation texts should match",
        )

    def test_single_fork_preserves_labels(self):
        """Test that a single fork preserves all labels in the label set."""
        original = self._create_test_corpus(
            title="Label Preservation Test",
            num_documents=1,
            num_annotations_per_doc=1,
            num_relationships=0,
            num_folders=0,
            num_notes_per_doc=0,
        )
        original_snapshot = CorpusSnapshot.from_corpus(original)

        forked = self._execute_fork(original)
        self.assertIsNotNone(forked, "Fork should succeed")
        assert forked is not None

        forked_snapshot = CorpusSnapshot.from_corpus(forked)

        self.assertEqual(
            original_snapshot.label_count,
            forked_snapshot.label_count,
            "Label count should match",
        )
        self.assertEqual(
            original_snapshot.label_texts,
            forked_snapshot.label_texts,
            "Label texts should match",
        )

    def test_fork_establishes_parent_relationship(self):
        """Test that forked corpus has correct parent relationship."""
        original = self._create_test_corpus(
            title="Parent Relationship Test",
            num_documents=1,
            num_annotations_per_doc=0,
            num_relationships=0,
            num_folders=0,
            num_notes_per_doc=0,
        )

        forked = self._execute_fork(original)
        self.assertIsNotNone(forked, "Fork should succeed")
        assert forked is not None

        self.assertEqual(
            forked.parent_id,
            original.pk,
            "Forked corpus should have original as parent",
        )
        self.assertEqual(
            forked.parent,
            original,
            "Forked corpus parent should be the original corpus",
        )

    def test_multi_generation_fork_no_degradation(self):
        """
        Test that forking through multiple generations doesn't degrade data.

        This is the core round-trip test: fork a corpus multiple times and
        ensure no data loss occurs.
        """
        num_generations = 3

        # Create original corpus with comprehensive data
        original = self._create_test_corpus(
            title="Multi-Gen Test",
            num_documents=3,
            num_annotations_per_doc=3,
            num_relationships=2,  # Now implemented in fork
            num_folders=2,  # Now implemented in fork
            num_notes_per_doc=0,  # Not yet implemented in fork
        )
        original_snapshot = CorpusSnapshot.from_corpus(original)

        # Track all generations
        generations = [original]
        snapshots = [original_snapshot]

        # Fork through multiple generations
        current = original
        for gen in range(num_generations):
            forked = self._execute_fork(current)
            self.assertIsNotNone(
                forked,
                f"Fork should succeed at generation {gen + 1}",
            )
            assert forked is not None

            snapshot = CorpusSnapshot.from_corpus(forked)
            generations.append(forked)
            snapshots.append(snapshot)
            current = forked

        # Verify no degradation between generations
        for i in range(len(snapshots) - 1):
            current_snapshot = snapshots[i]
            next_snapshot = snapshots[i + 1]

            # Document count should be stable
            self.assertEqual(
                current_snapshot.document_count,
                next_snapshot.document_count,
                f"Document count degraded at generation {i + 1}: "
                f"{current_snapshot.document_count} -> {next_snapshot.document_count}",
            )

            # Annotation count should be stable
            self.assertEqual(
                current_snapshot.annotation_count,
                next_snapshot.annotation_count,
                f"Annotation count degraded at generation {i + 1}: "
                f"{current_snapshot.annotation_count} -> {next_snapshot.annotation_count}",
            )

            # Label count should be stable
            self.assertEqual(
                current_snapshot.label_count,
                next_snapshot.label_count,
                f"Label count degraded at generation {i + 1}: "
                f"{current_snapshot.label_count} -> {next_snapshot.label_count}",
            )

            # Folder count should be stable
            self.assertEqual(
                current_snapshot.folder_count,
                next_snapshot.folder_count,
                f"Folder count degraded at generation {i + 1}: "
                f"{current_snapshot.folder_count} -> {next_snapshot.folder_count}",
            )

            # Relationship count should be stable
            self.assertEqual(
                current_snapshot.relationship_count,
                next_snapshot.relationship_count,
                f"Relationship count degraded at generation {i + 1}: "
                f"{current_snapshot.relationship_count} -> {next_snapshot.relationship_count}",
            )

        # Verify final generation matches original (for copied data)
        final_snapshot = snapshots[-1]

        self.assertEqual(
            original_snapshot.document_count,
            final_snapshot.document_count,
            f"After {num_generations} generations, document count should match original",
        )
        self.assertEqual(
            original_snapshot.annotation_count,
            final_snapshot.annotation_count,
            f"After {num_generations} generations, annotation count should match original",
        )
        self.assertEqual(
            original_snapshot.label_count,
            final_snapshot.label_count,
            f"After {num_generations} generations, label count should match original",
        )
        self.assertEqual(
            original_snapshot.folder_count,
            final_snapshot.folder_count,
            f"After {num_generations} generations, folder count should match original",
        )
        self.assertEqual(
            original_snapshot.relationship_count,
            final_snapshot.relationship_count,
            f"After {num_generations} generations, relationship count should match original",
        )

    def test_fork_chain_maintains_ancestry(self):
        """Test that fork chain maintains correct parent relationships."""
        num_generations = 4

        original = self._create_test_corpus(
            title="Ancestry Test",
            num_documents=1,
            num_annotations_per_doc=1,
            num_relationships=0,
            num_folders=0,
            num_notes_per_doc=0,
        )

        generations = [original]
        current = original

        for _ in range(num_generations):
            forked = self._execute_fork(current)
            self.assertIsNotNone(forked)
            assert forked is not None
            generations.append(forked)
            current = forked

        # Verify ancestry chain
        for i in range(1, len(generations)):
            child = generations[i]
            expected_parent = generations[i - 1]

            self.assertEqual(
                child.parent_id,
                expected_parent.pk,
                f"Generation {i} should have generation {i-1} as parent",
            )

        # Verify we can traverse back to original
        current = generations[-1]
        ancestors = []
        while current.parent_id:
            ancestors.append(current.parent_id)
            current = Corpus.objects.get(pk=current.parent_id)

        self.assertEqual(
            len(ancestors),
            num_generations,
            f"Should have {num_generations} ancestors",
        )
        self.assertEqual(
            ancestors[-1],
            original.pk,
            "Oldest ancestor should be original corpus",
        )

    def test_annotation_text_integrity_across_generations(self):
        """Test that annotation text content is preserved exactly through forks."""
        # Create corpus with specific annotation texts
        original = self._create_test_corpus(
            title="Text Integrity Test",
            num_documents=2,
            num_annotations_per_doc=3,
            num_relationships=0,
            num_folders=0,
            num_notes_per_doc=0,
        )

        # Get original annotation texts
        original_texts = set(
            Annotation.objects.filter(
                corpus=original,
                analysis__isnull=True,
            ).values_list("raw_text", flat=True)
        )

        # Fork through 3 generations
        current = original
        for gen in range(3):
            forked = self._execute_fork(current)
            self.assertIsNotNone(forked)
            assert forked is not None

            forked_texts = set(
                Annotation.objects.filter(
                    corpus=forked,
                    analysis__isnull=True,
                ).values_list("raw_text", flat=True)
            )

            self.assertEqual(
                original_texts,
                forked_texts,
                f"Annotation texts should be preserved at generation {gen + 1}",
            )

            current = forked

    def test_multi_generation_title_prefix_stacking(self):
        """
        Test that [FORK] prefixes stack in multi-generation forks.

        When forking a fork, the title becomes [FORK] [FORK] Original Title.
        This is intentional behavior - each fork prepends [FORK] to track lineage.
        """
        original = self._create_test_corpus(
            title="Original Title",
            num_documents=1,
            num_annotations_per_doc=0,
            num_relationships=0,
            num_folders=0,
            num_notes_per_doc=0,
        )

        # First fork
        gen1 = self._execute_fork(original)
        self.assertIsNotNone(gen1)
        assert gen1 is not None
        self.assertEqual(gen1.title, "[FORK] Original Title")

        # Get the forked document title
        gen1_doc = gen1._get_active_documents().first()
        assert gen1_doc is not None
        self.assertEqual(gen1_doc.title, "[FORK] Document 0")

        # Second fork (fork of fork)
        gen2 = self._execute_fork(gen1)
        self.assertIsNotNone(gen2)
        assert gen2 is not None
        self.assertEqual(
            gen2.title,
            "[FORK] [FORK] Original Title",
            "Second generation should have stacked [FORK] prefix",
        )

        gen2_doc = gen2._get_active_documents().first()
        assert gen2_doc is not None
        self.assertEqual(
            gen2_doc.title,
            "[FORK] [FORK] Document 0",
            "Document title should also have stacked [FORK] prefix",
        )

        # Third fork
        gen3 = self._execute_fork(gen2)
        self.assertIsNotNone(gen3)
        assert gen3 is not None
        self.assertEqual(
            gen3.title,
            "[FORK] [FORK] [FORK] Original Title",
            "Third generation should have triple [FORK] prefix",
        )

    def test_empty_corpus_fork(self):
        """Test that forking an empty corpus works correctly."""
        empty_corpus = Corpus.objects.create(
            title="Empty Corpus",
            description="A corpus with no documents",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, empty_corpus, [PermissionTypes.CRUD])

        forked = self._execute_fork(empty_corpus)
        self.assertIsNotNone(forked, "Fork of empty corpus should succeed")
        assert forked is not None

        forked_snapshot = CorpusSnapshot.from_corpus(forked)

        self.assertEqual(forked_snapshot.document_count, 0)
        self.assertEqual(forked_snapshot.annotation_count, 0)
        self.assertEqual(forked.parent_id, empty_corpus.pk)

    def test_fork_does_not_copy_analysis_annotations(self):
        """Test that analysis-generated annotations are NOT copied during fork."""
        from opencontractserver.analyzer.models import Analysis, Analyzer

        original = self._create_test_corpus(
            title="Analysis Exclusion Test",
            num_documents=2,
            num_annotations_per_doc=2,
            num_relationships=0,
            num_folders=0,
            num_notes_per_doc=0,
        )

        # Create an analyzer and analysis
        # Note: Analyzer requires either host_gremlin or task_name to be set (not both null)
        analyzer = Analyzer.objects.create(
            id="test-analyzer",
            description="Test analyzer",
            task_name="test_task",
            creator=self.user,
        )

        analysis = Analysis.objects.create(
            analyzer=analyzer,
            analyzed_corpus=original,
            creator=self.user,
        )

        # Create analysis-generated annotation
        doc = original._get_active_documents().first()
        _analysis_annotation = Annotation.objects.create(  # noqa: F841
            page=1,
            raw_text="Analysis generated annotation",
            document=doc,
            corpus=original,
            analysis=analysis,  # This marks it as analysis-generated
            creator=self.user,
        )

        # Count annotations before fork
        original_user_annotations = Annotation.objects.filter(
            corpus=original,
            analysis__isnull=True,
        ).count()
        original_all_annotations = Annotation.objects.filter(
            corpus=original,
        ).count()

        self.assertEqual(
            original_all_annotations,
            original_user_annotations + 1,
            "Should have user annotations plus one analysis annotation",
        )

        # Fork
        forked = self._execute_fork(original)
        self.assertIsNotNone(forked)

        # Verify analysis annotation was NOT copied
        forked_annotations = Annotation.objects.filter(corpus=forked)
        self.assertEqual(
            forked_annotations.count(),
            original_user_annotations,
            "Forked corpus should only have user annotations, not analysis annotations",
        )

        # Verify none of the forked annotations are analysis-generated
        forked_analysis_annotations = forked_annotations.filter(
            analysis__isnull=False
        ).count()
        self.assertEqual(
            forked_analysis_annotations,
            0,
            "No forked annotations should be analysis-generated",
        )


class CorpusForkPreservationTest(TestCase):
    """
    Tests that verify folders and relationships ARE copied during fork.

    These tests validate that the fork implementation correctly preserves
    folder structure and annotation relationships.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="preservation_test_user",
            password="testpass123",
        )

    def test_relationships_are_copied(self):
        """
        Test that relationships are correctly copied during fork.

        Verifies that relationship count, labels, and annotation connections
        are preserved in the forked corpus.
        """
        # Create corpus with relationships
        corpus = Corpus.objects.create(
            title="Relationship Test",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, corpus, [PermissionTypes.CRUD])

        # Create document and annotations
        doc = Document.objects.create(
            title="Test Doc",
            creator=self.user,
        )
        DocumentPath.objects.create(
            document=doc,
            corpus=corpus,
            path="/documents/test",
            version_number=1,
            is_current=True,
            creator=self.user,
        )
        # Document is already linked to corpus via DocumentPath above

        label_set = LabelSet.objects.create(
            title="Test Labels",
            creator=self.user,
        )
        token_label = AnnotationLabel.objects.create(
            text="Token",
            label_type=TOKEN_LABEL,
            creator=self.user,
        )
        rel_label = AnnotationLabel.objects.create(
            text="Related",
            label_type=RELATIONSHIP_LABEL,
            creator=self.user,
        )
        label_set.annotation_labels.add(token_label, rel_label)
        corpus.label_set = label_set
        corpus.save()

        ann1 = Annotation.objects.create(
            page=1,
            raw_text="First",
            document=doc,
            corpus=corpus,
            annotation_label=token_label,
            creator=self.user,
        )
        ann2 = Annotation.objects.create(
            page=1,
            raw_text="Second",
            document=doc,
            corpus=corpus,
            annotation_label=token_label,
            creator=self.user,
        )

        # Create relationship
        relationship = Relationship.objects.create(
            relationship_label=rel_label,
            corpus=corpus,
            document=doc,
            creator=self.user,
        )
        relationship.source_annotations.add(ann1)
        relationship.target_annotations.add(ann2)

        original_rel_count = Relationship.objects.filter(corpus=corpus).count()
        self.assertEqual(original_rel_count, 1)

        # Fork - include relationship_ids
        doc_ids = [doc.pk]
        annotation_ids = [ann1.pk, ann2.pk]
        folder_ids: list[int] = []
        relationship_ids = [relationship.pk]

        forked = Corpus.objects.create(
            title="[FORK] Relationship Test",
            creator=self.user,
            parent_id=corpus.pk,
            backend_lock=True,
        )
        set_permissions_for_obj_to_user(self.user, forked, [PermissionTypes.CRUD])

        fork_corpus(
            new_corpus_id=forked.pk,
            doc_ids=doc_ids,
            label_set_id=label_set.pk,
            annotation_ids=annotation_ids,
            folder_ids=folder_ids,
            relationship_ids=relationship_ids,
            user_id=self.user.pk,
        )

        forked.refresh_from_db()

        # Verify relationships ARE copied
        forked_rel_count = Relationship.objects.filter(corpus=forked).count()
        self.assertEqual(
            forked_rel_count,
            1,
            "Relationships should be copied during fork",
        )

        # Verify the relationship has correct annotations
        forked_rel = Relationship.objects.filter(corpus=forked).first()
        assert forked_rel is not None
        self.assertEqual(
            forked_rel.source_annotations.count(),
            1,
            "Forked relationship should have source annotation",
        )
        self.assertEqual(
            forked_rel.target_annotations.count(),
            1,
            "Forked relationship should have target annotation",
        )

        # Verify relationship label was mapped correctly
        self.assertIsNotNone(
            forked_rel.relationship_label,
            "Forked relationship should have a label",
        )
        assert forked_rel.relationship_label is not None
        self.assertEqual(
            forked_rel.relationship_label.text,
            "Related",
            "Forked relationship label text should match original",
        )

    def test_folders_are_copied(self):
        """
        Test that folder structure is correctly copied during fork.

        Verifies that folder count, names, and hierarchy are preserved
        in the forked corpus.
        """
        corpus = Corpus.objects.create(
            title="Folder Test",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, corpus, [PermissionTypes.CRUD])

        # Create folder structure
        root = CorpusFolder.objects.create(
            name="Root Folder",
            corpus=corpus,
            creator=self.user,
        )
        _child = CorpusFolder.objects.create(  # noqa: F841
            name="Child Folder",
            corpus=corpus,
            parent=root,
            creator=self.user,
        )

        original_folder_count = CorpusFolder.objects.filter(corpus=corpus).count()
        self.assertEqual(original_folder_count, 2)

        # Fork - include folder_ids
        # Note: with_tree_fields() provides default tree_ordering which ensures parents before children
        folder_ids = list(
            CorpusFolder.objects.filter(corpus=corpus)
            .with_tree_fields()
            .values_list("id", flat=True)
        )

        forked = Corpus.objects.create(
            title="[FORK] Folder Test",
            creator=self.user,
            parent_id=corpus.pk,
            backend_lock=True,
        )
        set_permissions_for_obj_to_user(self.user, forked, [PermissionTypes.CRUD])

        fork_corpus(
            new_corpus_id=forked.pk,
            doc_ids=[],
            label_set_id=None,
            annotation_ids=[],
            folder_ids=folder_ids,
            relationship_ids=[],
            user_id=self.user.pk,
        )

        forked.refresh_from_db()

        # Verify folders ARE copied
        forked_folder_count = CorpusFolder.objects.filter(corpus=forked).count()
        self.assertEqual(
            forked_folder_count,
            2,
            "Folders should be copied during fork",
        )

        # Verify folder names are preserved
        forked_folder_names = set(
            CorpusFolder.objects.filter(corpus=forked).values_list("name", flat=True)
        )
        self.assertEqual(
            forked_folder_names,
            {"Root Folder", "Child Folder"},
            "Folder names should be preserved",
        )

        # Verify hierarchy is preserved
        forked_child = CorpusFolder.objects.get(corpus=forked, name="Child Folder")
        self.assertIsNotNone(
            forked_child.parent,
            "Child folder should have a parent",
        )
        self.assertEqual(
            forked_child.parent.name,
            "Root Folder",
            "Child folder's parent should be Root Folder",
        )

    def test_document_folder_assignment_preserved(self):
        """
        Test that documents maintain their folder assignments after fork.
        """
        corpus = Corpus.objects.create(
            title="Doc Folder Test",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, corpus, [PermissionTypes.CRUD])

        # Create folder
        folder = CorpusFolder.objects.create(
            name="My Folder",
            corpus=corpus,
            creator=self.user,
        )

        # Create document in folder
        doc = Document.objects.create(
            title="Test Doc",
            creator=self.user,
        )
        DocumentPath.objects.create(
            document=doc,
            corpus=corpus,
            folder=folder,
            path="/documents/test",
            version_number=1,
            is_current=True,
            creator=self.user,
        )
        # Document is already linked to corpus via DocumentPath above

        # Verify original setup
        original_path = DocumentPath.objects.get(
            corpus=corpus, document=doc, is_current=True
        )
        self.assertEqual(original_path.folder, folder)

        # Fork
        folder_ids = [folder.pk]

        forked = Corpus.objects.create(
            title="[FORK] Doc Folder Test",
            creator=self.user,
            parent_id=corpus.pk,
            backend_lock=True,
        )
        set_permissions_for_obj_to_user(self.user, forked, [PermissionTypes.CRUD])

        fork_corpus(
            new_corpus_id=forked.pk,
            doc_ids=[doc.pk],
            label_set_id=None,
            annotation_ids=[],
            folder_ids=folder_ids,
            relationship_ids=[],
            user_id=self.user.pk,
        )

        forked.refresh_from_db()

        # Verify folder was copied
        forked_folder = CorpusFolder.objects.filter(corpus=forked).first()
        self.assertIsNotNone(forked_folder)
        self.assertEqual(forked_folder.name, "My Folder")

        # Verify document is in the forked folder
        forked_doc = forked._get_active_documents().first()
        self.assertIsNotNone(forked_doc)

        forked_path = DocumentPath.objects.filter(
            corpus=forked, document=forked_doc, is_current=True, is_deleted=False
        ).first()
        self.assertIsNotNone(forked_path)
        assert forked_path is not None
        self.assertEqual(
            forked_path.folder,
            forked_folder,
            "Document should be in the forked folder",
        )

    def test_notes_not_copied_limitation(self):
        """
        LIMITATION: Notes are not currently copied during fork.

        This test documents the current behavior. Once note copying is
        implemented, this test should be updated to verify notes ARE copied.
        """
        corpus = Corpus.objects.create(
            title="Notes Test",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, corpus, [PermissionTypes.CRUD])

        doc = Document.objects.create(
            title="Test Doc",
            creator=self.user,
        )
        DocumentPath.objects.create(
            document=doc,
            corpus=corpus,
            path="/documents/test",
            version_number=1,
            is_current=True,
            creator=self.user,
        )
        # Document is already linked to corpus via DocumentPath above

        # Create note
        _note = Note.objects.create(  # noqa: F841
            title="Test Note",
            content="Note content",
            document=doc,
            corpus=corpus,
            creator=self.user,
        )

        original_note_count = Note.objects.filter(corpus=corpus).count()
        self.assertEqual(original_note_count, 1)

        # Fork
        forked = Corpus.objects.create(
            title="[FORK] Notes Test",
            creator=self.user,
            parent_id=corpus.pk,
            backend_lock=True,
        )
        set_permissions_for_obj_to_user(self.user, forked, [PermissionTypes.CRUD])

        fork_corpus(
            new_corpus_id=forked.pk,
            doc_ids=[doc.pk],
            label_set_id=None,
            annotation_ids=[],
            folder_ids=[],
            relationship_ids=[],
            user_id=self.user.pk,
        )

        forked.refresh_from_db()

        # CURRENT LIMITATION: Notes are NOT copied
        forked_note_count = Note.objects.filter(corpus=forked).count()
        self.assertEqual(
            forked_note_count,
            0,
            "LIMITATION: Notes are not currently copied during fork. "
            "If this test fails, the limitation may have been fixed - update accordingly!",
        )

    def test_labelset_icon_copied(self):
        """
        Test that label set icon is copied during fork.
        """
        from django.core.files.base import ContentFile

        corpus = Corpus.objects.create(
            title="Icon Test",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, corpus, [PermissionTypes.CRUD])

        # Create label set with icon
        label_set = LabelSet.objects.create(
            title="Labeled Set",
            creator=self.user,
        )
        # Create a simple icon file
        icon_content = b"fake icon content for testing"
        label_set.icon.save("test_icon.png", ContentFile(icon_content))
        label_set.save()

        corpus.label_set = label_set
        corpus.save()

        # Fork
        forked = Corpus.objects.create(
            title="[FORK] Icon Test",
            creator=self.user,
            parent_id=corpus.pk,
            backend_lock=True,
        )
        set_permissions_for_obj_to_user(self.user, forked, [PermissionTypes.CRUD])

        fork_corpus(
            new_corpus_id=forked.pk,
            doc_ids=[],
            label_set_id=label_set.pk,
            annotation_ids=[],
            folder_ids=[],
            relationship_ids=[],
            user_id=self.user.pk,
        )

        forked.refresh_from_db()

        # Verify label set was created with icon
        self.assertIsNotNone(forked.label_set, "Forked corpus should have a label set")
        self.assertTrue(
            forked.label_set.icon and forked.label_set.icon.name,
            "Forked label set should have an icon",
        )

    def test_document_files_copied(self):
        """
        Test that document txt_extract_file and pawls_parse_file are copied during fork.
        """
        from django.core.files.base import ContentFile

        corpus = Corpus.objects.create(
            title="File Copy Test",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, corpus, [PermissionTypes.CRUD])

        # Create document with txt_extract_file and pawls_parse_file
        doc = Document.objects.create(
            title="Test Doc With Files",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, doc, [PermissionTypes.CRUD])

        # Add txt extract file
        txt_content = b"This is extracted text content."
        doc.txt_extract_file.save("test_extract.txt", ContentFile(txt_content))

        # Add pawls parse file
        pawls_content = b'[{"page": 1, "tokens": []}]'
        doc.pawls_parse_file.save("test_doc.pawls", ContentFile(pawls_content))
        doc.save()

        # Add document to corpus
        DocumentPath.objects.create(
            document=doc,
            corpus=corpus,
            path="/documents/test",
            version_number=1,
            is_current=True,
            creator=self.user,
        )
        # Document is already linked to corpus via DocumentPath above

        # Fork
        forked = Corpus.objects.create(
            title="[FORK] File Copy Test",
            creator=self.user,
            parent_id=corpus.pk,
            backend_lock=True,
        )
        set_permissions_for_obj_to_user(self.user, forked, [PermissionTypes.CRUD])

        fork_corpus(
            new_corpus_id=forked.pk,
            doc_ids=[doc.pk],
            label_set_id=None,
            annotation_ids=[],
            folder_ids=[],
            relationship_ids=[],
            user_id=self.user.pk,
        )

        forked.refresh_from_db()

        # Verify document was forked with files
        forked_doc = forked._get_active_documents().first()
        self.assertIsNotNone(forked_doc, "Forked corpus should have a document")
        self.assertTrue(
            forked_doc.txt_extract_file and forked_doc.txt_extract_file.name,
            "Forked document should have txt_extract_file",
        )
        self.assertTrue(
            forked_doc.pawls_parse_file and forked_doc.pawls_parse_file.name,
            "Forked document should have pawls_parse_file",
        )


class CorpusForkMetadataTest(TestCase):
    """
    Tests for metadata forking functionality.

    These tests verify that metadata schemas (Fieldsets, Columns) and values
    (Datacells) are correctly copied during corpus forking.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="metadata_fork_test_user",
            password="testpass123",
        )

    def test_metadata_schema_copied(self):
        """
        Test that metadata schema (Fieldset + Columns) is copied during fork.
        """
        # Create corpus
        corpus = Corpus.objects.create(
            title="Metadata Schema Test",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, corpus, [PermissionTypes.CRUD])

        # Create metadata fieldset linked to corpus
        fieldset = Fieldset.objects.create(
            name="Test Metadata Schema",
            description="Schema for testing",
            corpus=corpus,
            creator=self.user,
        )

        # Create columns with different data types
        col1 = Column.objects.create(
            name="Text Field",
            fieldset=fieldset,
            output_type="str",
            data_type="STRING",
            is_manual_entry=True,
            validation_config={"required": True, "max_length": 100},
            help_text="Enter text here",
            display_order=1,
            creator=self.user,
        )
        col2 = Column.objects.create(
            name="Number Field",
            fieldset=fieldset,
            output_type="int",
            data_type="INTEGER",
            is_manual_entry=True,
            validation_config={"min_value": 0, "max_value": 100},
            default_value=42,
            display_order=2,
            creator=self.user,
        )
        col3 = Column.objects.create(
            name="Choice Field",
            fieldset=fieldset,
            output_type="str",
            data_type="CHOICE",
            is_manual_entry=True,
            validation_config={"choices": ["Option A", "Option B", "Option C"]},
            display_order=3,
            creator=self.user,
        )

        # Collect column IDs
        metadata_column_ids = [col1.pk, col2.pk, col3.pk]

        # Create forked corpus shell
        forked = Corpus.objects.create(
            title="[FORK] Metadata Schema Test",
            creator=self.user,
            parent_id=corpus.pk,
            backend_lock=True,
        )
        set_permissions_for_obj_to_user(self.user, forked, [PermissionTypes.CRUD])

        # Execute fork
        result = fork_corpus(
            new_corpus_id=forked.pk,
            doc_ids=[],
            label_set_id=None,
            annotation_ids=[],
            folder_ids=[],
            relationship_ids=[],
            user_id=self.user.pk,
            metadata_column_ids=metadata_column_ids,
            metadata_datacell_ids=[],
        )

        self.assertIsNotNone(result)
        forked.refresh_from_db()

        # Verify fieldset was created
        self.assertTrue(
            hasattr(forked, "metadata_schema") and forked.metadata_schema,
            "Forked corpus should have metadata_schema",
        )

        # Verify fieldset properties
        self.assertEqual(
            forked.metadata_schema.name,
            "[FORK] Test Metadata Schema",
            "Fieldset name should have [FORK] prefix",
        )

        # Verify column count
        forked_columns = forked.metadata_schema.columns.all()
        self.assertEqual(
            forked_columns.count(),
            3,
            "Forked fieldset should have 3 columns",
        )

        # Verify column properties preserved
        forked_col_names = set(forked_columns.values_list("name", flat=True))
        self.assertEqual(
            forked_col_names,
            {"Text Field", "Number Field", "Choice Field"},
            "Column names should be preserved",
        )

        # Verify validation config preserved
        forked_choice_col = forked_columns.get(name="Choice Field")
        self.assertEqual(
            forked_choice_col.validation_config["choices"],
            ["Option A", "Option B", "Option C"],
            "Validation config should be preserved",
        )

    def test_metadata_values_copied(self):
        """
        Test that metadata values (Datacells) are copied during fork.
        """
        # Create corpus with document
        corpus = Corpus.objects.create(
            title="Metadata Values Test",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, corpus, [PermissionTypes.CRUD])

        doc = Document.objects.create(
            title="Test Doc",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, doc, [PermissionTypes.CRUD])
        DocumentPath.objects.create(
            document=doc,
            corpus=corpus,
            path="/documents/test",
            version_number=1,
            is_current=True,
            creator=self.user,
        )
        # Document is already linked to corpus via DocumentPath above

        # Create metadata schema
        fieldset = Fieldset.objects.create(
            name="Test Schema",
            description="Schema for testing",
            corpus=corpus,
            creator=self.user,
        )

        col = Column.objects.create(
            name="Status",
            fieldset=fieldset,
            output_type="str",
            data_type="STRING",
            is_manual_entry=True,
            display_order=1,
            creator=self.user,
        )

        # Create datacell (metadata value)
        datacell = Datacell.objects.create(
            column=col,
            document=doc,
            data={"value": "Active"},
            data_definition="Document status",
            extract=None,  # Manual metadata
            creator=self.user,
        )

        # Fork
        forked = Corpus.objects.create(
            title="[FORK] Metadata Values Test",
            creator=self.user,
            parent_id=corpus.pk,
            backend_lock=True,
        )
        set_permissions_for_obj_to_user(self.user, forked, [PermissionTypes.CRUD])

        result = fork_corpus(
            new_corpus_id=forked.pk,
            doc_ids=[doc.pk],
            label_set_id=None,
            annotation_ids=[],
            folder_ids=[],
            relationship_ids=[],
            user_id=self.user.pk,
            metadata_column_ids=[col.pk],
            metadata_datacell_ids=[datacell.pk],
        )

        self.assertIsNotNone(result)
        forked.refresh_from_db()

        # Verify datacell was copied
        forked_doc = forked._get_active_documents().first()
        self.assertIsNotNone(forked_doc)

        # Get forked column
        forked_col = forked.metadata_schema.columns.first()
        self.assertIsNotNone(forked_col)

        # Get forked datacell
        forked_datacell = Datacell.objects.filter(
            document=forked_doc,
            column=forked_col,
            extract__isnull=True,
        ).first()

        self.assertIsNotNone(forked_datacell, "Datacell should be copied")
        assert forked_datacell is not None
        self.assertEqual(
            forked_datacell.data["value"],
            "Active",
            "Datacell value should be preserved",
        )
        self.assertEqual(
            forked_datacell.data_definition,
            "Document status",
            "Datacell data_definition should be preserved",
        )

    def test_metadata_all_data_types_preserved(self):
        """
        Test that all metadata data types are correctly preserved during fork.
        """
        corpus = Corpus.objects.create(
            title="Data Types Test",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, corpus, [PermissionTypes.CRUD])

        fieldset = Fieldset.objects.create(
            name="All Types Schema",
            description="Schema with all data types",
            corpus=corpus,
            creator=self.user,
        )

        # Create columns for each data type
        data_types = [
            ("STRING", "str"),
            ("TEXT", "str"),
            ("BOOLEAN", "bool"),
            ("INTEGER", "int"),
            ("FLOAT", "float"),
            ("DATE", "str"),
            ("DATETIME", "str"),
            ("URL", "str"),
            ("EMAIL", "str"),
            ("CHOICE", "str"),
            ("MULTI_CHOICE", "list"),
            ("JSON", "dict"),
        ]

        columns = []
        for i, (data_type, output_type) in enumerate(data_types):
            validation_config = {}
            if data_type in ["CHOICE", "MULTI_CHOICE"]:
                validation_config = {"choices": ["A", "B", "C"]}

            col = Column.objects.create(
                name=f"{data_type} Column",
                fieldset=fieldset,
                output_type=output_type,
                data_type=data_type,
                is_manual_entry=True,
                validation_config=validation_config if validation_config else None,
                display_order=i,
                creator=self.user,
            )
            columns.append(col)

        column_ids = [c.pk for c in columns]

        # Fork
        forked = Corpus.objects.create(
            title="[FORK] Data Types Test",
            creator=self.user,
            parent_id=corpus.pk,
            backend_lock=True,
        )
        set_permissions_for_obj_to_user(self.user, forked, [PermissionTypes.CRUD])

        result = fork_corpus(
            new_corpus_id=forked.pk,
            doc_ids=[],
            label_set_id=None,
            annotation_ids=[],
            folder_ids=[],
            relationship_ids=[],
            user_id=self.user.pk,
            metadata_column_ids=column_ids,
            metadata_datacell_ids=[],
        )

        self.assertIsNotNone(result)
        forked.refresh_from_db()

        # Verify all columns were copied with correct data types
        forked_columns = forked.metadata_schema.columns.all()
        self.assertEqual(forked_columns.count(), len(data_types))

        for data_type, _ in data_types:
            col = forked_columns.filter(data_type=data_type).first()
            self.assertIsNotNone(col, f"Column with data_type {data_type} should exist")
            self.assertTrue(
                col.is_manual_entry, f"{data_type} column should be manual entry"
            )

    def test_multi_generation_metadata_preservation(self):
        """
        Test that metadata is preserved through multiple fork generations.
        """
        # Create original corpus with metadata
        original = Corpus.objects.create(
            title="Multi-Gen Metadata Test",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, original, [PermissionTypes.CRUD])

        # Add document
        doc = Document.objects.create(title="Test Doc", creator=self.user)
        set_permissions_for_obj_to_user(self.user, doc, [PermissionTypes.CRUD])
        DocumentPath.objects.create(
            document=doc,
            corpus=original,
            path="/documents/test",
            version_number=1,
            is_current=True,
            creator=self.user,
        )
        # Document is already linked to corpus via DocumentPath above

        # Add metadata schema
        fieldset = Fieldset.objects.create(
            name="Original Schema",
            description="Original metadata schema",
            corpus=original,
            creator=self.user,
        )

        col = Column.objects.create(
            name="Important Field",
            fieldset=fieldset,
            output_type="str",
            data_type="STRING",
            is_manual_entry=True,
            validation_config={"required": True},
            display_order=1,
            creator=self.user,
        )

        datacell = Datacell.objects.create(
            column=col,
            document=doc,
            data={"value": "Original Value"},
            data_definition="Test field",
            extract=None,
            creator=self.user,
        )

        # Fork through 3 generations
        current_corpus = original
        current_doc_id = doc.pk
        current_col_id = col.pk
        current_datacell_id = datacell.pk

        for gen in range(3):
            forked = Corpus.objects.create(
                title=f"[FORK] Gen {gen + 1}",
                creator=self.user,
                parent_id=current_corpus.pk,
                backend_lock=True,
            )
            set_permissions_for_obj_to_user(self.user, forked, [PermissionTypes.CRUD])

            result = fork_corpus(
                new_corpus_id=forked.pk,
                doc_ids=[current_doc_id],
                label_set_id=None,
                annotation_ids=[],
                folder_ids=[],
                relationship_ids=[],
                user_id=self.user.pk,
                metadata_column_ids=[current_col_id],
                metadata_datacell_ids=[current_datacell_id],
            )

            self.assertIsNotNone(result, f"Fork should succeed at gen {gen + 1}")
            forked.refresh_from_db()

            # Verify metadata exists
            self.assertTrue(
                hasattr(forked, "metadata_schema") and forked.metadata_schema,
                f"Gen {gen + 1} should have metadata_schema",
            )
            self.assertEqual(
                forked.metadata_schema.columns.count(),
                1,
                f"Gen {gen + 1} should have 1 column",
            )

            # Get forked document and datacell for next iteration
            forked_doc = forked._get_active_documents().first()
            forked_col = forked.metadata_schema.columns.first()
            forked_datacell = Datacell.objects.filter(
                document=forked_doc,
                column=forked_col,
                extract__isnull=True,
            ).first()

            self.assertIsNotNone(forked_datacell, f"Gen {gen + 1} should have datacell")
            assert forked_datacell is not None
            self.assertEqual(
                forked_datacell.data["value"],
                "Original Value",
                f"Gen {gen + 1} should preserve value",
            )

            # Update for next iteration
            current_corpus = forked
            current_doc_id = forked_doc.pk
            current_col_id = forked_col.pk
            current_datacell_id = forked_datacell.pk

    def test_corpus_without_metadata_fork(self):
        """
        Test that forking a corpus without metadata succeeds (backward compatibility).
        """
        corpus = Corpus.objects.create(
            title="No Metadata Corpus",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, corpus, [PermissionTypes.CRUD])

        # Fork with empty metadata lists
        forked = Corpus.objects.create(
            title="[FORK] No Metadata Corpus",
            creator=self.user,
            parent_id=corpus.pk,
            backend_lock=True,
        )
        set_permissions_for_obj_to_user(self.user, forked, [PermissionTypes.CRUD])

        result = fork_corpus(
            new_corpus_id=forked.pk,
            doc_ids=[],
            label_set_id=None,
            annotation_ids=[],
            folder_ids=[],
            relationship_ids=[],
            user_id=self.user.pk,
            metadata_column_ids=[],
            metadata_datacell_ids=[],
        )

        self.assertIsNotNone(result, "Fork should succeed")
        forked.refresh_from_db()

        # Verify no metadata schema
        self.assertFalse(
            hasattr(forked, "metadata_schema") and forked.metadata_schema,
            "Forked corpus should not have metadata_schema",
        )

    def test_forked_metadata_fresh_approval_status(self):
        """
        Test that forked datacells have fresh approval status (not copied).
        """
        corpus = Corpus.objects.create(
            title="Approval Status Test",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, corpus, [PermissionTypes.CRUD])

        doc = Document.objects.create(title="Test Doc", creator=self.user)
        set_permissions_for_obj_to_user(self.user, doc, [PermissionTypes.CRUD])
        DocumentPath.objects.create(
            document=doc,
            corpus=corpus,
            path="/documents/test",
            version_number=1,
            is_current=True,
            creator=self.user,
        )
        # Document is already linked to corpus via DocumentPath above

        fieldset = Fieldset.objects.create(
            name="Test Schema",
            description="Schema",
            corpus=corpus,
            creator=self.user,
        )

        col = Column.objects.create(
            name="Field",
            fieldset=fieldset,
            output_type="str",
            data_type="STRING",
            is_manual_entry=True,
            display_order=1,
            creator=self.user,
        )

        # Create datacell with approval status
        datacell = Datacell.objects.create(
            column=col,
            document=doc,
            data={"value": "Test"},
            data_definition="Test",
            extract=None,
            creator=self.user,
            approved_by=self.user,  # Set approval
        )

        # Fork
        forked = Corpus.objects.create(
            title="[FORK] Approval Status Test",
            creator=self.user,
            parent_id=corpus.pk,
            backend_lock=True,
        )
        set_permissions_for_obj_to_user(self.user, forked, [PermissionTypes.CRUD])

        result = fork_corpus(
            new_corpus_id=forked.pk,
            doc_ids=[doc.pk],
            label_set_id=None,
            annotation_ids=[],
            folder_ids=[],
            relationship_ids=[],
            user_id=self.user.pk,
            metadata_column_ids=[col.pk],
            metadata_datacell_ids=[datacell.pk],
        )

        self.assertIsNotNone(result)
        forked.refresh_from_db()

        # Get forked datacell
        forked_doc = forked._get_active_documents().first()
        forked_col = forked.metadata_schema.columns.first()
        forked_datacell = Datacell.objects.filter(
            document=forked_doc,
            column=forked_col,
            extract__isnull=True,
        ).first()

        self.assertIsNotNone(forked_datacell)
        assert forked_datacell is not None
        self.assertIsNone(
            forked_datacell.approved_by,
            "Forked datacell should not have approved_by",
        )
        self.assertIsNone(
            forked_datacell.rejected_by,
            "Forked datacell should not have rejected_by",
        )


class CorpusForkRegressionTest(TestCase):
    """
    Regression tests for bugs discovered in corpus forking.

    These tests ensure previously fixed bugs don't regress.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="fork_regression_test_user",
            password="testpass123",
        )

    def test_fork_generates_unique_slug(self):
        """
        Regression test for slug collision bug.

        Previously, forking a corpus didn't clear the slug before save,
        causing 'duplicate key value violates unique constraint
        uniq_corpus_slug_per_creator_cs' errors.

        Fix: Clear corpus.slug before save() so Django generates a new one.
        """
        # Create corpus with a specific slug
        corpus = Corpus.objects.create(
            title="Slug Test Corpus",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, corpus, [PermissionTypes.CRUD])
        original_slug = corpus.slug

        self.assertIsNotNone(original_slug)
        self.assertTrue(len(original_slug) > 0)

        # Fork the corpus
        forked = Corpus.objects.create(
            title="[FORK] Slug Test Corpus",
            creator=self.user,
            parent_id=corpus.pk,
            backend_lock=True,
        )
        set_permissions_for_obj_to_user(self.user, forked, [PermissionTypes.CRUD])

        result = fork_corpus(
            new_corpus_id=forked.pk,
            doc_ids=[],
            label_set_id=None,
            annotation_ids=[],
            folder_ids=[],
            relationship_ids=[],
            user_id=self.user.pk,
            metadata_column_ids=[],
            metadata_datacell_ids=[],
        )

        self.assertIsNotNone(result)
        forked.refresh_from_db()

        # Verify forked corpus has a different slug
        self.assertIsNotNone(forked.slug)
        self.assertNotEqual(
            forked.slug,
            original_slug,
            "Forked corpus should have a different slug than original",
        )

    def test_multiple_forks_same_corpus_no_collision(self):
        """
        Test that forking the same corpus multiple times doesn't cause collisions.

        This tests both slug uniqueness and general fork stability.
        """
        # Create source corpus
        corpus = Corpus.objects.create(
            title="Multi-Fork Test",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, corpus, [PermissionTypes.CRUD])

        # Fork the same corpus 3 times
        forked_slugs = set()
        for i in range(3):
            forked = Corpus.objects.create(
                title=f"[FORK] Multi-Fork Test {i}",
                creator=self.user,
                parent_id=corpus.pk,
                backend_lock=True,
            )
            set_permissions_for_obj_to_user(self.user, forked, [PermissionTypes.CRUD])

            result = fork_corpus(
                new_corpus_id=forked.pk,
                doc_ids=[],
                label_set_id=None,
                annotation_ids=[],
                folder_ids=[],
                relationship_ids=[],
                user_id=self.user.pk,
                metadata_column_ids=[],
                metadata_datacell_ids=[],
            )

            self.assertIsNotNone(result, f"Fork {i} should succeed")
            forked.refresh_from_db()
            self.assertFalse(forked.error, f"Fork {i} should not have error")

            # Collect slugs to verify uniqueness
            forked_slugs.add(forked.slug)

        # All slugs should be unique
        self.assertEqual(
            len(forked_slugs),
            3,
            "All forked corpora should have unique slugs",
        )

    def test_fork_with_same_title_different_users(self):
        """
        Test that different users can fork a corpus without slug collision.

        The unique constraint is (creator_id, slug), so different users
        should be able to have the same slug.
        """
        # Create another user
        other_user = User.objects.create_user(
            username="other_fork_user",
            password="testpass123",
        )

        # Create source corpus
        corpus = Corpus.objects.create(
            title="Shared Fork Test",
            creator=self.user,
            is_public=True,
        )
        set_permissions_for_obj_to_user(self.user, corpus, [PermissionTypes.CRUD])

        # Fork by first user
        forked1 = Corpus.objects.create(
            title="[FORK] Shared Fork Test",
            creator=self.user,
            parent_id=corpus.pk,
            backend_lock=True,
        )
        set_permissions_for_obj_to_user(self.user, forked1, [PermissionTypes.CRUD])

        result1 = fork_corpus(
            new_corpus_id=forked1.pk,
            doc_ids=[],
            label_set_id=None,
            annotation_ids=[],
            folder_ids=[],
            relationship_ids=[],
            user_id=self.user.pk,
            metadata_column_ids=[],
            metadata_datacell_ids=[],
        )

        self.assertIsNotNone(result1)

        # Fork by second user
        forked2 = Corpus.objects.create(
            title="[FORK] Shared Fork Test",
            creator=other_user,
            parent_id=corpus.pk,
            backend_lock=True,
        )
        set_permissions_for_obj_to_user(other_user, forked2, [PermissionTypes.CRUD])

        result2 = fork_corpus(
            new_corpus_id=forked2.pk,
            doc_ids=[],
            label_set_id=None,
            annotation_ids=[],
            folder_ids=[],
            relationship_ids=[],
            user_id=other_user.pk,
            metadata_column_ids=[],
            metadata_datacell_ids=[],
        )

        self.assertIsNotNone(result2)

        # Both forks should succeed
        forked1.refresh_from_db()
        forked2.refresh_from_db()
        self.assertFalse(forked1.error)
        self.assertFalse(forked2.error)


# ============================================================================
# Parity tests: fork(C) MUST produce the same end-state as export(C)+import(C).
# These are the contract the V2 fork refactor is built around.  Each fork
# generation produces a corpus whose state — stripped of fork-prefix
# decorations — matches what a fresh export/import would produce.
# ============================================================================


class CorpusForkExportImportParityTest(TestCase):
    """
    Verifies that a single fork and a single export+import of the same
    rich corpus fixture produce identical end-state, and that 3 sequential
    forks remain stable across generations.
    """

    def setUp(self):
        from opencontractserver.tests._corpus_fixture import build_rich_test_corpus

        self.user = User.objects.create_user(
            username="fork_parity_user",
            password="testpass",
            email="forkparity@example.com",
        )
        self.source_corpus = build_rich_test_corpus(self.user)

    # ----- helpers -------------------------------------------------------

    def _fork(self, source: Corpus) -> Corpus:
        """Run a fork via the production utility and return the new corpus."""
        from opencontractserver.utils.corpus_forking import build_fork_corpus_task

        task = build_fork_corpus_task(corpus_pk_to_fork=source.id, user=self.user)
        new_id = task.apply().get()
        self.assertIsNotNone(new_id, "fork_corpus returned None — fork failed")
        return Corpus.objects.get(pk=new_id)

    def _export_import(self, source: Corpus) -> Corpus:
        """Run a full V2 export+import cycle and return the new corpus."""
        from tempfile import SpooledTemporaryFile

        from opencontractserver.tasks.export_tasks_v2 import build_corpus_v2_zip
        from opencontractserver.tasks.import_tasks_v2 import (
            import_corpus_v2_from_bytes,
        )

        # build_corpus_v2_zip returns a SpooledTemporaryFile (in-memory until
        # the configured threshold, then spilled to disk) — the OOM fix for
        # issue #1649. Use as a context manager so the temp file is released
        # on either path through this helper.
        with build_corpus_v2_zip(
            corpus_pk=source.id,
            user_for_visibility=None,
            include_conversations=True,
        ) as zip_bytes:
            self.assertIsInstance(zip_bytes, SpooledTemporaryFile)
            new_id = import_corpus_v2_from_bytes(
                zip_source=zip_bytes,
                user_id=self.user.id,
                seed_corpus_id=None,
            )
        self.assertIsNotNone(new_id, "import_corpus_v2_from_bytes returned None")
        return Corpus.objects.get(pk=new_id)

    # ----- tests ---------------------------------------------------------

    def test_fork_matches_export_import(self) -> None:
        """
        Fork(C) and export+import(C) must produce snapshot-identical
        corpora (modulo the fork's ``"[FORK] "`` title prefix).
        """
        from opencontractserver.tests._corpus_snapshot import snapshot_corpus

        baseline = snapshot_corpus(self.source_corpus)

        forked = self._fork(self.source_corpus)
        fork_snap = snapshot_corpus(forked, strip_fork_prefix=True)

        ei = self._export_import(self.source_corpus)
        ei_snap = snapshot_corpus(ei)

        for key in baseline.keys():
            self.assertEqual(
                fork_snap[key],
                baseline[key],
                msg=f"Fork lost data in '{key}'",
            )
            self.assertEqual(
                ei_snap[key],
                baseline[key],
                msg=f"Export+import lost data in '{key}'",
            )
            self.assertEqual(
                fork_snap[key],
                ei_snap[key],
                msg=(
                    f"Fork and export+import diverged in '{key}' — "
                    "the parity invariant is broken"
                ),
            )

    def test_three_fork_generations_preserve_state(self) -> None:
        """
        3 sequential forks must produce the same end-state corpus as the
        original, modulo the stacking ``"[FORK] "`` prefix.
        """
        from opencontractserver.tests._corpus_snapshot import snapshot_corpus

        baseline = snapshot_corpus(self.source_corpus)

        gen1 = self._fork(self.source_corpus)
        snap1 = snapshot_corpus(gen1, strip_fork_prefix=True)

        gen2 = self._fork(gen1)
        snap2 = snapshot_corpus(gen2, strip_fork_prefix=True)

        gen3 = self._fork(gen2)
        snap3 = snapshot_corpus(gen3, strip_fork_prefix=True)

        for key in baseline.keys():
            self.assertEqual(
                snap1[key], baseline[key], msg=f"Generation 1 lost data in '{key}'"
            )
            self.assertEqual(
                snap2[key], baseline[key], msg=f"Generation 2 lost data in '{key}'"
            )
            self.assertEqual(
                snap3[key], baseline[key], msg=f"Generation 3 lost data in '{key}'"
            )

        # Title-prefix stacking sanity check: each generation should add
        # exactly one ``"[FORK] "`` prefix to the corpus title.
        self.assertEqual(gen1.title, f"[FORK] {self.source_corpus.title}")
        self.assertEqual(gen2.title, f"[FORK] [FORK] {self.source_corpus.title}")
        self.assertEqual(gen3.title, f"[FORK] [FORK] [FORK] {self.source_corpus.title}")

        # StructuralAnnotationSet must remain deduped to a single row —
        # ``content_hash``-based dedup is the headline V2 invariant and
        # the fork wrapper inherits it for free.
        self.assertEqual(
            StructuralAnnotationSet.objects.filter(
                content_hash="rt_struct_hash"
            ).count(),
            1,
        )
