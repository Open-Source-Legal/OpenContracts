// Non-component module keyed to pipeline-icons tests. Playwright CT's babel
// plugin treats TestWrapper files as component modules and rejects non-
// component exports from them — keep the shared icon-name list here so both
// the TestWrapper and the ct.tsx file can import it.
export const PIPELINE_ICON_NAMES = [
  "DoclingIcon",
  "LlamaParseIcon",
  "TextParserIcon",
  "PdfThumbnailIcon",
  "TextThumbnailIcon",
  "ModernBertIcon",
  "SentenceTransformerIcon",
  "MultimodalIcon",
  "GenericComponentIcon",
] as const;
