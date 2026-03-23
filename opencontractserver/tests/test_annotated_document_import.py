#  Copyright (C) 2022  John Scrudato / Gordium Knot Inc. d/b/a OpenSource.Legal
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as
#  published by the Free Software Foundation, either version 3 of the
#  License, or (at your option) any later version.

#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.

#  You should have received a copy of the GNU Affero General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.
import base64
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from pypdf import PdfReader

from opencontractserver.annotations.models import AnnotationLabel, LabelSet
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.tasks.import_tasks import import_document_to_corpus
from opencontractserver.tests.fixtures import SAMPLE_PDF_FILE_TWO_PATH
from opencontractserver.types.dicts import OpenContractsAnnotatedDocumentImportType
from opencontractserver.types.enums import LabelType
from opencontractserver.utils.compact_pawls import expand_pawls_pages

User = get_user_model()


class TestImportDocumentToCorpus(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpassword"
        )
        self.label_set = LabelSet.objects.create(
            title="Test Label Set",
            description="Test Label Set Description",
            creator=self.user,
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            description="Test Corpus Description",
            label_set=self.label_set,
            creator=self.user,
        )

    def test_import_document_to_corpus(self):
        # Read the test PDF file and convert it to base64
        with open(SAMPLE_PDF_FILE_TWO_PATH, "rb") as pdf_file:
            pdf_data = pdf_file.read()
            pdf_base64 = base64.b64encode(pdf_data).decode("utf-8")

        # Create test labels
        text_labels = {
            "test_text_label": {
                "id": "0",
                "color": "red",
                "description": "Test Text Label",
                "icon": "tags",
                "text": "test_text_label",
                "label_type": LabelType.TOKEN_LABEL.value,
            }
        }
        doc_labels = {
            "test_doc_label": {
                "id": "1",
                "color": "yellow",
                "description": "Test Doc Label",
                "icon": "tags",
                "text": "test_doc_label",
                "label_type": LabelType.DOC_TYPE_LABEL.value,
            }
        }

        # Create test annotations
        annotations = [
            {
                "id": None,
                "annotationLabel": "test_text_label",
                "rawText": "Test Text",
                "page": 1,
                "annotation_json": {
                    "1": {
                        "bounds": {"top": 0, "bottom": 1, "left": 0, "right": 1},
                        "tokensJsons": [{"pageIndex": 1, "tokenIndex": 0}],
                        "rawText": "Test Text",
                    }
                },
                "structural": False,
                "parent_id": None,
                "annotation_type": "TOKEN_LABEL",
            }
        ]

        # Create test data for import_document_to_corpus
        document_import_data: OpenContractsAnnotatedDocumentImportType = {
            "doc_data": {
                "title": "Test Document",
                "content": "Dummy",
                "description": "Dummy",
                "doc_labels": ["test_doc_label"],
                "labelled_text": annotations,
                "page_count": 1,
                "pawls_file_content": [
                    {
                        "page": {"width": 100, "height": 100, "index": 1},
                        "tokens": [
                            {"x": 0, "y": 0, "width": 10, "height": 10, "text": "Test"}
                        ],
                    }
                ],
            },
            "pdf_name": "test_document",
            "pdf_base64": pdf_base64,
            "text_labels": text_labels,
            "doc_labels": doc_labels,
        }

        # Call the import_document_to_corpus task
        document_id = import_document_to_corpus(
            self.corpus.id, self.user.id, document_import_data
        )

        # Check that the document was created
        document = Document.objects.get(id=document_id)
        self.assertEqual(document.title, "Test Document")

        # Check that the labels were created
        self.assertEqual(
            AnnotationLabel.objects.filter(text="test_text_label").count(), 1
        )
        self.assertEqual(
            AnnotationLabel.objects.filter(text="test_doc_label").count(), 1
        )

        # Check that the annotations were created
        annotations = document.doc_annotations.all()
        self.assertEqual(annotations.count(), 2)
        self.assertEqual(
            annotations.filter(annotation_label__text="test_text_label").count(), 1
        )
        self.assertEqual(
            annotations.filter(annotation_label__text="test_doc_label").count(), 1
        )

        # Check that the PDF file was imported correctly
        with document.pdf_file.open("rb") as pdf_file:
            pdf_reader = PdfReader(pdf_file)
            self.assertEqual(len(pdf_reader.pages), 9)

        # Check that the PAWLS file was imported correctly
        with document.pawls_parse_file.open("r") as pawls_file:
            raw_pawls = json.load(pawls_file)
            pawls_data = expand_pawls_pages(raw_pawls)
            self.assertEqual(len(pawls_data), 1)
            self.assertEqual(len(pawls_data[0]["tokens"]), 1)
            self.assertEqual(pawls_data[0]["tokens"][0]["text"], "Test")

    def test_import_with_bbox_annotations(self):
        """Integration test: bbox_annotations are resolved to TOKEN_LABEL
        annotations during the annotated document import pathway."""

        with open(SAMPLE_PDF_FILE_TWO_PATH, "rb") as pdf_file:
            pdf_base64 = base64.b64encode(pdf_file.read()).decode("utf-8")

        # Label that bbox_annotations will reference
        text_labels = {
            "bbox_label": {
                "id": "0",
                "color": "blue",
                "description": "Label from bbox",
                "icon": "tags",
                "text": "bbox_label",
                "label_type": LabelType.TOKEN_LABEL.value,
            }
        }

        # PAWLs tokens: three tokens on page 0
        pawls_pages = [
            {
                "page": {"width": 612.0, "height": 792.0, "index": 0},
                "tokens": [
                    {"x": 100, "y": 100, "width": 50, "height": 12, "text": "Hello"},
                    {"x": 160, "y": 100, "width": 60, "height": 12, "text": "World"},
                    {"x": 400, "y": 100, "width": 40, "height": 12, "text": "Outside"},
                ],
            }
        ]

        # bbox_annotations: a bounding box covering only the first two tokens
        bbox_annotations = [
            {
                "id": "bbox-1",
                "annotationLabel": "bbox_label",
                "rawText": "Hello World",
                "bounds": {"0": [{"top": 90, "bottom": 120, "left": 80, "right": 250}]},
            }
        ]

        document_import_data: OpenContractsAnnotatedDocumentImportType = {
            "doc_data": {
                "title": "BBox Import Test",
                "content": "Hello World Outside",
                "description": "Test bbox resolution during import",
                "doc_labels": [],
                "labelled_text": [],
                "bbox_annotations": bbox_annotations,
                "page_count": 1,
                "pawls_file_content": pawls_pages,
            },
            "pdf_name": "bbox_test_document",
            "pdf_base64": pdf_base64,
            "text_labels": text_labels,
            "doc_labels": {},
        }

        document_id = import_document_to_corpus(
            self.corpus.id, self.user.id, document_import_data
        )
        self.assertIsNotNone(document_id)

        document = Document.objects.get(id=document_id)
        self.assertEqual(document.title, "BBox Import Test")

        # The label should have been created
        self.assertTrue(AnnotationLabel.objects.filter(text="bbox_label").exists())

        # Exactly one annotation (the resolved bbox) should exist on the document
        annotations = document.doc_annotations.filter(
            annotation_label__text="bbox_label"
        )
        self.assertEqual(annotations.count(), 1)

        ann = annotations.first()
        self.assertEqual(ann.raw_text, "Hello World")
        self.assertEqual(ann.page, 0)
        self.assertEqual(ann.annotation_type, "TOKEN_LABEL")

        # The annotation JSON is stored in compact v2 format; expand to v1 to
        # verify the matched token references.
        from opencontractserver.annotations.compact_json import expand_annotation_json

        ann_json = expand_annotation_json(ann.json, ann.raw_text)
        self.assertIn("0", ann_json)
        tokens_refs = ann_json["0"]["tokensJsons"]
        self.assertEqual(len(tokens_refs), 2)
        self.assertEqual(tokens_refs[0], {"pageIndex": 0, "tokenIndex": 0})
        self.assertEqual(tokens_refs[1], {"pageIndex": 0, "tokenIndex": 1})
