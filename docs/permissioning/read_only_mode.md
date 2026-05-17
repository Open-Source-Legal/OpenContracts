# Read-Only Mode Implementation

## Overview

Read-only mode prevents users from modifying documents and annotations while still allowing viewing and navigation. This mode is triggered by insufficient permissions or explicit configuration.

## When Read-Only Mode is Active

1. **No UPDATE Permission**: User lacks CAN_UPDATE permission (corpus or document)
2. **Explicit Override**: Parent component passes `readOnly={true}`
3. **No Corpus Context**: Document viewed outside corpus (limited features)
4. **Backend Lock**: Document has `backendLock: true`

## Component Support Status

### ✅ Fully Implemented

#### Document Renderers
- **PDF Component**: Accepts `read_only` prop, prevents annotation creation
- **TxtAnnotatorWrapper**: Accepts `readOnly` and `allowInput` props

#### Annotation Components
- **UnifiedLabelSelector**: Disabled when `readOnly={true}`
- **SelectionLayer**: Shows "Document is read-only" message
- **AnnotationMenu**: Shows only copy option (no Apply Label)

#### Floating Components
- **FloatingDocumentInput**: Hides chat mode button
- **FloatingDocumentControls**: Hides "Start New Analysis" button
- **FloatingAnalysesPanel**: Passes readOnly to AnalysisTraySelector
- **FloatingExtractsPanel**: Passes readOnly to ExtractTraySelector
- **FloatingSummaryPreview**: Display-only component

#### Content Components
- **UnifiedContentFeed**: Passes readOnly to all content items
- **PostItNote**: Changes cursor to default, hides edit indicator
- **HighlightItem**: Disables delete functionality
- **RelationItem**: Disables delete and edit functions

#### Other Components
- **ChatTray**: Starts fresh conversation, hides history
- **UnifiedKnowledgeLayer**: Hides "Edit Summary" button
- **NoteEditor**: Component hidden entirely
- **NewNoteModal**: Component hidden entirely

### Components That Don't Need Changes
- **ZoomControls**: Zoom is inherently view-only
- **SidebarControlBar**: Navigation is view-only
- **SearchResultCard**: View-only by nature

## Implementation Patterns

> **Naming note**: the codebase currently mixes two prop names for the same
> concept:
> - **`readOnly`** (camelCase) — the standard React convention, used by most
>   components (`TxtAnnotatorWrapper`, `UnifiedContentFeed`, `HighlightItem`,
>   `RelationItem`, the styled-component transient prop `$readOnly`, etc.).
> - **`read_only`** (snake_case) — used by the legacy PDF viewer
>   (`PDF.tsx`) for historical reasons.
>
> When wiring read-only state through a new component, prefer **`readOnly`**.
> The `read_only` form on `PDF.tsx` is the outlier and is targeted for
> normalisation; if you touch that component, accept both names during the
> transition and forward the value to the renderer.

### Pattern 1: Conditional Rendering
```typescript
// Hide components that have no read-only use case
{!readOnly && (
  <NoteEditor
    noteId={editingNoteId}
    onSave={handleSave}
  />
)}
```

### Pattern 2: Prop Passing
```typescript
// Pass readOnly to child components
<UnifiedContentFeed
  readOnly={readOnly}
  items={contentItems}
/>
```

### Pattern 3: Conditional Handlers
```typescript
// Disable handlers in read-only mode (most components — camelCase)
<HighlightItem
  annotation={annotation}
  onDelete={readOnly ? undefined : handleDelete}
  readOnly={readOnly}
/>

// Legacy PDF viewer — snake_case
<PDF
  document={document}
  read_only={readOnly}
/>
```

### Pattern 4: UI State Changes
```typescript
// Change cursor and hover states
const PostItNote = styled.div<{ $readOnly?: boolean }>`
  cursor: ${props => props.$readOnly ? 'default' : 'pointer'};

  &:hover .edit-indicator {
    display: ${props => props.$readOnly ? 'none' : 'block'};
  }
`;
```

## User Experience in Read-Only Mode

### Visual Indicators
1. **Cursor Changes**: Pointer cursor becomes default cursor
2. **Hidden Controls**: Edit/delete buttons are hidden
3. **Disabled Inputs**: Form inputs are disabled
4. **Status Messages**: "Document is read-only" shown when attempting actions

### Available Features
- ✅ View document content
- ✅ Navigate pages
- ✅ Zoom in/out
- ✅ Search within document
- ✅ View existing annotations
- ✅ Copy text
- ✅ View notes (cannot edit)
- ✅ Navigate between documents

### Disabled Features
- ❌ Create new annotations
- ❌ Edit existing annotations
- ❌ Delete annotations
- ❌ Create/edit notes
- ❌ Start new analyses
- ❌ Modify summaries
- ❌ Change corpus settings

## Testing Read-Only Mode

### Unit Tests
```typescript
describe('Read-Only Mode', () => {
  it('should prevent annotation creation', () => {
    render(<DocumentKnowledgeBase readOnly={true} />);
    // Select text
    selectText('sample text');
    // Verify no annotation menu appears
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  it('should hide edit buttons', () => {
    render(<UnifiedKnowledgeLayer readOnly={true} />);
    expect(screen.queryByText('Edit Summary')).not.toBeInTheDocument();
  });
});
```

### Integration Tests
```typescript
it('should enforce read-only when user lacks permissions', () => {
  const mockPermissions = ['CAN_READ']; // No UPDATE
  render(
    <MockedProvider mocks={[mockWithPermissions(mockPermissions)]}>
      <DocumentKnowledgeBase documentId="123" corpusId="456" />
    </MockedProvider>
  );
  // Verify read-only behavior
});
```

### E2E Tests
```typescript
test('read-only mode prevents modifications', async ({ page }) => {
  // Login as read-only user
  await loginAsReadOnlyUser(page);

  // Navigate to document
  await page.goto('/documents/123');

  // Try to select text for annotation
  await page.selectText('sample text');

  // Verify no annotation menu
  await expect(page.locator('.annotation-menu')).not.toBeVisible();
});
```

## Migration Guide

### For Existing Components

1. **Add readOnly prop to interface**:
```typescript
interface MyComponentProps {
  // ... existing props
  readOnly?: boolean;
}
```

2. **Conditionally render edit controls**:
```typescript
{!readOnly && (
  <Button onClick={handleEdit}>Edit</Button>
)}
```

3. **Disable interaction handlers**:
```typescript
const handleClick = readOnly ? undefined : () => {
  // Edit logic
};
```

4. **Update styles for read-only state**:
```typescript
cursor: ${props => props.readOnly ? 'default' : 'pointer'};
```

### For New Components

1. Always accept `readOnly` prop
2. Design with read-only mode in mind
3. Provide clear visual feedback
4. Test both modes thoroughly

## Troubleshooting

### Component not respecting read-only mode
1. Verify component receives readOnly prop
2. Check if handlers are conditionally disabled
3. Ensure UI elements are hidden/disabled

### Read-only mode too restrictive
1. Identify view-only features being blocked
2. Separate modification from viewing logic
3. Allow navigation and viewing operations

### Inconsistent read-only behavior
1. Check permission flow from parent
2. Verify all child components receive prop
3. Ensure consistent prop naming (readOnly vs read_only)
