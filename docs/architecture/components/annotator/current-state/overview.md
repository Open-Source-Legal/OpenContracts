# PDF Annotation System Overview

**Last Updated**: 2026-01-09

## Table of Contents

1. [Key Questions](#key-questions)
2. [High-level Architecture](#high-level-architecture)
3. [Layer System](#layer-system)
4. [Component Hierarchy](#component-hierarchy)
5. [Major Features](#major-features)
6. [Virtualized Rendering System](#virtualized-rendering-system)
7. [State Management](#state-management)
8. [Specific Component Deep Dives](#specific-component-deep-dives)

## Key Questions

### 1. How is the PDF loaded?
- The PDF is loaded in the `DocumentKnowledgeBase` component when it receives document data from the GraphQL query
- The component uses `pdfjs-dist` to load the PDF file specified by `document.pdfFile`
- Loading progress is tracked and displayed to the user
- Once loaded, the PDF document proxy and PAWLS parsing data are combined to create `PDFPageInfo` objects for each page

### 2. Where and how are annotations loaded?
- Annotations are loaded via the `GET_DOCUMENT_KNOWLEDGE_AND_ANNOTATIONS` GraphQL query in `DocumentKnowledgeBase`
- The query fetches:
  - Document metadata and file paths
  - All annotations - returned as two separate arrays:
    - `allAnnotations` - regular user/system annotations
    - `allStructuralAnnotations` - structural markup annotations (sections, paragraphs, etc.)
  - Document type annotations
  - Annotation relationships (with `structural` boolean property)
  - Corpus label information
  - Document notes and relationships
  - Summary version history
- Annotations are processed and stored in separate Jotai atoms:
  - `pdfAnnotationsAtom` - regular annotations only
  - `structuralAnnotationsAtom` - structural annotations only (kept separate to prevent duplication)
  - `allAnnotationsAtom` - computed atom that merges and deduplicates both arrays
  - Each annotation has a `structural: boolean` property for filtering

### 3. Where is the PAWLS layer loaded?
- PAWLS data is loaded alongside the PDF in `DocumentKnowledgeBase`
- The `getPawlsLayer` function fetches the token data from `document.pawlsParseFile`
- PAWLS data provides token-level information for each page, enabling precise text selection and annotation

## High-level Architecture

The PDF annotation system uses a sophisticated dual-layer architecture:

1. **Document Layer**: Traditional PDF/text viewing with annotations
2. **Knowledge Layer**: Summary view with version history and editing

Key architectural components:

1. **Virtualized Rendering**: Only visible pages are rendered for performance
2. **State Management with Jotai**: Centralized, reactive state management
3. **Computed Derivations**: Automatic updates when dependencies change
4. **Unified Feed System**: Combines notes, annotations, relationships in one view
5. **Summary Versioning**: Git-like version control for document summaries
6. **Resizable Panels**: Flexible layout with chat panel width management

## Layer System

The `DocumentKnowledgeBase` implements a dual-layer architecture:

### Document Layer
- PDF/text document viewing with annotations
- Search functionality
- Annotation creation and editing
- Extract and analysis results
- Traditional document interaction

### Knowledge Layer
- Document summary viewing and editing
- Version history browsing
- Markdown-based content
- Knowledge synthesis view

Users can switch between layers based on their current task, with some features (like chat) available in both layers.

## Component Hierarchy

```
DocumentKnowledgeBase
├── Layer Management (activeLayer: "knowledge" | "document")
├── Tab Navigation System
│   ├── Summary (knowledge layer)
│   ├── Chat (both layers)
│   ├── Notes (both layers)
│   ├── Relationships (both layers)
│   ├── Annotations (document layer)
│   ├── Relations (document layer)
│   ├── Search (document layer)
│   ├── Analyses (document layer)
│   └── Extracts (document layer)
├── Document Layer Components
│   ├── PdfAnnotatorWrapper / DocxAnnotatorWrapper
│   │   └── PdfAnnotator / DocxAnnotator (@os-legal/react-contract-annotate)
│   ├── TxtAnnotatorWrapper (for text files)
│   ├── FloatingDocumentControls
│   ├── FloatingDocumentInput
│   └── ZoomControls
├── Knowledge Layer Components
│   ├── UnifiedKnowledgeLayer
│   ├── VersionHistorySidebar
│   └── Markdown Editor/Viewer
├── Shared Components
│   ├── UnifiedContentFeed (feed mode)
│   ├── ChatTray
│   ├── FloatingSummaryPreview (PiP view)
│   └── UnifiedLabelSelector
└── Resizable Right Panel System
```

## Major Features

### 1. Unified Feed System

**Components**: [`UnifiedContentFeed`](../../../../../frontend/src/components/knowledge_base/document/unified_feed/UnifiedContentFeed.tsx), [`SidebarControlBar`](../../../../../frontend/src/components/knowledge_base/document/unified_feed/SidebarControlBar.tsx)

The unified feed combines multiple content types into a single, filterable view:
- Notes
- Annotations
- Relationships
- Search results

Features:
- Filter by content type
- Sort by page order or chronologically
- Seamless switching between chat mode and feed mode
- Real-time updates as content changes

### 2. Summary Version History

**Hook**: `useSummaryVersions` (used in [`DocumentKnowledgeBase.tsx`](../../../../../frontend/src/components/knowledge_base/document/DocumentKnowledgeBase.tsx))

Git-like version control for document summaries:
- View all previous versions
- Compare changes between versions
- Create new versions when editing
- Author and timestamp tracking
- Revert to previous versions

### 3. Floating Summary Preview

**Component**: [`FloatingSummaryPreview`](../../../../../frontend/src/components/knowledge_base/document/floating_summary_preview/FloatingSummaryPreview.tsx)

Picture-in-picture style preview that:
- Shows current summary while in document layer
- Allows quick switching to knowledge layer
- Updates in real-time
- Can be minimized or expanded

### 4. Chat Panel Width Management

**Hook**: `useChatPanelWidth` (defined in [`UISettingsAtom.tsx`](../../../../../frontend/src/components/annotator/context/UISettingsAtom.tsx))

Sophisticated resizable panel system:
- Preset sizes: quarter (25%), half (50%), full (90%)
- Custom width with drag handle
- Auto-minimize when hovering over document
- Persistent width preferences
- Smooth animations

### 5. Tab-based Navigation

**Type**: `SidebarViewMode` (defined in [`frontend/src/components/knowledge_base/document/unified_feed/types.ts`](../../../../../frontend/src/components/knowledge_base/document/unified_feed/types.ts))

The sidebar uses a mode-based navigation system with the following modes:
- `chat` - AI chat interface
- `feed` - Unified content feed with notes, annotations, relationships
- `extract` - Extract results view (when an extract is selected)
- `analysis` - Analysis results view (when an analysis is selected)
- `discussions` - Document discussions/threads

Features:
- Icons and labels for each mode
- Visual indicators for active mode
- Collapsible sidebar on hover
- Mode automatically switches based on user actions (e.g., selecting an extract)

### 6. Note Management System

**Components**: [`NoteModal`](../../../../../frontend/src/components/knowledge_base/document/StickyNotes.tsx), [`NoteEditor`](../../../../../frontend/src/components/knowledge_base/document/NoteEditor.tsx), [`NewNoteModal`](../../../../../frontend/src/components/knowledge_base/document/NewNoteModal.tsx)

Rich note-taking features:
- Sticky note visual style
- Markdown content support
- Edit and create capabilities
- Author attribution
- Chronological organization

### 7. Extract and Analysis Management

**Components**: [`FloatingExtractsPanel`](../../../../../frontend/src/components/knowledge_base/document/FloatingExtractsPanel.tsx), [`FloatingAnalysesPanel`](../../../../../frontend/src/components/knowledge_base/document/FloatingAnalysesPanel.tsx)

Document analysis features:
- Run custom analyzers on documents
- View extract results in structured format
- Create new extracts with fieldsets
- Single document results view

### 8. Floating Controls

**Components**: [`FloatingDocumentControls`](../../../../../frontend/src/components/knowledge_base/document/FloatingDocumentControls.tsx), [`FloatingDocumentInput`](../../../../../frontend/src/components/knowledge_base/document/FloatingDocumentInput.tsx), [`ZoomControls`](../../../../../frontend/src/components/knowledge_base/document/ZoomControls.tsx)

Modern floating UI elements:
- Zoom in/out controls
- Quick chat/search input
- Document action buttons
- Context-aware visibility
- **Annotation Controls**: Shows when right panel is closed
  - Provides same filtering options as sidebar
  - Label display settings (Always/On Hover/Hide)
  - Label filters for selective viewing
  - Structural annotation toggle

### 9. Structural Annotation System

**Atoms**: `structuralAnnotationsAtom`, `showStructuralAnnotationsAtom`

Sophisticated handling of structural annotations:
- **Separate Storage**: Structural annotations stored separately from regular annotations
- **Performance Optimization**: Hidden by default to reduce visual noise
- **Smart Toggle**: When enabling structural view, automatically enables "Show Selected Only"
- **Unified Filtering**: Single `useVisibleAnnotations` hook handles all visibility logic
- **Backend Consistency**: Mirrors backend's separation of annotation types

## Virtualized Rendering System

PDF and DOCX documents are drawn by `@os-legal/react-contract-annotate`,
which virtualizes PDF pages itself (visible pages plus an overscan; pages
holding the selection or the active highlight stay mounted). See
[Document Viewer (PDF and DOCX)](../../../../frontend/document_viewer.md).

## State Management

The system uses Jotai atoms for reactive state management:

### Core Atoms
- `pdfAnnotationsAtom` - Regular annotations only
- `structuralAnnotationsAtom` - Structural annotations only (kept separate)
- `allAnnotationsAtom` - Computed atom that merges and deduplicates both
- `perPageAnnotationsAtom` - Page-indexed annotation map for O(1) lookups
- `selectedAnnotationsAtom` - Currently selected annotation IDs
- `chatSourceStateAtom` - Chat message source tracking

### UI State Atoms
- `showStructuralAnnotationsAtom` - Toggle for structural annotations (default: false)
- `showSelectedAnnotationOnlyAtom` - Show only selected (auto-enabled with structural)
- `showAnnotationBoundingBoxesAtom` - Toggle bounding box visibility
- `showAnnotationLabelsAtom` - Label display mode (ALWAYS/ON_HOVER/HIDE)
- `spanLabelsToViewAtom` - Active label filters
- `zoomLevelAtom` - PDF zoom level
- `chatPanelWidthModeAtom` - Panel width mode (quarter/half/full/custom)

### Local Component State
- `activeLayer` - Current layer (knowledge/document) in DocumentKnowledgeBase
- `showRightPanel` - Right panel visibility in DocumentKnowledgeBase
- `sidebarViewMode` - Chat vs feed mode in right panel

### Computed State
- Annotations automatically filter based on user preferences via `useVisibleAnnotations`
- Visible pages calculate based on scroll position
- Summary versions update when changes are saved

## Specific Component Deep Dives

### DocumentKnowledgeBase.tsx

**Source**: [`frontend/src/components/knowledge_base/document/DocumentKnowledgeBase.tsx`](../../../../../frontend/src/components/knowledge_base/document/DocumentKnowledgeBase.tsx)

The main container component that:
- Manages the overall layout with resizable panels
- Handles data fetching via GraphQL
- Coordinates between knowledge base view and document annotation view
- Manages chat conversations, notes, and document relationships
- Controls layer switching and sidebar mode navigation
- Handles initial annotation selection from props or URL

Key responsibilities:
- Data loading and transformation
- Panel resize management
- Sidebar mode switching (chat, feed, extract, analysis, discussions)
- Layer switching logic
- URL parameter synchronization

### PdfAnnotatorWrapper and DocxAnnotatorWrapper

**Source**: [`frontend/src/components/annotator/components/wrappers/`](../../../../../frontend/src/components/annotator/components/wrappers/)

Mount `@os-legal/react-contract-annotate`'s `PdfAnnotator` / `DocxAnnotator`
on the loaded document and bind them to OpenContracts' state through
`annotator/bindings/useViewerBindings.tsx` (annotations, highlights,
selection, zoom, display settings, the selection menu, Edit/Delete). See
[Document Viewer (PDF and DOCX)](../../../../frontend/document_viewer.md).

### UnifiedContentFeed

**Source**: [`frontend/src/components/knowledge_base/document/unified_feed/UnifiedContentFeed.tsx`](../../../../../frontend/src/components/knowledge_base/document/unified_feed/UnifiedContentFeed.tsx)

Component that provides a unified view of all document content:
- Combines notes, annotations, relationships, and search results
- Sortable by page order or chronologically
- Filterable by content type
- Provides consistent interaction patterns

### FloatingSummaryPreview

**Source**: [`frontend/src/components/knowledge_base/document/floating_summary_preview/FloatingSummaryPreview.tsx`](../../../../../frontend/src/components/knowledge_base/document/floating_summary_preview/FloatingSummaryPreview.tsx)

Picture-in-picture style component that:
- Shows document summary while in document layer
- Allows quick navigation to knowledge layer
- Displays current version information
- Can be expanded to show more content

This architecture creates a flexible, highly performant system for both document annotation and knowledge management, with smooth transitions between different viewing modes and consistent state management across the application.
