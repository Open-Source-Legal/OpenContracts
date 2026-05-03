"""Tool for rendering a PDF page as a base64-encoded image."""

import logging

from opencontractserver.documents.models import Document

from ._helpers import _db_sync_to_async

logger = logging.getLogger(__name__)


def get_page_image(
    document_id: int,
    page_number: int,
    image_format: str = "jpeg",
    dpi: int = 150,
) -> str:
    """
    Get a specific page from a PDF document as a base64-encoded image.
    This allows agents to visually inspect pages for diagrams, images, tables, and other visual content.

    Args:
        document_id: The primary key (ID) of the Document
        page_number: The page number to render (1-indexed)
        image_format: The image format to use ('jpeg' or 'png'), defaults to 'jpeg'
        dpi: The resolution in dots per inch (default 150, higher values = better quality but larger files)

    Returns:
        A base64-encoded string of the page image

    Raises:
        ValueError: If document doesn't exist, has no PDF file, page number is invalid, or format is unsupported
    """
    import base64
    import io

    from pdf2image import convert_from_bytes

    try:
        doc = Document.objects.get(pk=document_id)
    except Document.DoesNotExist:
        raise ValueError(f"Document with id={document_id} does not exist.")

    # Check if document is a PDF
    if doc.file_type != "application/pdf":
        raise ValueError(
            f"Document {document_id} is not a PDF (file_type: {doc.file_type}). "
            "Page imaging is only supported for PDF documents."
        )

    if not doc.pdf_file:
        raise ValueError(f"Document {document_id} has no PDF file attached.")

    # Validate page number
    if page_number < 1:
        raise ValueError(f"Invalid page number {page_number}. Page numbers start at 1.")

    if doc.page_count and page_number > doc.page_count:
        raise ValueError(
            f"Page number {page_number} exceeds document page count ({doc.page_count})."
        )

    # Validate image format
    valid_formats = {"jpeg", "png"}
    image_format = image_format.lower()
    if image_format not in valid_formats:
        raise ValueError(
            f"Unsupported image format '{image_format}'. Must be one of: {valid_formats}"
        )

    try:
        # Read PDF file
        with doc.pdf_file.open("rb") as pdf_file:
            pdf_bytes = pdf_file.read()

        # Convert the specified page to an image
        images = convert_from_bytes(
            pdf_bytes,
            dpi=dpi,
            first_page=page_number,
            last_page=page_number,
            fmt=image_format,
        )

        if not images:
            raise ValueError(
                f"Failed to render page {page_number} of document {document_id}"
            )

        # Get the first (and only) image
        page_image = images[0]

        # Convert to bytes
        image_io = io.BytesIO()
        # Use uppercase format name for PIL
        pil_format = "JPEG" if image_format == "jpeg" else "PNG"
        page_image.save(image_io, format=pil_format)
        image_io.seek(0)

        # Encode to base64
        image_bytes = image_io.getvalue()
        base64_encoded = base64.b64encode(image_bytes).decode("utf-8")

        logger.info(
            f"Successfully rendered page {page_number} of document {document_id} "
            f"(format: {image_format}, dpi: {dpi}, size: {len(base64_encoded)} chars)"
        )

        return base64_encoded

    except Exception as e:
        logger.error(
            f"Error rendering page {page_number} of document {document_id}: {e}"
        )
        raise ValueError(
            f"Failed to render page {page_number} of document {document_id}: {str(e)}"
        )


async def aget_page_image(
    document_id: int,
    page_number: int,
    image_format: str = "jpeg",
    dpi: int = 150,
) -> str:
    """Async wrapper around :func:`get_page_image`."""
    return await _db_sync_to_async(get_page_image)(
        document_id=document_id,
        page_number=page_number,
        image_format=image_format,
        dpi=dpi,
    )
