import base64
import pathlib
import uuid

import pytest
from django.core.files.base import ContentFile
from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from opencontractserver.analyzer.models import Analysis, Analyzer
from opencontractserver.annotations.models import Annotation, AnnotationLabel
from opencontractserver.corpuses.models import Corpus, TemporaryFileHandle
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.tasks.import_tasks import import_corpus
from opencontractserver.tasks.utils import package_zip_into_base64
from opencontractserver.types.enums import AnnotationFilterMode, PermissionTypes
from opencontractserver.users.models import User
from opencontractserver.utils.etl import build_document_export, build_label_lookups
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user


@pytest.mark.django_db
class ExportCorpusWithAnalysesTestCase(TestCase):
    """
    Test suite that verifies we can layer on multiple Analyses with extra Annotations,
    and confirm our export pipeline's annotation counts vary according to the
    'annotation_filter_mode' in build_document_export().

    This is modeled on test_corpus_export.py, but focuses on multi-analysis filtering behaviors.
    """

    fixtures_path = pathlib.Path(__file__).parent / "fixtures"

    user: User
    original_corpus_obj: Corpus
    document: Document
    analyzer_a: Analyzer
    analysis_a: Analysis
    analyzer_b: Analyzer
    analysis_b: Analysis
    original_corpus_obj_label: AnnotationLabel
    analysis_a_label: AnnotationLabel
    analysis_b_label: AnnotationLabel

    def setUp(self):
        """
        Create a user, a corpus, two analyses (Analysis A & B), a document, and several annotations.
        Some annotations are tied purely to the corpus label set. Some are tied to Analysis A or B.
        """

        self.user = User.objects.create_user(username="bob", password="12345678")

        export_zip_base64_file_string = package_zip_into_base64(
            self.fixtures_path / "Test_Corpus_EXPORT.zip"
        )
        self.original_corpus_obj = Corpus.objects.create(
            title="New Import", creator=self.user, backend_lock=False
        )
        set_permissions_for_obj_to_user(
            self.user, self.original_corpus_obj, [PermissionTypes.ALL]
        )

        base64_img_bytes = export_zip_base64_file_string.encode("utf-8")
        decoded_file_data = base64.decodebytes(base64_img_bytes)

        with transaction.atomic():
            temporary_file = TemporaryFileHandle.objects.create()
            temporary_file.file.save(
                f"corpus_import_{uuid.uuid4()}.pdf", ContentFile(decoded_file_data)
            )

        import_task = import_corpus.s(
            temporary_file.id, self.user.id, self.original_corpus_obj.id
        )

        import_task.apply().get()

        # Get document via DocumentPath since Document no longer has corpus field
        doc_path = DocumentPath.objects.filter(corpus=self.original_corpus_obj).first()
        assert doc_path is not None
        self.document = doc_path.document

        # 4) Create two Analyzers & two Analyses referencing this corpus
        self.analyzer_a = Analyzer.objects.create(
            id="ANALYZER_A",
            description="First Analyzer",
            disabled=False,
            is_public=True,
            creator=self.user,
            task_name="fake.task.name.1",
        )
        self.analysis_a = Analysis.objects.create(
            analyzer=self.analyzer_a,
            analyzed_corpus=self.original_corpus_obj,
            creator=self.user,
            analysis_started=timezone.now(),
            analysis_completed=timezone.now(),
        )

        self.analyzer_b = Analyzer.objects.create(
            id="ANALYZER_B",
            description="Second Analyzer",
            disabled=False,
            is_public=True,
            creator=self.user,
            task_name="fake.task.name.2",
        )
        self.analysis_b = Analysis.objects.create(
            analyzer=self.analyzer_b,
            analyzed_corpus=self.original_corpus_obj,
            creator=self.user,
            analysis_started=timezone.now(),
            analysis_completed=timezone.now(),
        )

        # 5) Build some label objects
        #    We'll create a label for the corpus (like a normal corpus-based token label),
        #    plus separate "analysis-only" labels that appear only in Analysis A or B.
        self.original_corpus_obj_label = AnnotationLabel.objects.create(
            text="Corpus Label",
            label_type="TOKEN_LABEL",
            color="#FF0000",  # e.g. Red
            creator=self.user,
        )
        self.analysis_a_label = AnnotationLabel.objects.create(
            text="AnalysisA Label",
            label_type="TOKEN_LABEL",
            color="#00FF00",  # e.g. Green
            creator=self.user,
        )
        self.analysis_b_label = AnnotationLabel.objects.create(
            text="AnalysisB Label",
            label_type="TOKEN_LABEL",
            color="#0000FF",  # e.g. Blue
            creator=self.user,
        )

        # 6) Create some Annotations referencing these labels. Some purely corpus-based (no analysis),
        #    some referencing analysis A or B.
        #    We'll pretend each annotation belongs to the one doc we created.
        #    Also note that corpus-based annotations typically don't set analysis_id.
        Annotation.objects.create(
            document=self.document,
            corpus=self.original_corpus_obj,
            annotation_label=self.original_corpus_obj_label,
            creator=self.user,
            json={
                "0": {
                    "bounds": {
                        "top": 88.44,
                        "left": 76.2,
                        "right": 186.23999999999998,
                        "bottom": 103.08,
                    },
                    "rawText": "ACTIVE WITH ME, Inc.",
                    "tokensJsons": [
                        {"pageIndex": 0, "tokenIndex": 22},
                        {"pageIndex": 0, "tokenIndex": 23},
                        {"pageIndex": 0, "tokenIndex": 24},
                        {"pageIndex": 0, "tokenIndex": 25},
                    ],
                }
            },
        )
        Annotation.objects.create(
            document=self.document,
            corpus=self.original_corpus_obj,
            annotation_label=self.original_corpus_obj_label,
            creator=self.user,
            json={
                "0": {
                    "bounds": {
                        "top": 88.44,
                        "left": 76.2,
                        "right": 186.23999999999998,
                        "bottom": 103.08,
                    },
                    "rawText": "ACTIVE WITH ME, Inc.",
                    "tokensJsons": [
                        {"pageIndex": 0, "tokenIndex": 22},
                        {"pageIndex": 0, "tokenIndex": 23},
                        {"pageIndex": 0, "tokenIndex": 24},
                        {"pageIndex": 0, "tokenIndex": 25},
                    ],
                }
            },
        )
        Annotation.objects.create(
            document=self.document,
            corpus=self.original_corpus_obj,
            annotation_label=self.analysis_a_label,
            analysis=self.analysis_a,
            creator=self.user,
            json={
                "0": {
                    "bounds": {
                        "top": 88.44,
                        "left": 76.2,
                        "right": 186.23999999999998,
                        "bottom": 103.08,
                    },
                    "rawText": "ACTIVE WITH ME, Inc.",
                    "tokensJsons": [
                        {"pageIndex": 0, "tokenIndex": 22},
                        {"pageIndex": 0, "tokenIndex": 23},
                        {"pageIndex": 0, "tokenIndex": 24},
                        {"pageIndex": 0, "tokenIndex": 25},
                    ],
                }
            },
        )
        Annotation.objects.create(
            document=self.document,
            corpus=self.original_corpus_obj,
            annotation_label=self.analysis_b_label,
            analysis=self.analysis_b,
            creator=self.user,
            json={
                "0": {
                    "bounds": {
                        "top": 88.44,
                        "left": 76.2,
                        "right": 186.23999999999998,
                        "bottom": 103.08,
                    },
                    "rawText": "ACTIVE WITH ME, Inc.",
                    "tokensJsons": [
                        {"pageIndex": 0, "tokenIndex": 22},
                        {"pageIndex": 0, "tokenIndex": 23},
                        {"pageIndex": 0, "tokenIndex": 24},
                        {"pageIndex": 0, "tokenIndex": 25},
                    ],
                }
            },
        )

    def test_filter_modes_change_annotation_count(self):
        """
        Asserts that the number of exported annotations changes
        depending on the annotation_filter_mode when calling build_document_export.
        """

        # 1) Build label lookups for the entire corpus, ignoring or including analyses as needed
        #    For CORPUS_LABELSET_ONLY, we should see only "corpus_label" in the lookup
        # NOTE: build_label_lookups is annotated to take an AnnotationFilterMode enum,
        # but its body compares the argument against raw string literals (== "ANALYSES_ONLY"
        # etc.), so callers must pass the string value, not the enum member. The string
        # form is the contract this test deliberately exercises; the arg-type ignores below
        # reflect that production annotation/runtime mismatch (see final report).
        lookups_corpus_only = build_label_lookups(
            corpus_id=self.original_corpus_obj.id,
            analysis_ids=None,
            annotation_filter_mode="CORPUS_LABELSET_ONLY",  # type: ignore[arg-type]
        )
        self.assertEqual(
            len(lookups_corpus_only["text_labels"]), 4
        )  # just "Corpus Label"

        # 2) Now check CORPUS_LABELSET_PLUS_ANALYSES for both A and B
        lookups_plus_analyses = build_label_lookups(
            corpus_id=self.original_corpus_obj.id,
            analysis_ids=[self.analysis_a.id, self.analysis_b.id],
            annotation_filter_mode="CORPUS_LABELSET_PLUS_ANALYSES",  # type: ignore[arg-type]
        )
        # We expect 3 total labels: corpus_label + analysis_a_label + analysis_b_label
        self.assertEqual(len(lookups_plus_analyses["text_labels"]), 6)

        # 3) ANALYSES_ONLY
        lookups_analyses_only = build_label_lookups(
            corpus_id=self.original_corpus_obj.id,
            analysis_ids=[self.analysis_a.id, self.analysis_b.id],
            annotation_filter_mode="ANALYSES_ONLY",  # type: ignore[arg-type]
        )
        # We expect 2 total labels: analysis_a_label + analysis_b_label
        self.assertEqual(len(lookups_analyses_only["text_labels"]), 2)

        # Next, let's see how many annotations we get from build_document_export itself:

        # CORPUS_LABELSET_ONLY => 2 annotations (both reference corpus_label)
        (
            doc_name,
            base64_file,
            doc_export_data,
            text_lbls,
            doc_lbls,
        ) = build_document_export(
            label_lookups=lookups_corpus_only,
            doc_id=self.document.id,
            corpus_id=self.original_corpus_obj.id,
            analysis_ids=None,
            annotation_filter_mode=AnnotationFilterMode.CORPUS_LABELSET_ONLY,
        )

        assert doc_export_data is not None
        self.assertEqual(len(doc_export_data["labelled_text"]), 7)

        # CORPUS_LABELSET_PLUS_ANALYSES => 4 total annotations
        # (2 corpus-based + 1 from Analysis A + 1 from Analysis B)
        (
            doc_name,
            base64_file,
            doc_export_data,
            text_lbls,
            doc_lbls,
        ) = build_document_export(
            label_lookups=lookups_plus_analyses,
            doc_id=self.document.id,
            corpus_id=self.original_corpus_obj.id,
            analysis_ids=[self.analysis_a.id, self.analysis_b.id],
            annotation_filter_mode=AnnotationFilterMode.CORPUS_LABELSET_PLUS_ANALYSES,
        )
        assert doc_export_data is not None
        self.assertEqual(len(doc_export_data["labelled_text"]), 9)

        # ANALYSES_ONLY => 2 total annotations (1 from Analysis A, 1 from B)
        (
            doc_name,
            base64_file,
            doc_export_data,
            text_lbls,
            doc_lbls,
        ) = build_document_export(
            label_lookups=lookups_analyses_only,
            doc_id=self.document.id,
            corpus_id=self.original_corpus_obj.id,
            analysis_ids=[self.analysis_a.id, self.analysis_b.id],
            annotation_filter_mode=AnnotationFilterMode.ANALYSES_ONLY,
        )
        assert doc_export_data is not None
        self.assertEqual(len(doc_export_data["labelled_text"]), 2)
