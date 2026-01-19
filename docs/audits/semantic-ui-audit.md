# Semantic UI Audit Report

**Date**: 2026-01-19
**Scope**: Full frontend codebase (`frontend/src/`)
**Total Files Using Semantic UI**: 179 files (180 import statements)

---

## Executive Summary

The OpenContracts frontend has extensive Semantic UI React integration across 179 files. This audit documents every component using Semantic UI, rates the refactoring difficulty (1-5 scale), and identifies whether each component is actively used.

### Key Findings

| Metric | Count |
|--------|-------|
| Files importing `semantic-ui-react` | 179 |
| Dead code files (unused) | 12 |
| Files using `@rjsf/semantic-ui` | 4 |
| Files already using `@os-legal/ui` | 34+ |

### Dependency Versions

```json
{
  "semantic-ui-css": "^2.4.1",
  "semantic-ui-react": "2.1.5",
  "@rjsf/semantic-ui": "^5.24.12"
}
```

### Global CSS Import

```typescript
// frontend/src/App.tsx (line 15)
import "semantic-ui-css/semantic.min.css";
```

---

## Difficulty Rating Scale

| Rating | Description | Typical Effort |
|--------|-------------|----------------|
| **1** | Trivial - Type imports only or 1:1 replacement exists | Hours |
| **2** | Easy - Isolated component, straightforward swap | 1 day |
| **3** | Moderate - Multiple SUI components, some custom styling | 2-3 days |
| **4** | Hard - Complex integration, custom behavior, state mgmt | 1 week |
| **5** | Very Hard - Deeply integrated, form logic, extensive redesign | 2+ weeks |

---

## Component Inventory by Category

### 1. TYPE IMPORTS ONLY (Rating: 1)

These files only import TypeScript types from Semantic UI.

| File | Imports | In Use? | Notes |
|------|---------|---------|-------|
| `src/types/graphql-api.ts` | `SemanticICONS` | Yes | GraphQL type definitions |
| `src/utils/layout.ts` | `SemanticWIDTHSNUMBER` | Yes | Layout utilities |
| `src/components/types.ts` | `SemanticICONS` | Yes | Component type defs |

**Refactor Strategy**: Replace with custom icon type union or use `lucide-react` icon names.

---

### 2. DEAD CODE - CAN BE DELETED (Rating: 0)

These components are defined but never imported anywhere in the codebase.

| File | Semantic Imports | Recommendation |
|------|------------------|----------------|
| `widgets/LoadingSpinner.tsx` | `Loader` | DELETE |
| `widgets/buttons/DocNavigation.tsx` | `Form` | DELETE |
| `widgets/data-display/LabelSetStatisticWidget.tsx` | `Icon`, `Popup`, `Statistic`, `Header` | DELETE |
| `widgets/selectors/PrimitiveTypeDropdown.tsx` | `Dropdown`, `DropdownProps` | DELETE |
| `widgets/model-filters/FilterToMetadataSelector.tsx` | `Menu`, `Label`, `Dropdown` | DELETE |
| `widgets/icon-picker/IconPickerModal.tsx` | `Modal`, `Button`, `Popup`, `Input` | DELETE |
| `common/CorpusRequiredEmptyState.tsx` | `Header`, `Icon`, `Button` | DELETE |
| `common/DropdownNoStrictMode.tsx` | `Dropdown`, `DropdownProps` | DELETE |

**Impact**: Removing these 8+ files eliminates ~10 Semantic UI imports with zero risk.

---

### 3. APP ROOT & LAYOUT (Rating: 3-4)

| File | Semantic Imports | In Use? | Rating | Notes |
|------|------------------|---------|--------|-------|
| `src/App.tsx` | `Container` | Yes | **3** | Main wrapper, easy swap |
| `layout/CardLayout.tsx` | `Segment` | Yes | **2** | Container styling |
| `layout/Footer.tsx` | Multiple | Yes | **3** | Footer with icons/links |
| `layout/CreateAndSearchBar.tsx` | Multiple | Yes | **4** | Complex search/create bar |

---

### 4. VIEWS (Main Pages) (Rating: 2-3)

| File | Semantic Imports | In Use? | Rating | Notes |
|------|------------------|---------|--------|-------|
| `views/Documents.tsx` | `Menu`, `Checkbox` | Yes | **2** | Already uses @os-legal/ui |
| `views/Corpuses.tsx` | `Tab`, `Menu` | Yes | **3** | Tabbed navigation |
| `views/UserProfile.tsx` | `Container`, `Button` | Yes | **2** | Simple layout |
| `views/TermsOfService.tsx` | `Container`, `Header`, `List` | Yes | **2** | Static content |
| `views/PrivacyPolicy.tsx` | `Container` | Yes | **1** | Wrapper only |

---

### 5. MODAL COMPONENTS (Rating: 3-5)

Modals are heavily used (29 instances). Core modal infrastructure requires careful migration.

#### Core Modal Infrastructure

| File | Semantic Imports | In Use? | Rating | Notes |
|------|------------------|---------|--------|-------|
| `widgets/modals/ConfirmModal.tsx` | `Modal`, `Button`, `Label`, `Icon`, `Header` | Yes | **4** | Used everywhere |
| `widgets/modals/ExportModal.tsx` | `Modal`, `Button`, `Icon`, `Header` | Yes | **3** | Export dialog |
| `widgets/modals/UploadModalStyles.ts` | `Modal`, `Button`, `Segment`, `List`, `Progress` | Yes | **4** | Styled upload |
| `widgets/modals/BulkUploadModal.tsx` | `Button`, `Form`, `Message`, `FormField`, `Icon` | Yes | **4** | Complex form |
| `widgets/modals/DocumentUploadModal.tsx` | `Icon`, `Header` + `@rjsf/semantic-ui` | Yes | **5** | RJSF integration |
| `widgets/modals/CreateExtractModal.tsx` | `Modal`, `Form` | Yes | **3** | Extract creation |
| `widgets/modals/SelectDocumentsModal.tsx` | Multiple | Yes | **4** | Document picker |
| `widgets/modals/SelectExportTypeModal.tsx` | Multiple + `@rjsf/semantic-ui` | Yes | **5** | RJSF integration |
| `widgets/modals/SelectCorpusAnalyzerOrFieldsetAnalyzer.tsx` | Multiple + `@rjsf/semantic-ui` | Yes | **5** | RJSF integration |

#### Modal Configuration Sections

| File | Semantic Imports | In Use? | Rating | Notes |
|------|------------------|---------|--------|-------|
| `widgets/modals/sections/BasicConfigSection.tsx` | `Grid` | Yes | **2** | Grid layout |
| `widgets/modals/sections/ExtractionConfigSection.tsx` | `Grid`, `Icon`, `Popup` | Yes | **3** | Help tooltips |
| `widgets/modals/sections/OutputTypeSection.tsx` | `Grid`, `Form` | Yes | **3** | Form controls |
| `widgets/modals/sections/AdvancedOptionsSection.tsx` | `Grid`, `Icon`, `Popup` | Yes | **3** | Complex options |

#### Folder Modals

| File | Semantic Imports | In Use? | Rating | Notes |
|------|------------------|---------|--------|-------|
| `corpuses/folders/CreateFolderModal.tsx` | `Modal`, `Form`, `Button`, `Message` | Yes | **3** | Folder creation |
| `corpuses/folders/EditFolderModal.tsx` | `Modal`, `Form`, `Button`, `Message` | Yes | **3** | Folder editing |
| `corpuses/folders/DeleteFolderModal.tsx` | `Modal`, `Button`, `Message` | Yes | **2** | Confirmation |
| `corpuses/folders/MoveFolderModal.tsx` | `Modal`, `Button`, `Message`, `Dropdown` | Yes | **3** | Folder move |

#### Other Modals

| File | Semantic Imports | In Use? | Rating | Notes |
|------|------------------|---------|--------|-------|
| `modals/UserSettingsModal.tsx` | `Modal`, `Header`, `Icon`, `Button`, `Form`, `Divider` | Yes | **4** | User settings |
| `modals/AddToCorpusModal.tsx` | Multiple | Yes | **3** | Corpus add dialog |
| `threads/EditMessageModal.tsx` | `Modal`, `Button` | Yes | **2** | Simple edit |
| `cookies/CookieConsent.tsx` | `List`, `Modal`, `Header`, `Icon`, `Button` | Yes | **3** | Legal consent |

---

### 6. DROPDOWN/SELECTOR COMPONENTS (Rating: 3-4)

Dropdowns are the second most complex integration after modals.

| File | Semantic Imports | In Use? | Rating | Notes |
|------|------------------|---------|--------|-------|
| `widgets/selectors/CorpusDropdown.tsx` | `Dropdown`, `DropdownProps` | Yes | **3** | Corpus selector |
| `widgets/selectors/FieldsetDropdown.tsx` | `Dropdown`, `DropdownProps` | Yes | **3** | Fieldset selector |
| `widgets/selectors/ExtractTaskDropdown.tsx` | `Dropdown`, `DropdownProps`, `Header` | Yes | **3** | Task selector |
| `widgets/icon-picker/IconDropdown.tsx` | `Dropdown` | Yes | **3** | Icon picker |
| `annotator/labels/view_labels_selector/ViewLabelSelector.tsx` | `Dropdown`, `DropdownProps` | Yes | **3** | Label view |
| `annotator/controls/AnnotationControls.tsx` | `Checkbox`, `CheckboxProps`, `Dropdown` | Yes | **4** | Complex controls |

---

### 7. FILTER COMPONENTS (Rating: 2-3)

| File | Semantic Imports | In Use? | Rating | Notes |
|------|------------------|---------|--------|-------|
| `widgets/model-filters/FilterToCorpusSelector.tsx` | `Label` | Yes | **2** | Simple label |
| `widgets/model-filters/FilterToLabelSelector.tsx` | `Label` | Yes | **2** | Simple label |
| `widgets/model-filters/FilterToLabelsetSelector.tsx` | `Label` | Yes | **2** | Simple label |
| `widgets/model-filters/FilterToAnalysesSelector.tsx` | `Label` | Yes | **2** | Simple label |
| `widgets/model-filters/FilterToCorpusActionOutputs.tsx` | `Checkbox`, `Menu`, `Label` | Yes | **3** | Complex filter |
| `widgets/model-filters/FilterStructuralAnnotations.tsx` | `Label` | Yes | **2** | Simple label |

---

### 8. CRUD COMPONENTS (Rating: 4-5)

| File | Semantic Imports | In Use? | Rating | Notes |
|------|------------------|---------|--------|-------|
| `widgets/CRUD/CRUDWidget.tsx` | `Header`, `Icon`, `Segment`, `Label`, `Grid` + `@rjsf/semantic-ui` | Yes | **5** | Core CRUD with RJSF |
| `widgets/CRUD/CRUDModal.tsx` | `Button`, `Modal`, `Icon`, `Header` | Yes | **4** | CRUD dialog |
| `widgets/CRUD/EmbedderSelector.tsx` | `Header`, `Segment`, `Dropdown`, `Message` | Yes | **3** | Embedder picker |
| `widgets/CRUD/LabelSetSelector.tsx` | `Header`, `Segment`, `Dropdown` | Yes | **3** | Label set picker |

---

### 9. ANNOTATOR COMPONENTS (Rating: 3-5)

The annotator is the most complex feature area.

#### Core Annotator

| File | Semantic Imports | In Use? | Rating | Notes |
|------|------------------|---------|--------|-------|
| `annotator/AnnotationSummary.tsx` | `Label`, `Card` | Yes | **3** | Summary display |
| `annotator/topbar/AnnotatorTopbar.tsx` | `Icon` | Yes | **2** | Icon only |
| `annotator/topbar/SelectedAnalysisCard.tsx` | `Card` | Yes | **2** | Card display |

#### Sidebar Components

| File | Semantic Imports | In Use? | Rating | Notes |
|------|------------------|---------|--------|-------|
| `annotator/sidebar/AnnotatorSidebar.tsx` | Multiple | Yes | **4** | Complex sidebar |
| `annotator/sidebar/HighlightItem.tsx` | `Label`, `Button`, `Popup`, `Icon` | Yes | **3** | Highlight display |
| `annotator/sidebar/RelationItem.tsx` | `Label`, `Card`, `Divider`, `List` | Yes | **3** | Relation display |
| `annotator/sidebar/RelationHighlightItem.tsx` | `List`, `Icon`, `Label`, `Button` | Yes | **3** | Relation highlight |
| `annotator/sidebar/LabelListItems.tsx` | `Card`, `Icon` | Yes | **2** | Label list |
| `annotator/sidebar/ModalityBadge.tsx` | `Label` | Yes | **2** | Simple badge |

#### Display Components

| File | Semantic Imports | In Use? | Rating | Notes |
|------|------------------|---------|--------|-------|
| `annotator/display/viewer/DocumentViewer.tsx` | `Menu` | Yes | **3** | Viewer menu |
| `annotator/display/components/ActionBar.tsx` | `Form`, `Icon`, `Popup`, `Menu`, `SemanticICONS` | Yes | **4** | Complex toolbar |
| `annotator/display/components/Containers.tsx` | `Icon` | Yes | **2** | Icons only |
| `annotator/display/components/RelationshipList.tsx` | `Card` | Yes | **2** | Card list |
| `annotator/display/components/Selection.tsx` | `Icon` | Yes | **2** | Icon only |

#### Label Components

| File | Semantic Imports | In Use? | Rating | Notes |
|------|------------------|---------|--------|-------|
| `annotator/labels/label_selector/LabelSelectorDialog.tsx` | Multiple | Yes | **4** | Label dialog |
| `annotator/labels/label_selector/LabelElements.tsx` | `Card`, `Icon`, `Popup`, `Header` | Yes | **3** | Label cards |
| `annotator/labels/doc_types/DocTypeLabels.tsx` | `Card`, `Icon`, `Popup`, `Header` | Yes | **3** | Doc type labels |
| `annotator/labels/doc_types/DocTypeLabelDisplay.tsx` | Multiple | Yes | **3** | Label display |
| `annotator/labels/doc_types/DocTypePopup.tsx` | `Button`, `Input`, `Icon` | Yes | **3** | Doc type editor |

#### Annotator Modals

| File | Semantic Imports | In Use? | Rating | Notes |
|------|------------------|---------|--------|-------|
| `annotator/components/modals/EditLabelModal.tsx` | Multiple | Yes | **4** | Label editor |
| `annotator/components/modals/RelationModal.tsx` | `Modal`, `Button`, `Label`, `Icon` | Yes | **3** | Relation editor |

#### Renderers

| File | Semantic Imports | In Use? | Rating | Notes |
|------|------------------|---------|--------|-------|
| `annotator/renderers/txt/TxtAnnotator.tsx` | `Modal`, `Button`, `Dropdown` | Yes | **4** | Text annotator |
| `annotator/renderers/txt/RadialButtonCloud.tsx` | `Button`, `Icon`, `SemanticICONS`, `Modal` | Yes | **4** | Radial menu |

#### Search Widget

| File | Semantic Imports | In Use? | Rating | Notes |
|------|------------------|---------|--------|-------|
| `annotator/search_widget/SearchSidebarWidget.tsx` | `Header`, `Segment`, `Icon`, `Message`, `Form` | Yes | **3** | Search sidebar |

---

### 10. KNOWLEDGE BASE COMPONENTS (Rating: 3-4)

| File | Semantic Imports | In Use? | Rating | Notes |
|------|------------------|---------|--------|-------|
| `knowledge_base/document/DocumentKnowledgeBase.tsx` | `Button`, `Header`, `Modal`, `Loader`, `Message`, `Icon` | Yes | **4** | Core KB view |
| `knowledge_base/document/NewNoteModal.tsx` | `Modal`, `Form`, `Button`, `Message` | Yes | **3** | Note creation |
| `knowledge_base/document/StickyNotes.tsx` | `Modal` | Yes | **2** | Modal wrapper |
| `knowledge_base/document/SelectDocumentFieldsetModal.tsx` | `Modal`, `Button`, `Input`, `Card`, `Header`, `Popup` | Yes | **4** | Fieldset picker |
| `knowledge_base/document/LayoutComponents.tsx` | `Modal` | Yes | **2** | Modal wrapper |
| `knowledge_base/document/FloatingDocumentControls.tsx` | `Checkbox` | Yes | **2** | Single control |
| `knowledge_base/document/FloatingDocumentInput.tsx` | `Form` | Yes | **2** | Form wrapper |
| `knowledge_base/document/StyledContainers.tsx` | `Button`, `Card`, `Segment` | Yes | **3** | Styled components |
| `knowledge_base/document/NoteEditor.tsx` | Multiple | Yes | **3** | Note editor |

#### Summary Components

| File | Semantic Imports | In Use? | Rating | Notes |
|------|------------------|---------|--------|-------|
| `knowledge_base/document/floating_summary_preview/SummaryEditorModal.tsx` | `Modal`, `Button`, `Header` | Yes | **3** | Summary editor |
| `knowledge_base/document/floating_summary_preview/SummaryHistoryModal.tsx` | `Modal`, `Button`, `Header`, `Loader` | Yes | **3** | History modal |
| `knowledge_base/document/floating_summary_preview/SummaryVersionStack.tsx` | `Loader` | Yes | **1** | Loader only |

#### Unified Feed

| File | Semantic Imports | In Use? | Rating | Notes |
|------|------------------|---------|--------|-------|
| `knowledge_base/document/layers/UnifiedKnowledgeLayer.tsx` | `Button`, `Icon` | Yes | **2** | Simple controls |
| `knowledge_base/document/unified_feed/UnifiedContentFeed.tsx` | `Loader`, `Button`, `Icon` | Yes | **2** | Simple controls |
| `knowledge_base/document/unified_feed/SidebarControlBar.tsx` | `Dropdown` | Yes | **3** | Dropdown control |
| `knowledge_base/document/unified_feed/RelationshipActionModal.tsx` | Multiple | Yes | **3** | Action modal |
| `knowledge_base/document/right_tray/ChatTray.tsx` | `Button`, `CardMeta` | Yes | **2** | Chat controls |

---

### 11. EXTRACT COMPONENTS (Rating: 3-4)

| File | Semantic Imports | In Use? | Rating | Notes |
|------|------------------|---------|--------|-------|
| `extracts/ExtractItem.tsx` | `Button`, `Card`, `Icon`, `Label` | Yes | **3** | Extract card |
| `extracts/ExtractListCard.tsx` | `Menu` | Yes | **2** | Menu wrapper |
| `extracts/list/ExtractList.tsx` | `Icon`, `Loader`, `Modal`, `Button` | Yes | **3** | List view |
| `extracts/list/ExtractListItem.tsx` | `Table`, `Icon`, `Button` | Yes | **3** | Table row |
| `extracts/datagrid/DataGrid.tsx` | Multiple | Yes | **4** | Data grid |
| `extracts/datagrid/DataCell.tsx` | `Table`, `Icon`, `Popup`, `Modal`, `Button`, `Loader` | Yes | **4** | Grid cell |
| `extracts/datagrid/EmptyDataCell.tsx` | `Table` | Yes | **2** | Empty cell |
| `extracts/datagrid/ExtractCellEditor.tsx` | Multiple | Yes | **4** | Cell editor |
| `extracts/datagrid/ExtractCellFormatter.tsx` | `Button`, `Popup`, `Icon`, `Modal` | Yes | **3** | Cell formatter |

---

### 12. CORPUS COMPONENTS (Rating: 2-4)

| File | Semantic Imports | In Use? | Rating | Notes |
|------|------------------|---------|--------|-------|
| `corpuses/CorpusDashboard.tsx` | `Header`, `Icon`, `SemanticICONS` | Yes | **3** | Dashboard header |
| `corpuses/CorpusItem.tsx` | Multiple | Yes | **3** | Corpus card |
| `corpuses/CorpusListView.tsx` | `Menu` | Yes | **2** | Menu only |
| `corpuses/CorpusSelector.tsx` | Multiple | Yes | **3** | Selector component |
| `corpuses/CorpusSettings.tsx` | Multiple | Yes | **4** | Settings page |
| `corpuses/CorpusMetadataSettings.tsx` | Multiple | Yes | **4** | Metadata settings |
| `corpuses/CorpusAgentSettings.tsx` | `Form`, `Button`, `Message`, `TextArea`, `Header` | Yes | **3** | Agent config |
| `corpuses/CorpusAgentManagement.tsx` | Multiple | Yes | **4** | Agent mgmt |
| `corpuses/CorpusChat.tsx` | `Button`, `Loader` | Yes | **2** | Chat controls |
| `corpuses/CorpusDescriptionEditor.tsx` | Multiple | Yes | **3** | Description editor |
| `corpuses/CorpusDocumentRelationships.tsx` | `Icon`, `Dropdown`, `Button`, `Confirm` | Yes | **3** | Relationships |
| `corpuses/DocumentTableOfContents.tsx` | `Icon` | Yes | **2** | Icons only |
| `corpuses/ActionExecutionRow.tsx` | `Icon`, `Label` | Yes | **2** | Simple display |
| `corpuses/ActionExecutionTrail.tsx` | `Dropdown`, `Icon`, `Loader` | Yes | **3** | Trail display |
| `corpuses/CategorySelector.tsx` | `Icon` | Yes | **2** | Icons only |
| `corpuses/CreateCorpusActionModal.tsx` | Multiple | Yes | **4** | Complex modal |
| `corpuses/folders/FolderTreeSidebar.tsx` | `Loader` | Yes | **1** | Loader only |
| `corpuses/folders/TrashFolderView.tsx` | Multiple | Yes | **3** | Trash view |

---

### 13. DOCUMENT COMPONENTS (Rating: 2-3)

| File | Semantic Imports | In Use? | Rating | Notes |
|------|------------------|---------|--------|-------|
| `documents/DocumentItem.tsx` | Multiple | Yes | **3** | Document card |
| `documents/DocumentListItem.tsx` | `Icon` | Yes | **2** | Icon only |
| `documents/ModernDocumentItem.tsx` | `Icon` | Yes | **2** | Icon only |
| `documents/ModernContextMenu.tsx` | `Icon` | Yes | **2** | Icons only |
| `documents/DocumentMetadataGrid.tsx` | Multiple | Yes | **3** | Metadata grid |
| `documents/DocumentUploadList.tsx` | `Icon`, `List` | Yes | **2** | Upload list |
| `documents/VersionHistoryPanel.tsx` | `Modal`, `Button`, `Icon`, `Loader`, `Message` | Yes | **3** | History panel |
| `documents/VersionBadge.tsx` | `Popup` | Yes | **2** | Popup only |
| `documents/DocumentRelationshipModal.tsx` | Multiple | Yes | **3** | Relationship modal |

---

### 14. ANALYSIS COMPONENTS (Rating: 2-3)

| File | Semantic Imports | In Use? | Rating | Notes |
|------|------------------|---------|--------|-------|
| `analyses/AnalysesCards.tsx` | `Card` | Yes | **2** | Card wrapper |
| `analyses/AnalysisItem.tsx` | Multiple | Yes | **3** | Analysis card |
| `analyses/AnalysisSelectorForCorpus.tsx` | `Segment`, `Form`, `Button`, `Icon` | Yes | **3** | Selector |
| `analyses/AnalysisTraySelector.tsx` | `Form`, `Segment`, `Button` | Yes | **3** | Tray selector |
| `analyses/ExtractTraySelector.tsx` | `Form`, `Segment` | Yes | **2** | Simple selector |

---

### 15. LABELSET COMPONENTS (Rating: 3-4)

| File | Semantic Imports | In Use? | Rating | Notes |
|------|------------------|---------|--------|-------|
| `labelsets/LabelSetListCard.tsx` | `Menu` | Yes | **2** | Menu wrapper |
| `labelsets/LabelSetEditModal.tsx` | Multiple | Yes | **4** | Edit modal |
| `labelsets/LabelSetDetailPage.tsx` | `Dimmer`, `Loader`, `Message` | Yes | **2** | Detail page |
| `labelsets/AnnotationLabelCard.tsx` | Multiple | Yes | **3** | Label card |
| `labelsets/AnnotationLabelItem.tsx` | `Card`, `Popup`, `Icon`, `Statistic`, `Menu` | Yes | **3** | Label item |

---

### 16. BADGE COMPONENTS (Rating: 2-3)

| File | Semantic Imports | In Use? | Rating | Notes |
|------|------------------|---------|--------|-------|
| `badges/Badge.tsx` | `Label` | Yes | **2** | Simple label |
| `badges/BadgeManagement.tsx` | Multiple | Yes | **3** | Badge mgmt |
| `badges/AwardBadgeModal.tsx` | Multiple | Yes | **3** | Award modal |
| `badges/UserBadges.tsx` | `Header`, `Message`, `Dimmer`, `Loader`, `Segment` | Yes | **3** | User badges |
| `badges/MessageBadges.tsx` | `Popup` | Yes | **2** | Popup only |
| `badges/BadgeCriteriaConfig.tsx` | `Form`, `Dropdown`, `Input`, `Message` | Yes | **3** | Criteria config |

---

### 17. OTHER COMPONENTS (Rating: 2-4)

| File | Semantic Imports | In Use? | Rating | Notes |
|------|------------------|---------|--------|-------|
| `analyzers/AnalyzerSummaryCard.tsx` | `Card`, `Button`, `List`, `Header` | Yes | **3** | Summary card |
| `analytics/CorpusEngagementDashboard.tsx` | `Icon`, `Loader`, `Message`, `SemanticICONS` | Yes | **3** | Dashboard |
| `admin/GlobalSettingsPanel.tsx` | `Header`, `Segment`, `Card`, `Icon` | Yes | **3** | Settings panel |
| `admin/GlobalAgentManagement.tsx` | Multiple | Yes | **4** | Agent mgmt |
| `agents/BadgeConfigurator.tsx` | `Form`, `Input`, `Label` | Yes | **3** | Badge config |
| `community/Leaderboard.tsx` | Multiple | Yes | **3** | Leaderboard |
| `exports/ExportItemRow.tsx` | `Table`, `Icon`, `Button` | Yes | **3** | Export row |
| `metadata/editors/MetadataCellEditor.tsx` | Multiple | Yes | **4** | Cell editor |
| `moderation/ModerationDashboard.tsx` | Multiple | Yes | **4** | Moderation UI |
| `placeholders/PlaceholderItem.tsx` | `Item`, `Placeholder` | Yes | **2** | Skeleton |
| `profile/RecentActivity.tsx` | `Dimmer`, `Loader`, `Message` | Yes | **2** | Activity |
| `routes/NotFound.tsx` | `Button`, `Icon` | Yes | **2** | 404 page |

---

### 18. UTILITY/STYLED COMPONENTS (Rating: 2-3)

| File | Semantic Imports | In Use? | Rating | Notes |
|------|------------------|---------|--------|-------|
| `widgets/styled.ts` | `Form`, `Input`, `Checkbox`, `TextArea` | Yes | **3** | Styled forms |
| `widgets/ErrorBoundary.tsx` | `Message`, `Button`, `Container` | Yes | **3** | Error boundary |
| `widgets/ModelFieldBuilder.tsx` | `Button`, `Form`, `Grid` | Yes | **3** | Field builder |
| `widgets/color-picker/ColorPickerSegment.tsx` | `Segment` | Yes | **2** | Segment wrapper |
| `widgets/file-controls/FilePreviewAndUpload.tsx` | `Segment`, `Icon` | Yes | **2** | File controls |
| `widgets/permissions/MyPermissionsIndicator.tsx` | `Statistic`, `Icon` | Yes | **2** | Permissions |

---

### 19. DATA DISPLAY WIDGETS (Rating: 2-3)

| File | Semantic Imports | In Use? | Rating | Notes |
|------|------------------|---------|--------|-------|
| `widgets/data-display/Result.tsx` | `Header`, `Icon`, `SemanticCOLORS` | Yes | **2** | Result display |
| `widgets/data-display/DateTimeWidget.tsx` | `Statistic` | Yes | **2** | Date display |
| `widgets/data-display/Transfer.tsx` | `Segment`, `Grid` | Yes | **3** | Transfer list |
| `widgets/data-display/TruncatedText.tsx` | `Popup` | Yes | **2** | Truncation popup |

---

### 20. POPUP/TOOLTIP COMPONENTS (Rating: 3)

| File | Semantic Imports | In Use? | Rating | Notes |
|------|------------------|---------|--------|-------|
| `widgets/popups/ViewSettingsPopup.tsx` | Multiple | Yes | **3** | View settings |
| `widgets/popups/RelationshipViewSettingsPopup.tsx` | `Popup`, `Grid`, `Checkbox`, `Header`, `Label` | Yes | **3** | Relationship settings |

---

## Special Concern: @rjsf/semantic-ui Integration

Four files use React JSON Schema Forms with the Semantic UI theme. This is a **critical dependency** that requires special handling.

| File | Rating | Notes |
|------|--------|-------|
| `widgets/CRUD/CRUDWidget.tsx` | **5** | Core CRUD functionality |
| `widgets/modals/SelectExportTypeModal.tsx` | **5** | Export type selection |
| `widgets/modals/SelectCorpusAnalyzerOrFieldsetAnalyzer.tsx` | **5** | Analyzer selection |
| `widgets/modals/DocumentUploadModal.tsx` | **5** | Document upload |

**Migration Options**:
1. Create custom RJSF theme using new UI library
2. Use `@rjsf/core` with custom widgets
3. Replace RJSF forms with manual form implementations

---

## Component Usage Frequency

| Component | Import Count | Replacement Priority |
|-----------|--------------|---------------------|
| Icon | 54 | HIGH - `lucide-react` available |
| Button | 48 | HIGH - `@os-legal/ui` has Button |
| Modal | 29 | HIGH - Create custom Modal |
| Header | 27 | MEDIUM - Styled component |
| Label | 20 | MEDIUM - Chip/Badge in @os-legal/ui |
| Form | 20 | HIGH - Complex, needs careful migration |
| Message | 18 | MEDIUM - Toast/Alert component |
| Dropdown | 17 | HIGH - Complex, many variants |
| Popup | 16 | MEDIUM - Tooltip replacement |
| Segment | 15 | LOW - Styled div |
| Loader | 15 | LOW - Simple spinner |
| Card | 14 | MEDIUM - @os-legal/ui has CollectionCard |
| Menu | 10 | MEDIUM - Navigation component |
| Grid | 9 | LOW - CSS Grid/Flexbox |

---

## Migration Recommendations

### Phase 1: Quick Wins (1-2 weeks)
1. **Delete dead code** - Remove 12 unused components
2. **Replace type imports** - Create custom icon types
3. **Icon migration** - Swap `<Icon>` with `lucide-react`
4. **Loader migration** - Create simple spinner component
5. **Segment removal** - Replace with styled divs

### Phase 2: Component Replacements (4-6 weeks)
1. **Button** - Extend `@os-legal/ui` Button
2. **Label/Badge** - Use `@os-legal/ui` Chip
3. **Card** - Extend CollectionCard
4. **Message** - Create Alert component (or use toast)
5. **Header** - Styled typography components

### Phase 3: Complex Components (8-12 weeks)
1. **Modal** - Build custom Modal with `@floating-ui`
2. **Dropdown** - Use `react-select` (already a dependency)
3. **Popup/Tooltip** - Use `@floating-ui` or build custom
4. **Form components** - Build form primitives

### Phase 4: RJSF Migration (4-6 weeks)
1. Evaluate RJSF alternatives or custom theme
2. Create custom widgets matching new design system
3. Migrate CRUD forms incrementally

---

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Visual regression | HIGH | Component-by-component migration with Playwright CT tests |
| Form validation breaks | HIGH | Keep RJSF forms for last, test extensively |
| Modal/Popup positioning | MEDIUM | Use `@floating-ui` for positioning |
| Accessibility regression | MEDIUM | Test with screen readers after each phase |
| Bundle size increase | LOW | Tree-shake unused components |

---

## Appendix: Files by Semantic Component

### Icon (54 files)
<details>
<summary>Click to expand full list</summary>

- annotator/topbar/AnnotatorTopbar.tsx
- annotator/sidebar/HighlightItem.tsx
- annotator/sidebar/RelationHighlightItem.tsx
- annotator/sidebar/LabelListItems.tsx
- annotator/display/components/ActionBar.tsx
- annotator/display/components/Containers.tsx
- annotator/display/components/Selection.tsx
- annotator/labels/label_selector/LabelElements.tsx
- annotator/labels/doc_types/DocTypeLabels.tsx
- annotator/labels/doc_types/DocTypePopup.tsx
- annotator/components/modals/RelationModal.tsx
- annotator/renderers/txt/RadialButtonCloud.tsx
- annotator/search_widget/SearchSidebarWidget.tsx
- extracts/ExtractItem.tsx
- extracts/list/ExtractList.tsx
- extracts/list/ExtractListItem.tsx
- extracts/datagrid/DataCell.tsx
- extracts/datagrid/ExtractCellFormatter.tsx
- corpuses/CorpusDashboard.tsx
- corpuses/DocumentTableOfContents.tsx
- corpuses/ActionExecutionRow.tsx
- corpuses/ActionExecutionTrail.tsx
- corpuses/CategorySelector.tsx
- corpuses/CorpusDocumentRelationships.tsx
- documents/DocumentListItem.tsx
- documents/ModernDocumentItem.tsx
- documents/ModernContextMenu.tsx
- documents/DocumentUploadList.tsx
- documents/VersionHistoryPanel.tsx
- knowledge_base/document/DocumentKnowledgeBase.tsx
- knowledge_base/document/layers/UnifiedKnowledgeLayer.tsx
- knowledge_base/document/unified_feed/UnifiedContentFeed.tsx
- widgets/modals/BulkUploadModal.tsx
- widgets/modals/ConfirmModal.tsx
- widgets/modals/ExportModal.tsx
- widgets/modals/DocumentUploadModal.tsx
- widgets/modals/sections/ExtractionConfigSection.tsx
- widgets/modals/sections/AdvancedOptionsSection.tsx
- widgets/CRUD/CRUDModal.tsx
- widgets/CRUD/CRUDWidget.tsx
- widgets/file-controls/FilePreviewAndUpload.tsx
- widgets/permissions/MyPermissionsIndicator.tsx
- widgets/data-display/Result.tsx
- analytics/CorpusEngagementDashboard.tsx
- badges/AwardBadgeModal.tsx
- admin/GlobalSettingsPanel.tsx
- common/FeatureUnavailable.tsx
- modals/UserSettingsModal.tsx
- cookies/CookieConsent.tsx
- routes/NotFound.tsx
- exports/ExportItemRow.tsx

</details>

### Modal (29 files)
<details>
<summary>Click to expand full list</summary>

- annotator/components/modals/EditLabelModal.tsx
- annotator/components/modals/RelationModal.tsx
- annotator/renderers/txt/TxtAnnotator.tsx
- annotator/renderers/txt/RadialButtonCloud.tsx
- corpuses/folders/CreateFolderModal.tsx
- corpuses/folders/EditFolderModal.tsx
- corpuses/folders/DeleteFolderModal.tsx
- corpuses/folders/MoveFolderModal.tsx
- corpuses/CreateCorpusActionModal.tsx
- documents/VersionHistoryPanel.tsx
- documents/DocumentRelationshipModal.tsx
- extracts/list/ExtractList.tsx
- extracts/datagrid/DataCell.tsx
- extracts/datagrid/ExtractCellFormatter.tsx
- knowledge_base/document/DocumentKnowledgeBase.tsx
- knowledge_base/document/NewNoteModal.tsx
- knowledge_base/document/StickyNotes.tsx
- knowledge_base/document/SelectDocumentFieldsetModal.tsx
- knowledge_base/document/LayoutComponents.tsx
- knowledge_base/document/floating_summary_preview/SummaryEditorModal.tsx
- knowledge_base/document/floating_summary_preview/SummaryHistoryModal.tsx
- knowledge_base/document/unified_feed/RelationshipActionModal.tsx
- widgets/modals/ConfirmModal.tsx
- widgets/modals/ExportModal.tsx
- widgets/modals/CreateExtractModal.tsx
- widgets/modals/SelectDocumentsModal.tsx
- widgets/CRUD/CRUDModal.tsx
- modals/UserSettingsModal.tsx
- modals/AddToCorpusModal.tsx
- cookies/CookieConsent.tsx
- threads/EditMessageModal.tsx

</details>

---

*Generated for OpenContracts frontend audit*
