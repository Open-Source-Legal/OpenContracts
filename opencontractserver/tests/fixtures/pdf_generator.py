"""
PDF generator utilities for creating test documents with embedded images.

This module provides functions to programmatically create PDFs with text
and embedded images for integration testing of multimodal document processing.
"""

import io
from typing import Optional

from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


def create_test_image(
    width: int = 200,
    height: int = 150,
    color: str = "blue",
    format: str = "PNG",
) -> bytes:
    """
    Create a simple colored test image.

    Args:
        width: Image width in pixels.
        height: Image height in pixels.
        color: PIL color name or hex code.
        format: Image format (PNG, JPEG, etc.).

    Returns:
        Image data as bytes.
    """
    img = Image.new("RGB", (width, height), color=color)
    buffer = io.BytesIO()
    img.save(buffer, format=format)
    buffer.seek(0)
    return buffer.getvalue()


def create_pdf_with_image(
    text: str = "Test document with image",
    image_size: tuple[int, int] = (200, 150),
    image_color: str = "blue",
    title: Optional[str] = None,
) -> bytes:
    """
    Create a simple PDF with text and an embedded image.

    Creates a single-page PDF with:
    - A title (if provided)
    - Body text
    - An embedded colored rectangle image

    Args:
        text: Body text to display on the PDF.
        image_size: (width, height) tuple for the image in pixels.
        image_color: PIL color name or hex code for the image fill.
        title: Optional title displayed at the top of the page.

    Returns:
        PDF content as bytes.
    """
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # Add title if provided
    y_position = height - 72
    if title:
        c.setFont("Helvetica-Bold", 18)
        c.drawString(72, y_position, title)
        y_position -= 30

    # Add body text
    c.setFont("Helvetica", 12)
    c.drawString(72, y_position, text)
    y_position -= 30

    # Create and embed image
    img = Image.new("RGB", image_size, color=image_color)
    img_buffer = io.BytesIO()
    img.save(img_buffer, format="PNG")
    img_buffer.seek(0)

    c.drawImage(
        ImageReader(img_buffer),
        72,
        y_position - image_size[1],
        width=image_size[0],
        height=image_size[1],
    )

    c.save()
    buffer.seek(0)
    return buffer.getvalue()


def create_multi_page_pdf_with_images(
    pages: list[dict],
) -> bytes:
    """
    Create a multi-page PDF where each page can have text and/or images.

    Args:
        pages: List of page definitions. Each page dict can have:
            - "text": str - Text to display
            - "title": str - Optional title
            - "images": list[dict] - List of image definitions with:
                - "width": int (default 200)
                - "height": int (default 150)
                - "color": str (default "blue")
                - "x": int (default 72)
                - "y": int (optional, auto-calculated)

    Returns:
        PDF content as bytes.

    Example:
        >>> pages = [
        ...     {"title": "Page 1", "text": "Introduction", "images": [{"color": "red"}]},
        ...     {"text": "Analysis", "images": [{"color": "green"}, {"color": "blue"}]},
        ... ]
        >>> pdf_bytes = create_multi_page_pdf_with_images(pages)
    """
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    page_width, page_height = letter

    for page_def in pages:
        y_position = page_height - 72

        # Add title if provided
        title = page_def.get("title")
        if title:
            c.setFont("Helvetica-Bold", 18)
            c.drawString(72, y_position, title)
            y_position -= 30

        # Add text if provided
        text = page_def.get("text")
        if text:
            c.setFont("Helvetica", 12)
            # Handle multi-line text
            for line in text.split("\n"):
                c.drawString(72, y_position, line)
                y_position -= 15
            y_position -= 15  # Extra spacing after text

        # Add images if provided
        images = page_def.get("images", [])
        for img_def in images:
            img_width = img_def.get("width", 200)
            img_height = img_def.get("height", 150)
            img_color = img_def.get("color", "blue")
            img_x = img_def.get("x", 72)
            img_y = img_def.get("y", y_position - img_height)

            # Create image
            img = Image.new("RGB", (img_width, img_height), color=img_color)
            img_buffer = io.BytesIO()
            img.save(img_buffer, format="PNG")
            img_buffer.seek(0)

            c.drawImage(
                ImageReader(img_buffer),
                img_x,
                img_y,
                width=img_width,
                height=img_height,
            )

            # Update y_position for next image (if no explicit y)
            if "y" not in img_def:
                y_position = img_y - 20

        c.showPage()

    c.save()
    buffer.seek(0)
    return buffer.getvalue()


def create_pdf_with_chart_figure(
    title: str = "Financial Report",
    chart_title: str = "Revenue Growth",
    labels: Optional[list[str]] = None,
    values: Optional[list[int]] = None,
) -> bytes:
    """
    Create a PDF with a simple bar chart figure.

    Creates a more realistic test document that simulates a report
    with an embedded chart/figure.

    Args:
        title: Document title.
        chart_title: Title for the chart.
        labels: X-axis labels for the bars.
        values: Values for each bar.

    Returns:
        PDF content as bytes.
    """
    if labels is None:
        labels = ["Q1", "Q2", "Q3", "Q4"]
    if values is None:
        values = [100, 150, 120, 180]

    # Create a simple bar chart image
    chart_width = 400
    chart_height = 250
    img = Image.new("RGB", (chart_width, chart_height), color="white")

    # Draw bars (simple colored rectangles)
    from PIL import ImageDraw

    draw = ImageDraw.Draw(img)

    # Chart area
    margin = 40
    chart_area_width = chart_width - 2 * margin
    chart_area_height = chart_height - 2 * margin

    # Draw axes
    draw.line(
        [
            (margin, chart_height - margin),
            (chart_width - margin, chart_height - margin),
        ],
        fill="black",
        width=2,
    )
    draw.line(
        [(margin, margin), (margin, chart_height - margin)],
        fill="black",
        width=2,
    )

    # Draw bars
    max_value = max(values)
    bar_width = chart_area_width // (len(values) * 2)
    colors = ["#4285f4", "#34a853", "#fbbc04", "#ea4335"]

    for i, value in enumerate(values):
        bar_height = int((value / max_value) * chart_area_height * 0.8)
        x = margin + (i * 2 + 1) * bar_width
        y = chart_height - margin - bar_height
        draw.rectangle(
            [x, y, x + bar_width, chart_height - margin],
            fill=colors[i % len(colors)],
        )

    # Convert to bytes
    img_buffer = io.BytesIO()
    img.save(img_buffer, format="PNG")
    img_buffer.seek(0)

    # Create PDF
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # Title
    c.setFont("Helvetica-Bold", 24)
    c.drawString(72, height - 72, title)

    # Intro text
    c.setFont("Helvetica", 12)
    c.drawString(
        72, height - 110, f"This report shows {chart_title.lower()} over time."
    )

    # Chart title
    c.setFont("Helvetica-Bold", 14)
    c.drawString(72, height - 150, f"Figure 1: {chart_title}")

    # Embed chart
    c.drawImage(
        ImageReader(img_buffer),
        72,
        height - 420,
        width=chart_width,
        height=chart_height,
    )

    # Caption
    c.setFont("Helvetica-Oblique", 10)
    c.drawString(72, height - 440, "Source: Company financial data")

    c.save()
    buffer.seek(0)
    return buffer.getvalue()


def create_pdf_with_outline(
    pages: list[dict],
    outline: list[dict],
) -> bytes:
    """
    Create a multi-page PDF with an embedded ``/Outlines`` bookmark tree.

    Renders one page per entry in ``pages``, bookmarks every page, then
    attaches outline entries pointing at those pages. Used to exercise
    ``PdfOutlineEnricher``, which reads the bookmark tree via
    ``pypdf``'s ``reader.outline``.

    Args:
        pages: One dict per page. Recognised key:
            - "lines": list[str] - text lines drawn on the page (optional).
        outline: Ordered list of bookmark definitions. Each dict has:
            - "title": str  - bookmark title.
            - "page":  int  - 0-based index of the destination page.
            - "level": int  - nesting depth (0 = top level). Levels must be
              added in a valid order (a level-N entry requires a preceding
              level-(N-1) entry), per reportlab's outline API.

    Returns:
        PDF content as bytes.

    Example:
        >>> pdf = create_pdf_with_outline(
        ...     pages=[{"lines": ["Chapter One"]}, {"lines": ["Section A"]}],
        ...     outline=[
        ...         {"title": "Chapter One", "page": 0, "level": 0},
        ...         {"title": "Section A", "page": 1, "level": 1},
        ...     ],
        ... )
    """
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    page_width, page_height = letter

    for idx, page_def in enumerate(pages):
        c.bookmarkPage(f"page-{idx}")
        y_position = page_height - 72
        c.setFont("Helvetica", 12)
        for line in page_def.get("lines", []):
            c.drawString(72, y_position, line)
            y_position -= 18
        c.showPage()

    for entry in outline:
        c.addOutlineEntry(
            entry["title"],
            f"page-{entry['page']}",
            level=entry.get("level", 0),
        )

    c.save()
    buffer.seek(0)
    return buffer.getvalue()
