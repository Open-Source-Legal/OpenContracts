import logging
from dataclasses import dataclass, field
from typing import Optional

from opencontractserver.pipeline.base.file_types import FileTypeEnum
from opencontractserver.pipeline.base.settings_schema import (
    PipelineSetting,
    SettingType,
)
from opencontractserver.pipeline.base.thumbnailer import BaseThumbnailGenerator
from opencontractserver.thumbnails.pdfs import pdf_thumbnail_from_bytes
from opencontractserver.utils.logging import redact_sensitive_kwargs

logger = logging.getLogger(__name__)


class PdfThumbnailGenerator(BaseThumbnailGenerator):
    """
    A thumbnail generator that creates thumbnails from PDF files.

    Settings are loaded from PipelineSettings database. Use the management
    command `migrate_pipeline_settings` to seed initial values from environment.
    """

    title = "PDF Thumbnail Generator"
    description = "Generates a thumbnail image from PDF content."
    author = "JSv4"
    dependencies = []
    supported_file_types = [FileTypeEnum.PDF]

    @dataclass
    class Settings:
        """Configuration schema for PdfThumbnailGenerator."""

        height: int = field(
            default=300,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Height of generated thumbnail in pixels",
                )
            },
        )
        width: int = field(
            default=300,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Width of generated thumbnail in pixels",
                )
            },
        )

    def __init__(self, **kwargs_super):
        """Initialize the PdfThumbnailGenerator."""
        super().__init__(**kwargs_super)
        logger.info("PdfThumbnailGenerator initialized.")

    def _generate_thumbnail_impl(
        self, txt_content: Optional[str], pdf_bytes: Optional[bytes], **all_kwargs
    ) -> Optional[tuple[bytes, str]]:
        """
        Generate a thumbnail from bytes.

        Args:
            txt_content (Optional[str]): The content of the text file (unused by this thumbnailer).
            pdf_bytes (Optional[bytes]): The bytes of the PDF file.
            **all_kwargs: Keyword arguments, including 'height' and 'width'.

        Returns:
            Optional[Tuple[bytes, str]]: A tuple containing the thumbnail image bytes and file extension,
                                         or None if an error occurs.
        """
        height = all_kwargs.get("height", 300)
        width = all_kwargs.get("width", 300)
        logger.debug(
            f"PdfThumbnailGenerator generating with height={height}, width={width}. "
            f"All kwargs: {redact_sensitive_kwargs(all_kwargs)}"
        )

        try:
            # Determine desired dimensions
            thumbnail_size = (width, height)
            crop_size = (width, height)

            if not pdf_bytes:
                logger.warning("No PDF bytes provided to PdfThumbnailGenerator.")
                return None

            return pdf_thumbnail_from_bytes(
                pdf_bytes, thumbnail_size=thumbnail_size, crop_size=crop_size
            )

        except Exception as e:
            logger.error(f"Unable to create a thumbnail due to error: {e}")
            return None
