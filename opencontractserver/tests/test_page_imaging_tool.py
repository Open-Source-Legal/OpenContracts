import base64
import pathlib

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase
from PIL import Image

from opencontractserver.documents.models import Document
from opencontractserver.llms.tools.core_tools import get_page_image
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()

pytestmark = pytest.mark.django_db


class PageImagingToolTestCase(TestCase):
    """Test that the page imaging tool correctly renders PDF pages as images"""

    fixtures_path = pathlib.Path(__file__).parent / "fixtures"

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )

    def create_pdf_document(self, pdf_filename="TestDocument.pdf"):
        """Helper to create a document with a real PDF file from fixtures"""
        doc = Document.objects.create(
            title="Test PDF Document",
            description="Test document for page imaging",
            creator=self.user,
            file_type="application/pdf",
            page_count=2,  # Assuming test PDF has 2 pages
        )

        # Load a real PDF from fixtures
        pdf_path = self.fixtures_path / pdf_filename
        if pdf_path.exists():
            with open(pdf_path, "rb") as pdf_file:
                doc.pdf_file.save(pdf_filename, ContentFile(pdf_file.read()))
        else:
            # Create a minimal valid PDF if fixture doesn't exist
            # This is a minimal PDF with 1 blank page
            minimal_pdf = (
                b"%PDF-1.4\n"
                b"1 0 obj <</Type/Catalog/Pages 2 0 R>>endobj\n"
                b"2 0 obj <</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
                b"3 0 obj <</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Resources<<>>>>endobj\n"
                b"xref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n"
                b"0000000058 00000 n\n0000000115 00000 n\ntrailer\n"
                b"<</Size 4/Root 1 0 R>>\nstartxref\n206\n%%EOF"
            )
            doc.pdf_file.save("minimal.pdf", ContentFile(minimal_pdf))
            doc.page_count = 1

        doc.save()
        set_permissions_for_obj_to_user(self.user, doc, [PermissionTypes.ALL])
        return doc

    def create_non_pdf_document(self):
        """Helper to create a non-PDF document"""
        doc = Document.objects.create(
            title="Test Text Document",
            description="Non-PDF document",
            creator=self.user,
            file_type="text/plain",
            page_count=1,
        )

        content = b"Test content"
        doc.pdf_file.save("test_doc.txt", ContentFile(content))

        doc.save()
        return doc

    def test_get_page_image_success(self):
        """Test successfully getting a page image from a PDF"""

        pdf_doc = self.create_pdf_document()

        # Get the first page as an image
        base64_image = get_page_image(
            document_id=pdf_doc.id,
            page_number=1,
            image_format="jpeg",
            dpi=72,  # Low DPI for faster tests
        )

        # Verify it's valid base64
        assert isinstance(base64_image, str)
        assert len(base64_image) > 0

        # Verify we can decode it back to an image
        image_bytes = base64.b64decode(base64_image)
        assert len(image_bytes) > 0

        # Verify it's a valid JPEG
        import io

        image = Image.open(io.BytesIO(image_bytes))
        assert image.format == "JPEG"

    def test_get_page_image_png_format(self):
        """Test getting a page image in PNG format"""

        pdf_doc = self.create_pdf_document()

        # Get the first page as PNG
        base64_image = get_page_image(
            document_id=pdf_doc.id, page_number=1, image_format="png", dpi=72
        )

        # Verify it's a valid PNG
        image_bytes = base64.b64decode(base64_image)
        import io

        image = Image.open(io.BytesIO(image_bytes))
        assert image.format == "PNG"

    def test_get_page_image_different_dpi(self):
        """Test that different DPI values work"""

        pdf_doc = self.create_pdf_document()

        # Test with low DPI
        low_dpi_image = get_page_image(document_id=pdf_doc.id, page_number=1, dpi=50)

        # Test with higher DPI
        high_dpi_image = get_page_image(document_id=pdf_doc.id, page_number=1, dpi=150)

        assert len(low_dpi_image) > 0
        assert len(high_dpi_image) > 0

    def test_get_page_image_invalid_document(self):
        """Test error handling for non-existent document"""

        with pytest.raises(ValueError, match="does not exist"):
            get_page_image(document_id=99999, page_number=1)

    def test_get_page_image_non_pdf_document(self):
        """Test error handling for non-PDF documents"""

        text_doc = self.create_non_pdf_document()

        with pytest.raises(ValueError, match="is not a PDF"):
            get_page_image(document_id=text_doc.id, page_number=1)

    def test_get_page_image_invalid_page_number(self):
        """Test error handling for invalid page numbers"""

        pdf_doc = self.create_pdf_document()

        # Test page number less than 1
        with pytest.raises(ValueError, match="Page numbers start at 1"):
            get_page_image(document_id=pdf_doc.id, page_number=0)

        # Test page number greater than page count
        with pytest.raises(ValueError, match="exceeds document page count"):
            get_page_image(document_id=pdf_doc.id, page_number=999)

    def test_get_page_image_invalid_format(self):
        """Test error handling for unsupported image formats"""

        pdf_doc = self.create_pdf_document()

        with pytest.raises(ValueError, match="Unsupported image format"):
            get_page_image(
                document_id=pdf_doc.id,
                page_number=1,
                image_format="bmp",  # Unsupported format
            )

    def test_get_page_image_no_pdf_file(self):
        """Test error handling for documents without PDF files"""

        doc = Document.objects.create(
            title="Document Without PDF",
            creator=self.user,
            file_type="application/pdf",
            page_count=1,
        )

        with pytest.raises(ValueError, match="has no PDF file attached"):
            get_page_image(document_id=doc.id, page_number=1)
