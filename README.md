![OpenContracts](docs/assets/images/logos/OS_Legal_Logo.png)

# Open Contracts ([Demo](https://contracts.opensource.legal))
## The Free and Open Source Document Analytics Platform [![](https://img.shields.io/static/v1?label=Sponsor&message=%E2%9D%A4&logo=GitHub&color=%23fe8e86)](https://github.com/sponsors/JSv4)

---
| |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| --- |--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Backend CI/CD | [![codecov](https://codecov.io/gh/Open-Source-Legal/OpenContracts/branch/main/graph/badge.svg?token=RdVsiuaTVz)](https://codecov.io/gh/JSv4/OpenContracts)                                                                                                                                                                                                                                                                                                                  |
| Meta | [![code style - black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black) [![types - Mypy](https://img.shields.io/badge/types-Mypy-blue.svg)](https://github.com/python/mypy) [![imports - isort](https://img.shields.io/badge/imports-isort-ef8336.svg)](https://github.com/pycqa/isort) [![License - Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue)](https://www.apache.org/licenses/LICENSE-2.0) |

## TLDR: What Does it Do?

**Knowledge is power. Software is a tool.** OpenContracts is **FREE and OPEN SOURCE** software designed to put knowledge owners and subject matter experts in charge of their knowledge. Store it in an accessible and exportable format, and make it work with emerging agentic workflows and techniques.

OpenContracts is an **Apache 2.0** licensed enterprise document analytics tool. It supports multiple formats - including PDF and txt-based formats (with more on the way). It also supports multiple document ingestion pipelines with a [pluggable architecture](docs/pipelines/pipeline_overview.md) designed to make supporting new formats and ingestion engines easy - see our [Docling Integration](docs/pipelines/docling_parser.md) for an example. Writing your own custom document analytics tools where the results get displayed beautifully over the original document [is easy](docs/walkthrough/advanced/register-doc-analyzer.md). We also support mass document [data extraction](docs/extract_and_retrieval/data_extraction.md) with our custom [LLM framework](docs/architecture/llms/README.md) built on PydanticAI.

## Telemetry (as of v3.0.0-alpha2)

OpenContracts collects anonymous usage data to help improve the platform. We only collect:
- Installation events (unique installation ID per first DB initialization)
- Feature usage statistics (e.g., analyzer activations, post-processor runs)
- **Aggregate** usage (documents uploaded, total queries, total extracts, users served, etc.)

We **never** collect:
- Document contents
- Extracted data
- Identifiable user information
- Query contents

This data helps us understand which features are most valuable and prioritize development. Telemetry can be disabled by setting `TELEMETRY_ENABLED=False` in your settings.

### PDF-Annotation and Analysis:

![PDF Processing](/docs/assets/images/gifs/PDF%20Annotation%20Flow.gif)

### TXT-Based Format Annotation and Analysis:

![Txt Processing](/docs/assets/images/gifs/Txt%20Annotation%20Flow.gif)

### Data Extract:

![Data Grid](docs/assets/images/screenshots/data_grid_image.png)

### Rapidly Deployable Bespoke Analytics

![Analyzer Annotations](docs/assets/images/screenshots/Analyzer_Annotations.png)

### [DEVELOPING] Document Management

![Corpus Dashboard](docs/assets/images/screenshots/corpus_dashboard.png)

## Ok, now tell me more. What Does it Do?

OpenContracts provides several key features:

1. **Document Management** - Organize documents into collections (`Corpuses`) with fine-grained permissions
2. **Custom Metadata Schemas** - Define structured metadata fields with validation for consistent data collection
3. **Layout Parser** - Automatically extracts layout features from PDFs using modern parsing pipelines
4. **Automatic Vector Embeddings** - Generated for uploaded documents and extracted layout blocks (powered by pgvector)
5. **Pluggable Analyzer Architecture** - Deploy custom microservices to analyze documents and automatically annotate them
6. **Pluggable Parsing Pipelines** - Support new document formats with modular parsers (Docling, NLM-Ingest, etc.)
7. **Human Annotation Interface** - Manually annotate documents with multi-page annotations and collaborative features
8. **Custom LLM Framework** - Built on PydanticAI with conversation management, structured responses, and real-time streaming
9. **Bulk Data Extract** - Ask multiple questions across hundreds of documents using our agent-powered querying system
10. **Custom Extract Pipelines** - Create bespoke data extraction workflows displayed directly in the frontend

## Key Docs

We recommend you [browse our docs](https://jsv4.github.io/OpenContracts/) via our Mkdocs Site. You can also view the 
docs in the repo:

1. [Quickstart Guide](docs/quick_start.md) - You'll probably want to get started quickly. Setting up locally should be
   pretty painless if you're already running Docker.
2. [Basic Walkthrough](docs/walkthrough/key-concepts.md) - Check out the walkthrough to step through basic usage of the
   application for document and annotation management.
3. [Metadata System](docs/metadata/metadata_overview.md) - Learn how to define custom metadata schemas for your documents
   with comprehensive validation and type safety.
4. [PDF Annotation Data Format Overview](docs/architecture/PDF-data-layer.md) - You may be interested how we map text to
   PDFs visually and the underlying data format we're using.
5. [Custom LLM Framework](docs/architecture/llms/README.md) - Our PydanticAI-based framework provides 
   document and corpus agents with conversation management, structured responses, and real-time event streaming.
6. [Vector Store Architecture](docs/extract_and_retrieval/vector_stores.md) -
   We've used the latest open source tooling for vector storage in postgres to make it almost trivially easy to
   combine structured metadata and vector embeddings with our LLM agents.
7. [Write Custom Data Extractors](docs/walkthrough/advanced/write-your-own-extractors.md) - Custom data extract tasks are
   automatically loaded and displayed on the frontend to let users select how to ask questions and extract data from documents.

## Architecture and Data Flows at a Glance

### Core Data Standard

The core idea here - besides providing a platform to analyze contracts - is an open and standardized architecture that
makes data extremely portable. Powering this is a set of data standards to describe the text and layout blocks on a PDF
page:

![Data Format](docs/assets/images/diagrams/pawls-annotation-mapping.svg)

### Modern, Pluggable Document Processing Pipeline

OpenContracts features a powerful, modular pipeline system for processing documents. The architecture supports easy creation and integration of custom parsers, embedders, and thumbnail generators:

![parser pipeline diagram](docs/assets/images/diagrams/parser_pipeline.svg)

Each pipeline component inherits from a base class that defines a clear interface:
- **Parsers**: Extract text and structure from documents
- **Embedders**: Generate vector embeddings for semantic search
- **Thumbnailers**: Create visual previews of documents

Learn more about:
- [Pipeline Architecture Overview](docs/pipelines/pipeline_overview.md)
- [Docling Parser](docs/pipelines/docling_parser.md)
- [NLM-Ingest Parser](docs/pipelines/nlm_ingest_parser.md)

The modular design makes it easy to add custom processors - just inherit from the appropriate base class and implement the required methods. See our [pipeline documentation](docs/pipelines/pipeline_overview.md#creating-new-components) for details on creating your own components.

## Limitations

At the moment, we only support PDF and text-based formats (like plaintext and MD). With our new parsing pipeline, we can easily support other ooxml office formats like docx and xlsx, HOWEVER, open source viewers and editors are a rarity. One possible route is to leverage the many ooxml --> MD tools that now exist. This will be a reasonably good solution for the majority of documents once we add a markdown viewer and annotator (see our roadmap). 

## Production Deployment

For production deployments, OpenContracts includes a dedicated migration service to ensure database schema updates are applied correctly and efficiently:

### Database Migrations

Before starting production services, run database migrations using the dedicated migration service:

```bash
# Run migrations first
docker compose -f production.yml --profile migrate up migrate

# Then start main services  
docker compose -f production.yml up
```

The migration service:
- Runs exactly once to avoid race conditions
- Uses Docker Compose profiles for isolation
- Only depends on PostgreSQL, not other services
- Ensures django_celery_beat and other app tables are created before dependent services start

This prevents issues like celerybeat failing due to missing database tables.

## Acknowledgements

Special thanks to AllenAI's [PAWLS project](https://github.com/allenai/pawls) and Nlmatics
[nlm-ingestor](https://github.com/nlmatics/nlm-ingestor). They've pioneered a number of features and flows, and we are
using their code in some parts of the application.

NLmatics was also the creator of and inspiration for our data extract grid and parsing pipeline UI/UX:

![nlmatics_data_grid](docs/assets/images/screenshots/nlmatics_datagrid.png)

The company was ahead of its time, and, while the product is no longer available, OpenContracts aims to take some of its [best and most innovative features](https://youtu.be/lX9lynpQwFA) and make them open source and available to the masses!
