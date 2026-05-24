"""Tests for annotation images REST API endpoint."""

import base64
import json
from io import BytesIO

import pytest
from django.core.files.base import ContentFile
from django.test import TestCase
from PIL import Image
from rest_framework.test import APIClient

from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
    LabelSet,
    StructuralAnnotationSet,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.users.models import User
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

pytestmark = pytest.mark.django_db


class AnnotationImagesAPITestCase(TestCase):
    """Test the /api/annotations/<id>/images/ REST endpoint."""

    user: User
    other_user: User
    label_set: LabelSet
    annotation_label: AnnotationLabel
    corpus: Corpus

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

    def _create_structural_set_annotation(
        self,
        *,
        document_is_public: bool,
        corpus: object = _DEFAULT_CORPUS,
        corpus_is_public: bool = True,
        unique_tag: str = "structural_set",
    ) -> Annotation:
        """Build a structural_set-linked annotation (``document=None``).

        Mirrors the production shape where the annotation row itself has
        no document FK, but a Document linked to the same structural_set
        drives anonymous visibility via
        ``AnnotationQuerySet.visible_to_user``.
        """
        if corpus is self._DEFAULT_CORPUS:
            corpus_obj: Corpus | None = Corpus.objects.create(
                title=f"{unique_tag} corpus",
                creator=self.user,
                label_set=self.label_set,
                is_public=corpus_is_public,
            )
        else:
            corpus_obj = corpus  # type: ignore[assignment]

        pawls_data = self._create_pawls_with_images(num_pages=1, images_per_page=2)
        pawls_json = json.dumps(pawls_data).encode("utf-8")

        structural_set = StructuralAnnotationSet.objects.create(
            content_hash=f"hash_{unique_tag}",
            parser_name="test_parser",
            page_count=1,
        )
        structural_set.pawls_parse_file.save(
            "structural_pawls.json", ContentFile(pawls_json)
        )
        Document.objects.create(
            creator=self.user,
            title=f"{unique_tag} doc",
            description="Drives anon visibility for the set",
            pdf_file="test.pdf",
            structural_annotation_set=structural_set,
            is_public=document_is_public,
        )
        return Annotation.objects.create(
            document=None,
            corpus=corpus_obj,
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
                        {"pageIndex": 0, "tokenIndex": 1},
                        {"pageIndex": 0, "tokenIndex": 2},
                    ],
                    "rawText": "",
                }
            },
            content_modalities=["IMAGE"],
        )

    def test_anonymous_doc_attached_visibility_matrix(self):
        """Anonymous image visibility ≡ ``AnnotationQuerySet.visible_to_user``.

        For a document-attached annotation, the queryset admits anonymous
        callers iff ``structural=True AND document.is_public=True AND
        (corpus is null OR corpus.is_public=True)``. The image endpoint
        delegates to that queryset, so the matrix below pins both
        boundaries plus the corpusless branch in one place.
        """
        # (label, structural, doc_public, corpus_kind, corpus_public, expected_count)
        # corpus_kind: "fresh" → new corpus per case, "null" → corpus=None
        cases = [
            ("structural+public-doc+public-corpus", True, True, "fresh", True, 2),
            ("structural+public-doc+null-corpus", True, True, "null", True, 2),
            ("non-structural+public-doc+public-corpus", False, True, "fresh", True, 0),
            ("structural+public-doc+private-corpus", True, True, "fresh", False, 0),
            ("structural+private-doc+public-corpus", True, False, "fresh", True, 0),
        ]
        client = APIClient()  # no auth

        for (
            label,
            structural,
            doc_public,
            corpus_kind,
            corpus_public,
            expected,
        ) in cases:
            with self.subTest(case=label):
                annotation = self._create_public_annotated_document(
                    structural=structural,
                    document_is_public=doc_public,
                    corpus=None if corpus_kind == "null" else self._DEFAULT_CORPUS,
                    corpus_is_public=corpus_public,
                    title=label,
                )
                response = client.get(f"/api/annotations/{annotation.id}/images/")
                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertEqual(data["count"], expected, label)
                self.assertEqual(len(data["images"]), expected, label)

    def test_anonymous_structural_set_visibility_matrix(self):
        """Pins the ``structural_set``-linked branch of the queryset.

        Anonymous callers get images iff at least one Document using the
        set is public AND the corpus rule allows them. Without the
        public-document linkage there is no anonymous read path.
        """
        # (label, document_is_public, corpus_kind, corpus_public, expected_count)
        cases = [
            ("public-doc+null-corpus", True, "null", True, 2),
            ("public-doc+public-corpus", True, "fresh", True, 2),
            ("public-doc+private-corpus", True, "fresh", False, 0),
            ("private-doc+null-corpus", False, "null", True, 0),
        ]
        client = APIClient()  # no auth

        for i, (label, doc_public, corpus_kind, corpus_public, expected) in enumerate(
            cases
        ):
            with self.subTest(case=label):
                annotation = self._create_structural_set_annotation(
                    document_is_public=doc_public,
                    corpus=None if corpus_kind == "null" else self._DEFAULT_CORPUS,
                    corpus_is_public=corpus_public,
                    unique_tag=f"sset_anon_{i}_{label}",
                )
                response = client.get(f"/api/annotations/{annotation.id}/images/")
                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertEqual(data["count"], expected, label)
                self.assertEqual(len(data["images"]), expected, label)

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
        """Authenticated owners can fetch images for structural_set-linked annotations.

        ``visible_to_user`` admits these via the ``structural_set__documents__creator``
        branch, so the helper's owner-as-creator setup is sufficient.
        """
        client = APIClient()
        client.force_authenticate(user=self.user)

        annotation = self._create_structural_set_annotation(
            document_is_public=False,
            corpus=None,
            unique_tag="auth_structural_owner",
        )

        response = client.get(f"/api/annotations/{annotation.id}/images/")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 2)
        self.assertEqual(data["images"][0]["format"], "jpeg")
