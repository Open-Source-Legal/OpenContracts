# Virtualized Rendering

## PDF Pages

PDF pages are virtualized by `@os-legal/react-contract-annotate`, which
OpenContracts uses to draw PDF and DOCX documents: only the pages in view
plus an overscan are mounted, page heights are cached per zoom, and the
pages holding the selection or the active highlight stay mounted. The
implementation is the library's `src/pdf/PdfViewport.tsx`
([repo](https://github.com/Open-Source-Legal/react-contract-annotate)); how
OpenContracts binds to it is in
[Document Viewer (PDF and DOCX)](../../../../frontend/document_viewer.md).

## Unified Content Feed Virtualization

### Overview

The Unified Content Feed (`UnifiedContentFeed.tsx`) aggregates annotations, relationships, notes, and search results into a single virtualized feed. Unlike the PDF viewer which has fixed page heights, this feed handles **variable-height items** with dynamic content.

### Implementation Approach

We use **react-window v2** with dynamic height measurement for optimal performance with mixed content types.

#### Key Component Structure

```typescript
<AutoSizer>
  {({ height, width }) => (
    <div style={{ position: "relative", width, height }}>
      <List
        listRef={setListRef}
        defaultHeight={height}
        rowCount={virtualItems.length}
        rowHeight={dynamicRowHeight}
        rowComponent={RowComponent}
        overscanCount={5}
      />
    </div>
  )}
</AutoSizer>
```

### Critical Implementation Details

#### 1. Positioned Parent Container (The Tricky Part)

**Problem**: react-window v2 uses `position: absolute` for rows with `transform: translateY()` for positioning. Without a proper positioning context, rows render but remain invisible.

**Solution**: Wrap the List in a div with `position: relative` and explicit dimensions:

```typescript
// CRITICAL: This wrapper provides positioning context for absolute rows
<div style={{ position: "relative", width: `${width}px`, height: `${height}px` }}>
  <List ... />
</div>
```

**Why this matters**: We spent significant debugging time discovering rows were rendering (console logs confirmed) but weren't visible. The issue was the absolutely-positioned rows had no positioned ancestor, causing them to position incorrectly outside the visible area.

#### 2. Dynamic Height Measurement

For variable-height content, we use `useDynamicRowHeight`:

```typescript
const rowHeightManager = useDynamicRowHeight({
  defaultRowHeight: ESTIMATED_HEIGHTS.annotation,
});

const rowHeight = useMemo(() => {
  return {
    ...rowHeightManager,
    getRowHeight: (index: number) => {
      // First check measured height
      const measured = rowHeightManager.getRowHeight(index);
      if (measured !== undefined) return measured;

      // Fallback to smart estimation
      const item = virtualItems[index];
      switch (item.type) {
        case "annotation": {
          const textLength = item.data.rawText?.length || 0;
          // Account for text wrapping at ~50 chars/line
          return ESTIMATED_HEIGHTS.annotation + Math.floor(textLength / 50) * 20;
        }
        case "relationship": {
          // More connections = taller
          const connections = item.data.sourceIds.length + item.data.targetIds.length;
          return ESTIMATED_HEIGHTS.relationship + connections * 10;
        }
        // ... other types
      }
    },
  };
}, [virtualItems, rowHeightManager]);
```

#### 3. Height Estimation Strategy

**Initial estimates** prevent layout shifts during measurement:

```typescript
const ESTIMATED_HEIGHTS = {
  pageHeader: 90,
  note: 200,
  annotation: 160,  // Includes padding (0.875rem) + margin (0.5rem) + content
  relationship: 220,
  search: 140,
};
```

**Content-based adjustments** improve accuracy:
- Text length → extra line height
- Number of relationships → additional row space
- Note content length → proportional height increase

### Debugging Lessons Learned

#### Issue 1: Invisible Rows
- **Symptom**: Console logs showed rows rendering, but nothing visible
- **Diagnosis**: Inspected DOM showed `height: 0px, width: 0px` on row divs
- **Root Cause**: Missing positioned parent for absolute positioning
- **Fix**: Added `position: relative` wrapper with explicit dimensions

#### Issue 2: Overlapping Content
- **Symptom**: Items rendering on top of each other
- **Diagnosis**: Fixed heights (100px) didn't match actual content
- **Root Cause**: Variable content needs dynamic measurement
- **Fix**: Implemented `useDynamicRowHeight` with smart estimation

#### Issue 3: Excessive Spacing
- **Symptom**: Large gaps between items after initial fix
- **Diagnosis**: Over-generous height estimates
- **Root Cause**: Estimates didn't account for actual rendered size
- **Fix**: Dynamic measurement with content-aware fallback estimates

### Performance Characteristics

**Advantages over custom virtualization:**
- No manual scroll event handling
- Automatic visible range calculation
- Built-in overscan management
- Smooth height transitions as content measures

**Trade-offs:**
- Initial render shows estimated heights briefly
- Height measurement happens on first display
- Slight layout shift as measurements complete (minimal with good estimates)

### Best Practices

1. **Always wrap List in positioned container** - Critical for visibility
2. **Provide good height estimates** - Reduces measurement-induced layout shifts
3. **Use content-aware estimation** - Text length, connection count, etc.
4. **Set appropriate overscan** - Balance smoothness vs. performance (we use 5)
5. **Maintain listRef** - Enables programmatic scrolling to specific items

### Testing Approach

When debugging virtualization issues:

1. **Check console for render calls** - Are components being invoked?
2. **Inspect DOM for positioning** - Look for `position: absolute` and `transform`
3. **Verify container hierarchy** - Positioned parent present?
4. **Test with simple content** - Use colored divs to isolate rendering vs. content issues
5. **Monitor height estimates** - Log estimated vs. measured heights

## Future Enhancements

1. **Dynamic overscan** - Adjust based on scroll velocity
2. **Progressive rendering** - Low-res preview while scrolling
3. **Intersection Observer** - More efficient visibility detection
4. **Memory pressure handling** - Reduce overscan under memory constraints
5. **Predictive preloading** - Anticipate scroll direction
