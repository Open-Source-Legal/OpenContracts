import logging
import zipfile
from io import BytesIO
from typing import Optional

from opencontractserver.pipeline.base.file_types import FileTypeEnum
from opencontractserver.pipeline.base.thumbnailer import BaseThumbnailGenerator
from opencontractserver.utils.files import create_text_thumbnail

logger = logging.getLogger(__name__)


class DocxThumbnailGenerator(BaseThumbnailGenerator):
    """
    Thumbnail generator for DOCX files.

    Tries two approaches in order:
    1. Extract embedded thumbnail from the DOCX ZIP archive (docProps/thumbnail.jpeg)
    2. Fall back to generating a text-based thumbnail from the document content
    """

    title = "DOCX Thumbnail Generator"
    description = "Generates thumbnail images from DOCX documents."
    author = "OpenContracts Team"
    dependencies = []
    supported_file_types = [FileTypeEnum.DOCX]

    def __init__(self, **kwargs_super):
        """Initializes the DocxThumbnailGenerator."""
        super().__init__(**kwargs_super)
        logger.info("DocxThumbnailGenerator initialized.")

    def _generate_thumbnail_impl(
        self, txt_content: Optional[str], pdf_bytes: Optional[bytes], **all_kwargs
    ) -> Optional[tuple[bytes, str]]:
        """
        Generate a thumbnail from a DOCX file.

        First tries to extract an embedded thumbnail from the DOCX ZIP archive.
        Falls back to rendering text content as an image.

        Args:
            txt_content: The content of the text extraction (may not be available
                         yet during thumbnail generation since it runs before parsing).
            pdf_bytes: The bytes of the DOCX file (stored in pdf_file field).
            **all_kwargs: Keyword arguments including 'height' and 'width'.

        Returns:
            Tuple of (thumbnail_bytes, file_extension) or None.
        """
        height = all_kwargs.get("height", 300)
        width = all_kwargs.get("width", 300)

        # Approach 1: Try to extract embedded thumbnail from DOCX ZIP
        if pdf_bytes:
            embedded = self._extract_embedded_thumbnail(pdf_bytes)
            if embedded:
                logger.info("Using embedded thumbnail from DOCX file")
                return embedded

        # Approach 2: Fall back to text-based thumbnail
        # During thumbnail generation, txt_content may not be populated yet
        # (thumbnail runs before parsing). Try to extract text from the DOCX directly.
        text_for_thumbnail = txt_content
        if not text_for_thumbnail and pdf_bytes:
            text_for_thumbnail = self._extract_text_preview(pdf_bytes)

        if text_for_thumbnail:
            image = create_text_thumbnail(
                text=text_for_thumbnail, width=width, height=height
            )
            if image:
                image_bytes_io = BytesIO()
                image.save(image_bytes_io, format="PNG")
                return image_bytes_io.getvalue(), "png"

        return None

    @staticmethod
    def _extract_embedded_thumbnail(docx_bytes: bytes) -> Optional[tuple[bytes, str]]:
        """
        Extract an embedded thumbnail image from a DOCX ZIP archive.

        DOCX files may contain a thumbnail in docProps/thumbnail.jpeg or
        docProps/thumbnail.png.

        Args:
            docx_bytes: Raw bytes of the DOCX file.

        Returns:
            Tuple of (image_bytes, extension) or None if no thumbnail found.
        """
        try:
            with zipfile.ZipFile(BytesIO(docx_bytes), "r") as zf:
                # Check common thumbnail locations
                thumbnail_paths = [
                    ("docProps/thumbnail.jpeg", "jpeg"),
                    ("docProps/thumbnail.jpg", "jpeg"),
                    ("docProps/thumbnail.png", "png"),
                    ("docProps/thumbnail.emf", None),  # Skip EMF format
                ]
                for path, ext in thumbnail_paths:
                    if ext and path in zf.namelist():
                        return zf.read(path), ext
        except Exception as e:
            logger.debug(f"Could not extract embedded thumbnail: {e}")

        return None

    @staticmethod
    def _extract_text_preview(docx_bytes: bytes, max_chars: int = 500) -> Optional[str]:
        """
        Extract a text preview from a DOCX file for thumbnail rendering.

        Uses zipfile to read the document.xml directly, extracting text content
        without requiring python-docx.

        Args:
            docx_bytes: Raw bytes of the DOCX file.
            max_chars: Maximum characters to extract.

        Returns:
            Text preview string or None.
        """
        try:
            # Imported locally because this is an optional fallback path — avoids
            # loading the XML parser at module level for the common case where an
            # embedded thumbnail image is found first.
            import xml.etree.ElementTree as ET

            with zipfile.ZipFile(BytesIO(docx_bytes), "r") as zf:
                if "word/document.xml" not in zf.namelist():
                    return None

                with zf.open("word/document.xml") as doc_xml:
                    tree = ET.parse(doc_xml)

                # Extract text from w:t elements
                ns = {
                    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
                }
                texts = []
                total_len = 0

                for t_elem in tree.iter(f"{{{ns['w']}}}t"):
                    if t_elem.text:
                        texts.append(t_elem.text)
                        total_len += len(t_elem.text)
                        if total_len >= max_chars:
                            break

                if texts:
                    return " ".join(texts)[:max_chars]

        except Exception as e:
            logger.debug(f"Could not extract text preview from DOCX: {e}")

        return None
