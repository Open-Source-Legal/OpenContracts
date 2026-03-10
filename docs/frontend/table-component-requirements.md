# Table Component Requirements for `@os-legal/ui`

## 1. Purpose

Replace all usage of Semantic UI React's `Table` component (and ad-hoc `styled.table` implementations) with a single, composable `Table` family in `@os-legal/ui`. The new component must be a **drop-in replacement** that eliminates the CSS overrides, `!important` hacks, and duplicated styled-component scaffolding found across 13+ files today.

---

## 2. Current State Audit

### 2.1 Files Using Semantic UI `Table`

| File | Use Case | SUI Props |
|------|----------|-----------|
| `components/documents/DocumentMetadataGrid.tsx` | Editable metadata spreadsheet | `celled`, `compact` |
| `components/extracts/datagrid/DataGrid.tsx` | Extract data grid with approval workflow | `celled`, `compact` |
| `components/exports/ExportItemRow.tsx` | Row-only (renders inside parent table) | `textAlign="center"` on cells |
| `components/moderation/ModerationDashboard.tsx` | Audit log | `celled`, `striped` |
| `components/badges/BadgeManagement.tsx` | CRUD admin table | `celled` |
| `components/community/Leaderboard.tsx` | Ranked user list | `basic="very"`, `celled`, `selectable` |
| `components/admin/GlobalAgentManagement.tsx` | CRUD admin table | `basic="very"`, `celled` |
| `components/admin/WorkerAccountManagement.tsx` | CRUD admin table | `basic="very"`, `celled` |
| `components/corpuses/CorpusMetadataSettings.tsx` | Column config with reordering | *(none, all via styled wrapper)* |
| `components/corpuses/CorpusAgentManagement.tsx` | CRUD admin table | `basic="very"`, `celled`, `compact` |
| `components/corpuses/settings/WorkerTokensSection.tsx` | Token management | `basic="very"`, `celled` |

### 2.2 Files Using Custom `styled.table` (No Semantic UI)

| File | Use Case |
|------|----------|
| `components/corpuses/CorpusDocumentRelationships.tsx` | Document relationship matrix |
| `components/annotator/sidebar/SingleDocumentExtractResults.tsx` | Per-document extraction results |

### 2.3 Semantic UI Props Actually Used

Across all files, only this subset of Semantic UI's Table API is exercised:

- **Table root**: `celled`, `compact`, `basic="very"`, `striped`, `selectable`
- **Table.HeaderCell**: `width` (Semantic UI column width units), `textAlign`
- **Table.Cell**: `textAlign`, `colSpan`
- **Table.Row**: no SUI-specific props (only `key`, `style`, event handlers)

Props like `collapsing`, `fixed`, `singleLine`, `sorted`, `positive`, `negative`, `warning`, `error`, `active`, `disabled`, `rowSpan`, `stackable`, `unstackable`, `attached`, `inverted`, and `padded` are **never used**.

### 2.4 Workarounds and Hacks in Current Code

| Problem | Where | Current Hack |
|---------|-------|-------------|
| Semantic UI's header background/font can't be themed | `DataGrid.tsx`, `CorpusMetadataSettings.tsx`, `DocumentMetadataGrid.tsx` | Inline styles with `!important` overrides (7 instances of `!important` in DataGrid alone) |
| Sticky headers require fighting SUI's default styling | `DataGrid.tsx`, `DocumentMetadataGrid.tsx` | `styled(Table)` wrapper that overrides `&.ui.table` selector; manual `position: sticky` with z-index layering |
| Frozen first column for horizontal scroll | `DataGrid.tsx`, `DocumentMetadataGrid.tsx` | Manual `position: sticky; left: 0` with carefully layered z-index (5 for body, 11 for header corner) and box-shadow to fake a border |
| Row hover color conflicts with SUI defaults | Multiple files | `styled(Table)` or inline `style` to override `tbody tr:hover` |
| Cell padding doesn't match design system | All SUI table files | Every file independently overrides padding via `!important` or styled-components |
| SUI adds unwanted border-radius on `.ui.table` | `DocumentMetadataGrid.tsx` | Explicit `border-radius: 0` override |
| SUI's `basic="very"` still applies some borders developers don't want | Admin tables | Accepted as-is (minor inconsistency) |
| Two different styling strategies co-exist | Across files | `DataGrid.tsx` uses an inline `styles` object; `DocumentMetadataGrid.tsx` and `CorpusMetadataSettings.tsx` use `styled(Table)`; 2 files bypass SUI entirely with `styled.table` |
| OS_LEGAL_COLORS not integrated into table theme | All files | Every consumer manually applies colors via overrides rather than getting them from a theme |
| `TruncatedCell` reinvented in multiple places | `WorkerAccountManagement.tsx`, `DataGrid.tsx` | Each file defines its own truncation styled-component with slight variations |

---

## 3. Component API Design

### 3.1 Compound Component Structure

The component should follow the same compound-component pattern as Semantic UI for easy migration, but with a cleaner sub-component namespace:

```tsx
<Table variant="default" size="md" stickyHeader>
  <Table.Head>
    <Table.Row>
      <Table.HeadCell sticky="left">Name</Table.HeadCell>
      <Table.HeadCell sortable sorted="asc" onSort={handleSort}>Status</Table.HeadCell>
      <Table.HeadCell align="right">Actions</Table.HeadCell>
    </Table.Row>
  </Table.Head>
  <Table.Body>
    <Table.Row hoverable selected={isSelected} onClick={handleClick}>
      <Table.Cell sticky="left">Document A</Table.Cell>
      <Table.Cell><StatusBadge /></Table.Cell>
      <Table.Cell align="right"><IconButton /></Table.Cell>
    </Table.Row>
  </Table.Body>
  <Table.Footer>
    <Table.Row>
      <Table.Cell colSpan={3}>Pagination controls</Table.Cell>
    </Table.Row>
  </Table.Footer>
</Table>
```

### 3.2 Sub-Component Mapping (SUI to New)

| Semantic UI | New Component | Notes |
|------------|---------------|-------|
| `<Table>` | `<Table>` | Root. Renders `<table>`. |
| `<Table.Header>` | `<Table.Head>` | Renders `<thead>`. Shorter name avoids ambiguity with `<Table.HeaderCell>`. |
| `<Table.HeaderCell>` | `<Table.HeadCell>` | Renders `<th>`. |
| `<Table.Body>` | `<Table.Body>` | Renders `<tbody>`. |
| `<Table.Row>` | `<Table.Row>` | Renders `<tr>`. |
| `<Table.Cell>` | `<Table.Cell>` | Renders `<td>`. |
| `<Table.Footer>` | `<Table.Footer>` | Renders `<tfoot>`. |

### 3.3 Props Specification

#### `<Table>` (Root)

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `variant` | `"default" \| "bordered" \| "minimal"` | `"default"` | `"default"` = subtle row separators (replaces SUI default). `"bordered"` = full cell borders (replaces `celled`). `"minimal"` = no borders (replaces `basic="very"`). |
| `size` | `"sm" \| "md" \| "lg"` | `"md"` | Controls cell padding. `"sm"` replaces `compact`. |
| `striped` | `boolean` | `false` | Alternating row backgrounds. |
| `stickyHeader` | `boolean` | `false` | Makes `<Table.Head>` position-sticky. Applies correct z-index, background, and bottom-border/box-shadow. |
| `className` | `string` | — | For styled-components or custom classes. |
| `style` | `CSSProperties` | — | Escape hatch. |

**Not included** (unused in codebase): `selectable` (use `hoverable` on Row instead), `fixed`, `collapsing`, `attached`, `inverted`, `padded`, `stackable`.

#### `<Table.Head>`

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `className` | `string` | — | |
| `style` | `CSSProperties` | — | |

Automatically styles child `<th>` elements with OS Legal design tokens (uppercase, letter-spacing, font-weight 600, `surfaceHover` background).

#### `<Table.HeadCell>`

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `align` | `"left" \| "center" \| "right"` | `"left"` | Text alignment. Replaces SUI `textAlign`. |
| `width` | `string \| number` | — | CSS width value (e.g., `"40px"`, `"20%"`, `1` for `1fr` in future). Replaces SUI numeric `width`. |
| `sticky` | `"left" \| "right"` | — | Pins column. Handles `position: sticky`, z-index stacking (higher than body sticky cells), background color, and separator box-shadow. |
| `sortable` | `boolean` | `false` | Renders sort affordance (cursor, icon space). |
| `sorted` | `"asc" \| "desc" \| false` | `false` | Current sort state. Renders ChevronUp/Down icon. |
| `onSort` | `() => void` | — | Click handler for sort toggle. |
| `colSpan` | `number` | — | Standard HTML colspan. |
| `className` | `string` | — | |
| `style` | `CSSProperties` | — | |

#### `<Table.Body>`

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `className` | `string` | — | |
| `style` | `CSSProperties` | — | |

#### `<Table.Row>`

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `hoverable` | `boolean` | `true` | Show hover background. Disabled for special rows (e.g., annotation expansion rows). |
| `selected` | `boolean` | `false` | Applies selected background color (`selectedBg`). |
| `onClick` | `MouseEventHandler` | — | Makes row interactive (adds `cursor: pointer`). |
| `className` | `string` | — | |
| `style` | `CSSProperties` | — | |

**Not included**: `positive`, `negative`, `warning`, `error`, `active`, `disabled` (never used; consumers use inline badges/icons instead).

#### `<Table.Cell>`

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `align` | `"left" \| "center" \| "right"` | `"left"` | Text alignment. |
| `sticky` | `"left" \| "right"` | — | Frozen column. Handles position, z-index, background, and box-shadow separator. Must coordinate z-index with HeadCell sticky (HeadCell sticky corner gets highest z-index). |
| `truncate` | `boolean` | `false` | Applies `overflow: hidden; text-overflow: ellipsis; white-space: nowrap` with configurable `maxWidth`. Eliminates need for per-file `TruncatedCell` styled-components. |
| `maxWidth` | `string` | — | Only applies when `truncate` is true. |
| `colSpan` | `number` | — | Standard HTML colspan. |
| `rowSpan` | `number` | — | Standard HTML rowspan. |
| `className` | `string` | — | |
| `style` | `CSSProperties` | — | |

#### `<Table.Footer>`

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `className` | `string` | — | |
| `style` | `CSSProperties` | — | |

---

## 4. Styling Requirements

### 4.1 Design Token Integration

All visual properties must derive from `OS_LEGAL_COLORS`, `OS_LEGAL_TYPOGRAPHY`, and `OS_LEGAL_SPACING`:

| Visual Property | Token |
|----------------|-------|
| Header background | `OS_LEGAL_COLORS.surfaceHover` (`#f8fafc`) |
| Header text | `OS_LEGAL_COLORS.textPrimary` (`#1e293b`) — uppercase, 600 weight, 0.05em letter-spacing |
| Header font | `OS_LEGAL_TYPOGRAPHY.fontFamilySans` |
| Body text | `OS_LEGAL_COLORS.textPrimary` |
| Body secondary text | `OS_LEGAL_COLORS.textSecondary` |
| Row border | `OS_LEGAL_COLORS.border` (`#e2e8f0`) |
| Row hover background | `OS_LEGAL_COLORS.surfaceHover` |
| Selected row background | `OS_LEGAL_COLORS.selectedBg` (`rgba(15, 118, 110, 0.1)`) |
| Striped row background | `OS_LEGAL_COLORS.gray50` (`#f9fafb`) |
| Sticky column shadow | `3px 0 6px rgba(0,0,0,0.05)` (matches current DataGrid/MetadataGrid) |
| Sticky header shadow | `0 2px 4px rgba(0,0,0,0.1)` (matches current DocumentMetadataGrid) |
| Container border-radius | `OS_LEGAL_SPACING.borderRadiusCard` (`12px`) — when Table is wrapped |

### 4.2 CSS Architecture

1. **No dependency on `semantic-ui-css`**. The component must be fully self-contained.
2. **No `!important` required by consumers**. All SUI-era overrides become unnecessary.
3. Ship as styled-components (consistent with the rest of `@os-legal/ui`).
4. All styled elements should use the `&` selector scoping properly so they don't leak.
5. The root `<table>` element must set:
   - `border-collapse: collapse`
   - `width: 100%`
   - `table-layout: auto` by default (with `fixed` available via a `layout` prop if needed later)

### 4.3 Z-Index Layering

Sticky positioning requires a well-defined z-index stack. Define these as internal constants:

| Layer | Z-Index | Element |
|-------|---------|---------|
| Base | 0 | Normal body cells |
| Frozen body column | 5 | `Table.Cell` with `sticky="left"` or `sticky="right"` |
| Sticky header | 10 | `Table.Head` row when `stickyHeader` is true |
| Frozen header column | 11 | `Table.HeadCell` with `sticky` + parent has `stickyHeader` |

---

## 5. Behavioral Requirements

### 5.1 Sticky Header

When `<Table stickyHeader>`:
- The `<thead>` gets `position: sticky; top: 0`.
- Background color is set explicitly (not `transparent`) so content doesn't bleed through.
- A bottom border or box-shadow provides visual separation from scrolled content.
- Works inside any scrollable ancestor (`overflow: auto` on a parent div).

### 5.2 Frozen Columns

When `<Table.HeadCell sticky="left">` or `<Table.Cell sticky="left">`:
- The cell gets `position: sticky; left: 0` (or `right: 0`).
- Background color is explicitly set (opaque) so sibling cells don't show through during scroll.
- A vertical box-shadow on the inner edge provides a visual separator.
- When **both** `stickyHeader` and a frozen column are active on the same HeadCell, it receives the highest z-index (11) to sit above both the sticky header row and the frozen body column.
- Multiple frozen columns are **not** required for v1 (only the first/last column pattern is used today). However, the API shape (`sticky="left"`) should not preclude adding multi-column support later by accepting offsets.

### 5.3 Sorting

When `<Table.HeadCell sortable sorted="asc" onSort={fn}>`:
- The header cell renders a sort indicator icon (ChevronUp for `"asc"`, ChevronDown for `"desc"`).
- When `sorted` is `false`/omitted, the column shows a neutral sort affordance (e.g., muted ChevronsUpDown icon) on hover.
- Clicking the header cell calls `onSort`. **The component does not manage sort state internally** — it is controlled from outside.
- The sort icon should be positioned at the end of the header text, separated by a consistent gap.

### 5.4 Row Selection

Row selection state is **controlled externally** via the `selected` prop on `<Table.Row>`. The table component:
- Applies the selected background color.
- Does NOT manage a selection set, checkbox rendering, or select-all logic. These remain in the consumer component (as they are today in DataGrid).

### 5.5 Horizontal Scroll

The Table component itself does not render a scroll container. Consumers wrap it:

```tsx
<div style={{ overflow: "auto", WebkitOverflowScrolling: "touch" }}>
  <Table stickyHeader>...</Table>
</div>
```

Consider shipping an optional `<Table.ScrollContainer>` wrapper that applies:
- `overflow: auto`
- `-webkit-overflow-scrolling: touch`
- `border: 1px solid OS_LEGAL_COLORS.border`
- `border-radius: OS_LEGAL_SPACING.borderRadiusCard`

This would replace the `TableContainer`/`GridWrapper`/`TableWrapper` styled-components that every consumer currently defines independently.

### 5.6 Empty & Loading States

The component should NOT embed empty/loading states. Consumers render them conditionally *instead of* the table (this is the existing pattern). The table body should gracefully accept zero rows without visual artifacts.

---

## 6. Accessibility Requirements

| Requirement | Implementation |
|-------------|----------------|
| Semantic HTML | Render actual `<table>`, `<thead>`, `<tbody>`, `<tfoot>`, `<tr>`, `<th>`, `<td>` elements. |
| `scope` attribute | `<th>` elements in `<Table.Head>` should have `scope="col"`. |
| `aria-sort` | Sortable headers should set `aria-sort="ascending"`, `"descending"`, or `"none"`. |
| `role="button"` | Sortable headers should be keyboard-focusable and activatable with Enter/Space. |
| `aria-selected` | Selected rows should set `aria-selected="true"`. |
| Focus visible | Sortable headers and clickable rows must show a visible focus ring on keyboard navigation. |
| Color contrast | All text must meet WCAG AA contrast ratios against their backgrounds (already guaranteed by OS_LEGAL_COLORS tokens for most combinations; verify striped rows). |

---

## 7. Migration Guide (Per-File)

The migration from Semantic UI to the new component should be mechanical. Here's the mapping:

### 7.1 Prop Translation

| Semantic UI | New API | Notes |
|------------|---------|-------|
| `<Table celled>` | `<Table variant="bordered">` | |
| `<Table basic="very">` | `<Table variant="minimal">` | |
| `<Table compact>` | `<Table size="sm">` | |
| `<Table striped>` | `<Table striped>` | Same |
| `<Table selectable>` | Use `<Table.Row hoverable>` per-row | Row-level instead of table-level |
| `<Table.Header>` | `<Table.Head>` | Rename only |
| `<Table.HeaderCell>` | `<Table.HeadCell>` | Rename only |
| `<Table.HeaderCell textAlign="center">` | `<Table.HeadCell align="center">` | |
| `<Table.HeaderCell width={1}>` | `<Table.HeadCell width="..." >` | Convert SUI width units to CSS values |
| `<Table.Cell textAlign="center">` | `<Table.Cell align="center">` | |
| `<Table.Cell colSpan={n}>` | `<Table.Cell colSpan={n}>` | Same |

### 7.2 Elimination of Workarounds

| File | What Gets Deleted |
|------|-------------------|
| `DocumentMetadataGrid.tsx` | ~65 lines of `StyledTable = styled(Table)` overrides |
| `DataGrid.tsx` | ~195 lines of inline `styles` object (header/cell/frozen column styles) |
| `CorpusMetadataSettings.tsx` | ~40 lines of `StyledTable = styled(Table)` overrides + `DataTypeBadge` width hack |
| `Leaderboard.tsx` | `UserRow = styled(Table.Row)` (replace with `selected` prop + `onClick`) |
| `WorkerAccountManagement.tsx` | `TruncatedCell` styled-component (replace with `<Table.Cell truncate>`) |
| `CorpusDocumentRelationships.tsx` | Entire custom `styled.table` + `th`/`td` styling (~30 lines) |
| `SingleDocumentExtractResults.tsx` | Entire custom `styled.table` + `TableHeader` + `TableRow` + `TableCell` (~60 lines) |
| All SUI table files | `import { Table } from "semantic-ui-react"` line |

### 7.3 Custom `styled.table` Files

`CorpusDocumentRelationships.tsx` and `SingleDocumentExtractResults.tsx` already bypass Semantic UI. Their migration is even simpler — replace the custom styled elements with compound-component usage and delete the styled-component definitions entirely.

---

## 8. Testing Requirements

### 8.1 Component Tests (Playwright CT)

Each of the following states should be visually verified:

1. **Variants**: `default`, `bordered`, `minimal` — verify border rendering.
2. **Sizes**: `sm`, `md`, `lg` — verify padding differences.
3. **Striped rows**: Verify alternating background on even/odd rows.
4. **Sticky header**: Scroll container with enough rows to scroll; verify header stays fixed and has shadow.
5. **Frozen column**: Scroll container with enough columns to scroll horizontally; verify first column stays pinned with shadow separator.
6. **Sticky header + frozen column**: Corner cell (intersection) has highest z-index and doesn't flicker.
7. **Sortable headers**: Click triggers `onSort`; icons render for `asc`, `desc`, and unsorted states.
8. **Selected row**: Background color matches design token.
9. **Truncated cell**: Long text is ellipsized; tooltip or title attribute shows full text.
10. **Empty body**: Zero rows renders without visual artifacts.
11. **Footer**: Renders below body content.

### 8.2 Accessibility Tests

- Run axe-core on each variant; zero violations expected.
- Verify `aria-sort` on sortable headers.
- Verify keyboard navigation (Tab to sortable header, Enter to sort).

### 8.3 Migration Smoke Tests

After replacing each file, its existing component tests must continue to pass without modification (beyond updating import paths).

---

## 9. Out of Scope for v1

The following are explicitly **not required** for the initial release:

- **Virtual scrolling / windowed rows** — The largest table today (DocumentMetadataGrid) uses "Load More" pagination; no table renders thousands of rows simultaneously.
- **Column resizing** — No current usage.
- **Column reordering via drag-and-drop** — CorpusMetadataSettings uses up/down buttons, not DnD.
- **Built-in pagination** — All pagination is handled externally (cursor-based GraphQL pagination with Load More buttons).
- **Built-in filtering** — All filtering is handled by external dropdowns/inputs.
- **Built-in row selection (checkbox column)** — DataGrid manages its own checkbox column with complex indeterminate logic; the table component should not embed this.
- **Responsive stacking** — No current table uses Semantic UI's `stackable` prop. Mobile users get horizontal scroll.
- **Dark mode** — Not currently supported anywhere in the app.
- **`inverted`, `attached`, `padded`** variants — Never used.

---

## 10. File Inventory

Complete list of files that will need updating when this component ships:

```
# Direct Semantic UI Table imports (11 files)
frontend/src/components/documents/DocumentMetadataGrid.tsx
frontend/src/components/extracts/datagrid/DataGrid.tsx
frontend/src/components/exports/ExportItemRow.tsx
frontend/src/components/moderation/ModerationDashboard.tsx
frontend/src/components/badges/BadgeManagement.tsx
frontend/src/components/community/Leaderboard.tsx
frontend/src/components/admin/GlobalAgentManagement.tsx
frontend/src/components/admin/WorkerAccountManagement.tsx
frontend/src/components/corpuses/CorpusMetadataSettings.tsx
frontend/src/components/corpuses/CorpusAgentManagement.tsx
frontend/src/components/corpuses/settings/WorkerTokensSection.tsx

# Custom styled.table implementations (2 files)
frontend/src/components/corpuses/CorpusDocumentRelationships.tsx
frontend/src/components/annotator/sidebar/SingleDocumentExtractResults.tsx
```

Total: **13 files** to migrate.
