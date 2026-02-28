import base64
import json
import pathlib
import uuid
import zipfile

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import transaction
from django.test import TestCase
from pydantic import TypeAdapter, ValidationError

from opencontractserver.corpuses.models import Corpus, TemporaryFileHandle
from opencontractserver.tasks import import_corpus
from opencontractserver.tasks.utils import package_zip_into_base64
from opencontractserver.types.dicts import OpenContractDocExport
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.etl import build_document_export, build_label_lookups
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()

pytestmark = pytest.mark.django_db

# Expected bounding-box keys on every annotation page entry
_BOUNDS_KEYS = {"top", "bottom", "left", "right"}


class ExportCorpusTestCase(TestCase):
    fixtures_path = pathlib.Path(__file__).parent / "fixtures"

    def setUp(self):
        self.user = User.objects.create_user(username="bob", password="12345678")

        zip_path = self.fixtures_path / "Test_Corpus_EXPORT.zip"

        export_zip_base64_file_string = package_zip_into_base64(zip_path)
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

        # Load the import fixture so we can compare exports against original import
        with zipfile.ZipFile(zip_path, "r") as zf:
            self.import_data = json.loads(zf.read("data.json").decode("utf-8"))

    def test_export_utils(self):
        """Test that the export pipeline runs without errors and returns
        the expected label counts."""
        self.original_corpus_obj.refresh_from_db()

        label_lookups = build_label_lookups(corpus_id=self.original_corpus_obj.id)

        assert "text_labels" in label_lookups
        assert len(label_lookups["text_labels"]) == 3

        assert "doc_labels" in label_lookups
        assert len(label_lookups["doc_labels"]) == 1

        for doc in self.original_corpus_obj.get_documents():
            result = build_document_export(
                label_lookups=label_lookups,
                doc_id=doc.id,
                corpus_id=self.original_corpus_obj.id,
            )
            # Should return a 5-tuple with non-None annotation JSON
            self.assertEqual(len(result), 5)
            doc_name, base64_msg, doc_annotation_json, text_labels, doc_labels = result
            self.assertIsNotNone(doc_annotation_json)

    def test_exported_values_match_types(self):
        """Test that exported values from build_document_export match the
        expected Pydantic / TypedDict data shapes."""
        label_lookups = build_label_lookups(corpus_id=self.original_corpus_obj.id)

        for doc in self.original_corpus_obj.get_documents():
            (
                doc_name,
                base64_encoded_message,
                doc_annotation_json,
                text_labels,
                doc_labels,
            ) = build_document_export(
                label_lookups=label_lookups,
                doc_id=doc.id,
                corpus_id=self.original_corpus_obj.id,
            )

            # Validate doc_annotation_json matches OpenContractDocExport
            try:
                adapter = TypeAdapter(OpenContractDocExport)
                adapter.validate_python(doc_annotation_json)
            except ValidationError as e:
                self.fail(
                    f"doc_annotation_json does not match OpenContractDocExport: {e}"
                )

            self.assertIsInstance(doc_name, str)
            self.assertIsInstance(base64_encoded_message, str)
            self.assertIsInstance(text_labels, dict)
            self.assertIsInstance(doc_labels, dict)

            for label in text_labels.values():
                self.assertIsInstance(label, dict)
                self.assertIn("id", label)
                self.assertIn("text", label)
                self.assertIn("color", label)

            for label in doc_labels.values():
                self.assertIsInstance(label, dict)
                self.assertIn("id", label)
                self.assertIn("text", label)
                self.assertIn("color", label)

    # ------------------------------------------------------------------
    # New: Structure validation
    # ------------------------------------------------------------------

    def test_exported_document_structure(self):
        """Validate that each exported document contains all required
        top-level keys and that nested structures (annotations, PAWLS
        pages, bounding boxes) conform to the expected schema."""
        label_lookups = build_label_lookups(corpus_id=self.original_corpus_obj.id)

        for doc in self.original_corpus_obj.get_documents():
            (
                doc_name,
                base64_encoded_message,
                doc_annotation_json,
                text_labels,
                doc_labels,
            ) = build_document_export(
                label_lookups=label_lookups,
                doc_id=doc.id,
                corpus_id=self.original_corpus_obj.id,
            )

            # ----- Top-level keys -----
            required_keys = {
                "title",
                "content",
                "doc_labels",
                "labelled_text",
                "pawls_file_content",
                "page_count",
            }
            self.assertTrue(
                required_keys.issubset(doc_annotation_json.keys()),
                f"Missing keys: {required_keys - doc_annotation_json.keys()}",
            )

            # ----- Title / content / page_count -----
            self.assertIsInstance(doc_annotation_json["title"], str)
            self.assertGreater(len(doc_annotation_json["title"]), 0)
            self.assertIsInstance(doc_annotation_json["content"], str)
            self.assertIsInstance(doc_annotation_json["page_count"], int)
            self.assertGreater(doc_annotation_json["page_count"], 0)

            # ----- doc_labels list -----
            self.assertIsInstance(doc_annotation_json["doc_labels"], list)
            for dl in doc_annotation_json["doc_labels"]:
                self.assertIsInstance(dl, str)

            # ----- PAWLS pages -----
            pawls = doc_annotation_json["pawls_file_content"]
            self.assertIsInstance(pawls, list)
            self.assertGreater(len(pawls), 0)
            for page_obj in pawls:
                self.assertIn("page", page_obj)
                self.assertIn("tokens", page_obj)
                page_meta = page_obj["page"]
                for dim_key in ("width", "height", "index"):
                    self.assertIn(dim_key, page_meta)
                self.assertIsInstance(page_obj["tokens"], list)

            # ----- Annotations -----
            labelled_text = doc_annotation_json["labelled_text"]
            self.assertIsInstance(labelled_text, list)

            for annot in labelled_text:
                # Required fields on every annotation
                for field in (
                    "id",
                    "annotationLabel",
                    "rawText",
                    "page",
                    "annotation_json",
                ):
                    self.assertIn(field, annot, f"Annotation missing '{field}'")

                self.assertIsInstance(annot["rawText"], str)
                self.assertGreater(len(annot["rawText"]), 0)
                self.assertIsInstance(annot["page"], int)

                # annotation_json maps page numbers (as strings) to page data
                self.assertIsInstance(annot["annotation_json"], dict)
                for page_key, page_data in annot["annotation_json"].items():
                    self.assertIn("bounds", page_data)
                    self.assertTrue(
                        _BOUNDS_KEYS.issubset(page_data["bounds"].keys()),
                        f"Bounds missing keys: "
                        f"{_BOUNDS_KEYS - set(page_data['bounds'].keys())}",
                    )
                    self.assertIn("tokensJsons", page_data)
                    self.assertIsInstance(page_data["tokensJsons"], list)
                    for token_ref in page_data["tokensJsons"]:
                        self.assertIn("pageIndex", token_ref)
                        self.assertIn("tokenIndex", token_ref)

            # ----- PDF burn-in produces valid base64 for PDFs -----
            if doc.file_type == "application/pdf" and base64_encoded_message:
                decoded = base64.b64decode(base64_encoded_message)
                self.assertTrue(
                    decoded[:5] == b"%PDF-",
                    "Burned-in PDF does not start with %PDF- header",
                )

    # ------------------------------------------------------------------
    # New: Round-trip consistency (export vs. original import fixture)
    # ------------------------------------------------------------------

    def test_round_trip_consistency(self):
        """Compare exported data against the original import fixture to
        verify round-trip fidelity.

        Checks:
        - Document title matches
        - Document text content matches
        - PAWLS page count and dimensions match
        - Number of annotations matches
        - Annotation raw text values match
        - Annotation label names match (mapped through label lookups)
        - Annotation bounding boxes match (within tolerance)
        - Document-level labels match
        """
        label_lookups = build_label_lookups(corpus_id=self.original_corpus_obj.id)

        # The fixture has exactly one document
        fixture_doc_key = list(self.import_data["annotated_docs"].keys())[0]
        fixture_doc = self.import_data["annotated_docs"][fixture_doc_key]
        fixture_text_labels = self.import_data["text_labels"]

        # Export the single document in the corpus
        docs = list(self.original_corpus_obj.get_documents())
        self.assertEqual(len(docs), 1, "Expected exactly 1 document in corpus")

        (
            doc_name,
            _base64_msg,
            exported,
            text_labels,
            doc_labels,
        ) = build_document_export(
            label_lookups=label_lookups,
            doc_id=docs[0].id,
            corpus_id=self.original_corpus_obj.id,
        )

        # ----- Document title -----
        self.assertEqual(
            exported["title"],
            fixture_doc["title"],
            "Document title does not match fixture",
        )

        # ----- Document content -----
        self.assertEqual(
            exported["content"],
            fixture_doc["content"],
            "Document content does not match fixture",
        )

        # ----- PAWLS pages -----
        fixture_pawls = fixture_doc["pawls_file_content"]
        exported_pawls = exported["pawls_file_content"]
        self.assertEqual(
            len(exported_pawls),
            len(fixture_pawls),
            "PAWLS page count mismatch",
        )
        for i, (exp_page, fix_page) in enumerate(zip(exported_pawls, fixture_pawls)):
            self.assertEqual(
                exp_page["page"]["width"],
                fix_page["page"]["width"],
                f"Page {i} width mismatch",
            )
            self.assertEqual(
                exp_page["page"]["height"],
                fix_page["page"]["height"],
                f"Page {i} height mismatch",
            )
            self.assertEqual(
                exp_page["page"]["index"],
                fix_page["page"]["index"],
                f"Page {i} index mismatch",
            )
            self.assertEqual(
                len(exp_page["tokens"]),
                len(fix_page["tokens"]),
                f"Page {i} token count mismatch",
            )

        # ----- Document-level labels -----
        self.assertEqual(
            sorted(exported["doc_labels"]),
            sorted(fixture_doc["doc_labels"]),
            "Document-level labels do not match fixture",
        )

        # ----- Annotation count -----
        fixture_annots = fixture_doc["labelled_text"]
        exported_annots = exported["labelled_text"]
        self.assertEqual(
            len(exported_annots),
            len(fixture_annots),
            "Annotation count mismatch",
        )

        # Build a map from fixture label ID -> label text for comparison.
        # The export uses new DB IDs for labels, so we compare by label text.
        fixture_label_id_to_text = {
            lid: ldata["text"] for lid, ldata in fixture_text_labels.items()
        }
        exported_label_id_to_text = {
            lid: ldata["text"] for lid, ldata in text_labels.items()
        }

        # Sort both annotation lists by (rawText, page) to break ties stably
        fixture_sorted = sorted(fixture_annots, key=lambda a: (a["rawText"], a["page"]))
        exported_sorted = sorted(
            exported_annots, key=lambda a: (a["rawText"], a["page"])
        )

        for fix_annot, exp_annot in zip(fixture_sorted, exported_sorted):
            # Raw text
            self.assertEqual(
                exp_annot["rawText"],
                fix_annot["rawText"],
                "Annotation rawText mismatch",
            )

            # Page number
            self.assertEqual(
                exp_annot["page"],
                fix_annot["page"],
                f"Annotation page mismatch for '{exp_annot['rawText'][:40]}'",
            )

            # Label name (compare by resolved text, not by ID)
            fix_label_text = fixture_label_id_to_text[fix_annot["annotationLabel"]]
            exp_label_text = exported_label_id_to_text[exp_annot["annotationLabel"]]
            self.assertEqual(
                exp_label_text,
                fix_label_text,
                f"Label mismatch for annotation '{exp_annot['rawText'][:40]}'",
            )

            # Bounding boxes (compare per-page)
            fix_json = fix_annot["annotation_json"]
            exp_json = exp_annot["annotation_json"]
            self.assertEqual(
                set(exp_json.keys()),
                set(fix_json.keys()),
                f"Annotation page keys mismatch for '{exp_annot['rawText'][:40]}'",
            )

            for page_key in fix_json:
                fix_bounds = fix_json[page_key]["bounds"]
                exp_bounds = exp_json[page_key]["bounds"]
                for coord in ("top", "bottom", "left", "right"):
                    self.assertAlmostEqual(
                        exp_bounds[coord],
                        fix_bounds[coord],
                        places=2,
                        msg=(
                            f"Bounds '{coord}' mismatch on page {page_key} "
                            f"for '{exp_annot['rawText'][:40]}'"
                        ),
                    )

                # Token references count
                self.assertEqual(
                    len(exp_json[page_key]["tokensJsons"]),
                    len(fix_json[page_key]["tokensJsons"]),
                    f"Token ref count mismatch on page {page_key} "
                    f"for '{exp_annot['rawText'][:40]}'",
                )

    def test_exported_label_names_match_fixture(self):
        """Verify that the set of label *names* in the export matches the
        set of label names actually used in the import fixture's
        annotations."""
        label_lookups = build_label_lookups(corpus_id=self.original_corpus_obj.id)

        # Gather label names referenced by fixture annotations
        fixture_doc_key = list(self.import_data["annotated_docs"].keys())[0]
        fixture_doc = self.import_data["annotated_docs"][fixture_doc_key]
        fixture_text_labels = self.import_data["text_labels"]

        used_text_label_ids = {
            a["annotationLabel"] for a in fixture_doc["labelled_text"]
        }
        expected_text_label_names = {
            fixture_text_labels[lid]["text"]
            for lid in used_text_label_ids
            if lid in fixture_text_labels
        }

        expected_doc_label_names = set(fixture_doc["doc_labels"])

        # Exported label names
        exported_text_label_names = {
            v["text"] for v in label_lookups["text_labels"].values()
        }
        exported_doc_label_names = {
            v["text"] for v in label_lookups["doc_labels"].values()
        }

        self.assertEqual(
            exported_text_label_names,
            expected_text_label_names,
            "Exported text label names do not match fixture",
        )

        # Doc-level: the label lookup should contain at least the doc labels
        # used by the document
        self.assertTrue(
            expected_doc_label_names.issubset(exported_doc_label_names),
            f"Missing doc labels: "
            f"{expected_doc_label_names - exported_doc_label_names}",
        )
