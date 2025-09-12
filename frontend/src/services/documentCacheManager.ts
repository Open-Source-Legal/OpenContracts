/**
 * Document Cache Manager for OpenContracts
 *
 * Manages local caching of document files (PDFs, text, PAWLS data) using IndexedDB
 * with hash-based validation. Implements LRU eviction strategy and respects storage limits.
 */

interface CachedDocument {
  documentId: string;
  documentType: "pdf" | "text" | "pawls";
  hash?: string;
  data: Blob | string | any; // Blob for PDF, string for text, parsed JSON for PAWLS
  timestamp: number;
  size: number;
  // For test environment workaround
  testBlobContent?: string;
  testBlobType?: string;
}

interface CacheMetadata {
  documentId: string;
  documentType: "pdf" | "text" | "pawls";
  hash?: string;
  timestamp: number;
  size: number;
}

export class DocumentCacheManager {
  private db: IDBDatabase | null = null;
  private readonly DB_NAME = "OpenContractsDocumentCache";
  private readonly DB_VERSION = 2;
  private readonly STORE_NAME = "documents";
  private readonly METADATA_STORE_NAME = "metadata";
  private readonly MAX_CACHE_SIZE = 500 * 1024 * 1024; // 500MB
  private readonly MAX_AGE = 7 * 24 * 60 * 60 * 1000; // 7 days

  /**
   * Initialize the IndexedDB database
   */
  private async initDB(): Promise<IDBDatabase> {
    if (this.db) {
      return this.db;
    }

    return new Promise((resolve, reject) => {
      const request = indexedDB.open(this.DB_NAME, this.DB_VERSION);

      request.onerror = () => {
        console.error("Failed to open IndexedDB:", request.error);
        reject(request.error);
      };

      request.onsuccess = () => {
        this.db = request.result;
        resolve(this.db);
      };

      request.onupgradeneeded = (event) => {
        const db = (event.target as IDBOpenDBRequest).result;

        // Create document blob store
        if (!db.objectStoreNames.contains(this.STORE_NAME)) {
          const docStore = db.createObjectStore(this.STORE_NAME, {
            keyPath: "documentId",
          });
          docStore.createIndex("timestamp", "timestamp", { unique: false });
          docStore.createIndex("hash", "hash", { unique: false });
        }

        // Create metadata store for quick lookups
        if (!db.objectStoreNames.contains(this.METADATA_STORE_NAME)) {
          const metaStore = db.createObjectStore(this.METADATA_STORE_NAME, {
            keyPath: "documentId",
          });
          metaStore.createIndex("timestamp", "timestamp", { unique: false });
        }
      };
    });
  }

  /**
   * Create a unique cache key for a document
   */
  private getCacheKey(
    documentId: string,
    documentType: "pdf" | "text" | "pawls"
  ): string {
    return `${documentId}_${documentType}`;
  }

  /**
   * Get cached PDF if it exists and hash matches
   */
  async getCachedPDF(
    documentId: string,
    expectedHash: string
  ): Promise<Blob | null> {
    try {
      const db = await this.initDB();
      const transaction = db.transaction([this.STORE_NAME], "readonly");
      const store = transaction.objectStore(this.STORE_NAME);
      const cacheKey = this.getCacheKey(documentId, "pdf");

      return new Promise((resolve, reject) => {
        const request = store.get(cacheKey);

        request.onsuccess = () => {
          const cached = request.result as CachedDocument | undefined;

          if (!cached) {
            console.log(`No cached PDF found for document ${documentId}`);
            resolve(null);
            return;
          }

          // Check if hash matches
          if (cached.hash !== expectedHash) {
            console.log(
              `Hash mismatch for document ${documentId}. Cached: ${cached.hash}, Expected: ${expectedHash}`
            );
            // Remove outdated cache entry
            this.removeCachedDocument(cacheKey);
            resolve(null);
            return;
          }

          // Check if cache is too old
          const age = Date.now() - cached.timestamp;
          if (age > this.MAX_AGE) {
            console.log(
              `Cache too old for document ${documentId}. Age: ${age}ms`
            );
            this.removeCachedDocument(cacheKey);
            resolve(null);
            return;
          }

          // Update timestamp for LRU
          this.updateTimestamp(cacheKey);

          console.log(`Cache hit for PDF document ${documentId}`);

          // Handle different storage scenarios
          if (cached.data instanceof Blob) {
            // Real browser environment preserved the Blob
            resolve(cached.data);
          } else if (cached.testBlobContent) {
            // Test environment workaround - reconstruct from stored string
            const blob = new Blob([cached.testBlobContent], {
              type: cached.testBlobType || "application/pdf",
            });
            resolve(blob);
          } else {
            console.error("Unexpected PDF data format");
            resolve(null);
          }
        };

        request.onerror = () => {
          console.error("Error getting cached PDF:", request.error);
          reject(request.error);
        };
      });
    } catch (error) {
      console.error("Error in getCachedPDF:", error);
      return null;
    }
  }

  /**
   * Get cached text document if it exists
   */
  async getCachedText(
    documentId: string,
    expectedHash?: string
  ): Promise<string | null> {
    try {
      const db = await this.initDB();
      const transaction = db.transaction([this.STORE_NAME], "readonly");
      const store = transaction.objectStore(this.STORE_NAME);
      const cacheKey = this.getCacheKey(documentId, "text");

      return new Promise((resolve, reject) => {
        const request = store.get(cacheKey);

        request.onsuccess = async () => {
          const cached = request.result as CachedDocument | undefined;

          if (!cached) {
            console.log(`No cached text found for document ${documentId}`);
            resolve(null);
            return;
          }

          // Check if hash matches (if provided)
          if (expectedHash && cached.hash !== expectedHash) {
            console.log(`Hash mismatch for text document ${documentId}`);
            this.removeCachedDocument(cacheKey);
            resolve(null);
            return;
          }

          // Check if cache is too old
          const age = Date.now() - cached.timestamp;
          if (age > this.MAX_AGE) {
            console.log(`Cache too old for text document ${documentId}`);
            this.removeCachedDocument(cacheKey);
            resolve(null);
            return;
          }

          // Update timestamp for LRU
          this.updateTimestamp(cacheKey);

          console.log(`Cache hit for text document ${documentId}`);

          // Handle different storage formats
          try {
            if (typeof cached.data === "string") {
              // Expected format - text stored directly as string
              resolve(cached.data);
            } else if (cached.data instanceof Blob) {
              // Legacy format - stored as Blob (for backward compatibility)
              const text = await cached.data.text();
              resolve(text);
            } else if (
              cached.data &&
              typeof cached.data === "object" &&
              "text" in cached.data
            ) {
              // If it's an object with text property
              resolve(cached.data.text);
            } else {
              // Try to convert to string as fallback
              console.warn(
                "Unexpected data format in text cache:",
                typeof cached.data
              );
              resolve(String(cached.data));
            }
          } catch (error) {
            console.error("Error extracting text from cached data:", error);
            resolve(null);
          }
        };

        request.onerror = () => {
          console.error("Error getting cached text:", request.error);
          reject(request.error);
        };
      });
    } catch (error) {
      console.error("Error in getCachedText:", error);
      return null;
    }
  }

  /**
   * Get cached PAWLS data if it exists
   */
  async getCachedPawlsData(documentId: string): Promise<any | null> {
    try {
      const db = await this.initDB();
      const transaction = db.transaction([this.STORE_NAME], "readonly");
      const store = transaction.objectStore(this.STORE_NAME);
      const cacheKey = this.getCacheKey(documentId, "pawls");

      return new Promise((resolve, reject) => {
        const request = store.get(cacheKey);

        request.onsuccess = () => {
          const cached = request.result as CachedDocument | undefined;

          if (!cached) {
            console.log(
              `No cached PAWLS data found for document ${documentId}`
            );
            resolve(null);
            return;
          }

          // Check if cache is too old
          const age = Date.now() - cached.timestamp;
          if (age > this.MAX_AGE) {
            console.log(`PAWLS cache too old for document ${documentId}`);
            this.removeCachedDocument(cacheKey);
            resolve(null);
            return;
          }

          // Update timestamp for LRU
          this.updateTimestamp(cacheKey);

          console.log(`Cache hit for PAWLS data ${documentId}`);
          resolve(cached.data);
        };

        request.onerror = () => {
          reject(request.error);
        };
      });
    } catch (error) {
      console.error("Error in getCachedPawlsData:", error);
      return null;
    }
  }

  /**
   * Cache a PDF with its hash
   */
  async cachePDF(documentId: string, hash: string, blob: Blob): Promise<void> {
    try {
      const db = await this.initDB();

      // Check current cache size and evict if necessary
      const currentSize = await this.getCacheSize();
      const newSize = blob.size;

      if (currentSize + newSize > this.MAX_CACHE_SIZE) {
        await this.evictOldest(newSize);
      }

      const cacheKey = this.getCacheKey(documentId, "pdf");

      // Detect test environment - if Blob gets serialized incorrectly, store workaround data
      const isTestEnvironment =
        typeof (globalThis as any).FDBFactory !== "undefined";

      let cachedDoc: CachedDocument;
      if (isTestEnvironment && typeof FileReader !== "undefined") {
        // In test environment, we need to read the blob content BEFORE starting the transaction
        // because async operations can't happen during an IndexedDB transaction
        const reader = new FileReader();
        const textContent = await new Promise<string>((resolve, reject) => {
          reader.onload = () => resolve(reader.result as string);
          reader.onerror = reject;
          reader.readAsText(blob);
        });

        // Now start the transaction with the data ready
        const transaction = db.transaction(
          [this.STORE_NAME, this.METADATA_STORE_NAME],
          "readwrite"
        );
        const docStore = transaction.objectStore(this.STORE_NAME);
        const metaStore = transaction.objectStore(this.METADATA_STORE_NAME);

        cachedDoc = {
          documentId: cacheKey,
          documentType: "pdf",
          hash,
          data: blob, // Still try to store the blob
          testBlobContent: textContent, // But also store content as backup
          testBlobType: blob.type,
          timestamp: Date.now(),
          size: blob.size,
        };

        const metadata: CacheMetadata = {
          documentId: cacheKey,
          documentType: "pdf",
          hash,
          timestamp: cachedDoc.timestamp,
          size: blob.size,
        };

        return new Promise((resolve, reject) => {
          const docRequest = docStore.put(cachedDoc);
          const metaRequest = metaStore.put(metadata);

          transaction.oncomplete = () => {
            console.log(
              `Cached PDF for document ${documentId} (${blob.size} bytes)`
            );
            resolve();
          };

          transaction.onerror = () => {
            console.error("Error caching PDF:", transaction.error);
            reject(transaction.error);
          };
        });
      } else {
        // Real browser environment - store Blob normally
        const transaction = db.transaction(
          [this.STORE_NAME, this.METADATA_STORE_NAME],
          "readwrite"
        );
        const docStore = transaction.objectStore(this.STORE_NAME);
        const metaStore = transaction.objectStore(this.METADATA_STORE_NAME);

        cachedDoc = {
          documentId: cacheKey,
          documentType: "pdf",
          hash,
          data: blob,
          timestamp: Date.now(),
          size: blob.size,
        };

        const metadata: CacheMetadata = {
          documentId: cacheKey,
          documentType: "pdf",
          hash,
          timestamp: cachedDoc.timestamp,
          size: blob.size,
        };

        return new Promise((resolve, reject) => {
          const docRequest = docStore.put(cachedDoc);
          const metaRequest = metaStore.put(metadata);

          transaction.oncomplete = () => {
            console.log(
              `Cached PDF for document ${documentId} (${blob.size} bytes)`
            );
            resolve();
          };

          transaction.onerror = () => {
            console.error("Error caching PDF:", transaction.error);
            reject(transaction.error);
          };
        });
      }
    } catch (error) {
      console.error("Error in cachePDF:", error);
      throw error;
    }
  }

  /**
   * Cache a text document
   */
  async cacheText(
    documentId: string,
    text: string,
    hash?: string
  ): Promise<void> {
    try {
      // Store text directly as string instead of Blob for better compatibility
      const db = await this.initDB();

      // Check current cache size and evict if necessary
      const currentSize = await this.getCacheSize();
      const newSize = new Blob([text]).size;

      if (currentSize + newSize > this.MAX_CACHE_SIZE) {
        await this.evictOldest(newSize);
      }

      const transaction = db.transaction(
        [this.STORE_NAME, this.METADATA_STORE_NAME],
        "readwrite"
      );
      const docStore = transaction.objectStore(this.STORE_NAME);
      const metaStore = transaction.objectStore(this.METADATA_STORE_NAME);

      const cacheKey = this.getCacheKey(documentId, "text");

      const cachedDoc: CachedDocument = {
        documentId: cacheKey,
        documentType: "text",
        hash,
        data: text, // Store text directly
        timestamp: Date.now(),
        size: new Blob([text]).size, // Still calculate size for storage management
      };

      const metadata: CacheMetadata = {
        documentId: cacheKey,
        documentType: "text",
        hash,
        timestamp: cachedDoc.timestamp,
        size: cachedDoc.size,
      };

      return new Promise((resolve, reject) => {
        const docRequest = docStore.put(cachedDoc);
        const metaRequest = metaStore.put(metadata);

        transaction.oncomplete = () => {
          console.log(
            `Cached text for document ${documentId} (${cachedDoc.size} bytes)`
          );
          resolve();
        };

        transaction.onerror = () => {
          console.error("Error caching text:", transaction.error);
          reject(transaction.error);
        };
      });
    } catch (error) {
      console.error("Error in cacheText:", error);
      throw error;
    }
  }

  /**
   * Cache PAWLS data
   */
  async cachePawlsData(documentId: string, pawlsData: any): Promise<void> {
    try {
      const dataStr = JSON.stringify(pawlsData);
      const size = new Blob([dataStr]).size;
      const db = await this.initDB();

      // Check current cache size and evict if necessary
      const currentSize = await this.getCacheSize();

      if (currentSize + size > this.MAX_CACHE_SIZE) {
        await this.evictOldest(size);
      }

      const transaction = db.transaction(
        [this.STORE_NAME, this.METADATA_STORE_NAME],
        "readwrite"
      );
      const docStore = transaction.objectStore(this.STORE_NAME);
      const metaStore = transaction.objectStore(this.METADATA_STORE_NAME);

      const cacheKey = this.getCacheKey(documentId, "pawls");

      const cachedDoc: CachedDocument = {
        documentId: cacheKey,
        documentType: "pawls",
        data: pawlsData,
        timestamp: Date.now(),
        size,
      };

      const metadata: CacheMetadata = {
        documentId: cacheKey,
        documentType: "pawls",
        timestamp: cachedDoc.timestamp,
        size,
      };

      return new Promise((resolve, reject) => {
        const docRequest = docStore.put(cachedDoc);
        const metaRequest = metaStore.put(metadata);

        transaction.oncomplete = () => {
          console.log(
            `Cached PAWLS data for document ${documentId} (${size} bytes)`
          );
          resolve();
        };

        transaction.onerror = () => {
          console.error("Error caching PAWLS data:", transaction.error);
          reject(transaction.error);
        };
      });
    } catch (error) {
      console.error("Error in cachePawlsData:", error);
      throw error;
    }
  }

  /**
   * Validate if cached version matches expected hash without loading blob
   */
  async validateCache(
    documentId: string,
    documentType: "pdf" | "text" | "pawls",
    serverHash?: string
  ): Promise<boolean> {
    try {
      const db = await this.initDB();
      const transaction = db.transaction(
        [this.METADATA_STORE_NAME],
        "readonly"
      );
      const store = transaction.objectStore(this.METADATA_STORE_NAME);
      const cacheKey = this.getCacheKey(documentId, documentType);

      return new Promise((resolve, reject) => {
        const request = store.get(cacheKey);

        request.onsuccess = () => {
          const metadata = request.result as CacheMetadata | undefined;

          if (!metadata) {
            resolve(false);
            return;
          }

          // Check hash match (if provided) and age
          const hashValid = !serverHash || metadata.hash === serverHash;
          const ageValid = Date.now() - metadata.timestamp < this.MAX_AGE;
          const isValid = hashValid && ageValid;

          resolve(isValid);
        };

        request.onerror = () => {
          console.error("Error validating cache:", request.error);
          resolve(false);
        };
      });
    } catch (error) {
      console.error("Error in validateCache:", error);
      return false;
    }
  }

  /**
   * Remove a cached document
   */
  private async removeCachedDocument(cacheKey: string): Promise<void> {
    try {
      const db = await this.initDB();
      const transaction = db.transaction(
        [this.STORE_NAME, this.METADATA_STORE_NAME],
        "readwrite"
      );

      transaction.objectStore(this.STORE_NAME).delete(cacheKey);
      transaction.objectStore(this.METADATA_STORE_NAME).delete(cacheKey);

      return new Promise((resolve, reject) => {
        transaction.oncomplete = () => {
          console.log(`Removed cached document ${cacheKey}`);
          resolve();
        };

        transaction.onerror = () => {
          reject(transaction.error);
        };
      });
    } catch (error) {
      console.error("Error removing cached document:", error);
    }
  }

  /**
   * Update timestamp for LRU tracking
   */
  private async updateTimestamp(cacheKey: string): Promise<void> {
    try {
      const db = await this.initDB();
      const transaction = db.transaction(
        [this.STORE_NAME, this.METADATA_STORE_NAME],
        "readwrite"
      );

      const docStore = transaction.objectStore(this.STORE_NAME);
      const metaStore = transaction.objectStore(this.METADATA_STORE_NAME);

      const docRequest = docStore.get(cacheKey);

      docRequest.onsuccess = () => {
        const cached = docRequest.result as CachedDocument | undefined;
        if (cached) {
          cached.timestamp = Date.now();
          docStore.put(cached);

          // Update metadata too
          metaStore.get(cacheKey).onsuccess = (event) => {
            const metadata = (event.target as IDBRequest)
              .result as CacheMetadata;
            if (metadata) {
              metadata.timestamp = cached.timestamp;
              metaStore.put(metadata);
            }
          };
        }
      };
    } catch (error) {
      console.error("Error updating timestamp:", error);
    }
  }

  /**
   * Get total cache size
   */
  private async getCacheSize(): Promise<number> {
    try {
      const db = await this.initDB();
      const transaction = db.transaction(
        [this.METADATA_STORE_NAME],
        "readonly"
      );
      const store = transaction.objectStore(this.METADATA_STORE_NAME);

      return new Promise((resolve, reject) => {
        let totalSize = 0;
        const request = store.openCursor();

        request.onsuccess = (event) => {
          const cursor = (event.target as IDBRequest).result;
          if (cursor) {
            const metadata = cursor.value as CacheMetadata;
            totalSize += metadata.size;
            cursor.continue();
          } else {
            resolve(totalSize);
          }
        };

        request.onerror = () => {
          reject(request.error);
        };
      });
    } catch (error) {
      console.error("Error getting cache size:", error);
      return 0;
    }
  }

  /**
   * Evict oldest entries to make room for new content
   */
  private async evictOldest(bytesNeeded: number): Promise<void> {
    try {
      const db = await this.initDB();
      const transaction = db.transaction(
        [this.METADATA_STORE_NAME],
        "readonly"
      );
      const store = transaction.objectStore(this.METADATA_STORE_NAME);
      const index = store.index("timestamp");

      // Get all entries sorted by timestamp
      const entries: CacheMetadata[] = [];

      return new Promise((resolve, reject) => {
        const request = index.openCursor();

        request.onsuccess = async (event) => {
          const cursor = (event.target as IDBRequest).result;
          if (cursor) {
            entries.push(cursor.value as CacheMetadata);
            cursor.continue();
          } else {
            // Calculate how many to evict
            let bytesToFree = bytesNeeded;
            const toEvict: string[] = [];

            for (const entry of entries) {
              toEvict.push(entry.documentId);
              bytesToFree -= entry.size;

              if (bytesToFree <= 0) {
                break;
              }
            }

            // Evict selected entries
            for (const documentId of toEvict) {
              await this.removeCachedDocument(documentId);
            }

            console.log(
              `Evicted ${toEvict.length} cached documents to make room`
            );
            resolve();
          }
        };

        request.onerror = () => {
          reject(request.error);
        };
      });
    } catch (error) {
      console.error("Error evicting cache:", error);
    }
  }

  /**
   * Clear all cached documents
   */
  async clearCache(): Promise<void> {
    try {
      const db = await this.initDB();
      const transaction = db.transaction(
        [this.STORE_NAME, this.METADATA_STORE_NAME],
        "readwrite"
      );

      transaction.objectStore(this.STORE_NAME).clear();
      transaction.objectStore(this.METADATA_STORE_NAME).clear();

      return new Promise((resolve, reject) => {
        transaction.oncomplete = () => {
          console.log("Cleared all cached documents");
          resolve();
        };

        transaction.onerror = () => {
          reject(transaction.error);
        };
      });
    } catch (error) {
      console.error("Error clearing cache:", error);
      throw error;
    }
  }

  /**
   * Get cache statistics
   */
  async getCacheStats(): Promise<{
    count: number;
    totalSize: number;
    oldestTimestamp: number | null;
    newestTimestamp: number | null;
  }> {
    try {
      const db = await this.initDB();
      const transaction = db.transaction(
        [this.METADATA_STORE_NAME],
        "readonly"
      );
      const store = transaction.objectStore(this.METADATA_STORE_NAME);

      return new Promise((resolve, reject) => {
        let count = 0;
        let totalSize = 0;
        let oldestTimestamp: number | null = null;
        let newestTimestamp: number | null = null;

        const request = store.openCursor();

        request.onsuccess = (event) => {
          const cursor = (event.target as IDBRequest).result;
          if (cursor) {
            const metadata = cursor.value as CacheMetadata;
            count++;
            totalSize += metadata.size;

            if (!oldestTimestamp || metadata.timestamp < oldestTimestamp) {
              oldestTimestamp = metadata.timestamp;
            }
            if (!newestTimestamp || metadata.timestamp > newestTimestamp) {
              newestTimestamp = metadata.timestamp;
            }

            cursor.continue();
          } else {
            resolve({
              count,
              totalSize,
              oldestTimestamp,
              newestTimestamp,
            });
          }
        };

        request.onerror = () => {
          reject(request.error);
        };
      });
    } catch (error) {
      console.error("Error getting cache stats:", error);
      return {
        count: 0,
        totalSize: 0,
        oldestTimestamp: null,
        newestTimestamp: null,
      };
    }
  }
}

// Export singleton instance
export const documentCacheManager = new DocumentCacheManager();
