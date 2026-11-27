# Document Rendering and Annotation

> **Note**: For permission-related aspects of document rendering and annotations, see the [Consolidated Permissioning Guide](../permissioning/consolidated_permissioning_guide.md) - comprehensive documentation covering permission flows, document-level access control, corpus-level permissions, and component integration patterns.

## Overview

The `DocumentKnowledgeBase` component is responsible for rendering documents and enabling annotation functionality. It selects a viewer by the document's file type and provides a unified annotation experience across formats. PDF and DOCX are drawn by `@os-legal/react-contract-annotate`, bound to OpenContracts' state as described in [Document Viewer (PDF and DOCX)](./document_viewer.md); plain text is drawn by OpenContracts' own `TxtAnnotator`.

## Renderer Selection

[`DocumentViewer.tsx`](../../frontend/src/components/knowledge_base/document/document_kb/DocumentViewer.tsx) picks the viewer by `fileType`:

| File type | Viewer |
|---|---|
| `application/pdf` | `PdfAnnotatorWrapper` (`@os-legal/react-contract-annotate`'s `PdfAnnotator`) |
| DOCX | `DocxAnnotatorWrapper` (the library's `DocxAnnotator`) |
| Markdown | `MarkdownDocumentViewer` |
| `text/plain`, `application/txt` | `TxtAnnotatorWrapper` (`TxtAnnotator`) |

Any other type shows an "Unsupported File" state.

## How Annotation Works

### PDF and DOCX Annotation

PDFs are token based (PAWLS tokens per page); DOCX annotations are character
spans into the parser's text. In both, the user drags (PDF) or selects text
(DOCX), the library reports the selection, and OpenContracts' selection menu
(`annotator/bindings/AnnotationSelectionMenu.tsx`) offers the actions below.
Apply Label turns the selection into a `ServerTokenAnnotation` /
`ServerSpanAnnotation` and calls `createAnnotationHandler`, which persists it
through GraphQL. See [Document Viewer (PDF and DOCX)](./document_viewer.md).

### Selection Action Menu

After selecting text in any document type, users see an intelligent context menu:

#### Menu Options

| Action | Description | Keyboard Shortcut | Availability |
|--------|-------------|-------------------|--------------|
| Copy Text | Copies selected text to clipboard | C | Always available |
| Copy Link | Copies a `?tb=` deep link to the selection | L | Always available (PDF, DOCX, text) |
| Add link… | Creates an OC_URL link annotation | — | PDF, when permissions granted |
| Apply Label | Creates annotation with active label | A | When label selected & permissions granted |
| Cancel | Dismisses selection | ESC | Always available |

#### Intelligent Guidance

The menu provides contextual help based on the current state:

- **No Labelset**: "No labelset configured - Click the label selector (bottom right) to create one"
- **No Labels**: "No labels available - Click the label selector to create labels"
- **No Active Label**: "Select a label to annotate - Click the label selector (bottom right)"
- **Read-Only Mode**: "Document is read-only"
- **No Permissions**: "No corpus permissions"

#### Multi-Page Selection

Users can create annotations spanning multiple pages:

1. Click and drag to select text on the first page
2. Hold Shift key and continue selecting on subsequent pages
3. Release to see the action menu
4. Choose action to apply to entire multi-page selection

The system maintains separate selection queues per page and combines them into a single annotation with proper page mapping.

### Text Annotation

1. **Character-based System**: Text documents use character offsets (start/end indices) for annotations
2. **Span-based Rendering**: Text is broken into spans based on annotation boundaries
3. **Selection**: Users click and drag to select text
4. **Creation Flow**:
   - User selects text with mouse
   - `handleMouseUp` event captures the selection
   - Browser's Selection API provides the selected text and range
   - Global character offsets are calculated from the selection
   - `getSpan` creates a new `ServerSpanAnnotation` object
   - `createAnnotation` is called to persist the annotation

## Key Differences

| Feature | PDF | Text |
|---------|-----|------|
| Selection Unit | Tokens | Characters |
| Position Storage | Bounding boxes + token IDs | Start/end character indices |
| Rendering | Canvas + overlay | HTML spans with styling |
| Multi-page | Yes (virtualized scrolling) | No (single continuous text) |
| Visual Feedback | Highlight boxes on tokens | Background color on text spans |

## Annotation Data Structure

Both renderers create annotations that include:
- Label information (type, color, text)
- Position data (format depends on document type)
- Permissions (can_update, can_remove, etc.)
- Metadata (creator, created date, etc.)

The annotations are stored in the `pdfAnnotationsAtom` and synchronized with the backend through GraphQL mutations.

## Smart Label Management

### Overview

The Smart Label System provides an intelligent, streamlined approach to managing annotation labels directly from the document view. This eliminates the need to navigate away from your document to create labels or labelsets.

### Key Features

1. **Inline Label Creation**: Create new labels without leaving the document
2. **Automatic Labelset Management**: System automatically creates labelsets when needed
3. **Smart Search**: Search existing labels with partial, case-insensitive matching
4. **Type-Aware Labels**: Automatically determines label type based on document format

### How It Works

#### Label Selection and Creation Flow

1. **Opening the Label Selector**
   - Click the label selector button (tag icon) in the bottom-right corner
   - The selector expands to show available labels and a search field

2. **Searching for Labels**
   - Start typing in the search field
   - Results update in real-time with partial, case-insensitive matching
   - If no match is found, a "Create" option appears

3. **Creating New Labels**
   - When no labelset exists:
     - System prompts to create both labelset and label
     - Labelset is automatically named based on corpus title
     - Single operation creates all necessary components
   - When labelset exists:
     - Click "Create [label name]" from search results
     - Enter color and description (optional)
     - Label is immediately available for use

### Smart Mutation System

The system uses a unified `smartLabelSearchOrCreate` GraphQL mutation that:

```graphql
mutation SmartLabelSearchOrCreate(
  $corpusId: String!
  $searchTerm: String!
  $labelType: String!
  $createIfNotFound: Boolean
) {
  smartLabelSearchOrCreate(
    corpusId: $corpusId
    searchTerm: $searchTerm
    labelType: $labelType
    createIfNotFound: $createIfNotFound
  ) {
    labels { id, text, color }
    labelset { id, title }
    labelCreated
    labelsetCreated
  }
}
```

This single mutation handles:
- Searching for existing labels
- Creating new labels
- Creating labelsets when needed
- Updating corpus associations
- All in a single atomic transaction

### Context-Aware Guidance

When annotation conditions aren't met, the system provides helpful guidance:

| Condition | Message | Action |
|-----------|---------|--------|
| No labelset | "No labelset configured" | Prompts to create labelset |
| No labels | "No labels available" | Guides to label creation |
| No label selected | "Select a label to annotate" | Points to label selector |
| Read-only mode | "Document is read-only" | Explains restriction |
| No permissions | "No corpus permissions" | Indicates permission issue |

### Label Types by Document Format

The system automatically selects the appropriate label type:

- **PDF Documents**: Token labels (word/phrase level)
- **Text Documents**: Span labels (character range)
- **Document Labels**: Apply to entire document (available for all formats)

## Virtualized Rendering

PDF pages are virtualized by the library (only the visible pages plus an
overscan are mounted; pages holding the selection or the active highlight
stay mounted). See `src/pdf/PdfViewport.tsx` in
[react-contract-annotate](https://github.com/Open-Source-Legal/react-contract-annotate).

## State Management Architecture

The annotation system uses Jotai atoms for efficient, reactive state management:

### Core Atoms

#### Annotation Storage
- **`pdfAnnotationsAtom`**: Main storage container holding a `PdfAnnotations` object with three arrays:
  - `annotations`: Regular annotations (excludes structural)
  - `relations`: Array of `RelationGroup` objects representing relationships between annotations
  - `docTypes`: Document-level type annotations
  - `unsavedChanges`: Boolean flag for dirty state tracking
- **`structuralAnnotationsAtom`**: Separate storage for structural annotations
- **`allAnnotationsAtom`**: Computed atom that merges both sources with de-duplication
- **`perPageAnnotationsAtom`**: Computed map of `pageIndex → annotations[]` for efficient page-level access
- **`initialAnnotationsAtom`**: Stores the initial annotation state for change detection

#### Document State
- **`selectedDocumentAtom`**: Current document metadata
- **`pdfDocAtom`**: PDF.js document proxy instance
- **`pagesAtom`**: Map of page number to PDFPageInfo objects
- **`viewStateAtom`**: Loading/loaded/error state
- **`scrollContainerRefAtom`**: The viewer's container (plain text and Markdown scroll it; for PDF/DOCX it only frames the viewer, which scrolls its own root)

#### Navigation & Scrolling
- **`annotatorHandleAtom`**: The mounted PDF/DOCX viewer's handle, for moving it without changing the selection
- Selecting annotations or changing the active highlight scrolls the viewer by itself (see [Document Viewer](./document_viewer.md#scrolling))

### Key Hooks

```typescript
// Returns de-duplicated list of all annotations
useAllAnnotations(): (ServerTokenAnnotation | ServerSpanAnnotation)[]

// Returns annotations for a specific page
usePageAnnotations(pageIndex: number): Annotation[]

// Returns filtered annotations based on UI settings
useVisibleAnnotations(): Annotation[]

// Manages annotation creation and updates
useCreateAnnotation(): (annotation: Annotation) => Promise<void>

// Returns the full PdfAnnotations object including relations
usePdfAnnotations(): { pdfAnnotations: PdfAnnotations }
```

### Data Flow

1. **Load**: Document data fetched → processed into atoms
2. **Filter**: UI settings modify visible annotations via computed atoms
3. **Render**: Components subscribe to relevant atoms for reactive updates
4. **Update**: User actions trigger atom updates → automatic re-renders

### PdfAnnotations Container

The `PdfAnnotations` class serves as an immutable container for all annotation-related data:

```typescript
class PdfAnnotations {
  constructor(
    public readonly annotations: (ServerTokenAnnotation | ServerSpanAnnotation)[],
    public readonly relations: RelationGroup[],
    public readonly docTypes: DocTypeAnnotation[],
    public readonly unsavedChanges: boolean = false
  )
}
```

All updates create new instances, ensuring React's change detection works correctly.

## Unified Filtering System

The system implements a unified, atom-based filtering architecture that ensures consistency between annotations and relationships across all components.

### Core Principles

1. **Single Source of Truth**: All filtering state is managed through Jotai atoms in `UISettingsAtom`
2. **Consistent Behavior**: Annotations and relationships follow the same filtering rules
3. **Reactive Updates**: Filter changes immediately propagate to all consuming components

### Filter Layers

#### 1. Forced Visibility (Highest Priority)
Content that must always be shown regardless of other filters:
- Currently selected annotations and relationships
- Annotations involved in selected relationships
- Structural annotations when relationships are visible

#### 2. Standard Filters
Applied in order to remaining content:
- **Structural Toggle**: Hide/show structural annotations AND relationships
- **Label Filter**: Show only content with selected labels
- **Selected Only Mode**: Show only explicitly selected items and their connections

#### 3. Visibility Hooks

The system provides two primary hooks for filtered content:

```typescript
// For annotations
const visibleAnnotations = useVisibleAnnotations();

// For relationships
const visibleRelationships = useVisibleRelationships();
```

Both hooks read from the same underlying atom state, ensuring consistency.

### Relationship Filtering Logic

The `useVisibleRelationships()` hook applies the following rules:

1. **Always show selected relationships** (forced visibility)
2. **Filter structural relationships** based on `showStructural` setting
3. **In selected-only mode**, only show relationships connected to selected annotations
4. **Only show relationships with visible annotations** (prevents orphaned relationships)

### State Management Flow

```
User Action (e.g., toggle filter)
    ↓
UISettingsAtom updated
    ↓
useVisibleAnnotations() & useVisibleRelationships() recompute
    ↓
All consuming components re-render with filtered data
```

### Component Integration

- **FloatingDocumentControls**: Updates atom state via `AnnotationControls`
- **UnifiedContentFeed**: Consumes filtered data via visibility hooks
- **PDF/DOCX viewer**: Receives the same display settings; the library applies the visibility rules of `useVisibleAnnotations()`
- **TxtAnnotator**: Uses `useVisibleAnnotations()` for rendering
- **RelationshipList**: Uses `useVisibleRelationships()` for display

This unified approach eliminates the previous disconnect between prop-based and atom-based filtering, ensuring that all UI components show consistent filtered content.

## Scroll Synchronization

The PDF/DOCX viewer scrolls when the selected annotations change (to the
first one), when the active highlight changes, and on handle calls. The
active highlight is the picked chat source (the first when none is picked),
else the current search hit, else the `?tb=` text block. See
[Document Viewer](./document_viewer.md#scrolling).

## Zoom System

### Control Methods

Users can adjust zoom through multiple interfaces:

#### Keyboard Shortcuts
- **Ctrl/Cmd + Plus**: Zoom in (10% increment)
- **Ctrl/Cmd + Minus**: Zoom out (10% decrement)
- **Ctrl/Cmd + 0**: Reset to 100%

#### Mouse Controls
- **Ctrl/Cmd + Scroll Wheel**: Smooth zoom with mouse position as anchor

#### UI Controls
- Zoom control buttons with visual feedback
- Zoom indicator showing current level (appears briefly during zoom)

### Zoom Behavior

- **Range**: 50% (0.5x) to 400% (4x)
- **Initial Zoom**: Automatically fits page width to container
- **Persistence**: Zoom level maintained across page navigation
- **Performance**: All visible pages rescale simultaneously
- **Feedback**: Temporary zoom indicator shows current percentage

### Zoom Flow Architecture

The zoom system implements a sophisticated multi-layer architecture for efficient scaling of large documents:

#### 1. State Management
- **Storage**: Zoom level stored in `UISettingsAtom`, accessed via `useZoomLevel()` hook
- **Initial Value**: Calculated to fit page width to container width
- **Range Enforcement**: Clamped between 0.5 (50%) and 4.0 (400%)

#### 2. Input Handling ([`DocumentKnowledgeBase.tsx`](../../frontend/src/components/knowledge_base/document/DocumentKnowledgeBase.tsx))
All zoom inputs converge through a single `setZoomLevel()` call:
```typescript
// Keyboard: handleKeyboardZoom
// Mouse wheel: handleWheelZoom
// UI buttons: ZoomControls component
setZoomLevel(newZoom);
showZoomFeedback(); // Shows temporary zoom indicator
```

#### 3. Rendering at the New Zoom
The viewer's zoom is controlled by `zoomLevelAtom`; page-height caching,
coordinated re-rendering and render cancellation at the new scale are the
library's (`src/pdf/PdfViewport.tsx`).

## Permission Hierarchy

The system implements a clear permission hierarchy for annotation operations:

### Requirements for Annotation Creation

1. **Corpus Context**: Document must belong to a corpus (corpusId present)
2. **Permission Check**: User must have either:
   - Corpus update permissions (`canUpdateCorpus`), OR
   - Document update permissions (`CAN_UPDATE`)
3. **Mode Check**: Document must not be in read-only mode

### Permission Feedback

When permissions are insufficient, the system provides clear feedback:
- **No Corpus**: "Add document to corpus to create annotations"
- **Read-Only**: "Document is read-only"
- **No Permissions**: "No corpus permissions"

### Permission Sources

Permissions are derived from:
1. Corpus-level permissions (primary)
2. Document-level permissions (fallback)
3. Explicit read-only flag (override)

## Error Handling

The system implements comprehensive error handling for robustness:

### File Type Errors
- **Unsupported Types**: Shows dedicated message with file type info
- **Fallback**: Gracefully degrades to basic file info display

### Data Loading Errors
- **PAWLS Data Missing**: Continues without token mapping (selection disabled)
- **PDF Load Failure**: Shows error state with retry option
- **Text Extract Missing**: Falls back to unavailable message

### Network Errors
- **GraphQL Failures**: Toast notifications with error details
- **Retry Logic**: Automatic retry for transient failures
- **User Feedback**: Clear error messages with suggested actions

### Runtime Errors
- **Render Failures**: Caught and logged, page shows error state
- **Selection Errors**: Gracefully handled, selection cleared
- **Scroll Errors**: Logged but don't interrupt user experience

## Common Features

Both renderers support:
- Multiple annotation labels with different colors
- Annotation selection and highlighting
- Search result highlighting
- Chat source highlighting
- Hover effects showing annotation labels
- Context menus for editing/deleting annotations
- Smart label management system

---

*Last Updated: 2026-01-09*
