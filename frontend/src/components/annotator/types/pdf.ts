import { PDFPageProxy } from "pdfjs-dist/types/src/display/api";
import { Token } from "../../types";

/**
 * A loaded PDF page and its PAWLS tokens, normalised to the page's pdf.js
 * viewport at scale 1 (`useDocumentLoader`). OpenContracts builds its text
 * search index and token text maps from these, and hands them to the PDF
 * viewer (`bindings/convert.ts::toViewerPawls`), which owns all drawing and
 * selection geometry (`@os-legal/react-contract-annotate`).
 */
export class PDFPageInfo {
  constructor(
    public readonly page: PDFPageProxy,
    public readonly tokens: Token[] = []
  ) {}
}
