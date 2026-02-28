import io
import os
import tempfile
from unittest import mock

from django.conf import settings
from django.test import TestCase, override_settings

from opencontractserver.tests.fixtures import (
    SAMPLE_PDF,
    SAMPLE_PDF_NEEDS_OCR,
)
from opencontractserver.utils.files import (
    base_64_encode_bytes,
    check_if_pdf_needs_ocr,
    convert_hex_to_rgb_tuple,
    createHighlight,
    split_pdf_into_images,
)


class PDFUtilsTestCase(TestCase):
    def setUp(self) -> None:
        # Create sample PDF contents for testing
        self.sample_pdf_content = SAMPLE_PDF.read_bytes()
        self.need_ocr_pdf_content = SAMPLE_PDF_NEEDS_OCR.read_bytes()

    def test_check_if_pdf_needs_ocr_with_text(self):
        needs_ocr = check_if_pdf_needs_ocr(io.BytesIO(self.sample_pdf_content))
        self.assertFalse(needs_ocr)

    def test_check_if_pdf_needs_ocr_without_text(self):
        # Create a PDF without extractable text
        needs_ocr = check_if_pdf_needs_ocr(io.BytesIO(self.need_ocr_pdf_content))
        self.assertTrue(needs_ocr)

    def test_base_64_encode_bytes(self):
        test_bytes = b"Hello, World!"
        encoded = base_64_encode_bytes(test_bytes)
        self.assertEqual(encoded, "SGVsbG8sIFdvcmxkIQ==")

    def test_convert_hex_to_rgb_tuple(self):
        hex_color = "FF8000"
        rgb_tuple = convert_hex_to_rgb_tuple(hex_color)
        self.assertEqual(rgb_tuple, (255, 128, 0))

    def test_create_highlight(self):
        highlight = createHighlight(
            x1=10,
            y1=20,
            x2=30,
            y2=40,
            meta={"author": "Test Author", "contents": "Test Contents"},
            color=(1.0, 0.5, 0.0),
        )
        self.assertEqual(highlight["/Type"], "/Annot")
        self.assertEqual(highlight["/Subtype"], "/Highlight")
        self.assertEqual(highlight["/T"], "Test Author")
        self.assertEqual(highlight["/Contents"], "Test Contents")

    def test_split_pdf_into_images(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            # Call the function
            result = split_pdf_into_images(
                self.need_ocr_pdf_content, temp_dir, force_local=True
            )
            # Check the results
            self.assertEqual(len(result), 1)
            self.assertTrue(all(path.endswith(".png") for path in result))

            # Verify that files were actually created
            for path in result:
                self.assertTrue(os.path.exists(path))

    def test_split_pdf_into_images_s3(self) -> None:
        """
        Test split_pdf_into_images function when using AWS S3 storage.
        This test mocks the S3 client to avoid actual network calls.
        """
        with mock.patch("boto3.client") as mock_boto_client:
            mock_s3_client = mock.Mock()
            mock_boto_client.return_value = mock_s3_client

            # Mock settings.STORAGE_BACKEND to be AWS
            with mock.patch(
                "opencontractserver.utils.files.settings.STORAGE_BACKEND", "AWS"
            ):
                # Prepare the mock for s3.put_object
                mock_s3_client.put_object.return_value = {
                    "ResponseMetadata": {"HTTPStatusCode": 200}
                }

                # Call the function without force_local
                result = split_pdf_into_images(
                    self.need_ocr_pdf_content, "some/s3/path"
                )

                # Check the results
                self.assertEqual(len(result), 1)
                self.assertTrue(all(path.endswith(".png") for path in result))

                # Verify that put_object was called
                self.assertTrue(mock_s3_client.put_object.called)
                self.assertEqual(mock_s3_client.put_object.call_count, len(result))

                # Verify that the correct parameters were used in put_object
                for call_args in mock_s3_client.put_object.call_args_list:
                    args, kwargs = call_args
                    self.assertIn("Key", kwargs)
                    self.assertIn("Bucket", kwargs)
                    self.assertIn("Body", kwargs)
                    self.assertIn("ContentType", kwargs)
                    self.assertEqual(kwargs["Bucket"], settings.AWS_STORAGE_BUCKET_NAME)

    @override_settings(
        STORAGE_BACKEND="GCP",
        GS_BUCKET_NAME="test-gcs-bucket",
        GS_PROJECT_ID="test-gcs-project",
    )
    @mock.patch("google.cloud.storage.Client")
    def test_split_pdf_into_images_gcp(self, mock_gcs_client):
        """
        Ensure GCP branch initializes client, uploads via blob, and returns paths.
        """
        mock_client = mock.Mock()
        mock_bucket = mock.Mock()
        mock_blob = mock.Mock()

        mock_gcs_client.return_value = mock_client
        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        result = split_pdf_into_images(self.need_ocr_pdf_content, "some/gcs/path")

        self.assertEqual(len(result), 1)
        self.assertTrue(all(path.endswith(".png") for path in result))
        self.assertTrue(mock_bucket.blob.called)
        self.assertTrue(mock_blob.upload_from_string.called)

    def test_split_pdf_into_images_jpeg_format_local(self) -> None:
        """
        JPEG format is normalized and stored with .jpg extension when local.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            result = split_pdf_into_images(
                self.need_ocr_pdf_content,
                temp_dir,
                target_format="jpeg",
                force_local=True,
            )
            self.assertEqual(len(result), 1)
            self.assertTrue(all(path.endswith(".jpg") for path in result))
            for path in result:
                self.assertTrue(os.path.exists(path))

    def test_split_pdf_into_images_invalid_format_raises(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ValueError):
                split_pdf_into_images(
                    self.need_ocr_pdf_content,
                    temp_dir,
                    target_format="TIFF",
                    force_local=True,
                )
