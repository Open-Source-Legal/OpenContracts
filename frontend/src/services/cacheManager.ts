/**
 * CacheManager - Proactive Apollo Cache Management
 *
 * This module provides surgical cache invalidation and refresh capabilities
 * for critical application events such as authentication changes and entity CRUD.
 *
 * Design Principles:
 * 1. Full reset on identity change (login/logout) - ensures data freshness and security
 * 2. Targeted invalidation for entity CRUD - avoids unnecessary full cache clears
 * 3. Debouncing to prevent rapid repeated operations
 * 4. Clear separation of concerns - each function handles one type of cache operation
 *
 * Related to Issue #694 - Apollo Cache Stale Data Problem
 *
 * @see https://github.com/Open-Source-Legal/OpenContracts/issues/694
 */

import {
  ApolloClient,
  NormalizedCacheObject,
  DocumentNode,
} from "@apollo/client";
import {
  GET_CORPUSES,
  GET_DOCUMENTS,
  GET_DOCUMENTS_FOR_LIST,
} from "../graphql/queries";
import { GET_CORPUS_FOLDERS } from "../graphql/queries/folders";

// ============================================================================
// Types
// ============================================================================

/**
 * Result of a cache operation
 */
export interface CacheOperationResult {
  success: boolean;
  message: string;
  /** Time taken in milliseconds */
  duration?: number;
}

/**
 * Options for cache reset operations
 */
export interface CacheResetOptions {
  /** Whether to refetch active queries after reset (default: false) */
  refetchActive?: boolean;
  /** Reason for the reset (for logging) */
  reason?: string;
}

/**
 * Entity types that can trigger targeted cache invalidation
 */
export type InvalidatableEntity =
  | "document"
  | "corpus"
  | "annotation"
  | "thread";

/**
 * Options for targeted cache invalidation
 */
export interface InvalidationOptions {
  /** The entity type being affected */
  entityType: InvalidatableEntity;
  /** Optional corpus ID to scope the invalidation */
  corpusId?: string;
  /** Optional document ID to scope the invalidation */
  documentId?: string;
  /** Reason for the invalidation (for logging) */
  reason?: string;
}

// ============================================================================
// Cache Manager Class
// ============================================================================

/**
 * CacheManager provides methods for proactive Apollo cache management.
 *
 * This class is designed to be instantiated once and used throughout the app.
 * It handles both full cache resets (for auth changes) and targeted invalidation
 * (for entity CRUD operations).
 *
 * @example
 * ```tsx
 * // In a component
 * const { resetOnAuthChange, invalidateEntityQueries } = useCacheManager();
 *
 * // On logout (refetchActive defaults to false — the useRefetchOnAuthChange
 * // hook handles post-clear refetching for login; logout skips refetch
 * // because authToken is cleared before clearStore fires).
 * await resetOnAuthChange({ reason: "user_logout" });
 *
 * // After document upload
 * await invalidateEntityQueries({
 *   entityType: "document",
 *   corpusId: "corpus-123",
 *   reason: "document_upload"
 * });
 * ```
 */
export class CacheManager {
  private client: ApolloClient<NormalizedCacheObject>;
  private lastResetTime: number = 0;
  private lastInvalidationTime: Map<string, number> = new Map();

  /** Minimum time (ms) between full cache resets */
  private static readonly RESET_DEBOUNCE_MS = 1000;
  /** Minimum time (ms) between same-type invalidations */
  private static readonly INVALIDATION_DEBOUNCE_MS = 500;
  /** Maximum entries in lastInvalidationTime to prevent memory leak */
  private static readonly MAX_INVALIDATION_ENTRIES = 100;
  /** Entries older than this (ms) are eligible for cleanup */
  private static readonly INVALIDATION_ENTRY_TTL_MS = 60000;

  constructor(client: ApolloClient<NormalizedCacheObject>) {
    this.client = client;
  }

  // ==========================================================================
  // Private Helpers - Debounce Map Cleanup
  // ==========================================================================

  /**
   * Cleans up stale entries from the invalidation debounce map to prevent memory leaks.
   * Called automatically when new entries are added.
   *
   * Cleanup strategy:
   * 1. Remove entries older than TTL (they can't affect debouncing anyway)
   * 2. If still over max size, remove oldest entries until under limit
   */
  private cleanupInvalidationMap(): void {
    const now = Date.now();

    // First pass: remove entries older than TTL
    for (const [key, timestamp] of this.lastInvalidationTime) {
      if (now - timestamp > CacheManager.INVALIDATION_ENTRY_TTL_MS) {
        this.lastInvalidationTime.delete(key);
      }
    }

    // Second pass: if still over limit, remove oldest entries
    if (
      this.lastInvalidationTime.size > CacheManager.MAX_INVALIDATION_ENTRIES
    ) {
      const entries = Array.from(this.lastInvalidationTime.entries());
      entries.sort((a, b) => a[1] - b[1]); // Sort by timestamp ascending (oldest first)

      const entriesToRemove =
        entries.length - CacheManager.MAX_INVALIDATION_ENTRIES;
      for (let i = 0; i < entriesToRemove; i++) {
        this.lastInvalidationTime.delete(entries[i][0]);
      }
    }
  }

  // ==========================================================================
  // Full Cache Reset Operations
  // ==========================================================================

  /**
   * Completely clears the Apollo cache and optionally refetches active queries.
   *
   * This should be called on authentication state changes:
   * - User login (to clear any anonymous/previous user data)
   * - User logout (to clear authenticated user data for security)
   *
   * The operation is debounced to prevent rapid repeated clears.
   *
   * @param options - Configuration for the reset operation
   * @returns Result of the operation
   */
  async resetOnAuthChange(
    options: CacheResetOptions = {}
  ): Promise<CacheOperationResult> {
    const { refetchActive = false, reason = "auth_change" } = options;
    const startTime = performance.now();

    // Debounce: prevent multiple resets within the threshold
    const now = Date.now();
    if (now - this.lastResetTime < CacheManager.RESET_DEBOUNCE_MS) {
      console.debug(`[CacheManager] Skipping reset (debounced): ${reason}`);
      return {
        success: true,
        message: "Reset skipped (debounced)",
        duration: 0,
      };
    }
    this.lastResetTime = now;

    console.log(`[CacheManager] Resetting cache: ${reason}`);

    try {
      // Clear all cache data
      await this.client.clearStore();
      console.debug("[CacheManager] Cache cleared successfully");

      // Optionally refetch active queries to repopulate with fresh data
      if (refetchActive) {
        await this.client.refetchQueries({
          include: "active",
        });
        console.debug("[CacheManager] Active queries refetched");
      }

      const duration = performance.now() - startTime;
      console.log(
        `[CacheManager] Cache reset completed in ${duration.toFixed(1)}ms`
      );

      return {
        success: true,
        message: `Cache reset completed: ${reason}`,
        duration,
      };
    } catch (error) {
      const duration = performance.now() - startTime;
      console.error("[CacheManager] Error resetting cache:", error);

      return {
        success: false,
        message: `Cache reset failed: ${
          error instanceof Error ? error.message : "Unknown error"
        }`,
        duration,
      };
    }
  }

  /**
   * Performs a "soft reset" by only refetching active queries without clearing the cache.
   *
   * This is useful for refreshing data after operations that might have made
   * the cache stale, but where a full clear isn't necessary.
   *
   * @param reason - Reason for the refresh (for logging)
   * @returns Result of the operation
   */
  async refreshActiveQueries(
    reason: string = "manual_refresh"
  ): Promise<CacheOperationResult> {
    const startTime = performance.now();

    console.log(`[CacheManager] Refreshing active queries: ${reason}`);

    try {
      await this.client.refetchQueries({
        include: "active",
      });

      const duration = performance.now() - startTime;
      console.log(
        `[CacheManager] Active queries refreshed in ${duration.toFixed(1)}ms`
      );

      return {
        success: true,
        message: `Active queries refreshed: ${reason}`,
        duration,
      };
    } catch (error) {
      const duration = performance.now() - startTime;
      console.error("[CacheManager] Error refreshing queries:", error);

      return {
        success: false,
        message: `Query refresh failed: ${
          error instanceof Error ? error.message : "Unknown error"
        }`,
        duration,
      };
    }
  }

  // ==========================================================================
  // Targeted Cache Invalidation
  // ==========================================================================

  /**
   * Invalidates cache entries related to a specific entity type.
   *
   * This provides surgical cache invalidation for CRUD operations,
   * avoiding the overhead of a full cache reset.
   *
   * Entity-specific behavior:
   * - **document**: Refetches GET_DOCUMENTS, GET_DOCUMENTS_FOR_LIST, GET_CORPUS_FOLDERS
   * - **corpus**: Refetches GET_CORPUSES
   * - **annotation**: Refetches annotations for the specified document/corpus
   * - **thread**: Refetches conversation threads for the specified document/corpus
   *
   * @param options - Configuration for the invalidation
   * @returns Result of the operation
   */
  async invalidateEntityQueries(
    options: InvalidationOptions
  ): Promise<CacheOperationResult> {
    const {
      entityType,
      corpusId,
      documentId,
      reason = "entity_change",
    } = options;
    const startTime = performance.now();
    const cacheKey = `${entityType}:${corpusId || ""}:${documentId || ""}`;

    // Debounce: prevent rapid repeated invalidations for the same entity
    const now = Date.now();
    const lastTime = this.lastInvalidationTime.get(cacheKey) || 0;
    if (now - lastTime < CacheManager.INVALIDATION_DEBOUNCE_MS) {
      console.debug(
        `[CacheManager] Skipping invalidation (debounced): ${cacheKey}`
      );
      return {
        success: true,
        message: "Invalidation skipped (debounced)",
        duration: 0,
      };
    }
    this.lastInvalidationTime.set(cacheKey, now);
    this.cleanupInvalidationMap(); // Prevent unbounded map growth

    console.log(`[CacheManager] Invalidating ${entityType} queries: ${reason}`);

    try {
      const queriesToRefetch = this.getQueriesToRefetch(entityType, {
        corpusId,
        documentId,
      });

      if (queriesToRefetch.length === 0) {
        console.debug(
          "[CacheManager] No queries to refetch for entity type:",
          entityType
        );
        return {
          success: true,
          message: "No queries to refetch",
          duration: 0,
        };
      }

      await this.client.refetchQueries({
        include: queriesToRefetch,
      });

      const duration = performance.now() - startTime;
      console.log(
        `[CacheManager] Invalidated ${
          queriesToRefetch.length
        } queries in ${duration.toFixed(1)}ms`
      );

      return {
        success: true,
        message: `Invalidated ${entityType} queries: ${reason}`,
        duration,
      };
    } catch (error) {
      const duration = performance.now() - startTime;
      console.error("[CacheManager] Error invalidating queries:", error);

      return {
        success: false,
        message: `Invalidation failed: ${
          error instanceof Error ? error.message : "Unknown error"
        }`,
        duration,
      };
    }
  }

  /**
   * Invalidates queries related to document operations.
   *
   * Convenience method for document CRUD operations.
   *
   * @param corpusId - Optional corpus ID to scope the invalidation
   * @param reason - Reason for the invalidation
   */
  async invalidateDocumentQueries(
    corpusId?: string,
    reason: string = "document_change"
  ): Promise<CacheOperationResult> {
    return this.invalidateEntityQueries({
      entityType: "document",
      corpusId,
      reason,
    });
  }

  /**
   * Invalidates queries related to corpus operations.
   *
   * Convenience method for corpus CRUD operations.
   *
   * @param reason - Reason for the invalidation
   */
  async invalidateCorpusQueries(
    reason: string = "corpus_change"
  ): Promise<CacheOperationResult> {
    return this.invalidateEntityQueries({
      entityType: "corpus",
      reason,
    });
  }

  // ==========================================================================
  // Private Helpers
  // ==========================================================================

  /**
   * Determines which queries should be refetched based on entity type.
   *
   * @param entityType - The type of entity being modified
   * @param context - Additional context for scoping the queries
   * @returns Array of query document nodes to refetch
   */
  private getQueriesToRefetch(
    entityType: InvalidatableEntity,
    context: { corpusId?: string; documentId?: string }
  ): DocumentNode[] {
    switch (entityType) {
      case "document":
        // Document changes affect document lists and folder contents.
        // NOTE: This refetches ALL documents and corpus folders globally.
        // Future optimization: use corpusId/documentId from context to scope
        // refetches with query variables for large corpora.
        // Both the heavy ``GET_DOCUMENTS`` (corpus tabs, modals, relationships)
        // and the slim ``GET_DOCUMENTS_FOR_LIST`` (top-level Documents view)
        // are listed; Apollo's ``refetchQueries`` ignores entries with no
        // active observable, so listing both is safe and only the mounted
        // one will actually refetch.
        return [GET_DOCUMENTS, GET_DOCUMENTS_FOR_LIST, GET_CORPUS_FOLDERS];

      case "corpus":
        // Corpus changes affect corpus lists
        return [GET_CORPUSES];

      case "annotation":
        // Annotation changes are typically handled by the mutation's refetchQueries
        // But if we need to manually invalidate, refetch document-related queries
        return [GET_DOCUMENTS, GET_DOCUMENTS_FOR_LIST];

      case "thread":
        // Thread changes are typically handled by mutation refetchQueries
        // This is a fallback for manual invalidation
        return [];

      default:
        console.warn(`[CacheManager] Unknown entity type: ${entityType}`);
        return [];
    }
  }

  // ==========================================================================
  // Cache State Inspection (for debugging)
  // ==========================================================================

  /**
   * Returns the current cache contents for debugging purposes.
   *
   * @returns Extracted cache data
   */
  extractCacheForDebug(): Record<string, unknown> {
    try {
      return this.client.cache.extract();
    } catch (error) {
      console.error("[CacheManager] Error extracting cache:", error);
      return {};
    }
  }

  /**
   * Logs the current cache size for debugging.
   */
  logCacheSize(): void {
    try {
      const cache = this.client.cache.extract();
      const cacheString = JSON.stringify(cache);
      const sizeKB = (cacheString.length / 1024).toFixed(2);
      const entryCount = Object.keys(cache).length;

      console.log(`[CacheManager] Cache: ${entryCount} entries, ${sizeKB} KB`);
    } catch (error) {
      console.error("[CacheManager] Error logging cache size:", error);
    }
  }
}

// ============================================================================
// Singleton Instance (for non-React contexts)
// ============================================================================

/**
 * Singleton instance for use in non-React contexts (e.g., external scripts,
 * service workers, or utility functions that don't have access to React hooks).
 *
 * NOTE: In React components, prefer using the `useCacheManager` hook from
 * `hooks/useCacheManager.ts` instead. The hook provides proper memoization
 * and integrates with React's lifecycle.
 *
 * These singleton functions are primarily used for:
 * 1. Testing - allows tests to manage the singleton lifecycle
 * 2. Non-React contexts - rare cases where hooks aren't available
 *
 * @see useCacheManager for React component usage
 */
let cacheManagerInstance: CacheManager | null = null;

/**
 * Initializes the CacheManager singleton with an Apollo Client.
 *
 * NOTE: In React components, use the `useCacheManager` hook instead.
 * This function is intended for non-React contexts or testing scenarios.
 *
 * @param client - The Apollo Client instance
 */
export function initializeCacheManager(
  client: ApolloClient<NormalizedCacheObject>
): CacheManager {
  if (cacheManagerInstance) {
    console.warn(
      "[CacheManager] Already initialized, returning existing instance"
    );
    return cacheManagerInstance;
  }

  cacheManagerInstance = new CacheManager(client);
  console.log("[CacheManager] Initialized");
  return cacheManagerInstance;
}

/**
 * Gets the CacheManager singleton instance.
 *
 * NOTE: In React components, use the `useCacheManager` hook instead.
 *
 * @throws Error if CacheManager has not been initialized
 */
export function getCacheManager(): CacheManager {
  if (!cacheManagerInstance) {
    throw new Error(
      "[CacheManager] Not initialized. Call initializeCacheManager() first."
    );
  }
  return cacheManagerInstance;
}

/**
 * Checks if the CacheManager has been initialized.
 */
export function isCacheManagerInitialized(): boolean {
  return cacheManagerInstance !== null;
}

/**
 * Resets the CacheManager singleton. Used in tests to ensure clean state
 * between test cases.
 *
 * @internal This function is intended for testing only.
 */
export function resetCacheManagerForTesting(): void {
  cacheManagerInstance = null;
}

export default CacheManager;
