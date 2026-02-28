import logging
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Optional

from django.core.files.base import File

from opencontractserver.pipeline.base.file_types import FileTypeEnum

from .base_component import PipelineComponentBase

logger = logging.getLogger(__name__)


class BaseThumbnailGenerator(PipelineComponentBase, ABC):
    """
    Abstract base class for thumbnail generators. Thumbnail generators should inherit from this class.
    Handles automatic loading of settings from Django settings.PIPELINE_SETTINGS.
    """

    title: str = ""
    description: str = ""
    author: str = ""
    dependencies: list[str] = []
    supported_file_types: list[FileTypeEnum] = []
    input_schema: Mapping = (
        {}
    )  # If you want user to provide inputs, define a jsonschema here

    def __init__(self, **kwargs):
        """
        Initializes the Thumbnailer.
        Kwargs are passed to the superclass constructor (PipelineComponentBase).
        """
        super().__init__(**kwargs)

    @abstractmethod
    def _generate_thumbnail_impl(
        self, txt_content: Optional[str], pdf_bytes: Optional[bytes], **all_kwargs
    ) -> Optional[tuple[bytes, str]]:
        """
        Abstract internal method to generate a thumbnail from txt content and pdf bytes.
        Concrete subclasses must implement this method.

        Args:
            txt_content (Optional[str]): The content of the text file.
            pdf_bytes (Optional[bytes]): The bytes of the PDF file.
            **all_kwargs: All keyword arguments, including those from
                          PIPELINE_SETTINGS (e.g., height, width) and direct call-time arguments.

        Returns:
            Optional[Tuple[bytes, str]]: A tuple containing the thumbnail image bytes and file extension,
                                         or None if an error occurs.
        """
        pass

    def generate_thumbnail(self, doc_id: str | int, **kwargs) -> Optional[File]:
        """
        Generate a thumbnail for the given document ID by processing its text and PDF files.

        Args:
            doc_id (str | int): The ID of the document.

        Returns:
            Optional[File]: A Django File instance containing the thumbnail image, or None if an error occurs.
        """
        from django.core.files.base import ContentFile

        from opencontractserver.documents.models import Document

        try:
            # Load the Document instance
            document = Document.objects.get(id=doc_id)

            # Initialize variables
            txt_content: Optional[str] = None
            pdf_bytes: Optional[bytes] = None

            # Load the txt file content if available
            if document.txt_extract_file:
                with document.txt_extract_file.open("r") as txt_file:
                    txt_content = txt_file.read()

            # Load the pdf file bytes if available
            if document.pdf_file:
                with document.pdf_file.open("rb") as pdf_file:
                    pdf_bytes = pdf_file.read()

            # Default height and width can be part of component_settings or direct_kwargs
            default_dimensions = {"height": 300, "width": 300}
            component_settings = self.get_component_settings()

            # Merge order: defaults, then PIPELINE_SETTINGS, then direct_kwargs
            merged_kwargs = {**default_dimensions, **component_settings, **kwargs}

            logger.info(
                f"Calling _generate_thumbnail_impl with merged kwargs: {merged_kwargs}"
            )
            result = self._generate_thumbnail_impl(
                txt_content, pdf_bytes, **merged_kwargs
            )

            if result:
                thumbnail_bytes, extension = result
                thumbnail_file = ContentFile(thumbnail_bytes)
                thumb_filename = f"thumbnail_{doc_id}.{extension}"
                # Save thumbnail to document's icon field
                document.icon.save(thumb_filename, thumbnail_file)
                document.save()
                return thumbnail_file

            # If no thumbnail generated
            return None

        except Document.DoesNotExist:  # pragma: no cover -- defensive guard
            logger.warning("Document with id %s does not exist.", doc_id)
            return None
