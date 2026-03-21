# Supported File Formats

OpenContracts accepts several document formats for upload. Each format is routed
to a specific parser that extracts text, structure, and layout information.

## Core Formats

| Format | Extension | MIME Type | Default Parser |
|--------|-----------|-----------|----------------|
| PDF | `.pdf` | `application/pdf` | DoclingParser (ML-based REST microservice) |
| Plain Text | `.txt` | `text/plain` | TxtParser (sentence-level splitting via spaCy) |
| Word | `.docx` | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | DocxodusServiceParser (REST microservice) |

These are the formats registered in the pipeline's `FileTypeEnum` and are
available for both single uploads and bulk imports.

### Legacy MIME Aliases

The system also accepts `application/txt` as an alias for `text/plain` for
backward compatibility.

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
exposes a `supportedMimeTypes` GraphQL query that returns the currently
registered formats along with their pipeline coverage:

- Whether a parser is available
- Whether an embedder is available
- Whether a thumbnailer is available
- Whether the format is "fully supported" (all three stages covered)

This means that adding a new parser for a new file type automatically makes it
available in the upload UI without frontend changes.

## Processing Pipeline

Every uploaded document goes through a three-stage pipeline:

1. **Parsing** -- Extracts text, tokens, bounding boxes, and structural
   annotations
2. **Thumbnail generation** -- Creates a visual preview image
3. **Embedding** -- Generates vector embeddings for semantic search

Documents are not available for viewing or annotation until parsing completes.
A loading indicator is shown on the document card during processing.

For full pipeline architecture details, see the
[Pipeline Overview](../pipelines/pipeline_overview.md).
