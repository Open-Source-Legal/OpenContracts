import pathlib

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase

from opencontractserver.annotations.models import Annotation, AnnotationLabel
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.etl import build_document_export, build_label_lookups
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()

pytestmark = pytest.mark.django_db


class NonPDFExportTestCase(TestCase):
    """Test that non-PDF documents can be exported without errors"""

    fixtures_path = pathlib.Path(__file__).parent / "fixtures"

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )

        # Create a corpus
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.user, backend_lock=False
        )
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.ALL])

        # Create annotation labels
        self.text_label = AnnotationLabel.objects.create(
            text="TestLabel",
            label_type="TOKEN_LABEL",
            color="#FF0000",
            description="Test label",
            creator=self.user,
        )

        self.doc_label = AnnotationLabel.objects.create(
            text="DocTypeLabel",
            label_type="DOC_TYPE_LABEL",
            color="#00FF00",
            description="Doc type label",
            creator=self.user,
        )

    def create_document(self, file_type="application/pdf", has_pdf_file=True):
        """Helper to create a document with specified file type"""
        doc = Document.objects.create(
            title="Test Document",
            description="Test description",
            creator=self.user,
            file_type=file_type,
            page_count=1,
        )

        if has_pdf_file:
            # Create a simple file (not a real PDF for non-PDF types)
            content = b"Test content"
            doc.pdf_file.save(f"test_doc_{doc.id}.txt", ContentFile(content))

        # Create a simple text extract file
        doc.txt_extract_file.save(
            f"test_extract_{doc.id}.txt", ContentFile(b"Extracted text content")
        )

        # Create a simple pawls file with minimal structure
        pawls_content = (
            b'[{"page": {"index": 1, "width": 612, "height": 792}, "tokens": []}]'
        )
        doc.pawls_parse_file.save(
            f"test_pawls_{doc.id}.json", ContentFile(pawls_content)
        )

        doc.save()
        return doc

    def add_annotation_to_doc(self, doc, label, annotation_json=None):
        """Helper to add an annotation to a document"""
        if annotation_json is None:
            annotation_json = {
                "1": {"bounds": {"left": 10, "top": 20, "right": 100, "bottom": 40}}
            }

        return Annotation.objects.create(
            document=doc,
            corpus=self.corpus,
            annotation_label=label,
            raw_text="Test annotation text",
            page=1,
            json=annotation_json,
            creator=self.user,
        )

    def test_pdf_export_still_works(self):
        """Test that PDF export still works as before (backward compatibility)"""
        print("\n# TEST PDF EXPORT BACKWARD COMPATIBILITY ##")

        # Create a PDF document
        pdf_doc = self.create_document(file_type="application/pdf")
        self.corpus.add_document(document=pdf_doc, user=self.user)

        # Add annotation
        self.add_annotation_to_doc(pdf_doc, self.text_label)

        # Build label lookups
        label_lookups = build_label_lookups(corpus_id=self.corpus.id)

        # Export the document
        doc_name, base64_pdf, doc_json, text_labels, doc_labels = build_document_export(
            label_lookups=label_lookups, doc_id=pdf_doc.id, corpus_id=self.corpus.id
        )

        print(f"PDF export - doc_name: {doc_name}")
        print(f"PDF export - has base64_pdf: {bool(base64_pdf)}")
        print(f"PDF export - has doc_json: {bool(doc_json)}")

        # For PDFs, we should get the PDF bytes (though they might fail if not a real PDF)
        # The important thing is that it doesn't crash
        assert doc_name is not None
        assert doc_json is not None
        assert doc_json["title"] == "Test Document"
        print("\t\tSUCCESS - PDF export works")

    def test_non_pdf_text_export(self):
        """Test that non-PDF text documents can be exported"""
        print("\n# TEST NON-PDF TEXT DOCUMENT EXPORT ##")

        # Create a text document
        text_doc = self.create_document(file_type="text/plain")
        self.corpus.add_document(document=text_doc, user=self.user)

        # Add annotations
        self.add_annotation_to_doc(text_doc, self.text_label)
        Annotation.objects.create(
            document=text_doc,
            corpus=self.corpus,
            annotation_label=self.doc_label,
            raw_text="",
            creator=self.user,
        )

        # Build label lookups
        label_lookups = build_label_lookups(corpus_id=self.corpus.id)

        # Export the document
        doc_name, base64_pdf, doc_json, text_labels, doc_labels = build_document_export(
            label_lookups=label_lookups, doc_id=text_doc.id, corpus_id=self.corpus.id
        )

        print(f"Text export - doc_name: {doc_name}")
        print(f"Text export - base64_pdf: '{base64_pdf}' (should be empty)")
        print(f"Text export - has doc_json: {bool(doc_json)}")

        # For non-PDFs, we should get empty PDF bytes but valid JSON
        assert doc_name is not None
        assert base64_pdf == "", "Non-PDF should have empty base64_pdf string"
        assert doc_json is not None
        assert doc_json["title"] == "Test Document"
        assert doc_json["content"] == "Extracted text content"
        assert len(doc_json["labelled_text"]) == 1
        assert len(doc_json["doc_labels"]) == 1
        print("\t\tSUCCESS - Non-PDF text export works correctly")

    def test_non_pdf_docx_export(self):
        """Test that DOCX documents can be exported"""
        print("\n# TEST DOCX DOCUMENT EXPORT ##")

        # Create a DOCX document
        docx_doc = self.create_document(
            file_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        self.corpus.add_document(document=docx_doc, user=self.user)

        # Add annotation
        self.add_annotation_to_doc(docx_doc, self.text_label)

        # Build label lookups
        label_lookups = build_label_lookups(corpus_id=self.corpus.id)

        # Export the document
        doc_name, base64_pdf, doc_json, text_labels, doc_labels = build_document_export(
            label_lookups=label_lookups, doc_id=docx_doc.id, corpus_id=self.corpus.id
        )

        print(f"DOCX export - doc_name: {doc_name}")
        print(f"DOCX export - base64_pdf: '{base64_pdf}' (should be empty)")
        print(f"DOCX export - has doc_json: {bool(doc_json)}")

        # For non-PDFs, we should get empty PDF bytes but valid JSON
        assert doc_name is not None
        assert base64_pdf == "", "Non-PDF should have empty base64_pdf string"
        assert doc_json is not None
        assert doc_json["title"] == "Test Document"
        assert len(doc_json["labelled_text"]) == 1
        print("\t\tSUCCESS - DOCX export works correctly")

    def test_non_pdf_without_pdf_file(self):
        """Test that documents without pdf_file can be exported"""
        print("\n# TEST DOCUMENT WITHOUT PDF FILE ##")

        # Create a document without a pdf_file
        doc = self.create_document(file_type="text/plain", has_pdf_file=False)
        self.corpus.add_document(document=doc, user=self.user)

        # Add annotation
        self.add_annotation_to_doc(doc, self.text_label)

        # Build label lookups
        label_lookups = build_label_lookups(corpus_id=self.corpus.id)

        # Export the document
        doc_name, base64_pdf, doc_json, text_labels, doc_labels = build_document_export(
            label_lookups=label_lookups, doc_id=doc.id, corpus_id=self.corpus.id
        )

        print(f"No PDF file export - doc_name: {doc_name}")
        print(f"No PDF file export - base64_pdf: '{base64_pdf}' (should be empty)")
        print(f"No PDF file export - has doc_json: {bool(doc_json)}")

        # Should still work with empty PDF bytes
        assert doc_name == "document"
        assert base64_pdf == ""
        assert doc_json is not None
        assert len(doc_json["labelled_text"]) == 1
        print("\t\tSUCCESS - Export without PDF file works correctly")
