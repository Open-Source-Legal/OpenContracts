![OpenContracts](assets/images/logos/OS_Legal_Logo.png)

# Open Contracts

## The Free and Open Source Document Analytics Platform

---

| |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| --- |--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| CI/CD | [![codecov](https://codecov.io/gh/JSv4/OpenContracts/branch/main/graph/badge.svg?token=RdVsiuaTVz)](https://codecov.io/gh/JSv4/OpenContracts)                                                                                                                                                                                                                                                                                                                  |
| Meta | [![code style - black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black) [![types - Mypy](https://img.shields.io/badge/types-Mypy-blue.svg)](https://github.com/python/mypy) [![imports - isort](https://img.shields.io/badge/imports-isort-ef8336.svg)](https://github.com/pycqa/isort) [![License - MIT](https://img.shields.io/badge/license-MIT-green)](https://opensource.org/licenses/MIT) |

## What Does it Do?

OpenContracts is an **MIT Licensed** enterprise document analytics tool. It provides several key features:

1. **Manage Documents** - Manage document collections (`Corpuses`)
2. **Custom Metadata Schemas** - Define structured metadata fields with validation for consistent data collection
3. **Layout Parser** - Automatically extracts layout features from PDFs
4. **Automatic Vector Embeddings** - generated for uploaded PDFs and extracted layout blocks
5. **Pluggable microservice analyzer architecture** - to let you analyze documents and automatically annotate them
6. **Human Annotation Interface** - to manually annotated documents, including multi-page annotations.
7. **Data Extract** - ask multiple questions across hundreds of documents using complex LLM-powered querying behavior.
   Our sample implementation uses our battle-tested agent framework for precise data extraction and natural language querying.
8. **Custom Data Extract** - Custom data extract pipelines can be used on the frontend to query documents in bulk.

![Grid Review And Sources.gif](assets/images/gifs/Grid_Review_And_Sources.gif)

![Manual Annotations](assets/images/screenshots/Jumped_To_Annotation.png)

## Key Docs

1. [Quickstart Guide](quick_start.md) - You'll probably want to get started quickly. Setting up locally should be
   pretty painless if you're already running Docker.
2. [Basic Walkthrough](walkthrough/key-concepts.md) - Check out the walkthrough to step through basic usage of the
   application for document and annotation management.
3. [Metadata System](metadata/metadata_overview.md) - Learn how to define custom metadata schemas for your documents
   with comprehensive validation and type safety.
4. [PDF Annotation Data Format Overview](architecture/PDF-data-layer.md) - You may be interested how we map text to
   PDFs visually and the underlying data format we're using.
5. [Vector Store Architecture](extract_and_retrieval/vector_stores.md)
   We've used the latest open source tooling for vector storage in postgres to make it almost trivially easy to
   combine structured metadata and vector embeddings with an API-powered application.
6. [Write Custom Data Extractors](walkthrough/advanced/write-your-own-extractors.md) - Custom data extract tasks are
   automatically loaded and displayed on the frontend to let users select how to ask questions and extract data from documents.

## Architecture and Data Flows at a Glance

### Core Data Standard

The core idea here - besides providing a platform to analyze contracts - is an open and standardized architecture that
makes data extremely portable. Powering this is a set of data standards to describe the text and layout blocks on a PDF
page:

![Data Format](assets/images/diagrams/pawls-annotation-mapping.svg)

### Robust PDF Processing Pipeline

We have a robust PDF processing pipeline that is horizontally scalable and generates our standardized data
consistently for PDF inputs (We're working on adding additional formats soon):

![PDF Processor](assets/images/diagrams/PDF-processor-sequence-diagram.png)

Special thanks to Nlmatics and [nlm-ingestor](https://github.com/nlmatics/nlm-ingestor) for powering the layout parsing
and extraction.

## Limitations

At the moment, it only works with PDFs. In the future, it will be able to convert other document types to PDF for
storage and labeling. PDF is an excellent format for this as it introduces a consistent, repeatable format which we can
use to generate a text and x-y coordinate layer from scratch.

**Adding OCR and ingestion for other enterprise documents is a priority**.

## Acknowledgements

Special thanks to AllenAI's [PAWLS project](https://github.com/allenai/pawls) and Nlmatics
[nlm-ingestor](https://github.com/nlmatics/nlm-ingestor). They've pioneered a number of features and flows, and we are
using their code in some parts of the application.
