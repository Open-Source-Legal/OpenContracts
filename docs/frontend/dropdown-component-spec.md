# Dropdown Component Spec

## Problem Statement

The frontend currently has **27+ dropdown instances** spread across **5 distinct implementations**:

1. **`Dropdown.tsx`** — Custom styled-components action menu (no accessibility)
2. **`Select.tsx`** — `react-select` wrapper for multi/single value selection
3. **`CorpusDropdown.tsx` / `ExtractTaskDropdown.tsx`** — Semantic UI `<Dropdown>` wrappers with async search
4. **`ThreadSortDropdown.tsx`** — One-off styled-components sort menu (partial ARIA)
5. **`DocumentVersionSelector.tsx`** — One-off styled-components listbox (full ARIA)

Plus ~15 direct Semantic UI `<Dropdown>` imports scattered across feature components.

This fragmentation causes:

- **Inconsistent keyboard navigation** — only `DocumentVersionSelector` has full arrow-key support
- **Inconsistent accessibility** — ARIA attributes range from none to complete
- **Inconsistent styling** — hardcoded hex values instead of OS-Legal design tokens
- **Duplicated logic** — click-outside, escape-to-close, debounced search reimplemented per component
- **Migration friction** — Semantic UI dropdowns block the OS-Legal migration

## Goal

A single `Dropdown` component family that replaces all five implementations and every direct Semantic UI `<Dropdown>` import. It must cover four distinct behavioral modes with a shared foundation of keyboard navigation, accessibility, and OS-Legal styling.

---

## Use-Case Taxonomy

Analysis of all 27+ dropdown instances reveals four behavioral categories:

### 1. Action Menu

A trigger opens a list of clickable actions. No persistent selection state — items behave as buttons.

| Current Implementation | Location | Behavior |
|---|---|---|
| `Dropdown.tsx` | `CreateAndSearchBar` | Plus icon → "New Corpus", "Upload", etc. |
| `ThreadSortDropdown` | `ThreadList` | Sort button → "Newest", "Most Active", etc. |
| Semantic UI | `ActionExecutionTrail` | Filter button → action filter options |
| Semantic UI | `CorpusDocumentRelationships` | Relationship type filter actions |
| Semantic UI | `CreateCorpusActionModal` | Action selection |
| Semantic UI | `RunCorpusActionModal` | Action selection |

**Distinguishing traits**: Trigger is typically a button or icon. Menu closes after any item click. Items may have icons and descriptions. No "selected value" displayed in trigger.

### 2. Single Select

User picks exactly one value from a list. The selected value is reflected in the trigger.

| Current Implementation | Location | Behavior |
|---|---|---|
| Semantic UI | `EmbedderSelector` | Pick one embedding model |
| Semantic UI | `LabelSetSelector` | Pick one label set |
| Semantic UI | `SelectExportTypeModal` | Pick one export format |
| Semantic UI | `BadgeCriteriaConfig` | Pick one criteria type |
| Semantic UI | `MetadataCellEditor` | Pick one enum value |
| Semantic UI | `MoveFolderModal` | Pick one target folder |
| `Select.tsx` (react-select) | `FilterStructuralAnnotations` | Pick one filter mode ("ONLY", "EXCLUDE", "INCLUDE") |
| `DocumentVersionSelector` | Document header | Pick one document version |

**Distinguishing traits**: Trigger displays current value. May be clearable. May have search/filter. Options can have custom content (icons, descriptions). Controlled or uncontrolled.

### 3. Multi Select

User picks zero or more values. Selections shown as removable tags/chips in the trigger area.

| Current Implementation | Location | Behavior |
|---|---|---|
| Semantic UI | `ViewLabelSelector` | Filter visible annotation labels |
| Semantic UI | `AnnotationControls` | Label display filter (multiple) |
| `Select.tsx` (react-select) | `FilterToCorpusSelector` | Filter by multiple corpuses |
| `Select.tsx` (react-select) | `FilterToAnalysesSelector` | Filter by multiple analyses |
| `Select.tsx` (react-select) | `FilterToLabelSelector` | Filter by multiple labels |
| `Select.tsx` (react-select) | `FilterToLabelsetSelector` | Filter by multiple label sets |

**Distinguishing traits**: Trigger area grows to accommodate tags. Each tag has a remove button. Often paired with search to narrow large option lists. Clearing removes all selections.

### 4. Async Search Select

A single- or multi-select where options are fetched from the server, with debounced search triggering refetches.

| Current Implementation | Location | Behavior |
|---|---|---|
| `CorpusDropdown` (Semantic UI) | `CreateExtractModal`, others | Search → GraphQL refetch (300ms debounce) |
| `ExtractTaskDropdown` (Semantic UI) | `BasicConfigSection` | Search → GraphQL refetch (500ms debounce) |
| `LabelSetSelector` (Semantic UI) | `CorpusModal` | Search → reactive var → refetch |

**Distinguishing traits**: Options are not known upfront. Loading spinner during fetch. Search input triggers server-side filtering rather than (or in addition to) local filtering. May combine with single or multi select behavior.

---

## Component API

### Design Principles

1. **Compound components** — `Dropdown`, `Dropdown.Trigger`, `Dropdown.Menu`, `Dropdown.Item`, `Dropdown.Search`, `Dropdown.Tag` allow flexible composition while sharing state via context.
2. **Mode prop for common patterns** — `mode="menu" | "select" | "multiselect"` configures the most common behavioral defaults so simple cases stay simple.
3. **Headless state, styled shell** — Internal state management (open/close, focus, selection) is separated from rendering so consumers can override any visual element via `trigger`, `renderOption`, etc.
4. **OS-Legal tokens only** — All colors, radii, shadows, and typography reference `OS_LEGAL_COLORS`, `OS_LEGAL_TYPOGRAPHY`, and `OS_LEGAL_SPACING`. No hardcoded hex values.

### Core Props

```typescript
interface DropdownProps<T extends string | number = string> {
  /** Behavioral mode. Determines selection semantics and ARIA role. */
  mode: "menu" | "select" | "multiselect";

  /** Option definitions. Not required for mode="menu" when using
   *  Dropdown.Item children directly. */
  options?: DropdownOption<T>[];

  /** Current value (controlled). Single value for "select", array for
   *  "multiselect". Ignored for "menu". */
  value?: T | T[] | null;

  /** Default value (uncontrolled). */
  defaultValue?: T | T[] | null;

  /** Selection change handler. Provides the new value and the full
   *  option object(s) for convenience. */
  onChange?: (
    value: T | T[] | null,
    option: DropdownOption<T> | DropdownOption<T>[] | null
  ) => void;

  /** Placeholder text shown when no value is selected. */
  placeholder?: string;

  /** Disables the entire dropdown. */
  disabled?: boolean;

  /** Shows a loading spinner in the menu and/or trigger. */
  loading?: boolean;

  /** Allows clearing the selection back to null/empty.
   *  Defaults to false for "menu", true for "select"/"multiselect". */
  clearable?: boolean;

  /** Enables a search input for filtering options.
   *  "local" filters client-side against option labels.
   *  "async" fires onSearchChange and leaves filtering to the consumer. */
  searchable?: false | "local" | "async";

  /** Called when the search input value changes. Use with
   *  searchable="async" to trigger server-side fetching. */
  onSearchChange?: (query: string) => void;

  /** Debounce interval in ms applied to onSearchChange.
   *  Defaults to 300. Only relevant when searchable="async". */
  searchDebounceMs?: number;

  /** Makes the dropdown fill its container width. */
  fluid?: boolean;

  /** Menu opens upward instead of downward. */
  upward?: boolean;

  /** Menu horizontal alignment relative to trigger. */
  align?: "left" | "right";

  /** Custom trigger element. Replaces the default trigger button entirely.
   *  Receives render props for open state, selected value, etc. */
  trigger?: React.ReactNode | ((state: TriggerRenderProps<T>) => React.ReactNode);

  /** Custom option renderer. Receives the option and state (focused,
   *  selected) and returns a ReactNode. */
  renderOption?: (
    option: DropdownOption<T>,
    state: { isFocused: boolean; isSelected: boolean }
  ) => React.ReactNode;

  /** Custom renderer for selected value tags in multiselect mode. */
  renderTag?: (
    option: DropdownOption<T>,
    onRemove: () => void
  ) => React.ReactNode;

  /** Custom renderer for the "no options" empty state. */
  renderEmpty?: () => React.ReactNode;

  /** Maximum height for the dropdown menu in px before scrolling.
   *  Defaults to 300. */
  maxMenuHeight?: number;

  /** Additional class name on the root container. */
  className?: string;

  /** Inline styles on the root container. */
  style?: React.CSSProperties;

  /** Accessible label. Applied as aria-label on the trigger. Required
   *  if there is no visible label element associated via htmlFor. */
  "aria-label"?: string;

  /** ID of an external label element. Applied as aria-labelledby. */
  "aria-labelledby"?: string;

  /** Called when the dropdown opens. */
  onOpen?: () => void;

  /** Called when the dropdown closes. */
  onClose?: () => void;
}
```

### Option Type

```typescript
interface DropdownOption<T extends string | number = string> {
  /** Unique value used for selection identity. */
  value: T;

  /** Display label shown in the trigger and as default option text. */
  label: string;

  /** Optional icon — a ReactNode (e.g., a Lucide icon) or image URL string. */
  icon?: React.ReactNode | string;

  /** Optional secondary text shown below the label in the menu. */
  description?: string;

  /** Disables this individual option. */
  disabled?: boolean;

  /** Arbitrary data attached to the option, passed through to onChange. */
  data?: unknown;
}
```

### Trigger Render Props

```typescript
interface TriggerRenderProps<T> {
  isOpen: boolean;
  selectedValue: T | T[] | null;
  selectedOption: DropdownOption<T> | DropdownOption<T>[] | null;
  placeholder: string;
  disabled: boolean;
  loading: boolean;
}
```

### Compound Components (for menu mode)

When `mode="menu"`, consumers can use compound children instead of `options` for full control over menu content:

```typescript
// Dropdown.Item — a single clickable action
interface DropdownItemProps {
  /** Click handler for this action. */
  onClick?: () => void;
  /** Optional icon preceding the label. */
  icon?: React.ReactNode;
  /** Disables the item. */
  disabled?: boolean;
  /** Item content. */
  children: React.ReactNode;
}

// Dropdown.Divider — a visual separator between groups
// No props.

// Dropdown.Header — a non-interactive group label
interface DropdownHeaderProps {
  children: React.ReactNode;
}
```

---

## Behavioral Specification

### Open/Close

| Trigger | Behavior |
|---|---|
| Click trigger | Toggle open/closed |
| Enter or Space on trigger | Toggle open/closed |
| Escape (while open) | Close and return focus to trigger |
| Click outside | Close |
| Tab away from dropdown | Close |
| Item selection (menu mode) | Always close |
| Item selection (select mode) | Close |
| Item selection (multiselect mode) | Stay open (user typically selects multiple) |

### Keyboard Navigation (while open)

| Key | Behavior |
|---|---|
| ArrowDown | Move focus to next option (wrap: no — stop at last) |
| ArrowUp | Move focus to previous option (wrap: no — stop at first) |
| Home | Move focus to first option |
| End | Move focus to last option |
| Enter | Select focused option (or fire its onClick in menu mode) |
| Space | Select focused option (unless search input is focused) |
| Escape | Close menu, restore focus to trigger |
| Type-ahead (single character) | Jump to next option starting with that character (menu/select only, not when searchable) |
| Any printable character (when searchable) | Focus search input and begin filtering |

### Focus Management

- When the menu opens, focus moves to the **search input** (if searchable) or the **currently selected/first option**.
- When the menu closes, focus returns to the **trigger element**.
- `aria-activedescendant` on the listbox/menu tracks the visually focused option without moving DOM focus away from the search input (when searchable).

### Search Behavior

**Local search (`searchable="local"`):**
- Client-side substring match against `option.label` (case-insensitive).
- No options matching → show empty state (`renderEmpty` or default "No results found").
- Search clears when menu closes.

**Async search (`searchable="async"`):**
- Search input value is debounced (default 300ms, configurable via `searchDebounceMs`) and forwarded to `onSearchChange`.
- Consumer is responsible for updating `options` with server results.
- While fetching, `loading={true}` shows a spinner in the menu.
- Search clears when menu closes.

### Selection Behavior

**Single select:**
- Selecting an option replaces the current value.
- If `clearable`, a clear button in the trigger resets to `null`.
- Trigger displays the selected option's label (and icon if present).

**Multi select:**
- Selecting an option toggles it in/out of the value array.
- Selected options appear as removable tags in the trigger area.
- If `clearable`, a clear-all button resets to `[]`.
- Already-selected options show a checkmark in the menu.
- Menu stays open after selection to allow additional picks.

---

## ARIA Specification

### Menu Mode (`mode="menu"`)

Follows the [WAI-ARIA Menu Button pattern](https://www.w3.org/WAI/ARIA/apg/patterns/menu-button/).

| Element | Role / Attribute |
|---|---|
| Trigger | `role="button"`, `aria-haspopup="menu"`, `aria-expanded` |
| Menu container | `role="menu"`, `aria-label` or `aria-labelledby` |
| Menu item | `role="menuitem"`, `tabindex="-1"` |
| Disabled item | `aria-disabled="true"` |
| Divider | `role="separator"` |
| Group header | `role="presentation"` (non-interactive) |

### Select Mode (`mode="select"`)

Follows the [WAI-ARIA Combobox pattern](https://www.w3.org/WAI/ARIA/apg/patterns/combobox/) when searchable, or [Listbox pattern](https://www.w3.org/WAI/ARIA/apg/patterns/listbox/) when not.

| Element | Role / Attribute |
|---|---|
| Trigger (no search) | `role="combobox"`, `aria-haspopup="listbox"`, `aria-expanded`, `aria-activedescendant` |
| Trigger (searchable) | `role="combobox"`, `aria-autocomplete="list"`, `aria-expanded`, `aria-activedescendant` |
| Search input | Part of combobox, receives actual DOM focus |
| Menu container | `role="listbox"`, `aria-label` or `aria-labelledby` |
| Option | `role="option"`, `aria-selected`, `id` (for activedescendant) |
| Disabled option | `aria-disabled="true"` |

### Multi Select Mode (`mode="multiselect"`)

Same as select mode with additions:

| Element | Role / Attribute |
|---|---|
| Listbox | `aria-multiselectable="true"` |
| Selected tag | `role="option"` inside a group, or semantically a remove button with `aria-label="Remove {label}"` |

---

## Visual Design

All values reference OS-Legal design tokens from `osLegalStyles.ts`.

### Trigger

| State | Background | Border | Text |
|---|---|---|---|
| Default | `surface` (white) | `border` (#e2e8f0) | `textPrimary` (#1e293b) |
| Hover | `surfaceHover` (#f8fafc) | `borderHover` (#cbd5e1) | `textPrimary` |
| Focus | `surface` | `accent` (#0f766e), 2px | `textPrimary` |
| Open | `surface` | `accent` (#0f766e) | `textPrimary` |
| Disabled | `surfaceLight` (#f1f5f9) | `border` | `textMuted` (#94a3b8) |
| Placeholder text | — | — | `textSecondary` (#64748b) |

- Border radius: `borderRadiusButton` (8px)
- Min height: 38px (desktop), 44px (touch / below `MOBILE_VIEW_BREAKPOINT`)
- Font: Inter, 14px, weight 400
- Chevron icon: 16px, `textSecondary`, rotates 180deg when open
- Clear button: 16px, `textSecondary`, hover `danger` (#dc2626)

### Menu

| Property | Value |
|---|---|
| Background | `surface` (white) |
| Border | `border` (#e2e8f0), 1px |
| Border radius | `borderRadiusButton` (8px) |
| Shadow | `shadowCard` (0 4px 12px rgba(0,0,0,0.04)) — elevate to `shadowCardHover` if menu overlaps other interactive content |
| Max height | 300px (default), scrollable |
| Z-index | 1000 |
| Offset from trigger | 4px gap |

### Menu Option

| State | Background | Text |
|---|---|---|
| Default | transparent | `textPrimary` (#1e293b) |
| Focused (keyboard) | `accentLight` (rgba(15,118,110,0.1)) | `textPrimary` |
| Hovered (mouse) | `surfaceHover` (#f8fafc) | `textPrimary` |
| Selected | `accentLight` | `accent` (#0f766e), weight 500 |
| Selected + focused | `accentLight` with 0.15 opacity | `accent` |
| Disabled | transparent | `textMuted` (#94a3b8) |

- Padding: 10px 14px
- Font: Inter, 14px, weight 400
- Description text: Inter, 12px, `textSecondary`
- Icon: 16px, left-aligned with 8px gap to label
- Selected checkmark: 16px, right-aligned, `accent`
- Divider between options: 1px `border`
- No divider between last option and menu edge

### Multi-Select Tags

| Property | Value |
|---|---|
| Background | `accentLight` (rgba(15,118,110,0.1)) |
| Border | 1px solid rgba(15,118,110,0.2) |
| Text | `accent` (#0f766e), Inter 13px, weight 500 |
| Border radius | 6px |
| Remove icon | 12px, `accent`, hover `danger` |
| Padding | 2px 8px |
| Gap between tags | 4px |

### Search Input

- Rendered inside the menu, pinned to top, above scrollable options.
- Full width, no border on sides/top — only a bottom border of 1px `border`.
- Padding: 10px 14px.
- Placeholder: "Search..." in `textMuted`.
- Search icon (Lucide `Search`): 14px, `textSecondary`, left of input.
- Clear search button: appears when input is non-empty, 14px, `textSecondary`.

### Loading State

- Spinner replaces the chevron icon in the trigger when `loading` is true.
- If menu is open and loading, show a centered spinner below the search input (or in place of options if no stale options to display).
- Use a subtle fade animation, not a full skeleton.

### Empty State

- Centered text: "No results found" in `textSecondary`, Inter 14px.
- Padding: 24px.
- If `renderEmpty` is provided, render that instead.

---

## Responsive Behavior

| Breakpoint | Adaptation |
|---|---|
| Above 600px (desktop) | Standard dropdown menu positioned below/above trigger |
| Below 600px (`MOBILE_VIEW_BREAKPOINT`) | Trigger height increases to 44px for touch targets. Menu remains a positioned dropdown (not a bottom sheet) but uses `fluid` width to fill available space. Font sizes remain the same. |

---

## Planned Migration Path

### Phase 1: Build core component

Implement `Dropdown` with all three modes, keyboard navigation, ARIA, and OS-Legal styling. Ship alongside existing components — no removals yet.

### Phase 2: Migrate wrapper components

Replace the internals of `CorpusDropdown`, `ExtractTaskDropdown`, `EmbedderSelector`, `LabelSetSelector`, `Select.tsx` (react-select wrapper), and `DocumentVersionSelector` to use the new `Dropdown`. Their public APIs stay the same to avoid cascading changes.

### Phase 3: Migrate direct Semantic UI imports

Replace every direct `import { Dropdown } from "semantic-ui-react"` with the new component. Each file is a self-contained migration.

### Phase 4: Remove old implementations

Delete `Select.tsx` (react-select wrapper), the old `Dropdown.tsx`, and remove `semantic-ui-react` Dropdown from the bundle. Remove the `react-select` dependency if no other usages remain.

---

## Usage Examples

### Action Menu

```tsx
<Dropdown mode="menu" aria-label="Create new item" trigger={<IconButton icon={<Plus />} />}>
  <Dropdown.Item icon={<FolderPlus />} onClick={handleNewCorpus}>
    New Corpus
  </Dropdown.Item>
  <Dropdown.Item icon={<Upload />} onClick={handleUpload}>
    Upload Document
  </Dropdown.Item>
  <Dropdown.Divider />
  <Dropdown.Item icon={<FileText />} onClick={handleNewExtract}>
    New Extract
  </Dropdown.Item>
</Dropdown>
```

### Single Select

```tsx
<Dropdown
  mode="select"
  options={embedderOptions}
  value={selectedEmbedder}
  onChange={(val) => setSelectedEmbedder(val)}
  placeholder="Select embedding model"
  aria-label="Embedding model"
  fluid
/>
```

### Multi Select with Search

```tsx
<Dropdown
  mode="multiselect"
  options={labelOptions}
  value={selectedLabelIds}
  onChange={(vals) => setSelectedLabelIds(vals)}
  placeholder="Filter by labels"
  searchable="local"
  clearable
  aria-label="Label filter"
/>
```

### Async Search Select

```tsx
<Dropdown
  mode="select"
  options={corpusOptions}
  value={selectedCorpusId}
  onChange={(val, opt) => handleCorpusChange(opt)}
  placeholder="Search corpuses..."
  searchable="async"
  searchDebounceMs={300}
  onSearchChange={setCorpusSearchQuery}
  loading={corpusesLoading}
  clearable
  aria-label="Corpus"
/>
```

### Custom Option Rendering

```tsx
<Dropdown
  mode="select"
  options={taskOptions}
  value={selectedTask}
  onChange={setSelectedTask}
  placeholder="Select a task"
  searchable="async"
  onSearchChange={setTaskSearch}
  loading={tasksLoading}
  renderOption={(option, { isFocused, isSelected }) => (
    <div>
      <strong>{option.label}</strong>
      {option.description && (
        <div style={{ fontSize: "0.8125rem", color: OS_LEGAL_COLORS.textSecondary }}>
          {option.description}
        </div>
      )}
    </div>
  )}
  aria-label="Extract task"
/>
```

### Custom Trigger

```tsx
<Dropdown
  mode="select"
  options={versionOptions}
  value={currentVersion}
  onChange={handleVersionChange}
  trigger={({ isOpen, selectedOption }) => (
    <VersionPill isOutdated={isOutdated}>
      v{selectedOption?.label ?? "?"}
      <ChevronIcon rotated={isOpen} />
    </VersionPill>
  )}
  aria-label="Document version"
/>
```

---

## Dependencies

- **Runtime**: React 18+, `styled-components` (already in use), Lucide icons (already in use)
- **New dependencies**: None. This replaces `react-select` and removes the need for Semantic UI's `<Dropdown>`.
- **Design tokens**: `OS_LEGAL_COLORS`, `OS_LEGAL_TYPOGRAPHY`, `OS_LEGAL_SPACING` from `osLegalStyles.ts`

## Testing Requirements

- **Unit tests** (Vitest): State management, keyboard navigation logic, search debouncing, controlled/uncontrolled behavior, ARIA attribute correctness.
- **Component tests** (Playwright CT): Visual rendering of all modes, mouse interaction, keyboard interaction end-to-end, responsive behavior at mobile breakpoint, loading/empty states.
- **Accessibility**: Every test should use `getByRole` queries. Run axe checks against each mode's rendered output.
- **Use `--reporter=list`** flag per project conventions.
