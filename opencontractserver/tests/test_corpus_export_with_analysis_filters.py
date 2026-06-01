import base64
import pathlib
import uuid

import pytest
from django.core.files.base import ContentFile
from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from opencontractserver.analyzer.models import Analysis, Analyzer
from opencontractserver.annotations.models import (
    TOKEN_LABEL,
    Annotation,
    AnnotationLabel,
    LabelSet,
)
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
        # ``annotation_filter_mode`` accepts an AnnotationFilterMode member or its
        # string value interchangeably (the GraphQL/Celery boundaries deliver the
        # string); this test exercises the string form.
        lookups_corpus_only = build_label_lookups(
            corpus_id=self.original_corpus_obj.id,
            analysis_ids=None,
            annotation_filter_mode="CORPUS_LABELSET_ONLY",
        )
        # CORPUS_LABELSET_ONLY surfaces the corpus label plus the rest of the
        # corpus's label set via the augmentation block. #1868 makes that block
        # fire for the string form too (not just the enum form), so the lookup
        # now spans the whole imported label set; assert the mode *semantics* by
        # label identity rather than a raw count, which depends on the fixture's
        # label-set size. The analysis-only labels must never appear here.
        corpus_only_pks = set(lookups_corpus_only["text_labels"].keys())
        self.assertIn(str(self.original_corpus_obj_label.id), corpus_only_pks)
        self.assertNotIn(str(self.analysis_a_label.id), corpus_only_pks)
        self.assertNotIn(str(self.analysis_b_label.id), corpus_only_pks)

        # 2) Now check CORPUS_LABELSET_PLUS_ANALYSES for both A and B
        lookups_plus_analyses = build_label_lookups(
            corpus_id=self.original_corpus_obj.id,
            analysis_ids=[self.analysis_a.id, self.analysis_b.id],
            annotation_filter_mode="CORPUS_LABELSET_PLUS_ANALYSES",
        )
        # PLUS_ANALYSES is exactly the corpus-labelset set unioned with the two
        # analysis labels.
        analysis_pks = {
            str(self.analysis_a_label.id),
            str(self.analysis_b_label.id),
        }
        self.assertEqual(
            set(lookups_plus_analyses["text_labels"].keys()),
            corpus_only_pks | analysis_pks,
        )

        # 3) ANALYSES_ONLY
        lookups_analyses_only = build_label_lookups(
            corpus_id=self.original_corpus_obj.id,
            analysis_ids=[self.analysis_a.id, self.analysis_b.id],
            annotation_filter_mode="ANALYSES_ONLY",
        )
        # ANALYSES_ONLY keeps its narrow contract: only the analysis labels, with
        # no corpus-labelset augmentation.
        self.assertEqual(set(lookups_analyses_only["text_labels"].keys()), analysis_pks)

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


@pytest.mark.django_db
class BuildLabelLookupsStringEnumEquivalenceTestCase(TestCase):
    """Regression for #1868.

    ``AnnotationFilterMode`` is a str-mixin enum, so a member and its string
    value must drive identical behaviour. Before the fix, build_label_lookups
    compared the mode against bare string literals in some branches but against
    enum members in the corpus-labelset augmentation branch, so a *string*
    argument (what GraphQL/Celery deliver) silently skipped that augmentation;
    build_document_export compared only against enum members and raised
    ValueError (caught -> empty export) for a string argument, which is exactly
    what the V2 export path passes.
    """

    user: User
    corpus: Corpus
    referenced_label: AnnotationLabel
    orphan_label: AnnotationLabel
    analysis: Analysis
    analysis_label: AnnotationLabel
    document: Document

    def setUp(self):
        self.user = User.objects.create_user(username="eq", password="12345678")
        labelset = LabelSet.objects.create(title="LS", creator=self.user)
        self.corpus = Corpus.objects.create(
            title="Equivalence Corpus", label_set=labelset, creator=self.user
        )

        # A label referenced by a corpus annotation ...
        self.referenced_label = AnnotationLabel.objects.create(
            text="Referenced", label_type=TOKEN_LABEL, creator=self.user
        )
        # ... and one that lives in the labelset but has NO annotation. The
        # corpus-labelset augmentation block is the branch that used to be
        # skipped for string input, so this orphan label is the canary.
        self.orphan_label = AnnotationLabel.objects.create(
            text="Orphan", label_type=TOKEN_LABEL, creator=self.user
        )
        labelset.annotation_labels.add(self.referenced_label, self.orphan_label)

        analyzer = Analyzer.objects.create(
            id="EQ_ANALYZER",
            description="x",
            disabled=False,
            is_public=True,
            creator=self.user,
            task_name="fake.task.eq",
        )
        self.analysis = Analysis.objects.create(
            analyzer=analyzer,
            analyzed_corpus=self.corpus,
            creator=self.user,
            analysis_started=timezone.now(),
            analysis_completed=timezone.now(),
        )
        self.analysis_label = AnnotationLabel.objects.create(
            text="AnalysisLbl", label_type=TOKEN_LABEL, creator=self.user
        )

        self.document = Document.objects.create(
            title="Doc", creator=self.user, page_count=1
        )
        # Corpus annotation (no analysis) referencing referenced_label.
        Annotation.objects.create(
            document=self.document,
            corpus=self.corpus,
            annotation_label=self.referenced_label,
            raw_text="ref",
            creator=self.user,
        )
        # Analysis annotation referencing analysis_label.
        Annotation.objects.create(
            document=self.document,
            corpus=self.corpus,
            annotation_label=self.analysis_label,
            analysis=self.analysis,
            raw_text="an",
            creator=self.user,
        )

    def test_string_and_enum_inputs_are_equivalent(self):
        """A string mode and its enum member produce identical label lookups."""
        for mode in AnnotationFilterMode:
            from_enum = build_label_lookups(
                corpus_id=self.corpus.id,
                analysis_ids=[self.analysis.id],
                annotation_filter_mode=mode,
            )
            from_string = build_label_lookups(
                corpus_id=self.corpus.id,
                analysis_ids=[self.analysis.id],
                annotation_filter_mode=mode.value,
            )
            self.assertEqual(
                from_enum,
                from_string,
                msg=f"string vs enum diverged for {mode.value}",
            )

    def test_corpus_labelset_augmentation_fires_for_string_input(self):
        """Orphan labelset label is included for string input (the #1868 bug)."""
        for mode in ("CORPUS_LABELSET_ONLY", "CORPUS_LABELSET_PLUS_ANALYSES"):
            lookups = build_label_lookups(
                corpus_id=self.corpus.id,
                analysis_ids=None,
                annotation_filter_mode=mode,
            )
            self.assertIn(str(self.orphan_label.pk), lookups["text_labels"], mode)
            self.assertIn(str(self.referenced_label.pk), lookups["text_labels"], mode)

    def test_analyses_only_does_not_augment_with_corpus_labelset(self):
        """ANALYSES_ONLY keeps its narrow contract for both input forms."""
        for mode in ("ANALYSES_ONLY", AnnotationFilterMode.ANALYSES_ONLY):
            lookups = build_label_lookups(
                corpus_id=self.corpus.id,
                analysis_ids=[self.analysis.id],
                annotation_filter_mode=mode,
            )
            self.assertNotIn(str(self.orphan_label.pk), lookups["text_labels"])
            self.assertIn(str(self.analysis_label.pk), lookups["text_labels"])

    def test_build_document_export_accepts_string_mode(self):
        """build_document_export must not error on the string the V2 path passes.

        The fixture document deliberately has no file on disk. That is *not* a
        confound for this assertion: build_document_export synthesizes a stable
        ``document_<id>.placeholder`` name for fileless docs and treats the
        missing PAWLs/text reads as non-fatal, so a correct run always returns a
        non-empty ``doc_name`` and a populated ``doc_json``. Before the #1868
        fix, the string mode hit ``else: raise ValueError`` (caught by the
        function's own except), so the function returned ``("", "", None, {},
        {})`` — a silently dropped document. Asserting the exact placeholder name
        and the round-tripped title pins the success path rather than merely
        ``doc_name != ""``.
        """
        lookups = build_label_lookups(
            corpus_id=self.corpus.id,
            analysis_ids=None,
            annotation_filter_mode="CORPUS_LABELSET_ONLY",
        )
        doc_name, _b64, doc_json, _text, _doc = build_document_export(
            label_lookups=lookups,
            doc_id=self.document.id,
            corpus_id=self.corpus.id,
            analysis_ids=None,
            annotation_filter_mode="CORPUS_LABELSET_ONLY",
        )
        # Before the fix this returned ("", "", None, {}, {}) — a dropped doc.
        self.assertEqual(doc_name, f"document_{self.document.id}.placeholder")
        assert doc_json is not None  # narrow for type-checkers + guard the next line
        self.assertEqual(doc_json["title"], self.document.title)

    def test_invalid_mode_raises_valueerror(self):
        """A bogus mode string is rejected at the boundary, not silently defaulted."""
        with self.assertRaises(ValueError):
            build_label_lookups(
                corpus_id=self.corpus.id,
                analysis_ids=None,
                annotation_filter_mode="BOGUS_MODE",
            )
        with self.assertRaises(ValueError):
            build_document_export(
                label_lookups={"text_labels": {}, "doc_labels": {}},
                doc_id=self.document.id,
                corpus_id=self.corpus.id,
                analysis_ids=None,
                annotation_filter_mode="BOGUS_MODE",
            )
