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
            pawls_data = json.load(pawls_file)
            self.assertEqual(len(pawls_data), 1)
            self.assertEqual(len(pawls_data[0]["tokens"]), 1)
            self.assertEqual(pawls_data[0]["tokens"][0]["text"], "Test")
