import Axios from "axios";
import {
  LEGACY_TEXT_MIME_TYPE,
  DOCX_MIME_TYPE,
} from "../assets/configurations/constants";

/**
 * Check if a file type string represents a text-based document.
 * Handles both standard MIME types (text/plain) and the legacy
 * application/txt type used in some parts of the system.
 */
export const isTextFileType = (fileType: string | null | undefined): boolean =>
  fileType?.startsWith("text/") === true || fileType === LEGACY_TEXT_MIME_TYPE;

/**
 * Check if a file type string represents a PDF document.
 */
export const isPdfFileType = (fileType: string | null | undefined): boolean =>
  fileType === "application/pdf";

/**
 * Check if a file type string represents a DOCX document.
 */
export const isDocxFileType = (fileType: string | null | undefined): boolean =>
  fileType === DOCX_MIME_TYPE;

/**
 * Check if a file type uses span-based annotations (character offsets).
 * This includes TXT and DOCX — as opposed to PDF which uses token-based annotations.
 */
export const isSpanBasedFileType = (
  fileType: string | null | undefined
): boolean => isTextFileType(fileType) || isDocxFileType(fileType);

/**
 * Normalize a document's fileType + title into a short badge label
 * (e.g. "PDF" / "DOCX" / "TXT"). Handles both bare extension strings
 * ("pdf", "docx") and the full MIME types that the Django backend's
 * ``file_type`` field actually stores ("application/pdf",
 * DOCX_MIME_TYPE, "text/plain"). Falls back to the title extension and
 * finally "PDF" so the badge is never empty.
 */
export const getDocumentTypeBadge = (
  fileType: string | null | undefined,
  title: string | null | undefined
): string => {
  if (fileType) {
    const ft = fileType.toLowerCase();
    // Bare extension form (older fixtures, some upload paths).
    if (ft === "pdf") return "PDF";
    if (ft === "docx" || ft === "doc") return "DOCX";
    if (ft === "txt") return "TXT";
    // MIME-type form (live backend payload — see the helpers above
    // (isPdfFileType / isDocxFileType / isTextFileType) for the same
    // mappings expressed as predicates).
    if (isPdfFileType(ft)) return "PDF";
    if (isDocxFileType(ft) || ft.includes("wordprocessingml")) return "DOCX";
    if (isTextFileType(ft)) return "TXT";
    // Generic MIME (e.g. "application/json") -> trim prefix for display.
    const sub = ft.includes("/") ? ft.split("/").pop()! : ft;
    return sub.toUpperCase();
  }
  const parts = (title || "").split(".");
  if (parts.length > 1) {
    const ext = parts.pop()?.toLowerCase();
    if (ext === "pdf") return "PDF";
    if (ext === "docx" || ext === "doc") return "DOCX";
    if (ext === "txt") return "TXT";
    if (ext) return ext.toUpperCase();
  }
  return "PDF";
};

export const downloadFile = async (url: string): Promise<void> => {
  try {
    const res = await Axios.get(url, {
      responseType: "blob",
    });
    const contentType = res.headers["content-type"];
    const blob = new Blob([res.data], {
      type: typeof contentType === "string" ? contentType : undefined,
    });
    const link = document.createElement("a");
    link.href = window.URL.createObjectURL(blob);
    link.download = url.substring(url.lastIndexOf("/") + 1);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  } catch (e) {
    console.log("ERROR - Downloading file failed: ", e);
    throw e;
  }
};

/**
 * Formats a file size in bytes to a human-readable string.
 * @param bytes - File size in bytes
 * @returns Formatted string (e.g., "1.5 MB")
 */
export const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return "0 Bytes";
  const k = 1024;
  const sizes = ["Bytes", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
};
