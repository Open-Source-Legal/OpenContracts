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
| `SemanticICONS` type | `graphql-api.ts`, `types.ts`, `mutations.ts`, `icons.ts`, `ActionBar.tsx`, `RadialButtonCloud.tsx` (x2), `CorpusDashboard.tsx`, `CreateAndSearchBar.tsx`, `CorpusEngagementDashboard.tsx`, `Result.tsx`, `IconPickerModal.tsx` | Used as a type alias for icon name strings. Needs `resolveIcon()` mapping + `<DynamicIcon>` component. See [Icon Converter Strategy](#icon-converter-strategy). | 2–3 |
| `SemanticCOLORS` type | `Result.tsx` | Single usage. | 1 |
| `SemanticWIDTHSNUMBER` type | `utils/layout.ts` | Single usage in grid-width helper. Replace with `number`. | 1 |
| `DropdownNoStrictMode` wrapper | `common/DropdownNoStrictMode.tsx` | StrictMode workaround for SUI Dropdown; deletable once Dropdown is fully replaced. | 1 |

## Component-by-Component Inventory

Difficulty scale:
- **1** = Drop-in swap (e.g., `Icon` → Lucide, `Loader` → `Spinner`)
- **2** = Moderate refactor (different API, some prop mapping)
- **3** = Significant rework (compound components, complex state/layout)
- **4** = Major effort (deep integration, complex interactions, many sub-components)

### Icon (32+ files) — Difficulty: 1–2 (hardcoded) / 2–3 (dynamic+picker)

Three distinct layers of work (see [Icon Converter Strategy](#icon-converter-strategy) for full details):

**Layer 1 — Hardcoded JSX** (~150 instances across ~60 files, difficulty 1): Direct `<Icon name="plus" />` → `<Plus />` swaps. ~65 unique SUI icon names actually used in JSX. Mechanical find-and-replace.

**Layer 2 — Dynamic API-sourced names** (~10 callsites, difficulty 2–3): Components that render `<Icon name={variable} />` where the variable comes from GraphQL (e.g., `annotationLabel.icon`). Requires a runtime `resolveIcon()` mapping utility and a `<DynamicIcon>` wrapper component.

Key dynamic callsites:
- `LabelElements.tsx:62` — `<Icon name={label.icon} />`
- `LabelListItems.tsx:27` — `<Icon name={label?.icon ? label.icon : "tag"} />`
- `HighlightItem.tsx:226` — `<Icon name={annotation.annotationLabel.icon} />`
- `RelationModal.tsx:78` — `<Icon name={relation.icon ?? "tag"} />`
- `LabelSetEditModal.tsx:714` — `<Icon name={item.icon as any} />`
- `ModernContextMenu.tsx:207` — `<Icon name={item.icon as any} />`
- `ActionBar.tsx:179` — `{item.icon && <Icon name={item.icon} />}`
- `RadialButtonCloud.tsx` (both) — `<Icon name={btn.name} />`
- `CreateAndSearchBar.tsx:53` — `<Icon name={action.icon} />`

**Layer 3 — IconPicker rebuild** (1 file, difficulty 3): `icons.ts` contains 1,250 SUI icon names as the selectable catalog. Must be replaced with a Lucide icon catalog. `IconPickerModal.tsx` UI must render Lucide components instead of SUI `<Icon>`.

Additional static files using `SemanticICONS` type: `AnnotatorTopbar.tsx`, `Selection.tsx`, `Containers.tsx`, `ActionBar.tsx` (2), `ModernDocumentItem.tsx`, `ModernContextMenu.tsx`, `DocumentTableOfContents.tsx`, `CategorySelector.tsx`, `CorpusDashboard.tsx`, `ActionExecutionRow.tsx`, `CorpusDocumentRelationships.tsx`, `ActionExecutionTrail.tsx`, `CorpusEngagementDashboard.tsx` (2), `FeatureUnavailable.tsx`, `CorpusRequiredEmptyState.tsx`, `NotFound.tsx`, `VisibilitySlugSection.tsx`, `CategoriesSection.tsx`, `CorpusActionsSection.tsx`, `HighlightItem.tsx`, `RelationHighlightItem.tsx`, `LabelListItems.tsx`, `ContextBar.tsx`, `UnifiedKnowledgeLayer.tsx`, `RadialButtonCloud.tsx` (x2), `DocTypePopup.tsx`, `DocTypeLabelDisplay.tsx`, `DocTypeLabels.tsx`, `LabelElements.tsx`, plus hardcoded usages in: `UserSettingsModal.tsx`, `AddToCorpusModal.tsx`, `CookieConsent.tsx`, `MyPermissionsIndicator.tsx`, `Leaderboard.tsx`, `ExtractListItem.tsx`, `GlobalAgentManagement.tsx`, `AwardBadgeModal.tsx`, `BadgeManagement.tsx`, `CorpusActionsSection.tsx`, `MetadataCellEditor.tsx`, `AnalyzerSummaryCard.tsx`, `AnalysisItem.tsx`, `ConfirmModal.tsx`, `BulkImportModal.tsx`, `DocumentItem.tsx`, `VersionHistoryPanel.tsx`, `DocumentRelationshipModal.tsx`, `CorpusSelector.tsx`, `CorpusAgentManagement.tsx`, `CorpusMetadataSettings.tsx`, `CreateCorpusActionModal.tsx`, `ExtractItem.tsx`, `ExtractCellFormatter.tsx`, `DataGrid.tsx`, `DataCell.tsx`, `CRUDModal.tsx`, `MetadataColumnModal.tsx`, `UnifiedContentFeed.tsx`, `NotFound.tsx`, `ViewSettingsPopup.tsx`

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

## Icon Converter Strategy

### Problem Statement

Icon names are stored in the database (primarily the `AnnotationLabel.icon` field) and returned via GraphQL. Existing production data contains Semantic UI icon names (e.g. `"tags"`, `"file"`, `"arrow left"`). The frontend currently renders these dynamically via `<Icon name={label.icon} />`. After migration, these stored strings must resolve to Lucide components.

### Backend Icon Field Audit

| Model | Field Type | Values Stored | Affected? |
|---|---|---|---|
| **AnnotationLabel** | `CharField(128)` | SUI icon names (default: `"tags"`). Selected via IconPicker. | **YES** — primary concern |
| **Badge** | `CharField(100)` | Already Lucide names (`"Trophy"`, `"Star"`, `"Award"`) | No |
| **CorpusCategory** | `CharField(100)` | Already Lucide names (`"scroll"`, `"file-text"`) | No |
| **CorpusFolder** | `CharField(50)` | Already Lucide names (`"folder"`) | No |
| **Corpus** | `FileField` | Actual image files (base64 upload) | No — not icon names |
| **Document** | `FileField` | Actual image files (thumbnails) | No — not icon names |
| **LabelSet** | `FileField` | Actual image files (base64 upload) | No — not icon names |

**Key finding**: Only **AnnotationLabel** has SUI icon name strings in the database. Badge, CorpusCategory, and CorpusFolder already use Lucide names. Corpus/Document/LabelSet store actual image files.

### Implementation Plan

#### Step 1: Build `resolveIcon()` mapping utility (`utils/iconCompat.ts`)

A lookup table mapping SUI icon names → Lucide icon names. Only ~65–80 entries needed (the icons actually used in the app + common ones users may have picked via the IconPicker). Unknown names pass through as-is (handles models already storing Lucide names). Falls back to `HelpCircle` for truly unrecognized names.

SUI has many aliases (`"remove"` = `"close"` = `"x"`, `"setting"` = `"cog"` = `"configure"`). The mapping must handle all aliases for the commonly-used icons.

```typescript
// frontend/src/utils/iconCompat.ts
import { icons, type LucideIcon } from "lucide-react";
import { HelpCircle } from "lucide-react";

const SEMANTIC_TO_LUCIDE: Record<string, string> = {
  // Navigation
  "arrow left": "arrow-left",
  "arrow right": "arrow-right",
  "arrow up": "arrow-up",
  "arrow down": "arrow-down",
  "chevron up": "chevron-up",
  "chevron down": "chevron-down",
  "chevron left": "chevron-left",
  "chevron right": "chevron-right",
  // Actions
  "plus": "plus",
  "check": "check",
  "checkmark": "check",
  "close": "x",
  "remove": "x",
  "trash": "trash-2",
  "edit": "pencil",
  "pencil": "pencil",
  "save": "save",
  "download": "download",
  "upload": "upload",
  "cloud upload": "cloud-upload",
  "undo": "undo-2",
  "redo": "redo-2",
  "refresh": "refresh-cw",
  // Objects
  "file": "file",
  "file outline": "file",
  "file text": "file-text",
  "file text outline": "file-text",
  "file pdf outline": "file-text",
  "folder": "folder",
  "folder open": "folder-open",
  "folder open outline": "folder-open",
  "tags": "tags",
  "tag": "tag",
  "cog": "settings",
  "cogs": "settings",
  "setting": "settings",
  "settings": "settings",
  "configure": "settings",
  // ... ~50 more entries
};

export function resolveIconName(name: string): string {
  return SEMANTIC_TO_LUCIDE[name] ?? name;
}

export function resolveIcon(name: string): LucideIcon {
  const lucideName = resolveIconName(name);
  // lucide-react's `icons` object is keyed by PascalCase names
  const pascalName = lucideName.split("-").map(
    s => s.charAt(0).toUpperCase() + s.slice(1)
  ).join("");
  return (icons as Record<string, LucideIcon>)[pascalName] ?? HelpCircle;
}
```

#### Step 2: Build `<DynamicIcon>` component

A wrapper that accepts a string icon name (SUI or Lucide) and renders the correct Lucide component:

```typescript
// frontend/src/components/widgets/icons/DynamicIcon.tsx
import { resolveIcon } from "../../../utils/iconCompat";

interface DynamicIconProps {
  name: string;
  size?: number;
  color?: string;
  className?: string;
  style?: React.CSSProperties;
}

export const DynamicIcon: React.FC<DynamicIconProps> = ({
  name, size = 16, color, className, style
}) => {
  const IconComponent = resolveIcon(name);
  return <IconComponent size={size} color={color} className={className} style={style} />;
};
```

#### Step 3: Replace hardcoded `<Icon name="...">` with direct Lucide imports

~150 instances across ~60 files. Mechanical work:
```typescript
// Before
import { Icon } from "semantic-ui-react";
<Icon name="plus" />

// After
import { Plus } from "lucide-react";
<Plus size={16} />
```

#### Step 4: Replace dynamic `<Icon name={variable}>` with `<DynamicIcon>`

~10 callsites where icon name comes from API data:
```typescript
// Before
<Icon name={label.icon} />

// After
<DynamicIcon name={label.icon} />
```

#### Step 5: Rebuild IconPicker with Lucide catalog

Replace the 1,250-entry SUI icon catalog (`icons.ts`) with a Lucide catalog. The `IconPickerModal.tsx` must render Lucide components in its grid. New labels written via the picker will store Lucide icon names natively.

#### Step 6: No data migration needed

The `resolveIcon()` converter handles old SUI values at render time forever. New values written via the updated IconPicker use Lucide names. Old data degrades gracefully with a fallback icon. A data migration could be added later to normalize old values, but it's not required for correctness.

### Icon Mapping Size Estimate

| Category | Count | Notes |
|---|---|---|
| Unique SUI icons hardcoded in JSX | ~65 | Fully enumerable from codebase search |
| SUI aliases to handle | ~15 | `remove`/`close`/`x`, `setting`/`cog`/`configure`, etc. |
| Icons users may have picked via IconPicker | ~20–30 | Subset of the 1,250 catalog entries anyone would realistically use for annotation labels |
| **Total mapping entries needed** | **~80–110** | Well-bounded |

## Consolidated Difficulty Summary

| Difficulty | Component Categories | Estimated File Count |
|---|---|---|
| **1 — Easy** (drop-in swap) | Icon (hardcoded), Header, Segment, Container, Label, Loader/Dimmer, Message, List, Divider, Confirm, Input/TextArea, Grid, Placeholder, Checkbox/Radio | ~120 files |
| **2 — Moderate** (prop mapping, layout changes) | Button, Modal, Card, Popup, Menu, Statistic, Form, Table (simple) | ~50 files |
| **2–3 — Icon converter** (runtime mapping + picker rebuild) | `resolveIcon()` utility, `<DynamicIcon>` component, IconPicker rebuild, `SemanticICONS` type removal | ~15 files |
| **3 — Significant** (complex rework) | Dropdown/Select (search, multi-select), Tab, DataGrid (Table compound), `@rjsf/semantic-ui`, CreateCorpusActionModal, CorpusSelector | ~15 files |
| **4 — Major** (deep integration) | None individually, but the **collective Dropdown migration** across 19 files without a ready replacement is effectively a level-4 project | — |

## Recommended Migration Order

1. **Icon converter foundation** (prerequisite for step 2): Build `resolveIcon()` mapping utility and `<DynamicIcon>` wrapper component. This unblocks all Icon migration work and ensures API-sourced icon names render correctly throughout migration.
2. **Quick wins (Difficulty 1)**: Hardcoded Icon→Lucide direct imports, Header→styled, Segment→div, Container→div, Label→Chip, Loader→Spinner, Message→styled alert, List→`<ul>`. Replace dynamic Icon usages with `<DynamicIcon>`. Clears ~120 files.
3. **IconPicker rebuild**: Replace 1,250-entry SUI catalog with Lucide catalog. Rebuild `IconPickerModal.tsx` to render Lucide components. New data written after this point uses Lucide names natively.
4. **Medium tier (Difficulty 2)**: Button→OS-Legal Button, Modal→OS-Legal Modal, Card→styled-components, Popup→Tooltip. Clears ~50 files.
5. **Build a Select/Combobox component** before tackling Dropdown migration. Adopt Radix UI `Select`/`Combobox` or Headless UI.
6. **Dropdown migration (Difficulty 3)**: With the Select component built, migrate all 19 Dropdown usages.
7. **`@rjsf/semantic-ui` → `@rjsf/core`** with custom theme (3 files).
8. **Remove `SemanticICONS` type** system-wide — replace with `string` or a Lucide icon name union type in `graphql-api.ts`, `mutations.ts`, etc.
9. **Delete**: `semantic-ui-css`, `semantic-ui-react`, `@rjsf/semantic-ui` from `package.json`, remove `semantic.css`, `icons.ts` (old catalog), remove CSS imports from `App.tsx` and `playwright/index.tsx`.
10. **(Optional, post-migration)**: Data migration to normalize old SUI icon names in `AnnotationLabel` rows to Lucide names, allowing eventual removal of the `resolveIcon()` mapping table.
