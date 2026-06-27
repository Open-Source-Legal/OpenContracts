# LiteParse Parser

## Intro

The LiteParse Parser integrates [LiteParse](https://github.com/run-llama/liteparse)
(from LlamaIndex) to parse PDF documents **fully locally**. LiteParse is a
PDFium-based spatial text extractor (with optional Tesseract OCR for scanned
pages) — unlike the cloud-based [LlamaParse](llamaparse_parser.md), nothing
leaves your network, and unlike the [Docling](docling_parser.md) microservice it
runs in-process with no separate service to operate.

Implementation: `opencontractserver/pipeline/parsers/liteparse_parser.py::LiteParseParser`.

## What LiteParse provides (and what this parser adds)

LiteParse returns *line-level* spatial text items — each carrying the line's
text and an absolute bounding box (`x`, `y`, `width`, `height` in PDF points,
top-left origin) plus font metadata (`font_name`, `font_size`, `confidence`).
It does **not** classify items into element types or expose a parent-child
hierarchy. To match the core outputs of the other PDF engines, the parser
augments LiteParse's output:

| Output | Source |
|--------|--------|
| **Bounding boxes** | LiteParse `TextItem.x/y/width/height` (absolute PDF points, no fractional conversion needed) |
| **Word-level tokens** | pdfplumber (`extract_pawls_tokens_from_pdf`), the same path used by the LlamaParse parser; each LiteParse line bbox is mapped to the word tokens it encloses via a shapely spatial index |
| **Feature labels** | Derived from `font_size`: the modal size is body text (`Text Block`); larger sizes are ranked into heading levels (`Title` for the largest, `Section Header` below) |
| **Parent-child relationships** | A heading stack walked over the document in reading order assigns each line a `parent_id` to its nearest enclosing heading; these feed `import_annotations` (self-FK edges) and `build_subtree_groups_for_document` (materialised subtree relationships) |
| **Images** | pdfplumber (`extract_images_from_pdf`) — embedded images are added to the unified PAWLs token array and each gets an `Image` annotation |

Heading detection is heuristic (font-size based) and can be disabled with
`detect_headings=False`, in which case every line becomes a flat `Text Block`
with no parent (matching the LlamaParse parser's flat output).

## Configuration

### Selecting LiteParse

```bash
# Make LiteParse the PDF engine
PDF_PARSER=liteparse
```

LiteParse is PDF-only (PDFium). When it is selected, DOCX/PPTX uploads
automatically fall back to the Docling parser (see `_SELECTED_OFFICE_PARSER` in
`config/settings/base.py`).

### Environment variables

All optional; values seed the `PipelineSettings` database via
`python manage.py migrate_pipeline_settings`.

```bash
LITEPARSE_OUTPUT_FORMAT=markdown   # full-text layer format: json | text | markdown
LITEPARSE_OCR_ENABLED=False        # Tesseract OCR for scanned/garbled pages
LITEPARSE_OCR_LANGUAGE=eng
LITEPARSE_OCR_SERVER_URL=          # optional HTTP OCR server endpoint
LITEPARSE_DPI=150
LITEPARSE_NUM_WORKERS=4
LITEPARSE_TARGET_PAGES=            # e.g. "1-5,10"
LITEPARSE_MAX_PAGES=0              # 0 = all
LITEPARSE_PASSWORD=                # for encrypted PDFs (stored encrypted)
LITEPARSE_IMAGE_MODE=off           # LiteParse's own image handling; OC uses pdfplumber instead
LITEPARSE_DETECT_HEADINGS=True
LITEPARSE_HEADING_SIZE_RATIO=1.2   # size ratio above body at which a line is a heading
LITEPARSE_EXTRACT_IMAGES=True
```

## Usage

```python
from opencontractserver.pipeline.parsers.liteparse_parser import LiteParseParser

parser = LiteParseParser()
result = parser.parse_document(user_id=1, doc_id=123)

# Override per-call
result = parser.parse_document(
    user_id=1,
    doc_id=123,
    ocr_enabled=True,
    detect_headings=False,
)
```

## Output

Returns an `OpenContractDocExport` dict: `title`, `content` (the LiteParse
full-text / markdown layer), `description`, `pawls_file_content` (word + image
tokens per page), `page_count`, `labelled_text` (structural annotations with
`parent_id` set where a hierarchy was derived), `doc_labels` (empty), and
`relationships` (empty — the parent-child tree is materialised into
`OC_SUBTREE_GROUP` relationships downstream by `save_parsed_data`).

## Comparison with other PDF engines

| Feature | LiteParse | LlamaParse | Docling |
|---------|-----------|------------|---------|
| Deployment | In-process (local) | Cloud API | Local microservice |
| API key required | No | Yes | No |
| Word-level tokens | Yes (pdfplumber) | Yes (pdfplumber) | Yes |
| Feature labels | Heuristic (font size) | ML element types | ML element types |
| Parent-child hierarchy | Heuristic (heading stack) | No | Yes (groups) |
| OCR | Yes (Tesseract, optional) | Yes (automatic) | Yes (Tesseract) |
| Office formats (DOCX/PPTX) | No (falls back to Docling) | Yes | Yes |
| Privacy | Local | Cloud | Local |

## Dependencies

`liteparse` (see `requirements/ingestors/liteparse.txt`). Install with
`pip install liteparse`. pdfplumber/PIL (already required by the pipeline) power
token and image extraction. If `liteparse` is not installed the parser logs an
error and returns `None` rather than crashing startup (the import is lazy).

## See Also

- [Pipeline Overview](pipeline_overview.md)
- [LlamaParse Parser](llamaparse_parser.md)
- [Docling Parser](docling_parser.md)
- [LiteParse on GitHub](https://github.com/run-llama/liteparse)
