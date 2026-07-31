- Added a rendered Markdown view for markdown documents, with a **Rendered /
  Raw** toggle (`MarkdownDocumentViewer.tsx`). Markdown is a `text/…` subtype,
  so these documents fell into the plain-text branch of `DocumentViewer` and
  displayed their own source — `# Heading`, `- **Corpus:**` — which is exactly
  wrong for what produces them: saved chat answers, research reports and CAML
  articles are written to be read. The renderer is the same
  `MarkdownMessageRenderer` the chat uses, so a saved answer looks in the
  document viewer the way it looked in the conversation it came from.
- The toggle is not cosmetic: **Raw is the annotator**. Span annotations need
  character offsets into the source text, so annotating has to happen against
  the raw document; Rendered is the default because reading is the common case.
  The routing check runs before `isTextFileType` — reorder them and every
  markdown document silently reverts to showing source, which is what the new
  `DocumentViewer filetype routing` test guards.
