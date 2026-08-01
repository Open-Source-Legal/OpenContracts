# Supported File Formats

OpenContracts accepts several document formats for upload. **Core formats**
are parsed natively; a much larger set of **convertible formats** can
optionally be turned into PDF by an install-wide file converter before
parsing, so their content becomes searchable and annotatable through the
same pipeline as any other PDF.

## Core Formats

| Format | Extension | MIME Type | Default Parser |
|--------|-----------|-----------|----------------|
| PDF | `.pdf` | `application/pdf` | DoclingParser (ML-based REST microservice) |
| Plain Text | `.txt` | `text/plain` | TxtParser (sentence-level splitting via spaCy) |
| Word | `.docx` | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | DocxodusServiceParser (REST microservice) |

These are the formats registered in the pipeline's `FileTypeEnum` and are
always available, for both single uploads and bulk imports, regardless of
converter configuration. Markdown (`.md`) is also handled natively — it is
rendered client-side and skips the ingest pipeline entirely.

### Legacy MIME Aliases

The system also accepts `application/txt` as an alias for `text/plain` for
backward compatibility.

## Convertible Formats (via Gotenberg)

Everything outside the core formats above — legacy Microsoft Office, Apple
iWork, OpenDocument, WordPerfect, raster/vector images, HTML, and more — has
**no native parser**. These formats can instead be uploaded once an
administrator enables a **file converter**: an optional pre-parse step that
turns the upload into a PDF, which then flows through the normal PDF
pipeline (Docling parsing, thumbnailing, embedding) like any other PDF.

**This is off by default.** A fresh install accepts only the three core
formats above until a converter is configured — see
[Enabling/Disabling Gotenberg Conversion](../pipelines/pipeline_configuration.md#file-converters-gotenberg)
for the walkthrough.

OpenContracts ships one converter implementation, `GotenbergFileConverter`,
which delegates to a [Gotenberg](https://github.com/gotenberg/gotenberg)
service's LibreOffice conversion route. Gotenberg runs LibreOffice in its own
container, so the full LibreOffice import-filter catalogue is available
without bundling LibreOffice into the Django image. As of this writing it
covers **126 file extensions**, grouped roughly as:

| Category | Examples |
|----------|----------|
| Legacy Microsoft Office | `.doc`, `.dot`, `.ppt`, `.pps`, `.xls`, `.xlw` |
| Office Open XML (non-`.docx`) | `.pptx`, `.xlsx`, `.dotx`, `.potx`, `.xltx` |
| OpenDocument Format | `.odt`, `.ods`, `.odp`, `.odg`, `.fodt`, `.fods` |
| StarOffice / OpenOffice legacy | `.sxw`, `.sxc`, `.sxi`, `.sdw`, `.std` |
| Apple iWork | `.key`, `.numbers`, `.pages` |
| WordPerfect & other word processors | `.wpd`, `.abw`, `.hwp`, `.lwp` |
| Legacy spreadsheets | `123`, `.wk1`, `.wks`, `.dif`, `.dbf` |
| Raster & vector images | `.bmp`, `.gif`, `.jpg`, `.png`, `.tiff`, `.svg`, `.psd` |
| CAD & vector graphics | `.cdr`, `.cgm`, `.dxf`, `.eps`, `.wmf`, `.emf` |
| Web & markup | `.htm`, `.html`, `.xhtml`, `.xml` |
| Other | `.csv`, `.epub`, `.pub`, `.vsd`, `.rtf` |

This table is illustrative, not exhaustive. For the definitive, always-current
list see `GOTENBERG_SUPPORTED_EXTENSIONS` in
[`gotenberg_converter.py`](../../opencontractserver/pipeline/file_converters/gotenberg_converter.py),
or query it live via GraphQL (see
[Dynamic Format Discovery](#dynamic-format-discovery) below) — the frontend
upload dropzone reads the same query to build its accepted-file list.

Natively parsed formats (`pdf`, `txt`, `docx`, `md`) are always excluded from
conversion, even though `.docx` happens to sit outside the list above already
— `.doc` converts to PDF, but `.docx` keeps its native `DocxodusServiceParser`
path.

### How Conversion Fits Into the Pipeline

1. A convertible upload is stored with `file_type = application/octet-stream`
   (never a browser-renderable MIME type) until conversion succeeds.
2. `convert_document_to_pdf` runs at the head of the ingest chain, before
   thumbnailing and parsing, converting the file to PDF via the configured
   converter.
3. The original upload is preserved on `Document.original_file` /
   `Document.original_file_type` — nothing is discarded.
4. Once converted, `file_type` flips to `application/pdf` and the document
   proceeds through the ordinary PDF parser → thumbnailer → embedder stages.

If conversion fails, the document is marked FAILED and the ingest chain
halts, the same failure contract as a parser error.

For the full architecture (extension-keyed eligibility, failure semantics,
and the SSRF/stored-content security posture of running a LibreOffice-backed
service), see
[File Converters](../pipelines/pipeline_overview.md#file-converters) in the
Pipeline Architecture doc. For step-by-step instructions — including
screenshots — on turning conversion on or off, see
[File Converters (Gotenberg)](../pipelines/pipeline_configuration.md#file-converters-gotenberg)
in the Pipeline Configuration guide.

## Parser Details

### DoclingParser (PDF)

The default parser for PDFs uses the Docling ML microservice for advanced
layout extraction:

- Extracts text tokens with bounding boxes (PAWLs format)
- Detects document structure (headings, sections, tables, figures)
- Creates structural annotations automatically
- Supports automatic chunking for large PDFs
- Handles both OCR'd and non-OCR'd PDFs (performs its own OCR)
- Optional image extraction

### LlamaParseParser (PDF)

An alternative PDF parser using the LlamaParse cloud API:

- Supports 17 element types (Title, Section Header, Heading, Text Block, Table,
  Figure, Image, List, etc.)
- Multimodal support for complex layouts
- Requires a `LLAMAPARSE_API_KEY` environment variable

### TxtParser (Plain Text)

A simple parser for text files:

- Splits text into sentences using spaCy NLP
- Creates `SPAN_LABEL` annotations for each sentence
- Documents are treated as single-page (no PAWLs data)

### DocxodusServiceParser (Word)

Handles Word documents via the Docxodus microservice:

- Character-offset based annotations (aligned with WASM frontend rendering)
- Extracts structural layout from Word formatting
- Max file size: 50MB (before base64 encoding)

## Dynamic Format Discovery

The set of supported formats is not hardcoded on the frontend. The backend
exposes two GraphQL queries the frontend uses to build its accepted-upload
list:

- `supportedMimeTypes` -- returns the currently registered **core** formats
  along with their pipeline coverage:
  - Whether a parser is available
  - Whether an embedder is available
  - Whether a thumbnailer is available
  - Whether the format is "fully supported" (all three stages covered)
- `convertibleExtensions` -- returns the extension list the currently
  configured file converter accepts (empty if no converter is configured).
  The upload dropzone (`UploadModal`) unions this with the core formats and
  summarizes it as "+N convertible formats" rather than listing every
  extension.

This means that adding a new parser for a new file type, or enabling a file
converter, automatically makes it available in the upload UI without
frontend changes.

## Processing Pipeline

Every uploaded document goes through the same core stages:

1. **Conversion** (optional, convertible formats only) -- If a file converter
   is configured and the upload's extension is in its enabled set, the file
   is converted to PDF before the stages below run. See
   [Convertible Formats](#convertible-formats-via-gotenberg) above.
2. **Parsing** -- Extracts text, tokens, bounding boxes, and structural
   annotations
3. **Thumbnail generation** -- Creates a visual preview image
4. **Embedding** -- Generates vector embeddings for semantic search

Documents are not available for viewing or annotation until parsing completes.
A loading indicator is shown on the document card during processing.

For full pipeline architecture details, see the
[Pipeline Overview](../pipelines/pipeline_overview.md).
