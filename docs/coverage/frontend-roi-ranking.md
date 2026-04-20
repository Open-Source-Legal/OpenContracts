# Frontend Coverage ROI Audit (main)

Ranked list of files by uncovered line count — the biggest per-file wins if tested.
Source: Codecov project-level report (union of frontend-unit + frontend-component + frontend-e2e flags).

## Coverage by area

| Area | Files | Lines | Hits | Coverage | Uncovered |
|---|---:|---:|---:|---:|---:|
| `components` | 381 | 71058 | 26901 | 37.9% | 44157 |
| `views` | 13 | 5453 | 1714 | 31.4% | 3739 |
| `hooks` | 14 | 1698 | 675 | 39.8% | 1023 |
| `utils` | 28 | 3261 | 2844 | 87.2% | 417 |
| `App.tsx` | 1 | 415 | 59 | 14.2% | 356 |
| `routing` | 1 | 972 | 731 | 75.2% | 241 |
| `services` | 2 | 1016 | 806 | 79.3% | 210 |
| `assets` | 4 | 780 | 683 | 87.6% | 97 |
| `index.tsx` | 1 | 106 | 20 | 18.9% | 86 |
| `test-utils` | 1 | 74 | 0 | 0.0% | 74 |
| `types` | 9 | 248 | 188 | 75.8% | 60 |
| `theme` | 6 | 216 | 157 | 72.7% | 59 |
| `graphql` | 10 | 1129 | 1096 | 97.1% | 33 |
| `reportWebVitals.ts` | 1 | 13 | 2 | 15.4% | 11 |

## Top 50 highest-ROI files (most uncovered lines)

Testing any of these yields disproportionate coverage gain. Each line here is currently uncovered across unit + component + E2E tests combined.

| Rank | File | Lines | Coverage | Uncovered |
|---:|---|---:|---:|---:|
| 1 | `components/knowledge_base/document/DocumentKnowledgeBase.tsx` | 1961 | 25.5% | **1460** |
| 2 | `components/knowledge_base/document/right_tray/ChatTray.tsx` | 1417 | 25.3% | **1059** |
| 3 | `components/corpuses/CorpusChat.tsx` | 1079 | 10.7% | **964** |
| 4 | `views/Corpuses.tsx` | 1890 | 56.2% | **827** |
| 5 | `views/Documents.tsx` | 994 | 18.9% | **806** |
| 6 | `components/widgets/modals/SelectCorpusAnalyzerOrFieldsetAnalyzer.tsx` | 858 | 11.1% | **763** |
| 7 | `components/corpuses/CreateCorpusActionModal.tsx` | 939 | 19.8% | **753** |
| 8 | `components/labelsets/LabelSetDetailPage.tsx` | 793 | 12.2% | **696** |
| 9 | `components/documents/DocumentRelationshipModal.tsx` | 860 | 21.2% | **678** |
| 10 | `components/admin/SystemSettings.tsx` | 772 | 17.9% | **634** |
| 11 | `components/corpuses/CorpusAgentManagement.tsx` | 779 | 19.0% | **631** |
| 12 | `hooks/useAgentChat.ts` | 691 | 11.0% | **615** |
| 13 | `components/extracts/datagrid/DataGrid.tsx` | 888 | 32.5% | **599** |
| 14 | `components/documents/ModernDocumentItem.tsx` | 848 | 32.5% | **572** |
| 15 | `views/ExtractDetail.tsx` | 580 | 7.1% | **539** |
| 16 | `components/widgets/icon-picker/icons.ts` | 517 | 1.2% | **511** |
| 17 | `components/widgets/chat/ChatMessage.tsx` | 991 | 50.0% | **495** |
| 18 | `components/annotator/renderers/docx/DocxAnnotator.tsx` | 672 | 26.5% | **494** |
| 19 | `components/annotator/hooks/AnnotationHooks.tsx` | 685 | 30.6% | **475** |
| 20 | `components/knowledge_base/document/unified_feed/RelationshipActionModal.tsx` | 549 | 16.2% | **460** |
| 21 | `components/annotator/labels/EnhancedLabelSelector.tsx` | 640 | 30.1% | **447** |
| 22 | `components/corpuses/CorpusDescriptionEditor.tsx` | 541 | 20.1% | **432** |
| 23 | `components/knowledge_base/document/unified_feed/UnifiedContentFeed.tsx` | 577 | 29.8% | **405** |
| 24 | `components/admin/PipelineIcons.tsx` | 415 | 5.1% | **394** |
| 25 | `components/extracts/ExtractDetailContent.tsx` | 508 | 23.0% | **391** |
| 26 | `components/widgets/modals/FieldsetModal.tsx` | 557 | 30.9% | **385** |
| 27 | `components/admin/GlobalAgentManagement.tsx` | 418 | 8.8% | **381** |
| 28 | `components/annotator/renderers/txt/TxtAnnotator.tsx` | 871 | 57.6% | **369** |
| 29 | `views/Annotations.tsx` | 461 | 21.0% | **364** |
| 30 | `components/moderation/ModerationDashboard.tsx` | 501 | 27.5% | **363** |
| 31 | `components/widgets/modals/UploadModal/UploadModal.tsx` | 467 | 22.3% | **363** |
| 32 | `components/threads/MessageComposer.tsx` | 523 | 31.2% | **360** |
| 33 | `components/corpuses/folders/FolderDocumentBrowser.tsx` | 513 | 30.2% | **358** |
| 34 | `App.tsx` | 415 | 14.2% | **356** |
| 35 | `components/corpuses/folders/TrashFolderView.tsx` | 506 | 30.8% | **350** |
| 36 | `components/knowledge_base/document/FloatingDocumentControls.tsx` | 473 | 27.9% | **341** |
| 37 | `components/corpuses/DocumentTableOfContents.tsx` | 618 | 46.8% | **329** |
| 38 | `components/annotator/renderers/pdf/SelectionLayer.tsx` | 711 | 54.4% | **324** |
| 39 | `components/annotator/renderers/pdf/PDFPage.tsx` | 492 | 35.6% | **317** |
| 40 | `views/LabelSets.tsx` | 369 | 15.2% | **313** |
| 41 | `components/extracts/datagrid/ExtractCellFormatter.tsx` | 421 | 28.7% | **300** |
| 42 | `components/annotations/CorpusAnnotationCards.tsx` | 354 | 18.6% | **288** |
| 43 | `components/documents/DocumentMetadataGrid.tsx` | 445 | 36.6% | **282** |
| 44 | `components/threads/MessageItem.tsx` | 555 | 51.2% | **271** |
| 45 | `components/corpuses/DocumentAnnotationIndex.tsx` | 536 | 49.6% | **270** |
| 46 | `components/documents/DocumentItem.tsx` | 386 | 31.3% | **265** |
| 47 | `components/corpuses/settings/WorkerTokensSection.tsx` | 395 | 33.2% | **264** |
| 48 | `components/threads/hooks/useUnifiedMentionSearch.ts` | 298 | 11.4% | **264** |
| 49 | `components/documents/CorpusDocumentCards.tsx` | 325 | 19.1% | **263** |
| 50 | `views/Extracts.tsx` | 368 | 28.5% | **263** |

## Files at 0% coverage with >= 100 lines

Entire files with zero hits — prime candidates because the first test unlocks the full line count.

| File | Lines |
|---|---:|

## Methodology

- Data source: Codecov project-level API (merged across all three frontend flags)
- "Uncovered" = lines - hits, per Codecov merged report
- Ranking ignores files with <50 lines (noise)
- Numbers change on every merge; regenerate via the ranking script in this PR
