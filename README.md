![OpenContracts](docs/assets/images/logos/OS_Legal_Logo.png)

# OpenContracts ([Demo](https://contracts.opensource.legal))

The open source platform for building knowledge bases that humans and AI agents can work with together.

[![Sponsor](https://img.shields.io/static/v1?label=Sponsor&message=%E2%9D%A4&logo=GitHub&color=%23fe8e86)](https://github.com/sponsors/JSv4)

| | |
|---|---|
| Backend CI/CD | [![codecov](https://codecov.io/gh/Open-Source-Legal/OpenContracts/branch/main/graph/badge.svg?token=RdVsiuaTVz)](https://app.codecov.io/gh/open-source-legal/OpenContracts) |
| Meta | [![code style - black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black) [![types - Mypy](https://img.shields.io/badge/types-Mypy-blue.svg)](https://github.com/python/mypy) [![imports - isort](https://img.shields.io/badge/imports-isort-ef8336.svg)](https://github.com/pycqa/isort) [![License - AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-blue)](https://www.gnu.org/licenses/agpl-3.0) |

---

![Discovery Landing Page](docs/assets/images/screenshots/auto/landing--discovery-page--anonymous.png)

Most knowledge lives in documents. Contracts, regulations, research papers, policies — the stuff that governs how organizations actually work. That knowledge is usually trapped: locked in PDFs, scattered across drives, understood fully by a handful of people who happened to read the right things at the right time.

OpenContracts started in 2019 with a simple conviction: that knowledge needed to be carefully curated, and that machine learning systems were only as good as the data underneath them. It was built as a platform for human collaborators — lawyers, researchers, analysts — to annotate documents together and produce gold-standard training data.

Those collaborators mostly never came. The platform was too early, the problem too niche, the value too invisible.

Then large language models arrived, and the world suddenly needed exactly what OpenContracts had been building all along: structured, annotated, version-controlled knowledge bases that AI could actually reason over. The collaborators the platform was designed for finally showed up — they just turned out to be AI agents.

Today, OpenContracts is a self-hosted platform where teams build knowledge bases from their documents and where AI agents work alongside humans to search, analyze, and extend that knowledge. The core conviction hasn't changed. The best AI systems still need carefully curated data. The difference is that now, the curation and the AI happen in the same place.

<table>
<tr>
<td align="center" width="33%">
<br>
<img src="docs/assets/images/icons/agents.svg" width="48" height="48" alt="AI Agents">
<br>
<h4>AI Agents</h4>
<p>Configurable assistants that search, annotate, and reason over your knowledge base</p>
</td>
<td align="center" width="33%">
<br>
<img src="docs/assets/images/icons/mcp.svg" width="48" height="48" alt="MCP Server">
<br>
<h4>MCP Server</h4>
<p>Expose your corpus to Claude, Cursor, and any MCP-compatible AI tool</p>
</td>
<td align="center" width="33%">
<br>
<img src="docs/assets/images/icons/search.svg" width="48" height="48" alt="Multimodal Search">
<br>
<h4>Multimodal Search</h4>
<p>Vector embeddings and full-text search across documents and annotations</p>
</td>
</tr>
<tr>
<td align="center" width="33%">
<br>
<img src="docs/assets/images/icons/collaboration.svg" width="48" height="48" alt="Collaboration">
<br>
<h4>Collaboration</h4>
<p>Threaded discussions, @mentions, voting, and moderation at every level</p>
</td>
<td align="center" width="33%">
<br>
<img src="docs/assets/images/icons/extract.svg" width="48" height="48" alt="Data Extract">
<br>
<h4>Data Extract</h4>
<p>Structured extraction across hundreds of documents with LLM-powered queries</p>
</td>
<td align="center" width="33%">
<br>
<img src="docs/assets/images/icons/format.svg" width="48" height="48" alt="Format Preservation">
<br>
<h4>Format Preservation</h4>
<p>PDF layout fidelity with precise text-to-coordinate mapping via PAWLS</p>
</td>
</tr>
</table>

---

## What Makes This Different

### Human Knowledge as the Foundation

This is not another "chat with your PDFs" tool. OpenContracts treats human annotation as the ground truth. Teams define custom label schemas, annotate documents with precise selections (including multi-page spans), and map relationships between concepts. AI builds on top of that work — it doesn't replace it.

![Document Annotator](docs/assets/images/screenshots/auto/readme--document-annotator--with-pdf.png)

### Knowledge Bases, Not File Cabinets

Documents are organized into corpuses — version-controlled collections with folder hierarchies, fine-grained permissions, and full history. Fork a public corpus to build on someone else's annotations. Restore any previous version. Every change is tracked.

This is `git` for knowledge: you can branch, build, share, and never lose work.

![Corpus Home](docs/assets/images/screenshots/auto/readme--corpus-home--with-chat.png)

### AI Agents That Work With What You've Built

Configurable AI agents can search your documents, query your annotations, and participate in discussions — all grounded in the structured knowledge your team has created. They don't hallucinate in a vacuum; they reason over real, curated data.

@mention an agent in a discussion thread. Ask it to compare clauses across a hundred contracts. Let it surface patterns your team annotated last quarter. The agent's power comes from the quality of the knowledge base underneath it.

![AI Agent Response](docs/assets/images/screenshots/auto/threads--agent-message--response.png)

### Collaboration Where the Knowledge Lives

Forum-style threaded discussions at every level — global, per-corpus, per-document. @mention documents, corpuses, and AI agents. Upvote the best analysis. Pin critical findings. The conversation happens next to the source material, not in a separate tool.

![Discussion Threads](docs/assets/images/screenshots/auto/discussions--thread-list--with-threads.png)

### Shared Knowledge Compounds

Make a corpus public. Others fork it, refine the annotations, add documents, and share their improvements. Leaderboards and badges recognize contributors. Analytics show which knowledge bases are gaining traction and where the community is most active.

This is the DRY principle applied to institutional knowledge: annotate once, build on it forever.

![Analytics Dashboard](docs/assets/images/screenshots/auto/corpus--analytics--dashboard.png)

---

## See it in Action

### PDF Annotation Flow
![PDF Annotation Flow](docs/assets/images/gifs/PDF%20Annotation%20Flow.gif)

### Text Format Support
![Text Annotation Flow](docs/assets/images/gifs/Txt%20Annotation%20Flow.gif)

---

## Quick Start

### Development

```bash
git clone https://github.com/JSv4/OpenContracts.git
cd OpenContracts
docker compose -f local.yml up
```

### Production

```bash
# Apply database migrations first
docker compose -f production.yml --profile migrate up migrate

# Start services
docker compose -f production.yml up -d
```

---

## Documentation

Browse the full documentation at [jsv4.github.io/OpenContracts](https://jsv4.github.io/OpenContracts/) or in the repo:

| Guide | Description |
|-------|-------------|
| [Quick Start](docs/quick_start.md) | Get running with Docker in minutes |
| [Key Concepts](docs/walkthrough/key-concepts.md) | Core workflows and terminology |
| [PDF Data Format](docs/architecture/PDF-data-layer.md) | How text maps to PDF coordinates |
| [LLM Framework](docs/architecture/llms/README.md) | PydanticAI integration and agents |
| [Vector Stores](docs/extract_and_retrieval/vector_stores.md) | Semantic search architecture |
| [Pipeline Overview](docs/pipelines/pipeline_overview.md) | Parser and embedder system |
| [Custom Extractors](docs/walkthrough/advanced/write-your-own-extractors.md) | Build your own data extraction tasks |
| [v3.0.0.b3 Release Notes](docs/releases/v3.0.0.b3.md) | Latest features and migration guide |

---

<details>
<summary><strong>Architecture</strong></summary>

### Data Format

OpenContracts uses a standardized format for representing text and layout on PDF pages, enabling portable annotations across tools:

![Data Format](docs/assets/images/diagrams/pawls-annotation-mapping.svg)

### Processing Pipeline

The modular pipeline supports custom parsers, embedders, and thumbnail generators:

![Pipeline Diagram](docs/assets/images/diagrams/parser_pipeline.svg)

Each component inherits from a base class with a defined interface:
- **Parsers** — Extract text and structure from documents
- **Embedders** — Generate vector embeddings for search
- **Thumbnailers** — Create document previews

See the [pipeline documentation](docs/pipelines/pipeline_overview.md) for details on creating custom components.

</details>

---

## Telemetry

OpenContracts collects anonymous usage data to guide development priorities: installation events, feature usage statistics, and aggregate counts. We do not collect document contents, extracted data, user identities, or query contents.

**Disable backend telemetry**: Set `TELEMETRY_ENABLED=False` in your Django settings.
**Disable frontend analytics**: Leave `REACT_APP_POSTHOG_API_KEY` unset in `frontend/public/env-config.js`.

---

## Supported Formats

- PDF (full layout and annotation support)
- Text-based formats (plaintext, Markdown)

**Coming soon:** DOCX viewing and annotation powered by [Docxodus](https://github.com/JSv4/Docxodus).

---

## Acknowledgements

This project builds on work from:
- [AllenAI PAWLS](https://github.com/allenai/pawls) — PDF annotation data format and concepts
- [NLMatics nlm-ingestor](https://github.com/nlmatics/nlm-ingestor) — Document parsing pipeline

---

## License

AGPL-3.0 — See [LICENSE](LICENSE) for details.
