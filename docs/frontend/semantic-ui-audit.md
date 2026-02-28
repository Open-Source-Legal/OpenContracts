# Semantic UI Remaining Usage Audit

**Date**: 2026-02-28
**Total files importing `semantic-ui-react`**: 190 (189 in `src/`, 1 in `playwright/`)
**Total unique Semantic UI components used**: ~35
**Additional dependency**: `@rjsf/semantic-ui` (3 files)

## Global / Infrastructure Dependencies

| Item | Files | Notes | Difficulty |
|---|---|---|---|
| `semantic-ui-css` CSS import | `App.tsx`, `playwright/index.tsx` | Full 40K-line stylesheet loaded globally. Can't remove until all components are migrated. | 1 (blocked) |
| `semantic.css` custom copy | `src/assets/styles/semantic.css` | 40,701-line compiled SUI v2.4.2 CSS. Deletable only after full migration. | 1 |
| `@rjsf/semantic-ui` (JSON Schema Forms) | `CRUDWidget.tsx`, `SelectCorpusAnalyzerOrFieldsetAnalyzer.tsx`, `SelectExportTypeModal.tsx` | Swap to `@rjsf/core` with custom theme or `@rjsf/mui`. | 3 |
| `SemanticICONS` type | `graphql-api.ts`, `types.ts`, `mutations.ts`, `icons.ts`, `ActionBar.tsx`, `RadialButtonCloud.tsx` (x2), `CorpusDashboard.tsx`, `CreateAndSearchBar.tsx`, `CorpusEngagementDashboard.tsx`, `Result.tsx`, `IconPickerModal.tsx` | Used as a type alias for icon name strings. Need a custom union type or Lucide icon map. | 2 |
| `SemanticCOLORS` type | `Result.tsx` | Single usage. | 1 |
| `SemanticWIDTHSNUMBER` type | `utils/layout.ts` | Single usage in grid-width helper. Replace with `number`. | 1 |
| `DropdownNoStrictMode` wrapper | `common/DropdownNoStrictMode.tsx` | StrictMode workaround for SUI Dropdown; deletable once Dropdown is fully replaced. | 1 |

## Component-by-Component Inventory

Difficulty scale:
- **1** = Drop-in swap (e.g., `Icon` → Lucide, `Loader` → `Spinner`)
- **2** = Moderate refactor (different API, some prop mapping)
- **3** = Significant rework (compound components, complex state/layout)
- **4** = Major effort (deep integration, complex interactions, many sub-components)

### Icon (32 files) — Difficulty: 1–2

Mostly trivial 1:1 swaps to Lucide icons. The `SemanticICONS`-based dynamic lookups (ActionBar, CorpusEngagementDashboard, RadialButtonCloud, icon-picker) need an icon name mapping table (difficulty 2).

Files: `AnnotatorTopbar.tsx`, `Selection.tsx`, `Containers.tsx`, `ActionBar.tsx` (2), `ModernDocumentItem.tsx`, `ModernContextMenu.tsx`, `DocumentTableOfContents.tsx`, `CategorySelector.tsx`, `CorpusDashboard.tsx`, `ActionExecutionRow.tsx`, `CorpusDocumentRelationships.tsx`, `ActionExecutionTrail.tsx`, `CorpusEngagementDashboard.tsx` (2), `FeatureUnavailable.tsx`, `CorpusRequiredEmptyState.tsx`, `NotFound.tsx`, `VisibilitySlugSection.tsx`, `CategoriesSection.tsx`, `CorpusActionsSection.tsx`, `HighlightItem.tsx`, `RelationHighlightItem.tsx`, `LabelListItems.tsx`, `ContextBar.tsx`, `UnifiedKnowledgeLayer.tsx`, `RadialButtonCloud.tsx` (x2), `DocTypePopup.tsx`, `DocTypeLabelDisplay.tsx`, `DocTypeLabels.tsx`, `LabelElements.tsx`

### Button (40 files) — Difficulty: 1

Almost all are straightforward swaps to `@os-legal/ui` `<Button>`. Map `primary`/`secondary`/`basic` to `variant` props.

Files span: views (`UserProfile`), annotator (9), knowledge base (10), corpus (8+), corpus folders (6), widgets/modals (7), settings (4), other (11)

### Modal (26 files) — Difficulty: 2

Flatten `Modal.Content`/`Modal.Actions`/`Modal.Header` → `ModalBody`/`ModalFooter`/`ModalHeader`. Migration guide has an exact pattern.

Files: `CookieConsent.tsx`, `VersionHistoryPanel.tsx`, `UserSettingsModal.tsx`, `AddToCorpusModal.tsx`, `EditLabelModal.tsx`, `RelationModal.tsx`, `TxtAnnotator.tsx`, `RadialButtonCloud.tsx`, `DocumentKnowledgeBase.tsx`, `LayoutComponents.tsx`, `StickyNotes.tsx`, `SelectDocumentFieldsetModal.tsx`, `DocumentModals.tsx`, `NewNoteModal.tsx`, `SummaryEditorModal.tsx`, `SummaryHistoryModal.tsx`, `RelationshipActionModal.tsx`, folder modals (5), `RunCorpusActionModal.tsx`, `CreateCorpusActionModal.tsx` (3), widget modals (10), extract components (3), `UploadModalStyles.ts`

### Dropdown (19 files) — Difficulty: 2–3

No direct OS-Legal replacement. Need a custom `<Select>`/`<Combobox>` component or adopt a headless library (Radix, Headless UI). This is the **hardest component category** to migrate.

Files: `PrimitiveTypeDropdown.tsx`, `FieldsetDropdown.tsx`, `CorpusDropdown.tsx`, `ExtractTaskDropdown.tsx`, `IconDropdown.tsx`, `ViewLabelSelector.tsx`, `AnnotationControls.tsx` (3), `CorpusDocumentRelationships.tsx`, `RunCorpusActionModal.tsx`, `ActionExecutionTrail.tsx`, `MoveFolderModal.tsx`, `SidebarControlBar.tsx`, `TxtAnnotator.tsx`, `SelectExportTypeModal.tsx` (3), `FilterToMetadataSelector.tsx`, `CorpusSelector.tsx` (3), `BadgeCriteriaConfig.tsx`, `LabelSetSelector.tsx` (3), `EmbedderSelector.tsx` (3)

### Form (14+ files) — Difficulty: 1–2

Replace `Form`/`Form.Field` with `@os-legal/ui` `<Input>`, `<Textarea>`, and plain `<form>` elements.

Files: `ModelFieldBuilder.tsx`, `BadgeConfigurator.tsx`, `CorpusAgentSettings.tsx`, `CorpusDescriptionEditor.tsx`, `CorpusMetadataSettings.tsx`, `CreateCorpusActionModal.tsx` (3), `EditFolderModal.tsx`, `CreateFolderModal.tsx`, `NewNoteModal.tsx`, `FloatingDocumentInput.tsx`, `DocNavigation.tsx`, `SearchSidebarWidget.tsx`, `ExtractTraySelector.tsx`, `AnalysisTraySelector.tsx`, `AnalysisSelectorForCorpus.tsx`, modal sections (3), `styled.ts`

### Card (15 files) — Difficulty: 2

Replace with styled-components `<div>` patterns per migration guide.

Files: `AnnotationSummary.tsx`, `AnalysesCards.tsx`, `CorpusItem.tsx`, `SelectedAnalysisCard.tsx`, `RelationshipList.tsx`, `LabelListItems.tsx`, `LabelElements.tsx`, `DocTypeLabels.tsx`, `Relationships.tsx`, `ConversationListView.tsx`, `AnnotationLabelItem.tsx`, `AnnotationLabelCard.tsx`, `ExtractItem.tsx`, `SelectDocumentFieldsetModal.tsx`, `AnalyzerSummaryCard.tsx`

### Header (16+ files) — Difficulty: 1

All trivially replaced with styled `<h2>`/`<h3>` elements or OS-Legal typography.

### Segment (13 files) — Difficulty: 1

Replace with plain styled `<div>`. Trivial.

### Popup (19 files) — Difficulty: 1–2

Swap to `@os-legal/ui` `<Tooltip>` or a custom popover. Simple for tooltips, slightly more work for content-rich popups (ViewSettingsPopup, RelationshipViewSettingsPopup, ExtractCellFormatter, DataCell).

### Loader / Dimmer (12 + 3 files) — Difficulty: 1

Replace with `@os-legal/ui` `<Spinner>` or shimmer skeletons. Trivial.

### Message (14 files) — Difficulty: 1

Replace with styled alert/info boxes. Trivial.

### Label (10+ files) — Difficulty: 1

Swap to `@os-legal/ui` `<Chip>`. Trivial.

### Menu / Tab (10 + 1 files) — Difficulty: 2–3

Replace with custom styled menus or `@os-legal/ui` `<FilterTabs>`. The `Corpuses.tsx` `Tab` usage is the most complex (difficulty 3).

### Table (5 files) — Difficulty: 2–3

DataGrid is the hardest — relies on `Table`/`Table.Header`/`Table.Row`/`Table.Cell` compound components (difficulty 3).

Files: `ExportItemRow.tsx`, `ExtractListItem.tsx`, `DataGrid.tsx` (3), `DataCell.tsx`, `EmptyDataCell.tsx`

### Grid (8 files) — Difficulty: 1

Replace with CSS Flexbox/Grid. Trivial.

### Checkbox / Radio (6 files) — Difficulty: 1–2

Files: `Documents.tsx`, `AnnotationControls.tsx` (2), `ViewSettingsPopup.tsx`, `FloatingDocumentControls.tsx`, `FilterToCorpusActionOutputs.tsx`, `styled.ts`

### Other Components (1–3 files each) — Difficulty: 1–2

| Component | File(s) | Difficulty |
|---|---|---|
| Container | `App.tsx`, `TermsOfService.tsx`, `PrivacyPolicy.tsx`, `ErrorBoundary.tsx` | 1 |
| Statistic | `MyPermissionsIndicator.tsx`, `LabelSetStatisticWidget.tsx`, `DateTimeWidget.tsx` | 2 |
| Confirm | `CorpusSettings.tsx`, `CorpusDocumentRelationships.tsx` | 1 |
| List | `TermsOfService.tsx`, `CookieConsent.tsx`, `UploadModalStyles.ts` | 1 |
| Placeholder | `PlaceholderItem.tsx` | 1 |
| Item | `PlaceholderItem.tsx` | 1 |
| Progress | `UploadModalStyles.ts` | 2 |
| Divider | `UserSettingsModal.tsx` | 1 |
| Input | `BadgeConfigurator.tsx`, `DocTypePopup.tsx`, `IconPickerModal.tsx`, `styled.ts` | 1 |
| TextArea | `CorpusAgentSettings.tsx`, `styled.ts` | 1 |

## Consolidated Difficulty Summary

| Difficulty | Component Categories | Estimated File Count |
|---|---|---|
| **1 — Easy** (drop-in swap) | Icon, Header, Segment, Container, Label, Loader/Dimmer, Message, List, Divider, Confirm, Input/TextArea, Grid, Placeholder, Checkbox/Radio | ~120 files |
| **2 — Moderate** (prop mapping, layout changes) | Button, Modal, Card, Popup, Menu, Statistic, Form, Table (simple) | ~50 files |
| **3 — Significant** (complex rework) | Dropdown/Select (search, multi-select), Tab, DataGrid (Table compound), `@rjsf/semantic-ui`, CreateCorpusActionModal, CorpusSelector | ~15 files |
| **4 — Major** (deep integration) | None individually, but the **collective Dropdown migration** across 19 files without a ready replacement is effectively a level-4 project | — |

## Recommended Migration Order

1. **Quick wins (Difficulty 1)**: Icon→Lucide, Header→styled, Segment→div, Container→div, Label→Chip, Loader→Spinner, Message→styled alert, List→`<ul>`. Clears ~120 files.
2. **Medium tier (Difficulty 2)**: Button→OS-Legal Button, Modal→OS-Legal Modal, Card→styled-components, Popup→Tooltip. Clears ~50 files.
3. **Build a Select/Combobox component** before tackling Dropdown migration. Adopt Radix UI `Select`/`Combobox` or Headless UI.
4. **Dropdown migration (Difficulty 3)**: With the Select component built, migrate all 19 Dropdown usages.
5. **`@rjsf/semantic-ui` → `@rjsf/core`** with custom theme (3 files).
6. **Remove `SemanticICONS` type** system-wide (build a Lucide icon name union type or icon map).
7. **Delete**: `semantic-ui-css`, `semantic-ui-react`, `@rjsf/semantic-ui` from `package.json`, remove `semantic.css`, remove CSS imports from `App.tsx` and `playwright/index.tsx`.
