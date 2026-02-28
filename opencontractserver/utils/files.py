import base64
import logging
import os
import pathlib
import string
import textwrap
import typing
import uuid
from io import BytesIO
from typing import Union

from django.conf import settings
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader
from pypdf.generic import (
    ArrayObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
    TextStringObject,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Define printable characters more explicitly using their byte values
PRINTABLE_BYTES = set(
    bytes(
        string.ascii_letters + string.digits + string.punctuation + " \t\n\r", "ascii"
    )
)


def base_64_encode_bytes(doc_bytes: bytes):
    """
    Given bytes, encode base64 and utf-8
    """
    base64_encoded_data = base64.b64encode(doc_bytes)
    base64_encoded_message = base64_encoded_data.decode("utf-8")
    return base64_encoded_message


def convert_hex_to_rgb_tuple(color: str) -> tuple[int, ...]:
    color_tuple = tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))
    return color_tuple


# Courtesy of SO: https://gist.github.com/agentcooper/4c55133f5d95866acdee5017cd318558
# x1, y1 starts in bottom left corner
def createHighlight(
    x1: int, y1: int, x2: int, y2: int, meta: dict, color: tuple[float, float, float]
) -> DictionaryObject:
    logger.info("createHighlight() - Starting...")
    logger.info(f"meta: {meta}")
    logger.info(f"color: {color}")

    new_highlight = DictionaryObject()

    new_highlight.update(
        {
            NameObject("/F"): NumberObject(4),
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Highlight"),
            NameObject("/T"): TextStringObject(meta["author"]),
            NameObject("/Contents"): TextStringObject(meta["contents"]),
            NameObject("/C"): ArrayObject([FloatObject(c) for c in color]),
            NameObject("/Rect"): ArrayObject(
                [FloatObject(x1), FloatObject(y1), FloatObject(x2), FloatObject(y2)]
            ),
            NameObject("/QuadPoints"): ArrayObject(
                [
                    FloatObject(x1),
                    FloatObject(y2),
                    FloatObject(x2),
                    FloatObject(y2),
                    FloatObject(x1),
                    FloatObject(y1),
                    FloatObject(x2),
                    FloatObject(y1),
                ]
            ),
        }
    )

    return new_highlight


def add_highlight_to_new_page(highlight: DictionaryObject, page, output):
    # NOTE(deferred): `page` and `output` are untyped (PyPDF PageObject /
    # PdfWriter). Adding hints is deferred — this is internal to etl.py.
    highlight_ref = output._add_object(highlight)

    if "/Annots" in page:
        page[NameObject("/Annots")].append(highlight_ref)
    else:
        page[NameObject("/Annots")] = ArrayObject([highlight_ref])


def split_pdf_into_images(
    pdf_bytes: bytes,
    storage_path: str,
    target_format: typing.Literal["PNG", "JPEG"] = "PNG",
    force_local: bool = False,
) -> list[str]:
    """
    Given bytes of a PDF file, split into images of specified format, store them in appropriate temporary
    file storage location, and then return a list of file paths to the images, in page order.

    Storage path should be like this user_{user_id}/fragments for S3 or f"/tmp/user_{user_id}/pdf_fragments" for
    local storage.

    Args:
        pdf_bytes (bytes): The bytes of the PDF file to split.
        storage_path (str): The path to store the image fragments.
        target_format (Literal["PNG", "JPEG"]): The image format to save the pages as.
        force_local (bool): If True, forces the use of local filesystem even if settings.USE_AWS is True.

    Returns:
        list[str]: A list of file paths to the stored images in page order.
    """

    from pdf2image import convert_from_bytes

    page_paths: list[str] = []

    try:
        logger.debug("Starting split_pdf_into_images()")
        logger.debug(f"Received pdf_bytes of length: {len(pdf_bytes)}")
        logger.debug(f"Storage path: {storage_path}")
        logger.debug(f"Target format before uppercase conversion: {target_format}")
        logger.debug(f"Force local storage: {force_local}")

        # Ensure target_format is uppercase
        target_format = target_format.upper()
        logger.debug(f"Target format after uppercase conversion: {target_format}")
        if target_format not in ["PNG", "JPEG"]:
            logger.error(f"Unsupported target format: {target_format}")
            raise ValueError(f"Unsupported target format: {target_format}")

        # Resolution (754x1000) is chosen to match PAWLS coordinate system expectations
        logger.debug("Converting PDF to images at PAWLS-compatible resolution 754x1000")
        images = convert_from_bytes(pdf_bytes, size=(754, 1000))
        logger.debug(f"Number of images extracted: {len(images)}")

        # Determine file extension and content type
        file_extension = ".png" if target_format == "PNG" else ".jpg"
        content_type = f"image/{target_format.lower()}"
        logger.debug(f"File extension set to: {file_extension}")
        logger.debug(f"Content type set to: {content_type}")

        storage_backend = settings.STORAGE_BACKEND if not force_local else "LOCAL"
        logger.debug(f"Using storage backend: {storage_backend}")

        if storage_backend == "AWS":
            logger.debug("AWS storage backend detected, initializing S3 client")
            import boto3

            s3 = boto3.client("s3")
            logger.debug("S3 client initialized")
        elif storage_backend == "GCP":
            logger.debug("GCP storage backend detected, initializing GCS client")
            from google.cloud import storage as gcs

            gcs_client = gcs.Client(project=settings.GS_PROJECT_ID)
            gcs_bucket = gcs_client.bucket(settings.GS_BUCKET_NAME)
            logger.debug("GCS client initialized")
        else:
            logger.debug("Proceeding with local storage")

        for index, img in enumerate(images):
            logger.debug(f"Processing image {index + 1} of {len(images)}")

            # images is a list of Pillow Image objs.
            img_bytes_stream = BytesIO()
            logger.debug(
                f"Saving image {index + 1} to bytes stream in format {target_format}"
            )
            img.save(img_bytes_stream, target_format)
            img_bytes = img_bytes_stream.getvalue()
            logger.debug(f"Image {index + 1} bytes size: {len(img_bytes)} bytes")

            if storage_backend == "AWS":
                logger.debug("Uploading image to AWS S3")
                page_path = f"{storage_path}/{uuid.uuid4()}{file_extension}"
                logger.debug(f"Generated S3 page path: {page_path}")
                s3.put_object(
                    Key=page_path,
                    Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                    Body=img_bytes,
                    ContentType=content_type,
                )
                logger.debug(f"Image {index + 1} uploaded to S3 with key: {page_path}")
            elif storage_backend == "GCP":
                logger.debug("Uploading image to Google Cloud Storage")
                page_path = f"{storage_path}/{uuid.uuid4()}{file_extension}"
                logger.debug(f"Generated GCS page path: {page_path}")
                blob = gcs_bucket.blob(page_path)
                blob.upload_from_string(img_bytes, content_type=content_type)
                logger.debug(f"Image {index + 1} uploaded to GCS with key: {page_path}")
            else:
                logger.debug("Saving image locally")
                pdf_fragment_folder_path = pathlib.Path(storage_path)
                logger.debug(
                    f"Ensuring local directory exists at: {pdf_fragment_folder_path}"
                )
                pdf_fragment_folder_path.mkdir(parents=True, exist_ok=True)
                pdf_fragment_path = (
                    pdf_fragment_folder_path / f"{uuid.uuid4()}{file_extension}"
                )
                logger.debug(f"Generated local page path: {pdf_fragment_path}")
                with pdf_fragment_path.open("wb") as f:
                    logger.debug(f"Writing image {index + 1} bytes to file")
                    f.write(img_bytes)
                page_path = str(pdf_fragment_path.resolve())
                logger.debug(f"Image {index + 1} saved locally at: {page_path}")

            page_paths.append(page_path)
            logger.debug(f"Page path added to list: {page_path}")

    except Exception as e:
        logger.error(f"split_pdf_into_images() failed due to unexpected error: {e}")
        raise

    logger.debug(
        f"split_pdf_into_images() completed successfully with {len(page_paths)} page(s)"
    )
    return page_paths


def check_if_pdf_needs_ocr(file_object, threshold=10):
    pdf_reader = PdfReader(file_object)
    total_text = ""

    for page in pdf_reader.pages:
        total_text += page.extract_text()

    # Reset file pointer to the beginning for subsequent use
    file_object.seek(0)

    # If the total extracted text is less than the threshold, it likely needs OCR
    return len(total_text.strip()) < threshold


def is_plaintext_content(
    content: Union[str, bytes], sample_size: int = 1024, threshold: float = 0.8
) -> bool:
    """
    Check if the given content is plaintext.

    Args:
        content (Union[str, bytes]): The content to check. Can be a file path, bytes, or string.
        sample_size (int): The number of bytes to sample for the check.
        threshold (float): The threshold ratio of printable characters to consider as plaintext.

    Returns:
        bool: True if the content is plaintext, False otherwise.

    Raises:
        FileNotFoundError: If the provided content is a non-existent file path.
    """
    if isinstance(content, str):
        if not os.path.exists(content):
            raise FileNotFoundError(f"File not found: {content}")
        try:
            with open(content, "rb") as f:
                sample = f.read(sample_size)
        except OSError as e:
            # Handle potential errors during file read more gracefully
            print(f"Error reading file {content}: {e}")
            return False
    elif isinstance(content, bytes):
        sample = content[:sample_size]
    else:
        # Handle unexpected content types
        return False

    if not sample:
        return False  # Empty content is not considered plaintext

    # Use the explicit byte set for checking
    printable_count = sum(1 for byte in sample if byte in PRINTABLE_BYTES)

    # Avoid division by zero if sample somehow became empty after checks
    sample_len = len(sample)
    if sample_len == 0:
        return False  # Treat genuinely empty sample as not plaintext

    printable_ratio = printable_count / sample_len

    return printable_ratio >= threshold


def create_text_thumbnail(
    text: str,
    width: int = 300,
    height: int = 300,
    font_size: int = 12,
    margin: int = 20,
    line_spacing: int = 4,
) -> Image.Image:
    """
    Create a thumbnail image from the given text.

    Args:
        text (str): The text to render in the thumbnail.
        width (int): The width of the thumbnail image.
        height (int): The height of the thumbnail image.
        font_size (int): The font size to use for the text.
        margin (int): The margin around the text.
        line_spacing (int): The spacing between lines of text.

    Returns:
        Image.Image: A PIL Image object containing the rendered text thumbnail.
    """
    logger.debug(f"Creating text thumbnail with dimensions {width}x{height}")

    # Create a new white image
    img = Image.new("RGB", (width, height), color="white")
    draw = ImageDraw.Draw(img)

    # Load a font
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
        logger.debug("Using Arial font")
    except OSError:
        font = ImageFont.load_default()
        logger.debug("Using default font")

    # Calculate the maximum width of text
    max_width = width - 2 * margin

    # Wrap the text
    lines = textwrap.wrap(text, width=max_width // (font_size // 2))
    logger.debug(f"Text wrapped into {len(lines)} lines")

    # Draw the text
    y_text = margin
    for line in lines:
        draw.text((margin, y_text), line, font=font, fill="black")
        y_text += font_size + line_spacing

        # Stop if we've reached the bottom of the image
        if y_text > height - margin:
            logger.debug("Reached bottom of image, truncating text")
            break

    # Add some lines to simulate ruled paper
    for i in range(margin, height - margin, font_size + line_spacing):
        draw.line([(margin, i), (width - margin, i)], fill="lightblue", width=1)

    logger.debug("Text thumbnail created successfully")
    return img
