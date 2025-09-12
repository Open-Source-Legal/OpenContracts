/**
 * Cached REST API functions for document retrieval
 * Wraps existing REST functions with caching layer
 */
import axios from "axios";
import { PageTokens } from "../../types";
import { documentCacheManager } from "../../../services/documentCacheManager";
import {
  getPawlsLayer as uncachedGetPawlsLayer,
  getDocumentRawText as uncachedGetDocumentRawText,
} from "./rest";

/**
 * Get PAWLS layer data with caching
 */
export async function getPawlsLayer(
  url: string,
  documentId?: string
): Promise<PageTokens[]> {
  console.log(
    `📄 Loading PAWLS data for document ${documentId || "unknown"}...`
  );

  // If we have a document ID, try to get from cache first
  if (documentId) {
    const cached = await documentCacheManager.getCachedPawlsData(documentId);
    if (cached) {
      console.log(`✅ Loaded PAWLS data from CACHE for document ${documentId}`);
      return cached;
    }
  }

  // Fetch from server
  console.log(`🌐 Loading PAWLS data from HTTPS: ${url}`);
  const pawlsData = await uncachedGetPawlsLayer(url);

  // Cache for future use if we have document ID
  if (documentId && pawlsData) {
    await documentCacheManager
      .cachePawlsData(documentId, pawlsData)
      .then(() => {
        console.log(
          `  💾 PAWLS data cached successfully for document ${documentId}`
        );
      })
      .catch((err) => {
        console.error("  ⚠️ Failed to cache PAWLS data:", err);
      });
  }

  return pawlsData;
}

/**
 * Get document raw text with caching
 */
export async function getDocumentRawText(
  url: string,
  documentId?: string,
  hash?: string
): Promise<string> {
  console.log(`📄 Loading text document ${documentId || "unknown"}...`);

  // If we have a document ID, try to get from cache first
  if (documentId) {
    const cached = await documentCacheManager.getCachedText(documentId, hash);
    if (cached) {
      console.log(
        `✅ Loaded text document from CACHE for document ${documentId}`
      );
      return cached;
    }
  }

  // Fetch from server
  console.log(`🌐 Loading text document from HTTPS: ${url}`);
  const text = await uncachedGetDocumentRawText(url);

  // Cache for future use if we have document ID
  if (documentId && text) {
    await documentCacheManager
      .cacheText(documentId, text, hash)
      .then(() => {
        console.log(
          `  💾 Text document cached successfully for document ${documentId}`
        );
      })
      .catch((err) => {
        console.error("  ⚠️ Failed to cache text:", err);
      });
  }

  return text;
}

/**
 * Get PDF document with caching
 * Returns a blob URL that can be used with PDF.js
 */
export async function getCachedPDFUrl(
  pdfUrl: string,
  documentId: string,
  hash: string
): Promise<string> {
  console.log(`📄 Loading PDF document ${documentId}...`);

  // First check if we have a valid cached version
  const cachedBlob = await documentCacheManager.getCachedPDF(documentId, hash);

  if (cachedBlob) {
    console.log(`✅ Loaded PDF from CACHE for document ${documentId}`);
    // Create a blob URL from the cached blob
    return URL.createObjectURL(cachedBlob);
  }

  // Need to fetch from server
  console.log(`🌐 Loading PDF from HTTPS: ${pdfUrl}`);

  try {
    const response = await axios.get(pdfUrl, {
      responseType: "blob",
      onDownloadProgress: (progressEvent) => {
        if (progressEvent.total) {
          const percentCompleted = Math.round(
            (progressEvent.loaded * 100) / progressEvent.total
          );
          console.log(`  ⬇️ Downloading PDF: ${percentCompleted}%`);
        }
      },
    });

    const pdfBlob = response.data;

    // Cache the PDF for future use
    await documentCacheManager
      .cachePDF(documentId, hash, pdfBlob)
      .then(() => {
        console.log(`  💾 PDF cached successfully for document ${documentId}`);
      })
      .catch((err) => {
        console.error("  ⚠️ Failed to cache PDF:", err);
      });

    // Return blob URL for immediate use
    return URL.createObjectURL(pdfBlob);
  } catch (error) {
    console.error("Error fetching PDF:", error);
    // Fall back to direct URL if caching fails
    return pdfUrl;
  }
}

/**
 * Prevalidate if cache is up to date without loading the full document
 */
export async function validateDocumentCache(
  documentId: string,
  documentType: "pdf" | "text" | "pawls",
  serverHash?: string
): Promise<boolean> {
  return await documentCacheManager.validateCache(
    documentId,
    documentType,
    serverHash
  );
}
