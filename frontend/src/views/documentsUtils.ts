import { DocumentType } from "../types/graphql-api";

/**
 * Normalize a document's file type for display in badges and list rows.
 * Prefers the explicit `fileType` field when present and falls back to the
 * extension on the title. Returns `"PDF"` as a last resort so the badge is
 * never empty.
 */
export function getDocumentType(doc: DocumentType): string {
  if (doc.fileType) {
    const ft = doc.fileType.toLowerCase();
    if (ft === "pdf") return "PDF";
    if (ft === "docx" || ft === "doc") return "DOCX";
    if (ft === "txt") return "TXT";
    return ft.toUpperCase();
  }
  const fileName = doc.title || "";
  const parts = fileName.split(".");
  if (parts.length > 1) {
    const ext = parts.pop()?.toLowerCase();
    if (ext === "pdf") return "PDF";
    if (ext === "docx" || ext === "doc") return "DOCX";
    if (ext === "txt") return "TXT";
    if (ext) return ext.toUpperCase();
  }
  return "PDF";
}
