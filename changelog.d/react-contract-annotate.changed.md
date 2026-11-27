- **PDF and DOCX documents are drawn by `@os-legal/react-contract-annotate`**
  (^0.1.4), the viewer/annotator extracted from this codebase, instead of
  OpenContracts' own renderer. `PdfAnnotatorWrapper` and
  `DocxAnnotatorWrapper` (`frontend/src/components/annotator/components/wrappers/`)
  mount the library; `frontend/src/components/annotator/bindings/`
  (`useViewerBindings.tsx`, `convert.ts`, `AnnotationSelectionMenu.tsx`)
  binds it to the existing atoms: annotations, relations, search hits, chat
  sources and the `?tb=` block go in as data, while selection, zoom and the
  active highlight are controlled. The selection menu keeps its items,
  test ids and shortcuts. Plain-text documents still use `TxtAnnotator`.
  See `docs/frontend/document_viewer.md`.
- The viewer's root is now the scroll container; `#pdf-container` /
  `#docx-container` only frame it (`PDFContainer`'s `$frame`). Code that
  must move the viewer without changing the selection goes through
  `annotatorHandleAtom` (`useJumpToRelationship`); a change of the selection
  or the active highlight scrolls the viewer by itself, so the PDF-only
  `scrollIntoView` calls in `HighlightItem`, `FloatingDocumentInput` and
  `MobileFindSheet` are gone.
- DOCX gets the PDF's selection menu (Copy Text, Copy Link to a `?tb=` span,
  Apply Label) and Edit / Delete beside annotation labels; the DOCX viewer
  now applies "Show selected only" like the other formats, and shows the
  selected chat message's sources (or the one picked) like the PDF does,
  instead of every message's sources at once. A drag over a PDF that
  captures no token no longer opens an (empty) selection menu.
- The pdf.js worker is configured with the library's `configurePdfWorker`
  (`DocumentKnowledgeBase.tsx`), on the same `pdfjs-dist/legacy` instance
  OpenContracts loads documents with. Vitest inlines the library
  (`vite.config.ts`, `server.deps.inline`).
