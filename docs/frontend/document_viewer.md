# Document Viewer (PDF and DOCX)

PDF and DOCX documents are drawn by
[`@os-legal/react-contract-annotate`](https://www.npmjs.com/package/@os-legal/react-contract-annotate)
([repo](https://github.com/Open-Source-Legal/react-contract-annotate)), a
control-free viewer/annotator extracted from this codebase. It owns page
rendering, virtualization, token and span geometry, text selection, the
two-phase scroll to an annotation, DOCX conversion and projection, and the
DOCX isolation (scoped stylesheet, CSS/HTML allow-lists). Its README
documents the props, the handle, and the DOM contract.

OpenContracts owns everything around it: loading the document, the data
(annotations, relations, search hits, chat sources), all controls, menus,
dialogs, persistence and permissions. Plain-text and Markdown documents are
still rendered by OpenContracts (`renderers/txt/`, `MarkdownDocumentViewer`).

## Where the code is

| Concern | Code |
|---|---|
| Choosing a viewer by file type | `knowledge_base/document/document_kb/DocumentViewer.tsx` |
| PDF viewer | `annotator/components/wrappers/PdfAnnotatorWrapper.tsx` |
| DOCX viewer | `annotator/components/wrappers/DocxAnnotatorWrapper.tsx` |
| State → props, reports → state | `annotator/bindings/useViewerBindings.tsx` |
| Data conversion (annotations, highlights, drafts) | `annotator/bindings/convert.ts` |
| Selection menu (`renderSelectionMenu` slot) | `annotator/bindings/AnnotationSelectionMenu.tsx` |
| The viewer's handle | `annotator/context/AnnotatorHandleAtom.ts` |
| pdf.js worker | `knowledge_base/document/DocumentKnowledgeBase.tsx` (`configurePdfWorker`) |
| docxodus WebAssembly runtime | `frontend/tooling/docxodusWasm.ts` (served at `DOCXODUS_WASM_DEV_PATH` / `DOCXODUS_WASM_BUILD_DIR`) |

Paths are under `frontend/src/components/` unless they start with `frontend/`.

## Data flow

- **Document.** `useDocumentLoader` loads the PDF with pdf.js and the PAWLS
  tokens; the viewer gets `source={{ document: pdfDoc }}` and PAWLS built
  from the resolved pages (`convert.ts::toViewerPawls`), so its token indices
  are the ones the search index uses. A DOCX is passed as its bytes plus the
  parser's text (`docText`), which span offsets index into.
- **Annotations** come from `allAnnotationsAtom` (token annotations to the
  PDF viewer, span annotations to the DOCX viewer), converted once per object
  (`toViewerAnnotation`, the OpenContracts object in `meta`). Bare-hex label
  colours get their `#` (`toViewerColor`).
- **Highlights** are search hits, the selected chat message's sources, and
  the `?tb=` text block. Their ids are namespaced (`searchHighlightId`,
  `chatSourceHighlightId`, `TEXT_BLOCK_DEEPLINK_ID`). The active highlight
  is the picked chat source (the first when none is picked), else the
  current search hit, else the text block.
- **Controlled state**: selection (`selectedAnnotationIds`, URL-backed),
  zoom (`zoomLevelAtom`; the first fit-to-width uses
  `utils/pdfZoom.ts::computeFitToWidthZoom`), and the active highlight.
  Display settings (`showStructural`, `showSelectedOnly`,
  `showBoundingBoxes`, labels, the label filter) pass straight through; the
  library applies the same visibility rules as `useVisibleAnnotations`.
- **Creating**: a text selection opens `AnnotationSelectionMenu` (Copy
  Text, Copy Link, Add link…, Apply Label, Cancel; C / L / A / Esc). Apply
  Label commits the selection with the active label; the draft becomes a
  `ServerTokenAnnotation` / `ServerSpanAnnotation` (`draftToAnnotation`) for
  `useCreateAnnotation`. Creating needs an editable document and corpus
  update permission; copying always works.
- **Edit / Delete** sit beside each label (`annotationActions`), gated by the
  annotation's own permissions and its label's `readonly`.

## Scrolling

Nothing outside the viewer touches its DOM. A change of the selected
annotations or of the active highlight scrolls the viewer by itself, so the
sidebar, feed, search and chat only change state. Code that must move the
viewer without changing the selection uses the handle in
`annotatorHandleAtom` (e.g. `useJumpToRelationship`). The plain-text
annotator still registers its annotation elements in `AnnotationRefsAtoms`.

## Pitfalls

- **Slots run inside the library's Jotai Provider.** The library keeps its
  state in a private Jotai store and provides it with Jotai's `Provider`;
  OpenContracts uses the same `jotai` package, so atom hooks in slot content
  (`renderSelectionMenu`, `renderAnnotationActions`, …) would read the
  library's store. `useViewerBindings` wraps the menu in a `Provider` with
  OpenContracts' store; do the same for any new slot that reads atoms.
- **The viewer's root scrolls**, not `#pdf-container`: the container is a
  frame with `$frame` that only gives height. Scroll
  `#pdf-container [data-rca-root]` in tests.
- **A drag that captures no token** makes no selection and opens no menu.
- **Vitest** inlines the library (`server.deps.inline` in
  `frontend/vite.config.ts`) because its DOCX entry imports docxodus.

## Testing hooks

Component tests select the library's DOM contract: `[data-rca-root]` (scroll
container), `[data-rca-page]` (a PDF page), `[data-rca-selection-layer]`,
`[data-rca-annotation="<id>"]` (an annotation's box),
`[data-rca-highlight="<id>"]`, and `[data-rca-docx-frame]` with
`[data-annotation-id="<id>"]` for DOCX. The wrappers keep the
`pdf-annotator` / `docx-annotator` test ids. See `frontend/tests/DocxAnnotator.ct.tsx`
and the PDF tests in `frontend/tests/DocumentKnowledgeBase.ct.tsx`.
