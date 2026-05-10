"""Tests for the image tools module."""

import base64
import json
import pathlib

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, TransactionTestCase

from opencontractserver.annotations.models import Annotation, AnnotationLabel, LabelSet
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.llms.tools.image_tools import (
    ImageData,
    ImageReference,
    get_annotation_images,
    get_annotation_images_with_permission,
    get_document_image,
    get_document_image_with_permission,
    list_document_images,
    list_document_images_with_permission,
)
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()

pytestmark = pytest.mark.django_db


class ImageToolsTestCase(TestCase):
    """Tests for image retrieval tools."""

    fixtures_path = pathlib.Path(__file__).parent / "fixtures"

    @classmethod
    def setUpTestData(cls):
        """Set up test data that will be used across test methods."""
        cls.user = User.objects.create_user(
            username="imagetools_test_user", password="testpass123"
        )
        cls.other_user = User.objects.create_user(
            username="imagetools_other_user", password="otherpass123"
        )

    def _create_sample_image_base64(self, width: int = 100, height: int = 100) -> str:
        """Create a sample base64-encoded image for testing."""
        from io import BytesIO

        from PIL import Image

        img = Image.new("RGB", (width, height), color="red")
        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def _create_pawls_with_images(
        self, num_pages: int = 2, images_per_page: int = 2
    ) -> list[dict]:
        """Create PAWLS data with embedded images using unified token format.

        Images are added to the tokens[] array with is_image=True.
        """
        pages = []
        for page_idx in range(num_pages):
            # Start with a text token
            page_tokens = [
                {"x": 100, "y": 100, "width": 50, "height": 12, "text": "Test"}
            ]

            # Add image tokens after text tokens
            for img_idx in range(images_per_page):
                # Create a unique sample image for each position
                base64_data = self._create_sample_image_base64(
                    width=100 + img_idx * 10, height=100 + img_idx * 10
                )
                page_tokens.append(
                    {
                        "x": 50 + img_idx * 100,
                        "y": 50 + img_idx * 100,
                        "width": 80,
                        "height": 60,
                        "text": "",  # Required for unified token format
                        "is_image": True,  # Identifies this as an image token
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
                    "page": {
                        "width": 612,
                        "height": 792,
                        "index": page_idx,
                    },
                    "tokens": page_tokens,
                }
            )
        return pages

    def _create_document_with_images(
        self, num_pages: int = 2, images_per_page: int = 2
    ):
        """Create a document with PAWLs data containing images."""
        doc = Document.objects.create(
            title="Document with Images",
            description="Test document containing images",
            creator=self.user,
            file_type="application/pdf",
            page_count=num_pages,
        )

        pawls_data = self._create_pawls_with_images(num_pages, images_per_page)
        pawls_json = json.dumps(pawls_data)
        doc.pawls_parse_file.save("pawls_with_images.json", ContentFile(pawls_json))
        doc.save()

        set_permissions_for_obj_to_user(self.user, doc, [PermissionTypes.ALL])

        return doc

    def _create_document_without_images(self):
        """Create a document with PAWLs data but no images."""
        doc = Document.objects.create(
            title="Document without Images",
            description="Test document without images",
            creator=self.user,
            file_type="application/pdf",
            page_count=1,
        )

        pawls_data = [
            {
                "page": {"width": 612, "height": 792, "index": 0},
                "tokens": [
                    {"x": 100, "y": 100, "width": 50, "height": 12, "text": "Test"}
                ],
            }
        ]
        pawls_json = json.dumps(pawls_data)
        doc.pawls_parse_file.save("pawls_no_images.json", ContentFile(pawls_json))
        doc.save()

        set_permissions_for_obj_to_user(self.user, doc, [PermissionTypes.ALL])

        return doc

    # =========================================================================
    # Tests for list_document_images
    # =========================================================================

    def test_list_document_images_returns_all_images(self):
        """Test that list_document_images returns all images in a document."""
        doc = self._create_document_with_images(num_pages=2, images_per_page=3)

        images = list_document_images(doc.id)

        assert len(images) == 6  # 2 pages * 3 images per page
        assert all(isinstance(img, ImageReference) for img in images)

    def test_list_document_images_filter_by_page(self):
        """Test filtering images by page index."""
        doc = self._create_document_with_images(num_pages=3, images_per_page=2)

        # Get images for page 1 only (0-based)
        images = list_document_images(doc.id, page_index=1)

        assert len(images) == 2
        assert all(img.page_index == 1 for img in images)

    def test_list_document_images_empty_for_nonexistent_page(self):
        """Test that filtering by non-existent page returns empty list."""
        doc = self._create_document_with_images(num_pages=2, images_per_page=2)

        images = list_document_images(doc.id, page_index=99)

        assert images == []

    def test_list_document_images_returns_metadata(self):
        """Test that image references contain correct metadata."""
        doc = self._create_document_with_images(num_pages=1, images_per_page=1)

        images = list_document_images(doc.id)

        assert len(images) == 1
        img = images[0]
        assert img.page_index == 0
        # Token index 1 because index 0 is the text token "Test"
        assert img.token_index == 1
        assert img.width == 80
        assert img.height == 60
        assert img.format == "jpeg"
        assert img.image_type == "embedded"
        assert img.content_hash == "hash_0_0"

    def test_list_document_images_nonexistent_document(self):
        """Test that listing images for non-existent document returns empty list."""
        images = list_document_images(99999)

        assert images == []

    def test_list_document_images_no_pawls_data(self):
        """Test that listing images when document has no PAWLs data returns empty list."""
        doc = Document.objects.create(
            title="No PAWLs",
            creator=self.user,
            file_type="application/pdf",
        )

        images = list_document_images(doc.id)

        assert images == []

    def test_list_document_images_document_without_images(self):
        """Test listing images for document with PAWLs but no images."""
        doc = self._create_document_without_images()

        images = list_document_images(doc.id)

        assert images == []

    # =========================================================================
    # Tests for get_document_image
    # =========================================================================

    def test_get_document_image_returns_image_data(self):
        """Test that get_document_image returns valid ImageData."""
        doc = self._create_document_with_images(num_pages=1, images_per_page=1)

        # Token index 1 because index 0 is the text token "Test"
        result = get_document_image(doc.id, page_index=0, token_index=1)

        assert result is not None
        assert isinstance(result, ImageData)
        assert result.page_index == 0
        assert result.token_index == 1
        assert result.format == "jpeg"
        assert len(result.base64_data) > 0
        assert result.data_url.startswith("data:image/jpeg;base64,")

    def test_get_document_image_valid_base64(self):
        """Test that returned base64 data is valid and can be decoded."""
        doc = self._create_document_with_images(num_pages=1, images_per_page=1)

        # Token index 1 because index 0 is the text token "Test"
        result = get_document_image(doc.id, page_index=0, token_index=1)

        # Verify base64 decodes without error
        decoded = base64.b64decode(result.base64_data)
        assert len(decoded) > 0

        # Verify it's a valid JPEG
        from io import BytesIO

        from PIL import Image

        img = Image.open(BytesIO(decoded))
        assert img.format == "JPEG"

    def test_get_document_image_invalid_page_index(self):
        """Test that invalid page index returns None."""
        doc = self._create_document_with_images(num_pages=2, images_per_page=1)

        result = get_document_image(doc.id, page_index=99, token_index=0)

        assert result is None

    def test_get_document_image_invalid_token_index(self):
        """Test that invalid image index returns None."""
        doc = self._create_document_with_images(num_pages=1, images_per_page=2)

        result = get_document_image(doc.id, page_index=0, token_index=99)

        assert result is None

    def test_get_document_image_negative_indices(self):
        """Test that negative indices return None."""
        doc = self._create_document_with_images(num_pages=1, images_per_page=1)

        assert get_document_image(doc.id, page_index=-1, token_index=0) is None
        assert get_document_image(doc.id, page_index=0, token_index=-1) is None

    def test_get_document_image_nonexistent_document(self):
        """Test that non-existent document returns None."""
        result = get_document_image(99999, page_index=0, token_index=0)

        assert result is None

    # =========================================================================
    # Tests for get_annotation_images
    # =========================================================================

    def test_get_annotation_images_returns_referenced_images(self):
        """Test that get_annotation_images returns images referenced by annotation."""
        doc = self._create_document_with_images(num_pages=1, images_per_page=2)

        # Create a corpus, label set, and label for the annotation
        corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)
        label_set = LabelSet.objects.create(
            title="Test Label Set",
            creator=self.user,
        )
        corpus.label_set = label_set
        corpus.save()

        label = AnnotationLabel.objects.create(
            text="Figure",
            label_type="TOKEN_LABEL",
            creator=self.user,
        )
        label_set.annotation_labels.add(label)

        # Create annotation with tokensJsons reference
        # Token index 1 and 2 are image tokens (index 0 is the text token "Test")
        annotation = Annotation.objects.create(
            document=doc,
            corpus=corpus,
            annotation_label=label,
            raw_text="Figure 1",
            page=0,
            creator=self.user,
            json={
                "0": {
                    "bounds": {"left": 50, "top": 50, "right": 230, "bottom": 210},
                    "tokensJsons": [
                        {"pageIndex": 0, "tokenIndex": 1},
                        {"pageIndex": 0, "tokenIndex": 2},
                    ],
                }
            },
        )

        images = get_annotation_images(annotation.id)

        assert len(images) == 2
        assert all(isinstance(img, ImageData) for img in images)

    def test_get_annotation_images_no_references(self):
        """Test that annotation without image references returns empty list."""
        doc = self._create_document_with_images(num_pages=1, images_per_page=1)

        corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)
        label_set = LabelSet.objects.create(title="Test Label Set", creator=self.user)
        corpus.label_set = label_set
        corpus.save()

        label = AnnotationLabel.objects.create(
            text="Text",
            label_type="TOKEN_LABEL",
            creator=self.user,
        )
        label_set.annotation_labels.add(label)

        annotation = Annotation.objects.create(
            document=doc,
            corpus=corpus,
            annotation_label=label,
            raw_text="Some text",
            page=0,
            creator=self.user,
            json={
                "0": {"bounds": {"left": 50, "top": 50, "right": 130, "bottom": 110}}
            },
        )

        images = get_annotation_images(annotation.id)

        assert images == []

    def test_get_annotation_images_nonexistent_annotation(self):
        """Test that non-existent annotation returns empty list."""
        images = get_annotation_images(99999)

        assert images == []

    # =========================================================================
    # Tests for permission-checked versions
    # =========================================================================

    def test_list_document_images_with_permission_allowed(self):
        """Test permission-checked listing with permitted user."""
        doc = self._create_document_with_images(num_pages=1, images_per_page=2)

        images = list_document_images_with_permission(self.user, doc.id)

        assert len(images) == 2

    def test_list_document_images_with_permission_denied(self):
        """Test permission-checked listing with non-permitted user."""
        doc = self._create_document_with_images(num_pages=1, images_per_page=2)
        # other_user has no permissions on this document

        images = list_document_images_with_permission(self.other_user, doc.id)

        assert images == []

    def test_get_document_image_with_permission_allowed(self):
        """Test permission-checked image retrieval with permitted user."""
        doc = self._create_document_with_images(num_pages=1, images_per_page=1)

        # Token index 1 is the first image token (index 0 is the text token "Test")
        result = get_document_image_with_permission(
            self.user, doc.id, page_index=0, token_index=1
        )

        assert result is not None
        assert isinstance(result, ImageData)

    def test_get_document_image_with_permission_denied(self):
        """Test permission-checked image retrieval with non-permitted user."""
        doc = self._create_document_with_images(num_pages=1, images_per_page=1)

        # Token index 1 is the first image token (index 0 is the text token "Test")
        result = get_document_image_with_permission(
            self.other_user, doc.id, page_index=0, token_index=1
        )

        assert result is None

    def test_get_document_image_with_permission_nonexistent_idor_protection(self):
        """Test that non-existent document returns None (same as unauthorized)."""
        # This tests IDOR protection - non-existent and unauthorized should
        # return the same response to prevent enumeration
        result = get_document_image_with_permission(
            self.user, 99999, page_index=0, token_index=0
        )

        assert result is None

    def test_get_annotation_images_with_permission_allowed(self):
        """Test permission-checked annotation images with permitted user."""
        doc = self._create_document_with_images(num_pages=1, images_per_page=1)

        corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)
        label_set = LabelSet.objects.create(title="Test Label Set", creator=self.user)
        corpus.label_set = label_set
        corpus.save()

        # Permission on BOTH document and corpus required (MIN rule)
        set_permissions_for_obj_to_user(self.user, corpus, [PermissionTypes.ALL])

        label = AnnotationLabel.objects.create(
            text="Figure",
            label_type="TOKEN_LABEL",
            creator=self.user,
        )
        label_set.annotation_labels.add(label)

        # Token index 1 is the first image token (index 0 is the text token "Test")
        annotation = Annotation.objects.create(
            document=doc,
            corpus=corpus,
            annotation_label=label,
            raw_text="Figure",
            page=0,
            creator=self.user,
            json={
                "0": {
                    "bounds": {"left": 50, "top": 50, "right": 130, "bottom": 110},
                    "tokensJsons": [{"pageIndex": 0, "tokenIndex": 1}],
                }
            },
        )

        images = get_annotation_images_with_permission(self.user, annotation.id)

        assert len(images) == 1

    def test_get_annotation_images_with_permission_denied(self):
        """Test permission-checked annotation images with non-permitted user."""
        doc = self._create_document_with_images(num_pages=1, images_per_page=1)

        corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)
        label_set = LabelSet.objects.create(title="Test Label Set", creator=self.user)
        corpus.label_set = label_set
        corpus.save()

        label = AnnotationLabel.objects.create(
            text="Figure",
            label_type="TOKEN_LABEL",
            creator=self.user,
        )
        label_set.annotation_labels.add(label)

        # Token index 1 is the first image token (index 0 is the text token "Test")
        annotation = Annotation.objects.create(
            document=doc,
            corpus=corpus,
            annotation_label=label,
            raw_text="Figure",
            page=0,
            creator=self.user,
            json={
                "0": {
                    "bounds": {"left": 50, "top": 50, "right": 130, "bottom": 110},
                    "tokensJsons": [{"pageIndex": 0, "tokenIndex": 1}],
                }
            },
        )

        # other_user has no permission on the document
        images = get_annotation_images_with_permission(self.other_user, annotation.id)

        assert images == []


class ImageToolsStoragePathTestCase(TestCase):
    """Test image tools with storage path-based images (not base64)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="storage_test_user", password="testpass123"
        )

    def test_get_document_image_with_storage_path(self):
        """Test that images stored via path can be retrieved."""
        from io import BytesIO

        from django.core.files.base import ContentFile
        from django.core.files.storage import default_storage
        from PIL import Image

        # Create and save an image to storage
        img = Image.new("RGB", (100, 100), color="blue")
        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        image_bytes = buffer.getvalue()

        storage_path = "test_images/page_0_img_0.jpg"
        default_storage.save(storage_path, ContentFile(image_bytes))

        # Create document with PAWLs data referencing storage path
        doc = Document.objects.create(
            title="Storage Path Test",
            creator=self.user,
            file_type="application/pdf",
            page_count=1,
        )

        # Use unified token format - images are tokens with is_image=True
        pawls_data = [
            {
                "page": {"width": 612, "height": 792, "index": 0},
                "tokens": [
                    {
                        "x": 50,
                        "y": 50,
                        "width": 100,
                        "height": 100,
                        "text": "",  # Required for unified token format
                        "is_image": True,  # Identifies this as an image token
                        "format": "jpeg",
                        "original_width": 100,
                        "original_height": 100,
                        "image_path": storage_path,
                        "image_type": "embedded",
                    }
                ],
            }
        ]
        pawls_json = json.dumps(pawls_data)
        doc.pawls_parse_file.save("pawls_storage.json", ContentFile(pawls_json))
        doc.save()

        set_permissions_for_obj_to_user(self.user, doc, [PermissionTypes.ALL])

        # Test retrieval
        result = get_document_image(doc.id, page_index=0, token_index=0)

        assert result is not None
        assert isinstance(result, ImageData)
        assert len(result.base64_data) > 0

        # Verify decoded image matches
        decoded = base64.b64decode(result.base64_data)
        retrieved_img = Image.open(BytesIO(decoded))
        assert retrieved_img.size == (100, 100)

        # Cleanup
        default_storage.delete(storage_path)


class AsyncImageToolsTestCase(TransactionTestCase):
    """Tests for async versions of image tools.

    Uses TransactionTestCase because async functions access the database from
    different connections and need to see committed data.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="async_imagetools_test_user", password="testpass123"
        )
        self.other_user = User.objects.create_user(
            username="async_imagetools_other_user", password="otherpass123"
        )

    def _create_sample_image_base64(self, width: int = 100, height: int = 100) -> str:
        """Create a sample base64-encoded image for testing."""
        from io import BytesIO

        from PIL import Image

        img = Image.new("RGB", (width, height), color="green")
        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def _create_document_with_images_sync(
        self, num_pages: int = 1, images_per_page: int = 1
    ):
        """Create a document with PAWLs data containing images (sync version)."""
        doc = Document.objects.create(
            title="Async Test Document",
            description="Test document for async tests",
            creator=self.user,
            file_type="application/pdf",
            page_count=num_pages,
        )

        pages = []
        for page_idx in range(num_pages):
            page_tokens = [
                {"x": 100, "y": 100, "width": 50, "height": 12, "text": "Test"}
            ]

            for img_idx in range(images_per_page):
                base64_data = self._create_sample_image_base64()
                page_tokens.append(
                    {
                        "x": 50 + img_idx * 100,
                        "y": 50 + img_idx * 100,
                        "width": 80,
                        "height": 60,
                        "text": "",
                        "is_image": True,
                        "format": "jpeg",
                        "original_width": 100,
                        "original_height": 100,
                        "content_hash": f"async_hash_{page_idx}_{img_idx}",
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

        pawls_json = json.dumps(pages)
        doc.pawls_parse_file.save("async_pawls.json", ContentFile(pawls_json))
        doc.save()

        set_permissions_for_obj_to_user(self.user, doc, [PermissionTypes.ALL])
        return doc

    async def _create_document_with_images(
        self, num_pages: int = 1, images_per_page: int = 1
    ):
        """Create a document with PAWLs data containing images (async wrapper)."""
        from asgiref.sync import sync_to_async

        return await sync_to_async(self._create_document_with_images_sync)(
            num_pages, images_per_page
        )

    @pytest.mark.asyncio
    async def test_alist_document_images(self):
        """Test async list_document_images."""
        from opencontractserver.llms.tools.image_tools import alist_document_images

        doc = await self._create_document_with_images(num_pages=2, images_per_page=2)

        images = await alist_document_images(doc.id)

        assert len(images) == 4
        assert all(isinstance(img, ImageReference) for img in images)

    @pytest.mark.asyncio
    async def test_alist_document_images_with_page_filter(self):
        """Test async list_document_images with page filter."""
        from opencontractserver.llms.tools.image_tools import alist_document_images

        doc = await self._create_document_with_images(num_pages=2, images_per_page=2)

        images = await alist_document_images(doc.id, page_index=0)

        assert len(images) == 2
        assert all(img.page_index == 0 for img in images)

    @pytest.mark.asyncio
    async def test_aget_document_image(self):
        """Test async get_document_image."""
        from opencontractserver.llms.tools.image_tools import aget_document_image

        doc = await self._create_document_with_images(num_pages=1, images_per_page=1)

        result = await aget_document_image(doc.id, page_index=0, token_index=1)

        assert result is not None
        assert isinstance(result, ImageData)
        assert result.page_index == 0
        assert result.token_index == 1

    @pytest.mark.asyncio
    async def test_aget_document_image_invalid(self):
        """Test async get_document_image with invalid indices."""
        from opencontractserver.llms.tools.image_tools import aget_document_image

        doc = await self._create_document_with_images(num_pages=1, images_per_page=1)

        result = await aget_document_image(doc.id, page_index=99, token_index=0)

        assert result is None

    def _create_annotation_sync(self, doc):
        """Helper to create annotation synchronously."""
        corpus = Corpus.objects.create(title="Async Test Corpus", creator=self.user)
        label_set = LabelSet.objects.create(title="Async Test LS", creator=self.user)
        corpus.label_set = label_set
        corpus.save()

        # Permission on BOTH document and corpus required (MIN rule)
        set_permissions_for_obj_to_user(self.user, corpus, [PermissionTypes.ALL])

        label = AnnotationLabel.objects.create(
            text="Figure",
            label_type="TOKEN_LABEL",
            creator=self.user,
        )
        label_set.annotation_labels.add(label)

        annotation = Annotation.objects.create(
            document=doc,
            corpus=corpus,
            annotation_label=label,
            raw_text="Figure",
            page=0,
            creator=self.user,
            json={
                "0": {
                    "bounds": {"left": 50, "top": 50, "right": 130, "bottom": 110},
                    "tokensJsons": [{"pageIndex": 0, "tokenIndex": 1}],
                }
            },
        )
        return annotation

    @pytest.mark.asyncio
    async def test_aget_annotation_images(self):
        """Test async get_annotation_images."""
        from asgiref.sync import sync_to_async

        from opencontractserver.llms.tools.image_tools import aget_annotation_images

        doc = await self._create_document_with_images(num_pages=1, images_per_page=1)
        annotation = await sync_to_async(self._create_annotation_sync)(doc)

        images = await aget_annotation_images(annotation.id)

        assert len(images) == 1
        assert isinstance(images[0], ImageData)

    @pytest.mark.asyncio
    async def test_alist_document_images_with_permission(self):
        """Test async list_document_images_with_permission."""
        from opencontractserver.llms.tools.image_tools import (
            alist_document_images_with_permission,
        )

        doc = await self._create_document_with_images(num_pages=1, images_per_page=2)

        # Permitted user
        images = await alist_document_images_with_permission(self.user, doc.id)
        assert len(images) == 2

        # Non-permitted user
        images = await alist_document_images_with_permission(self.other_user, doc.id)
        assert images == []

    @pytest.mark.asyncio
    async def test_aget_document_image_with_permission(self):
        """Test async get_document_image_with_permission."""
        from opencontractserver.llms.tools.image_tools import (
            aget_document_image_with_permission,
        )

        doc = await self._create_document_with_images(num_pages=1, images_per_page=1)

        # Permitted user
        result = await aget_document_image_with_permission(
            self.user, doc.id, page_index=0, token_index=1
        )
        assert result is not None
        assert isinstance(result, ImageData)

        # Non-permitted user
        result = await aget_document_image_with_permission(
            self.other_user, doc.id, page_index=0, token_index=1
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_aget_annotation_images_with_permission(self):
        """Test async get_annotation_images_with_permission."""
        from asgiref.sync import sync_to_async

        from opencontractserver.llms.tools.image_tools import (
            aget_annotation_images_with_permission,
        )

        doc = await self._create_document_with_images(num_pages=1, images_per_page=1)
        annotation = await sync_to_async(self._create_annotation_sync)(doc)

        # Permitted user
        images = await aget_annotation_images_with_permission(self.user, annotation.id)
        assert len(images) == 1

        # Non-permitted user
        images = await aget_annotation_images_with_permission(
            self.other_user, annotation.id
        )
        assert images == []


class ImageToolsEdgeCasesTest(TestCase):
    """Tests for edge cases and error handling in image tools."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.user = User.objects.create_user(
            username="edge_case_test_user", password="testpass123"
        )
        cls.corpus = Corpus.objects.create(
            title="Test Corpus Edge Cases",
            creator=cls.user,
        )
        cls.label = AnnotationLabel.objects.create(
            text="Test Label",
            creator=cls.user,
        )

    def test_list_document_images_malformed_pawls_page(self):
        """Should handle malformed PAWLS page data gracefully."""
        from opencontractserver.llms.tools.image_tools import list_document_images

        # Create document with malformed PAWLS data (pages that aren't dicts)
        malformed_pawls = [
            "not a dict",  # String instead of dict
            None,  # None
            {
                "page": {"width": 612, "height": 792},
                "tokens": [],
            },  # Valid but no images
        ]
        document = Document.objects.create(
            title="Test Doc Malformed",
            creator=self.user,
            pdf_file=ContentFile(b"fake pdf content", name="test.pdf"),
            pawls_parse_file=ContentFile(
                json.dumps(malformed_pawls).encode(), name="test.pawls"
            ),
        )
        self.corpus.add_document(document=document, user=self.user)

        # Should not raise an exception
        result = list_document_images(document.id)
        self.assertEqual(result, [])

    def test_list_document_images_malformed_tokens(self):
        """Should handle malformed token data gracefully."""
        from opencontractserver.llms.tools.image_tools import list_document_images

        # Create document with malformed tokens
        pawls_data = [
            {
                "page": {"width": 612, "height": 792, "index": 0},
                "tokens": [
                    "not a dict",  # String instead of dict
                    None,  # None
                    {"x": 100, "y": 100, "is_image": True},  # Missing some fields
                ],
            }
        ]
        document = Document.objects.create(
            title="Test Doc Malformed Tokens",
            creator=self.user,
            pdf_file=ContentFile(b"fake pdf content", name="test.pdf"),
            pawls_parse_file=ContentFile(
                json.dumps(pawls_data).encode(), name="test.pawls"
            ),
        )
        self.corpus.add_document(document=document, user=self.user)

        result = list_document_images(document.id)
        # Should find the one valid image token (even with missing fields)
        self.assertEqual(len(result), 1)

    def test_get_document_image_not_an_image_token(self):
        """Should return None when token is not an image token."""
        from opencontractserver.llms.tools.image_tools import get_document_image

        pawls_data = [
            {
                "page": {"width": 612, "height": 792, "index": 0},
                "tokens": [
                    {"x": 100, "y": 100, "width": 50, "height": 12, "text": "Hello"},
                ],
            }
        ]
        document = Document.objects.create(
            title="Test Doc Text Only",
            creator=self.user,
            pdf_file=ContentFile(b"fake pdf content", name="test.pdf"),
            pawls_parse_file=ContentFile(
                json.dumps(pawls_data).encode(), name="test.pawls"
            ),
        )
        self.corpus.add_document(document=document, user=self.user)

        # Token at index 0 is text, not image
        result = get_document_image(document.id, page_index=0, token_index=0)
        self.assertIsNone(result)

    def test_get_annotation_images_missing_annotation(self):
        """Should return empty list when annotation doesn't exist."""
        from opencontractserver.llms.tools.image_tools import get_annotation_images

        # Use a non-existent ID
        result = get_annotation_images(999999)
        self.assertEqual(result, [])

    def test_get_annotation_images_empty_json(self):
        """Should return empty list when annotation has empty json."""
        from opencontractserver.llms.tools.image_tools import get_annotation_images

        document = Document.objects.create(
            title="Test Doc",
            creator=self.user,
            pdf_file=ContentFile(b"fake pdf content", name="test.pdf"),
        )
        self.corpus.add_document(document=document, user=self.user)

        annotation = Annotation.objects.create(
            document=document,
            corpus=self.corpus,
            annotation_label=self.label,
            creator=self.user,
            json={},  # Empty json
        )

        result = get_annotation_images(annotation.id)
        self.assertEqual(result, [])


class ImageToolsPermissionEdgeCasesTest(TestCase):
    """Tests for permission edge cases in image tools."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.user = User.objects.create_user(
            username="perm_edge_test_user", password="testpass123"
        )
        cls.other_user = User.objects.create_user(
            username="perm_edge_other_user", password="testpass123"
        )
        cls.superuser = User.objects.create_superuser(
            username="perm_edge_superuser", password="testpass123"
        )
        cls.corpus = Corpus.objects.create(
            title="Test Corpus Perm Edge",
            creator=cls.user,
        )
        cls.label = AnnotationLabel.objects.create(
            text="Test Label",
            creator=cls.user,
        )

    def test_superuser_bypasses_permission_checks(self):
        """Superuser should bypass all permission checks."""
        from opencontractserver.llms.tools.image_tools import (
            get_annotation_images_with_permission,
        )

        # Create document without granting permissions to anyone
        document = Document.objects.create(
            title="Private Doc",
            creator=self.other_user,  # Different user
            is_public=False,
        )

        annotation = Annotation.objects.create(
            document=document,
            corpus=self.corpus,
            annotation_label=self.label,
            creator=self.other_user,
            raw_text="Private annotation",
            json={},
        )

        # Superuser should get access (returns empty list since no images, but no error)
        result = get_annotation_images_with_permission(self.superuser, annotation.id)
        self.assertEqual(result, [])  # No images, but access was granted

    def test_annotation_with_created_by_analysis_permission_denied(self):
        """Annotations privately attached to an analysis stay hidden.

        Privacy is enforced by ``AnnotationQuerySet.visible_to_user``, which
        the image endpoint delegates to. Pinning the integration here
        catches any future divergence between the GraphQL feed and REST.
        """
        from opencontractserver.analyzer.models import Analysis, Analyzer

        # Owner of doc/corpus, but NOT the analysis creator.
        document = Document.objects.create(title="Doc with Analysis", creator=self.user)
        set_permissions_for_obj_to_user(self.user, document, [PermissionTypes.ALL])
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.ALL])

        analyzer = Analyzer.objects.create(
            id="test.analyzer.image_priv_denied",
            description="Privacy test analyzer",
            creator=self.other_user,
            task_name="test_analyzer",
        )
        private_analysis = Analysis.objects.create(
            analyzer=analyzer,
            analyzed_corpus=self.corpus,
            creator=self.other_user,
            is_public=False,
        )

        annotation = Annotation.objects.create(
            document=document,
            corpus=self.corpus,
            annotation_label=self.label,
            creator=self.other_user,
            created_by_analysis=private_analysis,
            raw_text="Analysis annotation",
            json={},
        )

        # self.user owns doc + corpus but cannot see the private analysis.
        result = get_annotation_images_with_permission(self.user, annotation.id)
        self.assertEqual(result, [])

    def test_annotation_with_created_by_extract_permission_denied(self):
        """Annotations privately attached to an extract stay hidden."""
        from opencontractserver.extracts.models import Extract, Fieldset

        document = Document.objects.create(title="Doc with Extract", creator=self.user)
        set_permissions_for_obj_to_user(self.user, document, [PermissionTypes.ALL])
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.ALL])

        fieldset = Fieldset.objects.create(
            name="Privacy Fieldset",
            description="Privacy test",
            creator=self.other_user,
        )
        private_extract = Extract.objects.create(
            name="Private Extract",
            fieldset=fieldset,
            creator=self.other_user,
        )

        annotation = Annotation.objects.create(
            document=document,
            corpus=self.corpus,
            annotation_label=self.label,
            creator=self.other_user,
            created_by_extract=private_extract,
            raw_text="Extract annotation",
            json={},
        )

        result = get_annotation_images_with_permission(self.user, annotation.id)
        self.assertEqual(result, [])

    def test_corpus_permission_check_denied(self):
        """User without corpus permission should be denied."""
        from opencontractserver.llms.tools.image_tools import (
            get_annotation_images_with_permission,
        )

        # Create document - grant document permission but NOT corpus permission
        document = Document.objects.create(
            title="Doc in Corpus",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, document, [PermissionTypes.ALL])

        # Create corpus without granting permissions
        private_corpus = Corpus.objects.create(
            title="Private Corpus",
            creator=self.other_user,
            is_public=False,
        )

        annotation = Annotation.objects.create(
            document=document,
            corpus=private_corpus,  # Corpus user doesn't have access to
            annotation_label=self.label,
            creator=self.other_user,
            raw_text="Corpus-restricted annotation",
            json={},
        )

        # User has doc permission but not corpus permission
        result = get_annotation_images_with_permission(self.user, annotation.id)
        self.assertEqual(result, [])


class ImageToolsStructuralAnnotationTest(TestCase):
    """Tests for structural annotation image handling."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        import hashlib

        cls.user = User.objects.create_user(
            username="struct_test_user", password="testpass123"
        )
        cls.other_user = User.objects.create_user(
            username="struct_other_user", password="testpass123"
        )
        cls.label = AnnotationLabel.objects.create(
            text="Structural Label",
            creator=cls.user,
        )
        cls.content_hash = hashlib.sha256(b"structural test content").hexdigest()

    def test_structural_annotation_permission_via_document(self):
        """Structural annotation should be accessible via document permission."""
        from opencontractserver.annotations.models import StructuralAnnotationSet
        from opencontractserver.llms.tools.image_tools import (
            get_annotation_images_with_permission,
        )

        # Create structural set
        struct_set = StructuralAnnotationSet.objects.create(
            content_hash=self.content_hash,
            creator=self.user,
        )

        # Create document using the structural set
        document = Document.objects.create(
            title="Doc with Struct Set",
            creator=self.user,
            structural_annotation_set=struct_set,
        )
        set_permissions_for_obj_to_user(self.user, document, [PermissionTypes.ALL])

        # Create structural annotation
        annotation = Annotation.objects.create(
            structural_set=struct_set,
            annotation_label=self.label,
            creator=self.user,
            raw_text="Structural annotation",
            structural=True,
            json={},
        )

        # User with document permission should access structural annotation
        result = get_annotation_images_with_permission(self.user, annotation.id)
        self.assertEqual(result, [])  # No images but access granted

    def test_structural_annotation_permission_denied(self):
        """Structural annotation should be denied if no accessible document."""
        import hashlib

        from opencontractserver.annotations.models import StructuralAnnotationSet
        from opencontractserver.llms.tools.image_tools import (
            get_annotation_images_with_permission,
        )

        # Create structural set with unique hash
        unique_hash = hashlib.sha256(b"denied test content").hexdigest()
        struct_set = StructuralAnnotationSet.objects.create(
            content_hash=unique_hash,
            creator=self.other_user,
        )

        # Create document using the structural set - but DON'T grant access to self.user
        document = Document.objects.create(
            title="Private Doc with Struct Set",
            creator=self.other_user,
            structural_annotation_set=struct_set,
            is_public=False,
        )
        # Only grant to other_user
        set_permissions_for_obj_to_user(
            self.other_user, document, [PermissionTypes.ALL]
        )

        # Create structural annotation
        annotation = Annotation.objects.create(
            structural_set=struct_set,
            annotation_label=self.label,
            creator=self.other_user,
            raw_text="Private structural annotation",
            structural=True,
            json={},
        )

        # self.user has no access to any document using this structural set
        result = get_annotation_images_with_permission(self.user, annotation.id)
        self.assertEqual(result, [])


class ImageToolsPreExtractedContentTest(TestCase):
    """Tests for pre-extracted image content file handling."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.user = User.objects.create_user(
            username="preextract_test_user", password="testpass123"
        )
        cls.label = AnnotationLabel.objects.create(
            text="Test Label",
            creator=cls.user,
        )

    def _create_sample_image_base64(self):
        """Create a sample base64-encoded image."""
        import base64
        from io import BytesIO

        from PIL import Image

        img = Image.new("RGB", (50, 50), color="blue")
        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def test_load_images_from_annotation_file_success(self):
        """Should load images from pre-extracted image_content_file."""
        from io import StringIO
        from unittest.mock import MagicMock

        from opencontractserver.llms.tools.image_tools import (
            _load_images_from_annotation_file,
        )

        base64_data = self._create_sample_image_base64()
        image_content = {
            "images": [
                {
                    "base64": base64_data,
                    "format": "jpeg",
                    "page_index": 0,
                    "token_index": 1,
                }
            ]
        }

        # Mock annotation with image_content_file
        mock_annotation = MagicMock()
        mock_annotation.pk = 123
        mock_file = MagicMock()
        mock_file.open.return_value.__enter__ = MagicMock(
            return_value=StringIO(json.dumps(image_content))
        )
        mock_file.open.return_value.__exit__ = MagicMock(return_value=False)
        mock_annotation.image_content_file = mock_file

        images = _load_images_from_annotation_file(mock_annotation)

        self.assertEqual(len(images), 1)
        self.assertEqual(images[0].format, "jpeg")
        self.assertEqual(images[0].page_index, 0)
        self.assertEqual(images[0].token_index, 1)

    def test_load_images_from_annotation_file_no_file(self):
        """Should return empty list when no image_content_file."""
        from unittest.mock import MagicMock

        from opencontractserver.llms.tools.image_tools import (
            _load_images_from_annotation_file,
        )

        mock_annotation = MagicMock()
        mock_annotation.pk = 123
        mock_annotation.image_content_file = None

        images = _load_images_from_annotation_file(mock_annotation)
        self.assertEqual(images, [])

    def test_load_images_from_annotation_file_empty(self):
        """Should return empty list when file contains no images."""
        from io import StringIO
        from unittest.mock import MagicMock

        from opencontractserver.llms.tools.image_tools import (
            _load_images_from_annotation_file,
        )

        image_content = {"images": []}

        mock_annotation = MagicMock()
        mock_annotation.pk = 123
        mock_file = MagicMock()
        mock_file.open.return_value.__enter__ = MagicMock(
            return_value=StringIO(json.dumps(image_content))
        )
        mock_file.open.return_value.__exit__ = MagicMock(return_value=False)
        mock_annotation.image_content_file = mock_file

        images = _load_images_from_annotation_file(mock_annotation)
        self.assertEqual(images, [])

    def test_load_images_from_annotation_file_malformed(self):
        """Should handle malformed file gracefully."""
        from io import StringIO
        from unittest.mock import MagicMock

        from opencontractserver.llms.tools.image_tools import (
            _load_images_from_annotation_file,
        )

        mock_annotation = MagicMock()
        mock_annotation.pk = 123
        mock_file = MagicMock()
        mock_file.open.return_value.__enter__ = MagicMock(
            return_value=StringIO("not valid json")
        )
        mock_file.open.return_value.__exit__ = MagicMock(return_value=False)
        mock_annotation.image_content_file = mock_file

        images = _load_images_from_annotation_file(mock_annotation)
        self.assertEqual(images, [])
