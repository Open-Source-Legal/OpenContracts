import logging
from io import BytesIO
from typing import Optional

from opencontractserver.pipeline.base.file_types import FileTypeEnum
from opencontractserver.pipeline.base.thumbnailer import BaseThumbnailGenerator
from opencontractserver.utils.files import create_text_thumbnail
from opencontractserver.utils.logging import redact_sensitive_kwargs

logger = logging.getLogger(__name__)


class TextThumbnailGenerator(BaseThumbnailGenerator):
    """
    A thumbnail generator that creates thumbnails from text content.
    """

    title = "Text Thumbnail Generator"
    description = "Generates a thumbnail image from text content."
    author = "Your Name"
    dependencies = []
    supported_file_types = [FileTypeEnum.TXT]

    def __init__(self, **kwargs_super):
        """Initializes the TextThumbnailGenerator."""
        super().__init__(**kwargs_super)
        logger.info("TextThumbnailGenerator initialized.")

    def _generate_thumbnail_impl(
        self, txt_content: Optional[str], pdf_bytes: Optional[bytes], **all_kwargs
    ) -> Optional[tuple[bytes, str]]:
        """
        Generate a thumbnail from text content.

        Args:
            txt_content (Optional[str]): The content of the text file.
            pdf_bytes (Optional[bytes]): The bytes of the PDF file (unused by this thumbnailer).
            **all_kwargs: Keyword arguments, including 'height' and 'width'.

        Returns:
            Optional[Tuple[bytes, str]]: A tuple containing the thumbnail image bytes and file extension,
                                         or None if an error occurs.
        """
        height = all_kwargs.get("height", 300)
        width = all_kwargs.get("width", 300)
        logger.debug(
            f"TextThumbnailGenerator generating with height={height}, width={width}. "
            f"All kwargs: {redact_sensitive_kwargs(all_kwargs)}"
        )

        if txt_content:
            # Use the create_text_thumbnail function to generate an image from text
            image = create_text_thumbnail(text=txt_content, width=width, height=height)
            if image:
                # Save the image to bytes
                image_bytes_io = BytesIO()
                image.save(image_bytes_io, format="PNG")
                image_bytes = image_bytes_io.getvalue()
                return image_bytes, "png"

        # Optionally, handle pdf_bytes if txt_content is not available
        if pdf_bytes:
            # Logic to generate thumbnail from PDF bytes (not implemented here)
            pass

        # If neither txt_content nor pdf_bytes could generate a thumbnail
        return None
