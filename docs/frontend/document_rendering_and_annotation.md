# Document Rendering and Annotation

## Overview

The `DocumentKnowledgeBase` component is responsible for rendering documents and enabling annotation functionality. It automatically selects the appropriate renderer based on the document's file type and provides a unified annotation experience across different document formats.

## Renderer Selection

The component chooses between two renderers based on the document's `fileType`:

### PDF Renderer
- **File types**: `application/pdf`
- **Component**: `PDF` (from `components/annotator/renderers/pdf/PDF.tsx`)
- **When selected**: When `document.fileType === "application/pdf"` and a PDF file URL is available

### Text Renderer
- **File types**: `application/txt`, `text/plain`
- **Component**: `TxtAnnotator` (wrapped by `TxtAnnotatorWrapper`)
- **When selected**: When `document.fileType === "application/txt"` or `"text/plain"` and a text extract file is available

The selection logic can be found in `DocumentKnowledgeBase.tsx` around lines 1003-1064:

```typescript
if (metadata.fileType === "application/pdf") {
  // Render PDF component
} else if (metadata.fileType === "application/txt" || metadata.fileType === "text/plain") {
  // Render TxtAnnotator component
} else {
  // Show unsupported file type message
}
```

## How Annotation Works

### PDF Annotation

1. **Token-based System**: PDFs use a PAWLS format that provides token-level information for each page
2. **Page Structure**: Each page is rendered as a canvas with an overlay for annotations
3. **Selection**: Users click and drag to select tokens on the page
4. **Creation Flow**:
   - User selects text by clicking and dragging
   - `SelectionBoundary` component detects the selection
   - Selection is converted to token indices
   - `createAnnotationHandler` is called with the annotation data
   - Annotation is sent to the backend via GraphQL mutation

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

## Common Features

Both renderers support:
- Multiple annotation labels with different colors
- Annotation selection and highlighting
- Search result highlighting
- Chat source highlighting
- Hover effects showing annotation labels
- Context menus for editing/deleting annotations
