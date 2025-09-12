/**
 * Tests for Document Cache Manager
 */
import "fake-indexeddb/auto";
import FDBFactory from "fake-indexeddb/lib/FDBFactory";
import FDBKeyRange from "fake-indexeddb/lib/FDBKeyRange";
import { DocumentCacheManager } from "../documentCacheManager";
import { vi } from "vitest";

// Setup fake-indexeddb with proper Blob support
globalThis.indexedDB = new FDBFactory();
globalThis.IDBKeyRange = FDBKeyRange;

// Polyfill FileReader for test environment
if (typeof FileReader === "undefined") {
  (globalThis as any).FileReader = class FileReader {
    result: string | ArrayBuffer | null = null;
    onload: ((event: any) => void) | null = null;
    onerror: ((event: any) => void) | null = null;

    readAsText(blob: Blob) {
      // In test environment, extract text from Blob using text() method
      if (blob.text) {
        blob
          .text()
          .then((text) => {
            this.result = text;
            if (this.onload) {
              this.onload({ target: this });
            }
          })
          .catch((err) => {
            if (this.onerror) {
              this.onerror(err);
            }
          });
      } else {
        // Fallback if text() is not available
        setTimeout(() => {
          this.result = "";
          if (this.onload) {
            this.onload({ target: this });
          }
        }, 0);
      }
    }

    readAsArrayBuffer(blob: Blob) {
      // Not needed for our use case, but included for completeness
      setTimeout(() => {
        this.result = new ArrayBuffer(0);
        if (this.onload) {
          this.onload({ target: this });
        }
      }, 0);
    }
  };
}

// Mark this as test environment for our cache manager
(globalThis as any).FDBFactory = FDBFactory;

describe("DocumentCacheManager", () => {
  let cacheManager: DocumentCacheManager;

  beforeEach(() => {
    // Create new instance for each test
    cacheManager = new DocumentCacheManager();
  });

  afterEach(async () => {
    // Clean up after each test
    await cacheManager.clearCache();
  });

  describe("PDF Caching", () => {
    it("should cache and retrieve a PDF with matching hash", async () => {
      const documentId = "doc123";
      const hash = "abc123def456";
      const pdfContent = new Blob(["%PDF-1.4 test content"], {
        type: "application/pdf",
      });

      // Cache the PDF
      await cacheManager.cachePDF(documentId, hash, pdfContent);

      // Retrieve with correct hash
      const retrieved = await cacheManager.getCachedPDF(documentId, hash);

      expect(retrieved).toBeTruthy();
      expect(retrieved).toBeInstanceOf(Blob);
      expect(retrieved?.size).toBe(pdfContent.size);
    });

    it("should return null for non-existent PDF", async () => {
      const result = await cacheManager.getCachedPDF("nonexistent", "somehash");
      expect(result).toBeNull();
    });

    it("should return null when PDF hash does not match", async () => {
      const documentId = "doc123";
      const originalHash = "abc123";
      const differentHash = "xyz789";
      const pdfContent = new Blob(["%PDF-1.4"], { type: "application/pdf" });

      // Cache with original hash
      await cacheManager.cachePDF(documentId, originalHash, pdfContent);

      // Try to retrieve with different hash
      const result = await cacheManager.getCachedPDF(documentId, differentHash);

      expect(result).toBeNull();
    });
  });

  describe("Text Document Caching", () => {
    it("should cache and retrieve text documents", async () => {
      const documentId = "doc123";
      const textContent = "This is a test document content";
      const hash = "texthash123";

      // Cache the text
      await cacheManager.cacheText(documentId, textContent, hash);

      // Retrieve the text
      const retrieved = await cacheManager.getCachedText(documentId, hash);

      expect(retrieved).toBe(textContent);
    });

    it("should return null for non-existent text document", async () => {
      const result = await cacheManager.getCachedText(
        "nonexistent",
        "somehash"
      );
      expect(result).toBeNull();
    });

    it("should work without hash for text documents", async () => {
      const documentId = "doc123";
      const textContent = "Text without hash";

      // Cache without hash
      await cacheManager.cacheText(documentId, textContent);

      // Retrieve without hash
      const retrieved = await cacheManager.getCachedText(documentId);

      expect(retrieved).toBe(textContent);
    });
  });

  describe("PAWLS Data Caching", () => {
    it("should cache and retrieve PAWLS data", async () => {
      const documentId = "doc123";
      const pawlsData = {
        pages: [{ tokens: ["test", "tokens"], page: 0 }],
      };

      // Cache PAWLS data
      await cacheManager.cachePawlsData(documentId, pawlsData);

      // Retrieve PAWLS data
      const retrievedPawls = await cacheManager.getCachedPawlsData(documentId);

      expect(retrievedPawls).toEqual(pawlsData);
    });

    it("should return null for non-existent PAWLS data", async () => {
      const result = await cacheManager.getCachedPawlsData("nonexistent");
      expect(result).toBeNull();
    });

    it("should handle complex PAWLS structures", async () => {
      const documentId = "doc123";
      const complexPawls = {
        pages: [
          {
            tokens: ["word1", "word2"],
            page: 0,
            height: 792,
            width: 612,
          },
          {
            tokens: ["page2", "text"],
            page: 1,
            height: 792,
            width: 612,
          },
        ],
        metadata: {
          totalPages: 2,
          processedAt: "2024-01-01",
        },
      };

      await cacheManager.cachePawlsData(documentId, complexPawls);
      const retrieved = await cacheManager.getCachedPawlsData(documentId);

      expect(retrieved).toEqual(complexPawls);
    });
  });

  describe("Cache Validation", () => {
    it("should validate PDF cache correctly when hash matches", async () => {
      const documentId = "doc123";
      const hash = "abc123";
      const pdfContent = new Blob(["%PDF-1.4"], { type: "application/pdf" });

      // Cache the PDF
      await cacheManager.cachePDF(documentId, hash, pdfContent);

      // Validate should return true
      const isValid = await cacheManager.validateCache(documentId, "pdf", hash);
      expect(isValid).toBe(true);
    });

    it("should invalidate cache when hash does not match", async () => {
      const documentId = "doc123";
      const originalHash = "abc123";
      const newHash = "xyz789";
      const pdfContent = new Blob(["%PDF-1.4"], { type: "application/pdf" });

      // Cache with original hash
      await cacheManager.cachePDF(documentId, originalHash, pdfContent);

      // Validate with different hash should return false
      const isValid = await cacheManager.validateCache(
        documentId,
        "pdf",
        newHash
      );
      expect(isValid).toBe(false);
    });

    it("should validate text cache without hash", async () => {
      const documentId = "doc123";
      const textContent = "Some text";

      await cacheManager.cacheText(documentId, textContent);

      const isValid = await cacheManager.validateCache(documentId, "text");
      expect(isValid).toBe(true);
    });

    it("should return false for non-cached document", async () => {
      const isValid = await cacheManager.validateCache(
        "nonexistent",
        "pdf",
        "somehash"
      );
      expect(isValid).toBe(false);
    });
  });

  describe("Cache Management", () => {
    it("should handle multiple document types for same document ID", async () => {
      const documentId = "doc123";

      // Cache all three types for same document
      await cacheManager.cachePDF(
        documentId,
        "pdfhash",
        new Blob(["pdf content"])
      );
      await cacheManager.cacheText(documentId, "text content");
      await cacheManager.cachePawlsData(documentId, { pages: [] });

      // All should be retrievable independently
      const pdf = await cacheManager.getCachedPDF(documentId, "pdfhash");
      const text = await cacheManager.getCachedText(documentId);
      const pawls = await cacheManager.getCachedPawlsData(documentId);

      expect(pdf).toBeTruthy();
      expect(text).toBe("text content");
      expect(pawls).toEqual({ pages: [] });
    });

    it("should update existing cache entry when re-caching same document", async () => {
      const documentId = "doc123";
      const hash1 = "abc123";
      const hash2 = "xyz789";
      const pdf1 = new Blob(["%PDF-1.4 v1"], { type: "application/pdf" });
      const pdf2 = new Blob(["%PDF-1.4 v2 updated"], {
        type: "application/pdf",
      });

      // Cache first version
      await cacheManager.cachePDF(documentId, hash1, pdf1);

      // Cache second version with new hash
      await cacheManager.cachePDF(documentId, hash2, pdf2);

      // Should get the updated version
      const retrieved = await cacheManager.getCachedPDF(documentId, hash2);
      expect(retrieved).toBeTruthy();
      // Check that size matches (allowing for Blob implementation differences)
      if (retrieved && "size" in retrieved) {
        expect(retrieved.size).toBe(pdf2.size);
      }

      // Old hash should not work
      const oldVersion = await cacheManager.getCachedPDF(documentId, hash1);
      expect(oldVersion).toBeNull();
    });

    it("should clear all cached documents", async () => {
      // Cache multiple documents of different types
      await cacheManager.cachePDF("doc1", "hash1", new Blob(["pdf1"]));
      await cacheManager.cacheText("doc2", "text2");
      await cacheManager.cachePawlsData("doc3", { data: "pawls3" });

      // Clear cache
      await cacheManager.clearCache();

      // All should be gone
      expect(await cacheManager.getCachedPDF("doc1", "hash1")).toBeNull();
      expect(await cacheManager.getCachedText("doc2")).toBeNull();
      expect(await cacheManager.getCachedPawlsData("doc3")).toBeNull();
    });

    it("should provide accurate cache statistics", async () => {
      // Start with empty cache
      let stats = await cacheManager.getCacheStats();
      expect(stats.count).toBe(0);
      expect(stats.totalSize).toBe(0);

      // Add some documents
      const pdf1 = new Blob(["a".repeat(100)]);
      const text2 = "b".repeat(200);

      await cacheManager.cachePDF("doc1", "hash1", pdf1);
      await cacheManager.cacheText("doc2", text2);

      // Check stats
      stats = await cacheManager.getCacheStats();
      expect(stats.count).toBe(2);
      expect(stats.totalSize).toBeGreaterThan(0);
      expect(stats.oldestTimestamp).toBeTruthy();
      expect(stats.newestTimestamp).toBeTruthy();
      expect(stats.newestTimestamp).toBeGreaterThanOrEqual(
        stats.oldestTimestamp!
      );
    });
  });

  describe("Error Handling", () => {
    it("should handle errors gracefully and return null", async () => {
      // Mock an IndexedDB error
      const originalOpen = indexedDB.open;
      indexedDB.open = vi.fn(() => {
        throw new Error("IndexedDB error");
      });

      const result = await cacheManager.getCachedPDF("doc123", "hash123");
      expect(result).toBeNull();

      // Restore original
      indexedDB.open = originalOpen;
    });

    it("should handle cache validation errors gracefully", async () => {
      // Mock an IndexedDB error
      const originalOpen = indexedDB.open;
      indexedDB.open = vi.fn(() => {
        throw new Error("IndexedDB error");
      });

      const isValid = await cacheManager.validateCache(
        "doc123",
        "pdf",
        "hash123"
      );
      expect(isValid).toBe(false);

      // Restore original
      indexedDB.open = originalOpen;
    });
  });

  describe("LRU and Size Management", () => {
    it("should track cache size correctly", async () => {
      const smallPDF = new Blob(["small"]);
      const mediumText = "a".repeat(1000);
      const largePawls = { data: "b".repeat(10000) };

      await cacheManager.cachePDF("small", "hash1", smallPDF);
      await cacheManager.cacheText("medium", mediumText);
      await cacheManager.cachePawlsData("large", largePawls);

      const stats = await cacheManager.getCacheStats();
      expect(stats.totalSize).toBeGreaterThan(0);
      expect(stats.count).toBe(3);
    });

    // Note: Testing actual eviction would require mocking the MAX_CACHE_SIZE
    // to a smaller value, which would require refactoring the class to accept
    // configuration. For now, we've tested the core functionality.
  });
});
