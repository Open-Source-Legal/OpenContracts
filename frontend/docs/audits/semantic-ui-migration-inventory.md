# Semantic UI Migration Inventory

**Last Updated:** 2026-01-19
**Branch:** `claude/audit-semantic-ui-PSLC8`

## Migration Progress

| Phase    | Status      | Components                                                               |
| -------- | ----------- | ------------------------------------------------------------------------ |
| Phase 1  | ✅ Complete | Dead code cleanup, Icon→lucide-react, Loader→Spinner, Segment→styled div |
| Phase 2  | ✅ Complete | Button, Message, Label, Card, Checkbox, Statistic, Progress, Placeholder |
| Phase 3  | ✅ Complete | Header, Form, Grid, List, Divider                                        |
| Phase 4+ | 🔲 Pending  | Modal, Dropdown, Popup, Menu, Table, etc.                                |

## Remaining Semantic UI Components

**Total:** 90 files (excluding `knowledge_base/document/`)

### High Priority - Core UI Components

#### Modal (19 files)

| File                    | Path                                                           |
| ----------------------- | -------------------------------------------------------------- |
| CookieConsent           | `src/components/cookies/CookieConsent.tsx`                     |
| CRUDModal               | `src/components/widgets/CRUD/CRUDModal.tsx`                    |
| ConfirmModal            | `src/components/widgets/modals/ConfirmModal.tsx`               |
| CreateExtractModal      | `src/components/widgets/modals/CreateExtractModal.tsx`         |
| ExportModal             | `src/components/widgets/modals/ExportModal.tsx`                |
| BulkImportModal         | `src/components/widgets/modals/BulkImportModal.tsx`            |
| UserSettingsModal       | `src/components/modals/UserSettingsModal.tsx`                  |
| EditMessageModal        | `src/components/threads/EditMessageModal.tsx`                  |
| VersionHistoryPanel     | `src/components/documents/VersionHistoryPanel.tsx`             |
| CorpusDescriptionEditor | `src/components/corpuses/CorpusDescriptionEditor.tsx`          |
| CreateFolderModal       | `src/components/corpuses/folders/CreateFolderModal.tsx`        |
| DeleteFolderModal       | `src/components/corpuses/folders/DeleteFolderModal.tsx`        |
| EditFolderModal         | `src/components/corpuses/folders/EditFolderModal.tsx`          |
| MoveFolderModal         | `src/components/corpuses/folders/MoveFolderModal.tsx`          |
| RelationModal           | `src/components/annotator/components/modals/RelationModal.tsx` |
| TxtAnnotator            | `src/components/annotator/renderers/txt/TxtAnnotator.tsx`      |
| ExtractList             | `src/components/extracts/list/ExtractList.tsx`                 |
| DataCell                | `src/components/extracts/datagrid/DataCell.tsx`                |
| ExtractCellFormatter    | `src/components/extracts/datagrid/ExtractCellFormatter.tsx`    |

#### Dropdown (15 files)

| File                        | Path                                                                         |
| --------------------------- | ---------------------------------------------------------------------------- |
| AnnotationControls          | `src/components/annotator/controls/AnnotationControls.tsx`                   |
| ViewLabelSelector           | `src/components/annotator/labels/view_labels_selector/ViewLabelSelector.tsx` |
| TxtAnnotator                | `src/components/annotator/renderers/txt/TxtAnnotator.tsx`                    |
| BadgeCriteriaConfig         | `src/components/badges/BadgeCriteriaConfig.tsx`                              |
| ActionExecutionTrail        | `src/components/corpuses/ActionExecutionTrail.tsx`                           |
| CorpusDocumentRelationships | `src/components/corpuses/CorpusDocumentRelationships.tsx`                    |
| MoveFolderModal             | `src/components/corpuses/folders/MoveFolderModal.tsx`                        |
| EmbedderSelector            | `src/components/widgets/CRUD/EmbedderSelector.tsx`                           |
| LabelSetSelector            | `src/components/widgets/CRUD/LabelSetSelector.tsx`                           |
| IconDropdown                | `src/components/widgets/icon-picker/IconDropdown.tsx`                        |
| OutputTypeSection           | `src/components/widgets/modals/sections/OutputTypeSection.tsx`               |
| ModelFieldBuilder           | `src/components/widgets/ModelFieldBuilder.tsx`                               |
| CorpusDropdown              | `src/components/widgets/selectors/CorpusDropdown.tsx`                        |
| ExtractTaskDropdown         | `src/components/widgets/selectors/ExtractTaskDropdown.tsx`                   |
| FieldsetDropdown            | `src/components/widgets/selectors/FieldsetDropdown.tsx`                      |

#### Popup (12 files)

| File                          | Path                                                                 |
| ----------------------------- | -------------------------------------------------------------------- |
| DocTypeLabels                 | `src/components/annotator/labels/doc_types/DocTypeLabels.tsx`        |
| LabelElements                 | `src/components/annotator/labels/label_selector/LabelElements.tsx`   |
| HighlightItem                 | `src/components/annotator/sidebar/HighlightItem.tsx`                 |
| MessageBadges                 | `src/components/badges/MessageBadges.tsx`                            |
| VersionBadge                  | `src/components/documents/VersionBadge.tsx`                          |
| DataCell                      | `src/components/extracts/datagrid/DataCell.tsx`                      |
| ExtractCellFormatter          | `src/components/extracts/datagrid/ExtractCellFormatter.tsx`          |
| AnnotationLabelItem           | `src/components/labelsets/AnnotationLabelItem.tsx`                   |
| TruncatedText                 | `src/components/widgets/data-display/TruncatedText.tsx`              |
| AdvancedOptionsSection        | `src/components/widgets/modals/sections/AdvancedOptionsSection.tsx`  |
| ExtractionConfigSection       | `src/components/widgets/modals/sections/ExtractionConfigSection.tsx` |
| RelationshipViewSettingsPopup | `src/components/widgets/popups/RelationshipViewSettingsPopup.tsx`    |

### Medium Priority

#### Menu (6 files)

| File                | Path                                                         |
| ------------------- | ------------------------------------------------------------ |
| DocumentViewer      | `src/components/annotator/display/viewer/DocumentViewer.tsx` |
| CorpusListView      | `src/components/corpuses/CorpusListView.tsx`                 |
| ExtractListCard     | `src/components/extracts/ExtractListCard.tsx`                |
| AnnotationLabelItem | `src/components/labelsets/AnnotationLabelItem.tsx`           |
| LabelSetListCard    | `src/components/labelsets/LabelSetListCard.tsx`              |
| Documents           | `src/views/Documents.tsx`                                    |

#### SemanticIcon (5 files)

| File                  | Path                                                               |
| --------------------- | ------------------------------------------------------------------ |
| DocTypeLabels         | `src/components/annotator/labels/doc_types/DocTypeLabels.tsx`      |
| LabelElements         | `src/components/annotator/labels/label_selector/LabelElements.tsx` |
| HighlightItem         | `src/components/annotator/sidebar/HighlightItem.tsx`               |
| LabelListItems        | `src/components/annotator/sidebar/LabelListItems.tsx`              |
| RelationHighlightItem | `src/components/annotator/sidebar/RelationHighlightItem.tsx`       |

#### Table (4 files)

| File            | Path                                                 |
| --------------- | ---------------------------------------------------- |
| ExportItemRow   | `src/components/exports/ExportItemRow.tsx`           |
| DataCell        | `src/components/extracts/datagrid/DataCell.tsx`      |
| EmptyDataCell   | `src/components/extracts/datagrid/EmptyDataCell.tsx` |
| ExtractListItem | `src/components/extracts/list/ExtractListItem.tsx`   |

#### Checkbox (3 files)

| File                        | Path                                                                   |
| --------------------------- | ---------------------------------------------------------------------- |
| AnnotationControls          | `src/components/annotator/controls/AnnotationControls.tsx`             |
| FilterToCorpusActionOutputs | `src/components/widgets/model-filters/FilterToCorpusActionOutputs.tsx` |
| Documents                   | `src/views/Documents.tsx`                                              |

### Lower Priority - Scattered Usage

| Component | Count | Files                                                     |
| --------- | ----- | --------------------------------------------------------- |
| Confirm   | 1     | `src/components/corpuses/CorpusDocumentRelationships.tsx` |
| Item      | 1     | `src/components/placeholders/PlaceholderItem.tsx`         |

## Excluded Files (17 files)

The following files in `knowledge_base/document/` are **intentionally excluded** from migration per project requirements:

- `DocumentKnowledgeBase.tsx`
- `NewNoteModal.tsx`
- `NoteEditor.tsx`
- `StickyNotes.tsx`
- `StyledContainers.tsx`
- `SelectDocumentFieldsetModal.tsx`
- `FloatingDocumentControls.tsx`
- `FloatingDocumentInput.tsx`
- `LayoutComponents.tsx`
- `right_tray/ChatTray.tsx`
- `floating_summary_preview/SummaryHistoryModal.tsx`
- `floating_summary_preview/SummaryEditorModal.tsx`
- `floating_summary_preview/SummaryVersionStack.tsx`
- `unified_feed/SidebarControlBar.tsx`
- `unified_feed/UnifiedContentFeed.tsx`
- `unified_feed/RelationshipActionModal.tsx`
- `layers/UnifiedKnowledgeLayer.tsx`

## Suggested Migration Phases

### Phase 4: Modal Migration (19 files)

- Replace `Modal` with @os-legal/ui Modal or custom styled modal
- Migrate `Modal.Header`, `Modal.Content`, `Modal.Actions` to styled components

### Phase 5: Dropdown Migration (15 files)

- Replace `Dropdown` with @os-legal/ui Select or custom dropdown
- Handle `DropdownProps` type migration

### Phase 6: Popup Migration (12 files)

- Replace `Popup` with Tooltip/Popover from @os-legal/ui
- Consider hover vs click trigger differences

### Phase 7: Remaining Components (19 files)

- Menu → styled nav/tabs or @os-legal/ui Tabs
- Table → styled table or custom data grid
- Checkbox → @os-legal/ui Toggle (already available)
- SemanticIcon → lucide-react icons
- Confirm → ConfirmModal pattern
- Item → styled div

## Component Mapping Reference

| Semantic UI | @os-legal/ui / Replacement |
| ----------- | -------------------------- |
| Modal       | Custom styled modal        |
| Dropdown    | Select or custom dropdown  |
| Popup       | Tooltip / Popover          |
| Menu        | Tabs or styled nav         |
| Table       | Styled table / custom grid |
| Checkbox    | Toggle                     |
| Icon        | lucide-react icons         |
| Confirm     | ConfirmModal pattern       |
| Item        | Styled div                 |
