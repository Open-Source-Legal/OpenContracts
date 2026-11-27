- OpenContracts' own PDF and DOCX renderers, now in
  `@os-legal/react-contract-annotate`: `annotator/renderers/pdf/`
  (`PDF.tsx`, `PDFPage.tsx`, `SelectionLayer.tsx`, `NativeLinkLayer.tsx`),
  `annotator/renderers/docx/` (`DocxAnnotator.tsx`, `docxOffsetUtils.ts`),
  the PDF overlay components in `annotator/display/components/`
  (`Selection`, `SelectionBoundary`, `SelectionTokenGroup`, `SearchResult`,
  `ChatSourceResult`, `TextBlockHighlight`, `ResultBoundary`, `Tokens`, …)
  and `display/effects.tsx`, with their unit tests and
  `frontend/tests/SelectionInfo.ct.tsx` (the library carries the equivalent
  tests).
- What only they used: `PDFPageInfo`'s geometry methods (it is now the page
  plus its tokens), the `pendingScroll*` and `isCreatingAnnotationAtom`
  atoms, the page/canvas/renderer/search/chat-source refs in
  `AnnotationRefsAtoms` (only TXT annotation refs remain),
  `RenderedSpanAnnotation`, `annotationSelectedViaRelationship`,
  `convertAnnotationTokensToText`, `computeAnnotationBoxShadow`,
  `textBlockToBounds`, the bounds helpers in `utils/transform.tsx`, the
  annotation-styling constants, `SELECTION_MENU_COOLDOWN_MS` and the PDF
  layer z-indexes, `useDocumentLoader`'s `zoomLevel` parameter, and the docs
  `scroll-to-annotation-flow.md` and `search_rendering.md`.
