"""Tests for annotation images REST API endpoint."""

import base64
import json
from io import BytesIO

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase
from PIL import Image
from rest_framework.test import APIClient

from opencontractserver.annotations.models import Annotation, AnnotationLabel, LabelSet
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()

pytestmark = pytest.mark.django_db


class AnnotationImagesAPITestCase(TestCase):
    """Test the /api/annotations/<id>/images/ REST endpoint."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data that will be used across test methods."""
        cls.user = User.objects.create_user(
            username="api_test_user", password="testpass123"
        )
        cls.other_user = User.objects.create_user(
            username="api_other_user", password="otherpass123"
        )

        # Create label set and label
        cls.label_set = LabelSet.objects.create(
            title="Test Label Set", creator=cls.user
        )
        cls.annotation_label = AnnotationLabel.objects.create(
            text="Figure", label_type="TOKEN_LABEL", color="#FF0000", creator=cls.user
        )
        cls.label_set.annotation_labels.add(cls.annotation_label)

        # Create corpus
        cls.corpus = Corpus.objects.create(
            title="Test Corpus", creator=cls.user, label_set=cls.label_set
        )
        set_permissions_for_obj_to_user(
            cls.user, cls.corpus, [PermissionTypes.READ, PermissionTypes.CRUD]
        )

    def _create_sample_image_base64(self, width: int = 100, height: int = 100) -> str:
        """Create a sample base64-encoded image for testing."""
        img = Image.new("RGB", (width, height), color="red")
        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def _create_pawls_with_images(
        self, num_pages: int = 1, images_per_page: int = 2
    ) -> list[dict]:
        """Create PAWLS data with embedded images using unified token format."""
        pages = []
        for page_idx in range(num_pages):
            page_tokens = [
                {"x": 100, "y": 100, "width": 50, "height": 12, "text": "Test"}
            ]

            for img_idx in range(images_per_page):
                base64_data = self._create_sample_image_base64(
                    width=100 + img_idx * 10, height=100 + img_idx * 10
                )
                page_tokens.append(
                    {
                        "x": 50 + img_idx * 100,
                        "y": 50 + img_idx * 100,
                        "width": 80,
                        "height": 60,
                        "text": "",
                        "is_image": True,
                        "format": "jpeg",
                        "original_width": 100 + img_idx * 10,
                        "original_height": 100 + img_idx * 10,
                        "content_hash": f"hash_{page_idx}_{img_idx}",
                        "image_type": "embedded",
                        "base64_data": base64_data,
                    }
                )

            pages.append(
                {
                    "page": {"width": 612, "height": 792, "index": page_idx},
                    "tokens": page_tokens,
                }
            )
        return pages

    # Sentinel for "use the test class's default corpus" without conflating
    # with the legitimate ``corpus=None`` test case (anonymous structural on
    # a corpusless public document).
    _DEFAULT_CORPUS = object()

    def _create_public_annotated_document(
        self,
        *,
        structural: bool = True,
        document_is_public: bool = True,
        corpus: object = _DEFAULT_CORPUS,
        corpus_is_public: bool = True,
        title: str = "Public Doc",
    ) -> Annotation:
        """Build a document + image-bearing annotation for anonymous-access tests.

        Returns the annotation; the test only needs the URL it produces. Pass
        ``corpus=None`` to test the corpusless branch; otherwise a fresh corpus
        is created with ``is_public=corpus_is_public``.
        """
        if corpus is self._DEFAULT_CORPUS:
            corpus_obj: Corpus | None = Corpus.objects.create(
                title=f"{title} corpus",
                creator=self.user,
                label_set=self.label_set,
                is_public=corpus_is_public,
            )
        else:
            corpus_obj = corpus  # type: ignore[assignment]

        pawls_data = self._create_pawls_with_images(num_pages=1, images_per_page=2)
        document = Document.objects.create(
            creator=self.user,
            title=title,
            description="Test fixture",
            pdf_file="test.pdf",
            is_public=document_is_public,
        )
        pawls_json = json.dumps(pawls_data).encode("utf-8")
        document.pawls_parse_file.save("test_pawls.json", ContentFile(pawls_json))

        return Annotation.objects.create(
            document=document,
            corpus=corpus_obj,
            creator=self.user,
            page=0,
            annotation_label=self.annotation_label,
            raw_text="",
            structural=structural,
            json={
                "0": {
                    "bounds": {"top": 50, "bottom": 110, "left": 50, "right": 230},
                    "tokensJsons": [
                        {"pageIndex": 0, "tokenIndex": 1},
                        {"pageIndex": 0, "tokenIndex": 2},
                    ],
                    "rawText": "",
                }
            },
            content_modalities=["IMAGE"],
        )

    def _create_test_document_with_images(
        self, owner: User
    ) -> tuple[Document, Annotation]:
        """Create a test document with images and an annotation referencing them."""
        pawls_data = self._create_pawls_with_images(num_pages=1, images_per_page=2)

        # Create document with PAWLS data
        document = Document.objects.create(
            creator=owner,
            title="Test Document with Images",
            description="Test document",
            pdf_file="test.pdf",
        )

        # Save PAWLS data to document
        pawls_json = json.dumps(pawls_data).encode("utf-8")
        document.pawls_parse_file.save("test_pawls.json", ContentFile(pawls_json))

        # Set permissions
        set_permissions_for_obj_to_user(
            owner, document, [PermissionTypes.READ, PermissionTypes.CRUD]
        )

        # Create annotation referencing image tokens (indices 1 and 2)
        annotation = Annotation.objects.create(
            document=document,
            corpus=self.corpus,
            creator=owner,
            page=0,
            annotation_label=self.annotation_label,
            raw_text="",
            json={
                "0": {
                    "bounds": {"top": 50, "bottom": 110, "left": 50, "right": 230},
                    "tokensJsons": [
                        {"pageIndex": 0, "tokenIndex": 1},  # First image
                        {"pageIndex": 0, "tokenIndex": 2},  # Second image
                    ],
                    "rawText": "",
                }
            },
            content_modalities=["IMAGE"],
        )

        return document, annotation

    def test_fetch_images_with_permission(self):
        """Test fetching images for annotation user has access to."""
        client = APIClient()
        client.force_authenticate(user=self.user)

        document, annotation = self._create_test_document_with_images(self.user)

        response = client.get(f"/api/annotations/{annotation.id}/images/")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("images", data)
        self.assertIn("count", data)
        self.assertEqual(data["annotation_id"], str(annotation.id))
        self.assertEqual(data["count"], 2)  # Should have 2 images
        self.assertGreater(len(data["images"]), 0)

        # Verify image data structure
        first_image = data["images"][0]
        self.assertIn("base64_data", first_image)
        self.assertIn("format", first_image)
        self.assertIn("data_url", first_image)
        self.assertIn("page_index", first_image)
        self.assertIn("token_index", first_image)
        self.assertEqual(first_image["format"], "jpeg")

    def test_fetch_images_without_permission(self):
        """Test IDOR protection - returns empty for unauthorized."""
        client = APIClient()
        client.force_authenticate(user=self.other_user)

        document, annotation = self._create_test_document_with_images(self.user)

        response = client.get(f"/api/annotations/{annotation.id}/images/")

        # Should return 200 with empty array (IDOR protection)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["images"]), 0)
        self.assertEqual(data["count"], 0)

    def test_fetch_images_unauthenticated_private(self):
        """
        Anonymous users hitting a non-public annotation get 200 with an empty
        array (IDOR protection) — same response shape as private/missing for
        authenticated users.
        """
        client = APIClient()
        document, annotation = self._create_test_document_with_images(self.user)

        response = client.get(f"/api/annotations/{annotation.id}/images/")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 0)
        self.assertEqual(len(data["images"]), 0)

    def test_fetch_images_anonymous_public_structural(self):
        """
        Anonymous users CAN fetch images for structural annotations on
        public documents in public corpora — mirrors what they can see via
        the GraphQL annotation queryset.
        """
        client = APIClient()  # no auth

        annotation = self._create_public_annotated_document(
            structural=True,
            document_is_public=True,
            corpus_is_public=True,
            title="Public Doc",
        )

        response = client.get(f"/api/annotations/{annotation.id}/images/")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 2)
        self.assertEqual(len(data["images"]), 2)
        self.assertEqual(data["images"][0]["format"], "jpeg")

    def test_fetch_images_anonymous_non_structural_blocked(self):
        """
        Anonymous users CANNOT fetch images for NON-structural annotations
        even on public document + corpus, because the annotation queryset
        only exposes structural annotations to anonymous users.
        """
        client = APIClient()  # no auth

        annotation = self._create_public_annotated_document(
            structural=False,
            document_is_public=True,
            corpus_is_public=True,
            title="Public Doc Non-Structural",
        )

        response = client.get(f"/api/annotations/{annotation.id}/images/")

        # Anonymous gate returns empty array (IDOR protection)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 0)
        self.assertEqual(len(data["images"]), 0)

    def test_fetch_images_anonymous_private_corpus_blocked(self):
        """
        Anonymous users CANNOT fetch images when the corpus is private,
        even for a structural annotation on a public document.
        """
        client = APIClient()  # no auth

        annotation = self._create_public_annotated_document(
            structural=True,
            document_is_public=True,
            corpus_is_public=False,
            title="Public Doc Private Corpus",
        )

        response = client.get(f"/api/annotations/{annotation.id}/images/")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 0)
        self.assertEqual(len(data["images"]), 0)

    def test_fetch_images_anonymous_private_document_blocked(self):
        """
        Anonymous users CANNOT fetch images when the document is NOT public,
        even for a structural annotation in an otherwise-public corpus.
        Pins the ``document.is_public`` half of the visibility rule.
        """
        client = APIClient()  # no auth

        annotation = self._create_public_annotated_document(
            structural=True,
            document_is_public=False,
            corpus_is_public=True,
            title="Private Doc Public Corpus",
        )

        response = client.get(f"/api/annotations/{annotation.id}/images/")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 0)
        self.assertEqual(len(data["images"]), 0)

    def test_fetch_images_anonymous_corpus_none_structural(self):
        """
        Anonymous users CAN fetch images for structural annotations on public
        documents even when ``corpus`` is NULL — the queryset's
        ``Q(corpus__isnull=True) | Q(corpus__is_public=True)`` branch
        explicitly admits this case (see AnnotationQuerySet.visible_to_user).
        """
        client = APIClient()  # no auth

        annotation = self._create_public_annotated_document(
            structural=True,
            document_is_public=True,
            corpus=None,  # exercise the Q(corpus__isnull=True) branch
            title="Public Doc Corpusless",
        )

        response = client.get(f"/api/annotations/{annotation.id}/images/")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 2)
        self.assertEqual(len(data["images"]), 2)

    def test_fetch_images_for_text_only_annotation(self):
        """Test fetching images for annotation with no images."""
        client = APIClient()
        client.force_authenticate(user=self.user)

        # Create document with images but annotation without image tokens
        pawls_data = self._create_pawls_with_images(num_pages=1, images_per_page=2)
        document = Document.objects.create(
            creator=self.user,
            title="Test Document",
            pdf_file="test.pdf",
        )
        pawls_json = json.dumps(pawls_data).encode("utf-8")
        document.pawls_parse_file.save("test_pawls.json", ContentFile(pawls_json))
        set_permissions_for_obj_to_user(self.user, document, [PermissionTypes.READ])

        # Create annotation referencing only text token (index 0)
        annotation = Annotation.objects.create(
            document=document,
            corpus=self.corpus,
            creator=self.user,
            page=0,
            annotation_label=self.annotation_label,
            raw_text="Test",
            json={
                "0": {
                    "bounds": {"top": 100, "bottom": 112, "left": 100, "right": 150},
                    "tokensJsons": [{"pageIndex": 0, "tokenIndex": 0}],  # Text token
                    "rawText": "Test",
                }
            },
            content_modalities=["TEXT"],
        )

        response = client.get(f"/api/annotations/{annotation.id}/images/")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["images"]), 0)
        self.assertEqual(data["count"], 0)

    def test_invalid_annotation_id(self):
        """Test with non-existent annotation ID."""
        client = APIClient()
        client.force_authenticate(user=self.user)

        response = client.get("/api/annotations/99999/images/")

        # Should return 200 with empty array (IDOR protection)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["images"]), 0)
        self.assertEqual(data["count"], 0)

    def test_fetch_images_for_structural_annotation(self):
        """Test fetching images for structural annotation without document."""
        from opencontractserver.annotations.models import StructuralAnnotationSet

        client = APIClient()
        client.force_authenticate(user=self.user)

        # Create PAWLS data with images
        pawls_data = self._create_pawls_with_images(num_pages=1, images_per_page=2)
        pawls_json = json.dumps(pawls_data).encode("utf-8")

        # Create StructuralAnnotationSet with PAWLS data
        structural_set = StructuralAnnotationSet.objects.create(
            content_hash="test_hash_structural",
            parser_name="test_parser",
            page_count=1,
        )
        structural_set.pawls_parse_file.save(
            "structural_pawls.json", ContentFile(pawls_json)
        )

        # Create document using this structural set
        document = Document.objects.create(
            creator=self.user,
            title="Test Structural Document",
            description="Test document",
            pdf_file="test_structural.pdf",
            structural_annotation_set=structural_set,
        )
        set_permissions_for_obj_to_user(
            self.user, document, [PermissionTypes.READ, PermissionTypes.CRUD]
        )

        # Create structural annotation (no document reference, references structural_set)
        annotation = Annotation.objects.create(
            document=None,  # Structural annotations don't have document
            corpus=None,
            structural_set=structural_set,
            structural=True,
            creator=self.user,
            page=0,
            annotation_label=self.annotation_label,
            raw_text="",
            json={
                "0": {
                    "bounds": {"top": 50, "bottom": 110, "left": 50, "right": 230},
                    "tokensJsons": [
                        {"pageIndex": 0, "tokenIndex": 1},  # First image
                        {"pageIndex": 0, "tokenIndex": 2},  # Second image
                    ],
                    "rawText": "",
                }
            },
            content_modalities=["IMAGE"],
        )

        response = client.get(f"/api/annotations/{annotation.id}/images/")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("images", data)
        self.assertEqual(data["count"], 2)  # Should have 2 images
        self.assertGreater(len(data["images"]), 0)

        # Verify image data structure
        first_image = data["images"][0]
        self.assertIn("base64_data", first_image)
        self.assertIn("format", first_image)
        self.assertEqual(first_image["format"], "jpeg")
