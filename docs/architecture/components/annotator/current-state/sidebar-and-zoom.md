# Sidebar and Auto-Zoom Documentation

## Overview
The document viewer features a resizable right sidebar (chat/feed panel) with automatic zoom adjustment to maintain consistent document proportions when the viewport changes. The sidebar pushes document content to the side on desktop while maintaining an overlay mode on mobile.

## Layout Architecture

### Desktop Layout (≥769px)
```
ContentArea (full width)
  ├─ FloatingInputWrapper (absolute, offset by panelWidth)
  └─ MainContentArea (position: relative)
      ├─ document-layer (width: 100 - panelWidth%)
      │   └─ PDFContainer (inherits constrained width)
      └─ SlidingPanel (absolute, right: 0, width: panelWidth%)
```

**Key Behavior:**
- Document area shrinks via `width: ${100 - panelWidth}%`
- Sidebar sits absolutely positioned at right edge
- Smooth 0.3s cubic-bezier transition on width changes
- Floating controls offset by `panelWidthPx` to avoid overlap

### Mobile Layout (≤768px)
```
ContentArea (full width)
  └─ MainContentArea
      ├─ document-layer (width: 100%)
      └─ SlidingPanel (fixed, inset: 0, full-screen overlay)
```

**Key Behavior:**
- Document stays full width
- Sidebar uses `position: fixed` with full-screen overlay
- No auto-zoom adjustments on mobile

## Sidebar Width Management

### Width Modes
Managed via `useChatPanelWidth()` hook:
```typescript
type PanelMode = "quarter" | "half" | "full" | "custom";

const getPanelWidthPercentage = (): number => {
  switch (mode) {
    case "quarter": return 25;
    case "half": return 50;
    case "full": return 90;
    case "custom": return customWidth || 50;
  }
};
```

### Resize System
Lines 1387-1441 in DocumentKnowledgeBase.tsx:

```typescript
// Drag handlers with snap-to-preset logic
handleResizeStart(e) {
  setIsDragging(true);
  setDragStartX(e.clientX);
  setDragStartWidth(getPanelWidthPercentage());
}

handleResizeMove(e) {
  const deltaX = dragStartX - e.clientX;
  const deltaPercent = (deltaX / window.innerWidth) * 100;
  let newWidth = dragStartWidth + deltaPercent;

  // Snap to presets within 3% threshold
  const snapThreshold = 3;
  if (Math.abs(newWidth - 25) < snapThreshold) setMode("quarter");
  else if (Math.abs(newWidth - 50) < snapThreshold) setMode("half");
  else if (Math.abs(newWidth - 90) < snapThreshold) setMode("full");
  else {
    setMode("custom");
    setCustomWidth(Math.max(20, Math.min(95, newWidth)));
  }
}
```

## Auto-Zoom System

### Core Concept
When the sidebar opens/resizes, the document viewport shrinks. Auto-zoom proportionally reduces zoom level to maintain the same visual document width relative to the available space.

### State Management
```typescript
const [autoZoomEnabled, setAutoZoomEnabled] = useState<boolean>(true);
const baseZoomRef = useRef<number>(zoomLevel);
const isAdjustingZoomRef = useRef<boolean>(false);
const justToggledAutoZoomRef = useRef<boolean>(false);
const prevAutoZoomEnabledRef = useRef<boolean>(autoZoomEnabled);
```

**baseZoomRef**: The "target" zoom when sidebar is closed
**isAdjustingZoomRef**: Prevents infinite loops during programmatic zoom changes
**justToggledAutoZoomRef**: Prevents immediate adjustment when toggle is enabled
**prevAutoZoomEnabledRef**: Tracks toggle state changes

### Zoom Calculation (Lines 731-776)
```typescript
useEffect(() => {
  if (!autoZoomEnabled || isMobile || activeLayer !== "document") return;
  if (justToggledAutoZoomRef.current || isAdjustingZoomRef.current) return;

  const panelWidth = getPanelWidthPercentage();

  if (showRightPanel) {
    // Store base zoom on first open
    if (baseZoomRef.current === zoomLevel || !baseZoomRef.current) {
      baseZoomRef.current = zoomLevel;
    }

    // Calculate adjusted zoom
    const viewportReduction = (100 - panelWidth) / 100;
    const adjustedZoom = baseZoomRef.current * viewportReduction;
    const clampedZoom = Math.max(0.5, Math.min(4, adjustedZoom));

    if (Math.abs(zoomLevel - clampedZoom) > 0.01) {
      isAdjustingZoomRef.current = true;
      setZoomLevel(clampedZoom);
    }
  } else {
    // Restore base zoom when sidebar closes
    if (baseZoomRef.current && Math.abs(zoomLevel - baseZoomRef.current) > 0.01) {
      isAdjustingZoomRef.current = true;
      setZoomLevel(baseZoomRef.current);
    }
  }
}, [autoZoomEnabled, showRightPanel, mode, customWidth, ...]);
```

### Manual Zoom Tracking (Lines 778-798)
When user manually zooms while sidebar is open, back-calculate the base zoom:
```typescript
useEffect(() => {
  if (!autoZoomEnabled || isMobile || isAdjustingZoomRef.current) return;

  if (showRightPanel && activeLayer === "document") {
    // User manually changed zoom - back-calculate base
    const panelWidth = getPanelWidthPercentage();
    const viewportReduction = (100 - panelWidth) / 100;
    const backCalculatedBase = zoomLevel / viewportReduction;
    baseZoomRef.current = Math.max(0.5, Math.min(4, backCalculatedBase));
  } else if (!showRightPanel) {
    // Sidebar closed - keep baseZoom in sync
    baseZoomRef.current = zoomLevel;
  }
}, [autoZoomEnabled, zoomLevel, showRightPanel, ...]);
```

### Toggle Behavior (Lines 715-729)
When auto-zoom is toggled ON, capture current zoom as new base:
```typescript
useEffect(() => {
  const wasDisabled = !prevAutoZoomEnabledRef.current;
  const isNowEnabled = autoZoomEnabled;

  if (wasDisabled && isNowEnabled) {
    // User toggled ON - use current zoom as base
    baseZoomRef.current = zoomLevel;
    justToggledAutoZoomRef.current = true; // Skip next adjustment cycle
  }

  prevAutoZoomEnabledRef.current = autoZoomEnabled;
}, [autoZoomEnabled, zoomLevel]);
```

## Container Width Synchronization

### ResizeObserver (Lines 688-705)
Watches PDF container for width changes and updates `containerWidth` state:
```typescript
useEffect(() => {
  const node = pdfContainerRef.current;
  if (!node) return;

  const resizeObserver = new ResizeObserver((entries) => {
    for (const entry of entries) {
      const newWidth = entry.contentRect.width;
      setContainerWidth(newWidth);
    }
  });

  resizeObserver.observe(node);
  return () => resizeObserver.disconnect();
}, [setContainerWidth]);
```

**Why it's needed:**
The PDF viewer (`<PdfAnnotatorWrapper containerWidth={containerWidth} />`) uses the pixel width for its first fit-to-width zoom. When the sidebar opens or closes, the container width changes and the viewer's root takes the new width.

## Floating Controls Offset

### Calculation (Lines 385-402)
```typescript
const calculateFloatingControlsState = () => {
  if (isMobile || !showRightPanel || activeLayer !== "document") {
    return { offset: 0, visible: true };
  }

  const panelWidthPercent = getPanelWidthPercentage();
  const windowWidth = window.innerWidth;
  const panelWidthPx = (panelWidthPercent / 100) * windowWidth;
  const remainingSpacePercent = 100 - panelWidthPercent;
  const remainingSpacePx = windowWidth - panelWidthPx;

  // Hide controls if < 10% viewport or < 100px remaining
  const shouldHide = remainingSpacePercent < 10 || remainingSpacePx < 100;

  return {
    offset: shouldHide ? 0 : panelWidthPx,
    visible: !shouldHide,
  };
};
```

**Applied to:**
- `FloatingInputWrapper` - search/chat input
- `EnhancedLabelSelector` - label selection UI
- `FloatingDocumentControls` - settings/analyses/extracts buttons
- `FloatingAnalysesPanel` - analyses overlay
- `FloatingExtractsPanel` - extracts overlay

All floating elements shift left by `offset` pixels to remain visible when sidebar opens.

## User Controls

### Auto-Zoom Toggle
Located in `FloatingDocumentControls` settings panel (gear icon):
```typescript
<ControlItem>
  <ControlLabel>
    <Maximize2 />
    Auto-Zoom Sidebar
  </ControlLabel>
  <StyledCheckbox
    toggle
    checked={autoZoomEnabled}
    onChange={() => onAutoZoomChange?.(!autoZoomEnabled)}
  />
</ControlItem>
```

**Enabled (default):** Document auto-zooms when sidebar opens/closes
**Disabled:** Document width adjusts but zoom stays fixed at user's manual setting

### Panel Width Control
Located in floating controls (columns icon when sidebar is open):
- **Compact (25%)** - Minimal sidebar width
- **Standard (50%)** - Default balanced width
- **Wide (90%)** - Maximum sidebar width
- **Custom** - User-dragged width via resize handle

## Example Scenarios

### Scenario 1: Opening Sidebar
1. User has zoom at 138%, sidebar closed
2. Click chat tab → sidebar opens at 50% width
3. Auto-zoom: `baseZoomRef = 1.38`, `adjustedZoom = 1.38 × 0.5 = 0.69` (69%)
4. Document shrinks to 50% width but maintains same proportional size

### Scenario 2: Resizing Sidebar
1. Sidebar open at 50%, zoom at 69%
2. User drags resize handle to 25% width
3. Auto-zoom: `adjustedZoom = 1.38 × 0.75 = 1.035` (103.5%)
4. Document expands to 75% width, zoom increases proportionally

### Scenario 3: Manual Zoom with Sidebar Open
1. Sidebar open at 50%, auto-zoom at 69%
2. User manually zooms to 80%
3. Back-calculate: `baseZoom = 0.8 / 0.5 = 1.6`
4. Close sidebar → zoom restores to 160% (user's intended base zoom)

### Scenario 4: Toggling Auto-Zoom
1. User disables auto-zoom, manually sets zoom to 120%, sidebar at 50%
2. User enables auto-zoom
3. `baseZoomRef` captures current 120% (not old base)
4. Next sidebar resize uses 120% as baseline

## Technical Notes
- Sidebar uses Framer Motion with spring physics for smooth animations
- Width transitions use `cubic-bezier(0.4, 0, 0.2, 1)` easing for consistency
- Zoom adjustments only occur on desktop (no mobile auto-zoom)
- All floating UI elements respect sidebar offset to prevent overlap
- ResizeObserver provides reactive width updates to PDF renderer
- Base zoom tracking ensures user intent is preserved across sidebar toggles
