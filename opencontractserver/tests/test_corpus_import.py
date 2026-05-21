import base64
import pathlib
import uuid

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import transaction
from django.test import TestCase

from opencontractserver.annotations.compact_json import expand_annotation_json
from opencontractserver.annotations.models import (
    DOC_TYPE_LABEL,
    RELATIONSHIP_LABEL,
    TOKEN_LABEL,
    Annotation,
    AnnotationLabel,
    Relationship,
)
from opencontractserver.corpuses.models import Corpus, TemporaryFileHandle
from opencontractserver.documents.models import Document
from opencontractserver.tasks import import_corpus
from opencontractserver.tasks.utils import package_zip_into_base64
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.importing import import_relationships
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()

# ---- Expected values derived from Test_Corpus_EXPORT.zip (V1 format) ----

# The fixture contains 79 text labels + 28 doc labels = 107 total.
EXPECTED_TEXT_LABEL_COUNT = 79
EXPECTED_DOC_LABEL_COUNT = 28
EXPECTED_TOTAL_LABEL_COUNT = EXPECTED_TEXT_LABEL_COUNT + EXPECTED_DOC_LABEL_COUNT

# Representative text labels to spot-check.
EXPECTED_TEXT_LABELS = {
    "Parties": {
        "color": "#c17717",
        "icon": "tag",
        "description": "Add a description for Parties",
        "label_type": TOKEN_LABEL,
    },
    "Governing Law": {
        "color": "#21baa8",
        "icon": "tag",
        "description": "Add a description for Governing Law",
        "label_type": TOKEN_LABEL,
    },
    "Anti-Assignment": {
        "color": "#7903af",
        "icon": "tag",
        "description": "Add a description for Anti-Assignment",
        "label_type": TOKEN_LABEL,
    },
    "Effective Date": {
        "color": "#075b82",
        "icon": "tag",
        "description": "Add a description for Effective Date",
        "label_type": TOKEN_LABEL,
    },
}

# Representative doc labels to spot-check.
EXPECTED_DOC_LABELS = {
    "Supply": {
        "color": "#0f4996",
        "icon": "tag",
        "description": "Add a description for Supply",
        "label_type": DOC_TYPE_LABEL,
    },
    "License_Agreements": {
        "color": "#cd0ed3",
        "icon": "tag",
        "description": "Add a description for License_Agreements",
        "label_type": DOC_TYPE_LABEL,
    },
}

# The fixture has one document with 5 text-level annotations and 1 doc-level
# annotation (6 total).
# Each entry: (label_text, raw_text, page, expected_page_key, token_count).
# None for raw_text means the text is too long to inline; the raw_text_and_page
# subtest skips these entries and they are matched by label + page in other subtests.
EXPECTED_TEXT_ANNOTATIONS = [
    ("Parties", " ACTIVE WITH ME, Inc.", 0, "0", 4),
    ("Parties", " Sheri Strangway", 5, "5", 2),
    ("Governing Law", None, 4, "4", 24),
    ("Anti-Assignment", None, 4, "4", 32),
    ("Parties", " Exhibit 10.2", 0, "0", 2),
]

# Expected bounds for the first annotation (ACTIVE WITH ME, Inc.).
EXPECTED_ACTIVE_BOUNDS = {
    "top": 88.44,
    "left": 76.2,
    "right": 186.24,
    "bottom": 103.08,
}


class TestCorpusImport(TestCase):
    """
    Tests for the corpus import pipeline.

    Validates field-level integrity of labels, annotations (5 text-level +
    1 doc-level = 6 total), and relationships after importing
    Test_Corpus_EXPORT.zip (V1 format).

    Read-only assertions are grouped into fewer test methods using subTest
    to minimize redundant import executions (each TransactionTestCase test
    flushes the database).
    """

    fixtures_path = pathlib.Path(__file__).parent / "fixtures"

    def setUp(self):
        self.user = User.objects.create_user(username="bob", password="12345678")

    def _run_import(self) -> Corpus:
        """Run the import pipeline synchronously and return the corpus."""
        export_zip_base64 = package_zip_into_base64(
            self.fixtures_path / "Test_Corpus_EXPORT.zip"
        )

        corpus_obj = Corpus.objects.create(
            title="New Import", creator=self.user, backend_lock=False
        )
        set_permissions_for_obj_to_user(self.user, corpus_obj, [PermissionTypes.ALL])

        decoded_data = base64.decodebytes(export_zip_base64.encode("utf-8"))
        with transaction.atomic():
            temp_file = TemporaryFileHandle.objects.create()
            temp_file.file.save(
                f"corpus_import_{uuid.uuid4()}.zip", ContentFile(decoded_data)
            )

        result = (
            import_corpus.s(temp_file.id, self.user.id, corpus_obj.id).apply().get()
        )
        self.assertIsNotNone(result, "Import task should return a corpus ID")
        self.assertIsInstance(
            result, int, "Import task must return an integer corpus ID"
        )
        return Corpus.objects.get(id=result)

    def _get_corpus_document(self, corpus: Corpus) -> Document:
        """Return the document linked to the corpus via its annotations."""
        # Note: relies on Annotation.document's related_query_name='doc_annotation'
        # (defined in opencontractserver/annotations/models.py)
        doc = (
            Document.objects.filter(doc_annotation__corpus=corpus)
            .distinct()
            .order_by("id")
            .first()
        )
        self.assertIsNotNone(doc, "Should have a corpus-linked document")
        return doc

    def _create_rel_label(self, text: str, color: str = "#000000") -> AnnotationLabel:
        """Create a standalone relationship label with permissions for self.user.

        Not added to any labelset — these are used to test
        import_relationships() in isolation, not the full label pipeline.
        """
        label = AnnotationLabel.objects.create(
            text=text,
            label_type=RELATIONSHIP_LABEL,
            color=color,
            icon="tag",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, label, [PermissionTypes.ALL])
        return label

    # ------------------------------------------------------------------
    # Object counts and label integrity (issue #999 requirement 1)
    # ------------------------------------------------------------------

    def test_import_counts_and_label_integrity(self):
        """Verify object counts and label field-level integrity after import."""
        corpus = self._run_import()

        # -- Object-count smoke tests --
        with self.subTest("object_counts"):
            self.assertEqual(
                AnnotationLabel.objects.count(), EXPECTED_TOTAL_LABEL_COUNT
            )
            # Assert the imported corpus exists by PK (the import task
            # overwrites the seed corpus title with the value from data.json).
            self.assertIsNotNone(corpus)
            self.assertTrue(Corpus.objects.filter(pk=corpus.pk).exists())
            # 1 standalone document + 1 corpus-isolated copy
            self.assertEqual(Document.objects.count(), 2)
            # 5 text annotations + 1 doc-level annotation
            self.assertEqual(Annotation.objects.count(), 6)
            self.assertEqual(Relationship.objects.count(), 0)

        # -- Label counts by type --
        with self.subTest("label_counts_by_type"):
            text_labels = AnnotationLabel.objects.filter(label_type=TOKEN_LABEL)
            self.assertEqual(text_labels.count(), EXPECTED_TEXT_LABEL_COUNT)

            doc_labels = AnnotationLabel.objects.filter(label_type=DOC_TYPE_LABEL)
            self.assertEqual(doc_labels.count(), EXPECTED_DOC_LABEL_COUNT)

        # -- Text label fields --
        with self.subTest("text_label_fields"):
            for label_text, expected in EXPECTED_TEXT_LABELS.items():
                label = AnnotationLabel.objects.get(
                    text=label_text, label_type=TOKEN_LABEL
                )
                self.assertEqual(label.color, expected["color"])
                self.assertEqual(label.icon, expected["icon"])
                self.assertEqual(label.description, expected["description"])
                self.assertEqual(label.label_type, expected["label_type"])
                self.assertEqual(label.creator, self.user)

        # -- Doc label fields --
        with self.subTest("doc_label_fields"):
            for label_text, expected in EXPECTED_DOC_LABELS.items():
                label = AnnotationLabel.objects.get(
                    text=label_text, label_type=DOC_TYPE_LABEL
                )
                self.assertEqual(label.color, expected["color"])
                self.assertEqual(label.icon, expected["icon"])
                self.assertEqual(label.description, expected["description"])
                self.assertEqual(label.label_type, expected["label_type"])
                self.assertEqual(label.creator, self.user)

        # -- Labels belong to corpus labelset --
        with self.subTest("labels_belong_to_corpus_labelset"):
            labelset = corpus.label_set
            self.assertIsNotNone(labelset)
            self.assertEqual(
                labelset.annotation_labels.count(), EXPECTED_TOTAL_LABEL_COUNT
            )

    # ------------------------------------------------------------------
    # Annotation validation (issue #999 requirement 2)
    # ------------------------------------------------------------------

    def test_annotation_validation(self):
        """Verify annotation field-level integrity: labels, text, pages,
        JSON structure, bounds, and tokens."""
        corpus = self._run_import()
        doc = self._get_corpus_document(corpus)

        # -- Label references --
        with self.subTest("label_references"):
            text_annots = Annotation.objects.filter(
                corpus=corpus, document=doc, annotation_label__label_type=TOKEN_LABEL
            )
            self.assertEqual(text_annots.count(), 5)
            self.assertEqual(
                text_annots.filter(annotation_label__text="Parties").count(), 3
            )
            self.assertEqual(
                text_annots.filter(annotation_label__text="Governing Law").count(), 1
            )
            self.assertEqual(
                text_annots.filter(annotation_label__text="Anti-Assignment").count(), 1
            )

        # -- Raw text and page numbers --
        with self.subTest("raw_text_and_page"):
            for label_text, raw_text, page, _, _ in EXPECTED_TEXT_ANNOTATIONS:
                if raw_text is None:
                    continue
                annot = Annotation.objects.get(
                    corpus=corpus,
                    document=doc,
                    annotation_label__text=label_text,
                    raw_text=raw_text,
                )
                self.assertEqual(
                    annot.page,
                    page,
                    f"Page mismatch for annotation '{raw_text}'",
                )

        # -- Annotation JSON: bounds and token counts --
        with self.subTest("spans_and_tokens"):
            for (
                label_text,
                raw_text,
                _,
                page_key,
                token_count,
            ) in EXPECTED_TEXT_ANNOTATIONS:
                qs = Annotation.objects.filter(
                    corpus=corpus,
                    document=doc,
                    annotation_label__text=label_text,
                ).order_by("page", "id")
                if raw_text is None:
                    # Can't filter by raw_text, so verify exactly one
                    # annotation exists for this label to avoid ambiguity.
                    self.assertEqual(
                        qs.count(),
                        1,
                        f"Expected exactly 1 annotation for {label_text}",
                    )
                else:
                    qs = qs.filter(raw_text=raw_text)
                annot = qs.first()
                self.assertIsNotNone(annot, f"Missing annotation for {label_text}")

                expanded = expand_annotation_json(
                    annot.json, raw_text=annot.raw_text or ""
                )
                self.assertIn(
                    page_key,
                    expanded,
                    f"annotation_json missing page key '{page_key}' "
                    f"for '{label_text}' / '{raw_text}'",
                )

                page_data = expanded[page_key]
                self.assertIn("bounds", page_data)

                tokens = page_data.get("tokensJsons", [])
                self.assertEqual(
                    len(tokens),
                    token_count,
                    f"Token count mismatch for '{label_text}' / '{raw_text}'",
                )

        # -- Bounding box spot-check --
        with self.subTest("bounds_values"):
            annot = Annotation.objects.get(
                corpus=corpus,
                document=doc,
                raw_text=" ACTIVE WITH ME, Inc.",
            )
            expanded = expand_annotation_json(annot.json, raw_text=annot.raw_text or "")
            bounds = expanded["0"]["bounds"]
            self.assertAlmostEqual(
                bounds["top"], EXPECTED_ACTIVE_BOUNDS["top"], places=1
            )
            self.assertAlmostEqual(
                bounds["left"], EXPECTED_ACTIVE_BOUNDS["left"], places=1
            )
            # Right edge has ~0.24 units of floating-point drift from
            # coordinate aggregation across multiple tokens; delta=0.3 is the
            # tightest tolerance that accommodates this without flaking.
            self.assertAlmostEqual(
                bounds["right"], EXPECTED_ACTIVE_BOUNDS["right"], delta=0.3
            )
            self.assertAlmostEqual(
                bounds["bottom"], EXPECTED_ACTIVE_BOUNDS["bottom"], places=1
            )

        # -- Token structure --
        with self.subTest("token_structure"):
            annot = Annotation.objects.get(
                corpus=corpus,
                document=doc,
                raw_text=" ACTIVE WITH ME, Inc.",
            )
            expanded = expand_annotation_json(annot.json, raw_text=annot.raw_text or "")
            tokens = expanded["0"]["tokensJsons"]
            for token in tokens:
                self.assertIn("pageIndex", token)
                self.assertIn("tokenIndex", token)
                self.assertEqual(token["pageIndex"], 0)

        # -- Doc-level annotation --
        with self.subTest("doc_level_annotation"):
            doc_annots = Annotation.objects.filter(
                corpus=corpus,
                document=doc,
                annotation_label__label_type=DOC_TYPE_LABEL,
            )
            self.assertEqual(doc_annots.count(), 1)
            self.assertEqual(doc_annots.first().annotation_label.text, "Supply")

    # ------------------------------------------------------------------
    # Relationship verification (issue #999 requirement 3)
    # ------------------------------------------------------------------

    def test_relationship_import(self):
        """Validate import_relationships: single links, multiple sources/targets,
        and structural flag preservation."""
        # NOTE: subtests share corpus state. Assert specific relationships by label
        # rather than using global counts, which would include earlier subtests' data.
        corpus = self._run_import()
        doc = self._get_corpus_document(corpus)

        # -- Single source → single target --
        with self.subTest("single_source_and_target"):
            source_annot = Annotation.objects.filter(
                corpus=corpus, document=doc, raw_text=" ACTIVE WITH ME, Inc."
            ).first()
            target_annot = Annotation.objects.filter(
                corpus=corpus, document=doc, annotation_label__text="Governing Law"
            ).first()
            self.assertIsNotNone(source_annot)
            self.assertIsNotNone(target_annot)

            rel_label = self._create_rel_label("references")

            annotation_id_map = {
                str(source_annot.pk): source_annot.pk,
                str(target_annot.pk): target_annot.pk,
            }

            relationships_data = [
                {
                    "id": "rel_1",
                    "relationshipLabel": "references",
                    "source_annotation_ids": [str(source_annot.pk)],
                    "target_annotation_ids": [str(target_annot.pk)],
                    "structural": False,
                },
            ]

            result = import_relationships(
                user_id=self.user.id,
                doc_obj=doc,
                corpus_obj=corpus,
                relationships_data=relationships_data,
                label_lookup={"references": rel_label},
                annotation_id_map=annotation_id_map,
            )

            self.assertEqual(len(result), 1)
            self.assertIn("rel_1", result)

            rel = result["rel_1"]
            self.assertEqual(rel.relationship_label, rel_label)
            self.assertEqual(rel.corpus, corpus)
            self.assertEqual(rel.document, doc)
            self.assertFalse(rel.structural)
            self.assertEqual(rel.source_annotations.count(), 1)
            self.assertEqual(rel.target_annotations.count(), 1)
            self.assertEqual(rel.source_annotations.first().pk, source_annot.pk)
            self.assertEqual(rel.target_annotations.first().pk, target_annot.pk)

        # -- Multiple sources → multiple targets --
        with self.subTest("multiple_sources_and_targets"):
            parties_annots = list(
                Annotation.objects.filter(
                    corpus=corpus,
                    document=doc,
                    annotation_label__text="Parties",
                )[:2]
            )
            gov_law = Annotation.objects.filter(
                corpus=corpus,
                document=doc,
                annotation_label__text="Governing Law",
            ).first()
            anti_assign = Annotation.objects.filter(
                corpus=corpus,
                document=doc,
                annotation_label__text="Anti-Assignment",
            ).first()
            self.assertEqual(len(parties_annots), 2)
            self.assertIsNotNone(gov_law)
            self.assertIsNotNone(anti_assign)

            rel_label_multi = self._create_rel_label("related_to", color="#112233")

            all_pks = [a.pk for a in parties_annots] + [gov_law.pk, anti_assign.pk]
            annotation_id_map_multi = {str(pk): pk for pk in all_pks}

            relationships_data_multi = [
                {
                    "id": "rel_multi",
                    "relationshipLabel": "related_to",
                    "source_annotation_ids": [str(a.pk) for a in parties_annots],
                    "target_annotation_ids": [
                        str(gov_law.pk),
                        str(anti_assign.pk),
                    ],
                    "structural": False,
                },
            ]

            result_multi = import_relationships(
                user_id=self.user.id,
                doc_obj=doc,
                corpus_obj=corpus,
                relationships_data=relationships_data_multi,
                label_lookup={"related_to": rel_label_multi},
                annotation_id_map=annotation_id_map_multi,
            )

            self.assertEqual(len(result_multi), 1)
            self.assertIn("rel_multi", result_multi)

            rel_m = result_multi["rel_multi"]
            self.assertEqual(rel_m.source_annotations.count(), 2)
            self.assertEqual(rel_m.target_annotations.count(), 2)

            source_pks = set(rel_m.source_annotations.values_list("pk", flat=True))
            self.assertEqual(source_pks, {a.pk for a in parties_annots})

            target_pks = set(rel_m.target_annotations.values_list("pk", flat=True))
            self.assertEqual(target_pks, {gov_law.pk, anti_assign.pk})

        # -- Structural flag preservation --
        with self.subTest("structural_flag"):
            annots = list(Annotation.objects.filter(corpus=corpus, document=doc)[:2])
            self.assertEqual(len(annots), 2)

            rel_label_struct = self._create_rel_label("structural_ref", color="#445566")

            annotation_id_map_struct = {str(a.pk): a.pk for a in annots}

            relationships_data_struct = [
                {
                    "id": "rel_struct",
                    "relationshipLabel": "structural_ref",
                    "source_annotation_ids": [str(annots[0].pk)],
                    "target_annotation_ids": [str(annots[1].pk)],
                    "structural": True,
                },
            ]

            result_struct = import_relationships(
                user_id=self.user.id,
                doc_obj=doc,
                corpus_obj=corpus,
                relationships_data=relationships_data_struct,
                label_lookup={"structural_ref": rel_label_struct},
                annotation_id_map=annotation_id_map_struct,
            )

            self.assertEqual(len(result_struct), 1)
            self.assertIn("rel_struct", result_struct)
            self.assertTrue(result_struct["rel_struct"].structural)
