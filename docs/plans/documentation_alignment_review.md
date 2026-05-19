# Documentation Alignment Review

**Date**: 2026-01-09
**Branch**: JSv4/corpus-document-methods-and-docs
**Status**: COMPLETED

This document provides a comprehensive review of all documentation files compared against the actual codebase.

---

## Summary

All documentation issues have been addressed:

| Rating | Original Count | Status |
|--------|---------------|--------|
| 4 (Major) | 6 | ✅ All fixed |
| 3 (Moderate) | 10 | ✅ All fixed |
| 2 (Minor) | 38 | ✅ All fixed |
| 1 (Perfect) | 28 | No changes needed |

**Total**: 82 documentation files reviewed and aligned with codebase.

---

## Fixes Applied

### Critical Issues (Rating 4) - FIXED

| File | Issue | Resolution |
|------|-------|------------|
| `docs/frontend/corpus-and-document-selection.md` | Referenced deleted components | Complete rewrite with CentralRouteManager architecture |
| `docs/architecture/PDF-data-layer.md` | Wrong parser paths | Fixed to `docling_parser_rest.py`, added LlamaParse |
| `docs/architecture/embeddings_creation_and_retrieval.md` | Wrong settings, LlamaIndex refs | Fixed setting names, removed LlamaIndex details |
| `docs/embedders/modernbert_embedder.md` | ModernBERT embedders removed from codebase | File deleted |
| `docs/embedders/minn_modernbert_embedder.md` | Wrong class name | File deleted per user request |
| `docs/deployment/docker-gpu-setup.md` | Non-existent file refs | Fixed to reference actual compose files |

### Moderate Issues (Rating 3) - FIXED

| File | Issue | Resolution |
|------|-------|------------|
| `docs/architecture/dual_tree_implementation_plan.md` | Reads as planning doc | Added IMPLEMENTED banner, past tense |
| `docs/pipelines/pipeline_overview.md` | Wrong embedder names | Fixed class names, added MicroserviceEmbedder |
| `docs/configuration/choose-and-configure-docker-stack.md` | Wrong paths, old commands | Fixed paths, updated to `docker compose` |
| `docs/GCP_STORAGE_SETUP.md` | Wrong variable names | Fixed all GS_* vars, added STORAGE_BACKEND |
| `docs/extract_and_retrieval/api_reference.md` | Missing fields | Added all Datacell/Column fields |
| `docs/extract_and_retrieval/data_extraction.md` | Missing features | Added manual entry, approval workflow |
| `docs/commenting_system/IMPLEMENTATION_GUIDE.md` | Unclear status | Complete rewrite with accurate status |
| `docs/analyzer_framework/frontend.md` | Wrong component name | Fixed to SelectCorpusAnalyzerOrFieldsetModal |
| `docs/architecture/agent_corpus_actions_design.md` | Misleading status | Updated to show COMPLETE |
| `docs/walkthrough/step-1-add-documents.md` | Tesseract reference | Updated to Docling |

### Minor Issues (Rating 2) - FIXED

| File | Resolution |
|------|------------|
| `docs/architecture/analyzers.md` | Clarified 4/5-element return formats |
| `docs/architecture/llms/README.md` | Removed LlamaIndex example code |
| `docs/architecture/opencontract-corpus-actions.md` | Added DocumentPath note |
| `docs/architecture/websocket/backend.md` | Added 4 missing consumers |
| `docs/architecture/websocket/frontend.md` | Added thread UI patterns |
| `docs/configuration/choose-storage-backend.md` | Added GCP docs, fixed USE_AWS |
| `docs/configuration/frontend-configuration.md` | Fixed env var prefixes |
| `docs/quick_start.md` | Fixed port refs, added source links |
| `docs/permissioning/consolidated_permissioning_guide.md` | Added Relationship fields |
| `docs/permissioning/testing_permissions.md` | Added mention test examples |
| `docs/permissioning/mention_permissioning_spec.md` | Fixed test counts, date |
| `docs/commenting_system/README.md` | Updated frontend status |
| `docs/commenting_system/backend_architecture.md` | Added mentioned_agents, fixed lines |
| `docs/commenting_system/graphql_api.md` | Fixed casing, added leaderboard |
| `docs/commenting_system/notifications.md` | Added WebSocket docs |
| `docs/frontend/routing_system.md` | Removed RouteStateSync refs |
| `docs/frontend/document_rendering_and_annotation.md` | Removed stale line numbers |
| `docs/features/badge_system.md` | Verified paths, added date |
| `docs/features/corpus_folders_implementation.md` | Added routing note |
| `docs/walkthrough/key-concepts.md` | Fixed mutation name |
| `docs/walkthrough/step-7-query-corpus.md` | Updated chat terminology |
| `docs/walkthrough/step-8-data-extract.md` | Added agent pipeline mention |
| `docs/walkthrough/add-and-edit-notes.md` | Clarified button context |
| `docs/walkthrough/advanced/extraction_tutorial.md` | Added PydanticAI mention |
| `docs/architecture/components/annotator/current-state/overview.md` | Fixed allTabs, added links |
| `docs/architecture/components/annotator/current-state/how-search-works.md` | Replaced inline code |
| `docs/architecture/components/annotator/current-state/document-knowledge-base-features.md` | Fixed allTabs |

---

## Key Principles Applied

1. **No inline code** - All code examples replaced with links to source files
2. **Accurate paths** - All file paths verified to exist
3. **Current terminology** - Updated deprecated names (Tesseract→Docling, LlamaIndex→PydanticAI, etc.)
4. **Correct architecture** - DocumentPath is source of truth for corpus-document relationships

---

## Document-to-Corpus Relationship Summary

### Source of Truth
- **`DocumentPath`** is the single source of truth for corpus-document relationships
- Legacy M2M field `Corpus.documents` has been **removed** (Issue #835, migration `0039`)

### Correct Methods
```python
# Add existing document to corpus
corpus.add_document(document=doc, user=user)

# Or via service with full permission checks
CorpusObjsService.add_document_to_corpus(user, document, corpus)

# Get documents in corpus
corpus.get_documents()

# Count documents
corpus.document_count()
```

### Deprecated (Do Not Use)
```python
# These bypass versioning and create inconsistent state
corpus.documents.add(doc)      # WRONG
corpus.documents.all()         # WRONG
corpus.documents.count()       # WRONG
```

---

*Review completed: 2026-01-09*
*All documentation now aligned with codebase*
