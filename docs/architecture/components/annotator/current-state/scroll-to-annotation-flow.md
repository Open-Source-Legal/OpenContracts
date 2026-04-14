# Scroll-to-Annotation Flow Documentation

## Overview

The PDF annotation system implements a sophisticated mechanism to automatically scroll to and highlight annotations when the document loads. This can be triggered by URL parameters, direct props, or programmatic selection. The system uses a two-phase approach to ensure smooth and accurate scrolling even with virtualized rendering.

## Entry Points

### 1. URL Parameters
When navigating to a document URL with annotation parameters:
```
/corpus/{corpusId}/document/{documentId}?ann=annotation1,annotation2
```

The `DocumentKBRoute` component extracts these IDs and passes them as `initialAnnotationIds` to `DocumentKnowledgeBase`.

### 2. Direct Props
Components can directly pass annotation IDs:
```typescript
<DocumentKnowledgeBase
  documentId={documentId}
  corpusId={corpusId}
  initialAnnotationIds={["ann-123", "ann-456"]}
  onClose={handleClose}
/>
```

### 3. Programmatic Selection
Other components can trigger selection by calling:
```typescript
setSelectedAnnotations(["ann-123"]);
```

## Complete Flow Sequence

### Phase 0: Initialization

1. **DocumentKnowledgeBase Mounts**
   - Receives `initialAnnotationIds` prop (if provided)
   - Sets up all necessary state atoms
   - Initiates GraphQL query for document data

2. **Initial Annotation Selection** (if IDs provided)
   ```typescript
   // In DocumentKnowledgeBase.tsx
   useEffect(() => {
     if (initialAnnotationIds && initialAnnotationIds.length > 0) {
       setSelectedAnnotations(initialAnnotationIds);
     }
   }, [initialAnnotationIds, setSelectedAnnotations]);
   ```

3. **URL Synchronization**
   - `CentralRouteManager` keeps URL and selection in sync (the earlier `useUrlAnnotationSync()` hook was removed as redundant — it created competing sync loops)
   - If URL has `?ann=...`, CentralRouteManager updates `selectedAnnotationIds` atom
   - If selection changes, CentralRouteManager updates the URL

### Phase 1: Page-Level Scrolling (PDF.tsx)

Once annotations are selected and the PDF is loaded:

1. **Calculate Target Page**
   ```typescript
   const selectedPageIdx = useMemo(() => {
     if (selectedAnnotations.length === 0) return undefined;
     const annot = allAnnotations.find((a) => a.id === selectedAnnotations[0]);
     return annot?.page; // Zero-based page index
   }, [selectedAnnotations, allAnnotations]);
   ```

2. **Ensure Page is Visible**
   - The virtualization system expands its range to include the selected page:
   ```typescript
   // In calcRange()
   if (selectedPageIdx !== undefined) {
     start = Math.min(start, selectedPageIdx);
     end = Math.max(end, selectedPageIdx);
   }
   ```

3. **Scroll to Page**
   ```typescript
   useEffect(() => {
     // No selection or no height data yet
     if (selectedAnnotations.length === 0 || pageHeights.length === 0) return;
     if (selectedPageIdx === undefined) return;

     const targetId = selectedAnnotations[0];

     // Scroll container so target page is visible
     const topOffset = Math.max(0, cumulative[selectedPageIdx] - 32);
     getScrollElement().scrollTo({ top: topOffset, behavior: "smooth" });

     // Tell PDFPage to center the annotation
     setPendingScrollId(targetId);
   }, [selectedAnnotations, selectedPageIdx, pageHeights, cumulative, zoomLevel]);
   ```

### Phase 2: Element-Level Scrolling (PDFPage.tsx)

Once the page is rendered and visible:

1. **Check for Pending Scroll**
   - Each PDFPage checks if it owns the pending annotation
   - Uses the `pendingScrollAnnotationIdAtom` set by PDF.tsx

2. **Find and Scroll to Element**
   ```typescript
   useEffect(() => {
     if (!hasPdfPageRendered) return;

     if (pendingScrollId) {
       // Check if this page owns the annotation
       const pageOwnsAnnotation = visibleAnnotations.some(
         (a) =>
           a instanceof ServerTokenAnnotation &&
           a.id === pendingScrollId &&
           a.json[pageIndex] !== undefined
       );
       if (!pageOwnsAnnotation) return;

       // Try to find and scroll to the element
       let cancelled = false;
       const tryScrollAnnot = () => {
         if (cancelled) return;
         const el = document.querySelector(
           `.selection_${pendingScrollId}`
         ) as HTMLElement | null;
         if (el) {
           el.scrollIntoView({ behavior: "smooth", block: "center" });
           setPendingScrollId(null); // Clear pending
         } else {
           requestAnimationFrame(tryScrollAnnot); // Retry next frame
         }
       };
       tryScrollAnnot();
     }
   }, [hasPdfPageRendered, pendingScrollId, /* ... */]);
   ```

## Key Components and Atoms

### State Atoms
- `selectedAnnotationIdsAtom` - Currently selected annotation IDs
- `pendingScrollAnnotationIdAtom` - Annotation ID waiting to be scrolled to
- `allAnnotationsAtom` - All annotations (computed from pdfAnnotationsAtom)
- `scrollContainerRefAtom` - Reference to the scrolling container

### Hooks
- `useAnnotationSelection()` - Access and update selected annotations
- `CentralRouteManager` - Keeps URL and selection in sync (replaced `useUrlAnnotationSync`)
- `useVisibleAnnotations()` - Get filtered list of visible annotations

### Components
- `DocumentKnowledgeBase` - Top-level component that initializes selection
- `PDF` - Handles page-level scrolling and virtualization
- `PDFPage` - Handles element-level scrolling within a page

## Timing and Dependencies

The scroll happens when ALL of these conditions are met:

1. **Annotations are loaded** - GraphQL query completed and atoms updated
2. **PDF is loaded** - PDF document proxy available
3. **Page heights calculated** - Heights cached for current zoom level
4. **Selection is set** - Either from props, URL, or user action
5. **Target page is rendered** - Virtualization includes the page

## Edge Cases and Considerations

### 1. Non-existent Annotations
If an annotation ID doesn't exist in the document:
- Page-level scroll is skipped (selectedPageIdx undefined)
- No error is thrown - fails silently

### 2. Multiple Selections
Only the first selected annotation is scrolled to:
```typescript
const targetId = selectedAnnotations[0];
```

### 3. Zoom Changes
Scrolling is retriggered when zoom changes because:
- Page heights change
- Cumulative positions change
- Annotation positions within pages change

### 4. Priority System
The system handles multiple scroll types with priority:
```typescript
/* 1️⃣  SEARCH (highest priority) */
if (pendingScrollSearchId) { /* ... */ }

/* 2️⃣  CHAT SOURCE */
if (pendingScrollChatSourceKey) { /* ... */ }

/* 3️⃣  NORMAL ANNOTATION */
if (pendingScrollId) { /* ... */ }
```

### 5. Retry Mechanism
If the annotation element isn't found immediately:
```typescript
requestAnimationFrame(tryScrollAnnot); // Retry next frame
```

This handles cases where React hasn't rendered the element yet.

## Performance Optimizations

1. **Memoized Calculations** - Page indices are only recalculated when dependencies change
2. **Debounced Scrolling** - Uses `requestAnimationFrame` for smooth performance
3. **Single Scroll Operation** - Combines container and element scrolling efficiently
4. **Cleanup on Unmount** - Clears pending scroll IDs and selected annotations

## Testing Considerations

When testing scroll-to-annotation:

1. **Mock the GraphQL response** with annotations that have proper page indices
2. **Wait for PDF to render** before expecting scroll behavior
3. **Check both phases** - page visibility and element centering
4. **Test edge cases** - non-existent IDs, multiple selections, zoom changes

## Example Usage

```typescript
// Route with annotation ID in URL
<Route
  path="/corpus/:corpusId/document/:documentId"
  element={<DocumentKBRoute />}
/>

// Direct component usage
<DocumentKnowledgeBase
  documentId="doc-123"
  corpusId="corpus-456"
  initialAnnotationIds={["annotation-789"]}
  onClose={() => navigate(-1)}
/>
```

The system will automatically:
1. Load the document and annotations
2. Select the specified annotation
3. Scroll the page into view
4. Center the annotation on screen
5. Update the URL to reflect the selection
