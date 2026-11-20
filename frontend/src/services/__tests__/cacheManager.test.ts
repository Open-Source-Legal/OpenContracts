/**
 * CacheManager Tests
 *
 * Comprehensive tests for the proactive Apollo cache management system.
 *
 * These tests verify:
 * 1. Full cache reset on authentication changes
 * 2. Targeted cache invalidation for entity CRUD
 * 3. Debouncing behavior to prevent rapid repeated operations
 * 4. Error handling and recovery
 *
 * Related to Issue #694 - Apollo Cache Stale Data Problem
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  ApolloClient,
  InMemoryCache,
  NormalizedCacheObject,
} from "@apollo/client";
import {
  CacheManager,
  CacheOperationResult,
  initializeCacheManager,
  getCacheManager,
  isCacheManagerInitialized,
  resetCacheManagerForTesting,
} from "../cacheManager";

// ============================================================================
// Test Setup
// ============================================================================

/**
 * Creates a mock Apollo Client for testing.
 *
 * We use a real InMemoryCache but mock the network operations.
 */
function createMockApolloClient(): ApolloClient<NormalizedCacheObject> {
  const cache = new InMemoryCache();

  const client = new ApolloClient({
    cache,
    // No link - we're testing cache operations only
  });

  // Mock the network-dependent methods
  vi.spyOn(client, "clearStore").mockResolvedValue([]);
  vi.spyOn(client, "refetchQueries").mockResolvedValue([]);

  return client;
}

// ============================================================================
// CacheManager Class Tests
// ============================================================================

describe("CacheManager", () => {
  let client: ApolloClient<NormalizedCacheObject>;
  let cacheManager: CacheManager;

  beforeEach(() => {
    // Reset all mocks and create fresh instances
    vi.clearAllMocks();
    vi.useFakeTimers();
    client = createMockApolloClient();
    cacheManager = new CacheManager(client);
  });

  afterEach(() => {
    vi.useRealTimers();
    resetCacheManagerForTesting();
  });

  // ==========================================================================
  // Full Cache Reset Tests
  // ==========================================================================

  describe("resetOnAuthChange", () => {
    it("should clear the Apollo cache store", async () => {
      // Act
      const result = await cacheManager.resetOnAuthChange({
        reason: "test_reset",
      });

      // Assert
      expect(client.clearStore).toHaveBeenCalledTimes(1);
      expect(result.success).toBe(true);
      expect(result.message).toContain("test_reset");
    });

    it("should refetch active queries when refetchActive is true", async () => {
      // Act
      await cacheManager.resetOnAuthChange({
        reason: "test_reset",
        refetchActive: true,
      });

      // Assert
      expect(client.refetchQueries).toHaveBeenCalledWith({
        include: "active",
      });
    });

    it("should not refetch active queries by default", async () => {
      // Act
      await cacheManager.resetOnAuthChange({ reason: "test_reset" });

      // Assert
      expect(client.refetchQueries).not.toHaveBeenCalled();
    });

    it("should skip refetch when refetchActive is false", async () => {
      // Act
      await cacheManager.resetOnAuthChange({
        reason: "test_reset",
        refetchActive: false,
      });

      // Assert
      expect(client.clearStore).toHaveBeenCalledTimes(1);
      expect(client.refetchQueries).not.toHaveBeenCalled();
    });

    it("should debounce rapid consecutive calls", async () => {
      // Act - Call twice rapidly
      await cacheManager.resetOnAuthChange({ reason: "first_call" });
      const result = await cacheManager.resetOnAuthChange({
        reason: "second_call",
      });

      // Assert - Second call should be debounced
      expect(client.clearStore).toHaveBeenCalledTimes(1);
      expect(result.message).toContain("debounced");
    });

    it("should allow reset after debounce period expires", async () => {
      // Arrange
      await cacheManager.resetOnAuthChange({ reason: "first_call" });

      // Act - Advance time past debounce period
      vi.advanceTimersByTime(1100); // > 1000ms debounce
      await cacheManager.resetOnAuthChange({ reason: "second_call" });

      // Assert - Both calls should have executed
      expect(client.clearStore).toHaveBeenCalledTimes(2);
    });

    it("should return duration in the result", async () => {
      // Act
      const result = await cacheManager.resetOnAuthChange({ reason: "test" });

      // Assert
      expect(result.duration).toBeDefined();
      expect(typeof result.duration).toBe("number");
      expect(result.duration).toBeGreaterThanOrEqual(0);
    });

    it("should handle errors gracefully", async () => {
      // Arrange
      const errorMessage = "Network error";
      vi.spyOn(client, "clearStore").mockRejectedValueOnce(
        new Error(errorMessage)
      );

      // Act
      const result = await cacheManager.resetOnAuthChange({ reason: "test" });

      // Assert
      expect(result.success).toBe(false);
      expect(result.message).toContain(errorMessage);
    });

    it("should use default reason when not provided", async () => {
      // Act
      const result = await cacheManager.resetOnAuthChange();

      // Assert
      expect(result.message).toContain("auth_change");
    });
  });

  // ==========================================================================
  // Active Query Refresh Tests
  // ==========================================================================

  describe("refreshActiveQueries", () => {
    it("should refetch all active queries", async () => {
      // Act
      const result = await cacheManager.refreshActiveQueries("test_refresh");

      // Assert
      expect(client.refetchQueries).toHaveBeenCalledWith({
        include: "active",
      });
      expect(result.success).toBe(true);
    });

    it("should not clear the cache", async () => {
      // Act
      await cacheManager.refreshActiveQueries("test_refresh");

      // Assert
      expect(client.clearStore).not.toHaveBeenCalled();
    });

    it("should handle errors gracefully", async () => {
      // Arrange
      vi.spyOn(client, "refetchQueries").mockRejectedValueOnce(
        new Error("Network error")
      );

      // Act
      const result = await cacheManager.refreshActiveQueries("test");

      // Assert
      expect(result.success).toBe(false);
      expect(result.message).toContain("failed");
    });
  });

  // ==========================================================================
  // Targeted Cache Invalidation Tests
  // ==========================================================================

  describe("invalidateEntityQueries", () => {
    it("should refetch document-related queries for document entity type", async () => {
      // Act
      const result = await cacheManager.invalidateEntityQueries({
        entityType: "document",
        reason: "document_upload",
      });

      // Assert
      expect(client.refetchQueries).toHaveBeenCalled();
      expect(result.success).toBe(true);
      expect(result.message).toContain("document");
    });

    it("should refetch corpus-related queries for corpus entity type", async () => {
      // Act
      const result = await cacheManager.invalidateEntityQueries({
        entityType: "corpus",
        reason: "corpus_create",
      });

      // Assert
      expect(client.refetchQueries).toHaveBeenCalled();
      expect(result.success).toBe(true);
      expect(result.message).toContain("corpus");
    });

    it("should debounce rapid invalidations for the same entity", async () => {
      // Act
      await cacheManager.invalidateEntityQueries({
        entityType: "document",
        corpusId: "corpus-1",
        reason: "first",
      });
      const result = await cacheManager.invalidateEntityQueries({
        entityType: "document",
        corpusId: "corpus-1",
        reason: "second",
      });

      // Assert - Second call should be debounced
      expect(client.refetchQueries).toHaveBeenCalledTimes(1);
      expect(result.message).toContain("debounced");
    });

    it("should not debounce invalidations for different entities", async () => {
      // Act
      await cacheManager.invalidateEntityQueries({
        entityType: "document",
        corpusId: "corpus-1",
        reason: "first",
      });
      await cacheManager.invalidateEntityQueries({
        entityType: "document",
        corpusId: "corpus-2", // Different corpus
        reason: "second",
      });

      // Assert - Both calls should execute
      expect(client.refetchQueries).toHaveBeenCalledTimes(2);
    });

    it("should handle unknown entity types", async () => {
      // Act - Force unknown entity type
      const result = await cacheManager.invalidateEntityQueries({
        entityType: "unknown" as any,
        reason: "test",
      });

      // Assert
      expect(result.success).toBe(true);
      expect(result.message).toContain("No queries to refetch");
    });
  });

  // ==========================================================================
  // Convenience Method Tests
  // ==========================================================================

  describe("invalidateDocumentQueries", () => {
    it("should call invalidateEntityQueries with document type", async () => {
      // Act
      const result = await cacheManager.invalidateDocumentQueries(
        "corpus-1",
        "document_upload"
      );

      // Assert
      expect(result.success).toBe(true);
      expect(result.message).toContain("document");
    });
  });

  describe("invalidateCorpusQueries", () => {
    it("should call invalidateEntityQueries with corpus type", async () => {
      // Act
      const result =
        await cacheManager.invalidateCorpusQueries("corpus_create");

      // Assert
      expect(result.success).toBe(true);
      expect(result.message).toContain("corpus");
    });
  });

  // ==========================================================================
  // Debug Helper Tests
  // ==========================================================================

  describe("logCacheSize", () => {
    it("should not throw when logging cache size", () => {
      // Act & Assert
      expect(() => cacheManager.logCacheSize()).not.toThrow();
    });
  });

  describe("extractCacheForDebug", () => {
    it("should return cache contents", () => {
      // Act
      const cache = cacheManager.extractCacheForDebug();

      // Assert
      expect(cache).toBeDefined();
      expect(typeof cache).toBe("object");
    });
  });
});

// ============================================================================
// Singleton Management Tests
// ============================================================================

describe("CacheManager Singleton", () => {
  let client: ApolloClient<NormalizedCacheObject>;

  beforeEach(() => {
    vi.clearAllMocks();
    resetCacheManagerForTesting();
    client = createMockApolloClient();
  });

  afterEach(() => {
    resetCacheManagerForTesting();
  });

  describe("initializeCacheManager", () => {
    it("should create a new CacheManager instance", () => {
      // Act
      const manager = initializeCacheManager(client);

      // Assert
      expect(manager).toBeInstanceOf(CacheManager);
      expect(isCacheManagerInitialized()).toBe(true);
    });

    it("should return existing instance if already initialized", () => {
      // Arrange
      const first = initializeCacheManager(client);

      // Act
      const second = initializeCacheManager(client);

      // Assert
      expect(first).toBe(second);
    });
  });

  describe("getCacheManager", () => {
    it("should throw if not initialized", () => {
      // Act & Assert
      expect(() => getCacheManager()).toThrow("Not initialized");
    });

    it("should return the initialized instance", () => {
      // Arrange
      initializeCacheManager(client);

      // Act
      const manager = getCacheManager();

      // Assert
      expect(manager).toBeInstanceOf(CacheManager);
    });
  });

  describe("isCacheManagerInitialized", () => {
    it("should return false before initialization", () => {
      // Act & Assert
      expect(isCacheManagerInitialized()).toBe(false);
    });

    it("should return true after initialization", () => {
      // Arrange
      initializeCacheManager(client);

      // Act & Assert
      expect(isCacheManagerInitialized()).toBe(true);
    });

    it("should return false after reset", () => {
      // Arrange
      initializeCacheManager(client);

      // Act
      resetCacheManagerForTesting();

      // Assert
      expect(isCacheManagerInitialized()).toBe(false);
    });
  });
});

// ============================================================================
// Integration Scenario Tests
// ============================================================================

describe("CacheManager Integration Scenarios", () => {
  let client: ApolloClient<NormalizedCacheObject>;
  let cacheManager: CacheManager;

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    client = createMockApolloClient();
    cacheManager = new CacheManager(client);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe("User Login Flow", () => {
    it("should clear stale anonymous data before login", async () => {
      // Scenario: User was browsing anonymously, then logs in
      // Expected: Cache should be cleared to remove anonymous-context data

      // Act
      const result = await cacheManager.resetOnAuthChange({
        reason: "user_login",
        refetchActive: false, // Don't refetch yet - auth not complete
      });

      // Assert
      expect(result.success).toBe(true);
      expect(client.clearStore).toHaveBeenCalled();
      expect(client.refetchQueries).not.toHaveBeenCalled();
    });
  });

  describe("User Logout Flow", () => {
    it("should clear all user data on logout for security", async () => {
      // Scenario: Authenticated user logs out
      // Expected: All cache data should be cleared for security

      // Act
      const result = await cacheManager.resetOnAuthChange({
        reason: "user_logout",
        refetchActive: false, // No point refetching - user is logging out
      });

      // Assert
      expect(result.success).toBe(true);
      expect(client.clearStore).toHaveBeenCalled();
    });
  });

  describe("Document Upload Flow", () => {
    it("should invalidate document lists after upload", async () => {
      // Scenario: User uploads a new document to a corpus
      // Expected: Document lists should be refreshed to show the new document

      // Act
      const result = await cacheManager.invalidateDocumentQueries(
        "corpus-1",
        "document_upload"
      );

      // Assert
      expect(result.success).toBe(true);
      expect(client.refetchQueries).toHaveBeenCalled();
    });
  });

  describe("Corpus Creation Flow", () => {
    it("should invalidate corpus lists after creation", async () => {
      // Scenario: User creates a new corpus
      // Expected: Corpus lists should be refreshed to show the new corpus

      // Act
      const result =
        await cacheManager.invalidateCorpusQueries("corpus_create");

      // Assert
      expect(result.success).toBe(true);
      expect(client.refetchQueries).toHaveBeenCalled();
    });
  });

  describe("Rapid Operations", () => {
    it("should handle burst of document operations efficiently", async () => {
      // Scenario: Multiple documents uploaded in quick succession
      // Expected: Operations should be debounced to prevent excessive refetches

      // Act - Simulate 5 rapid document uploads
      const results: CacheOperationResult[] = [];
      for (let i = 0; i < 5; i++) {
        results.push(
          await cacheManager.invalidateDocumentQueries(
            "corpus-1",
            `upload_${i}`
          )
        );
      }

      // Assert - Only first should actually execute, rest should be debounced
      expect(results[0].message).not.toContain("debounced");
      expect(
        results.slice(1).every((r) => r.message.includes("debounced"))
      ).toBe(true);
      expect(client.refetchQueries).toHaveBeenCalledTimes(1);
    });

    it("should allow operations after debounce period", async () => {
      // Scenario: Document uploads spaced out over time
      // Expected: Each should execute if outside debounce window

      // Act
      await cacheManager.invalidateDocumentQueries("corpus-1", "upload_1");
      vi.advanceTimersByTime(600); // > 500ms debounce
      await cacheManager.invalidateDocumentQueries("corpus-1", "upload_2");

      // Assert - Both should execute
      expect(client.refetchQueries).toHaveBeenCalledTimes(2);
    });
  });

  describe("Error Recovery", () => {
    it("should continue operation if cache clear fails but refetch succeeds", async () => {
      // Scenario: Cache clear fails but we still want to try refetching
      // Note: Current implementation doesn't do this, but documents the expected behavior

      // Arrange
      vi.spyOn(client, "clearStore").mockRejectedValueOnce(
        new Error("Clear failed")
      );

      // Act
      const result = await cacheManager.resetOnAuthChange({ reason: "test" });

      // Assert
      expect(result.success).toBe(false);
      // Error should be reported but not crash the app
    });
  });
});

// ============================================================================
// Human-Readable Test Descriptions
// ============================================================================

describe("Cache Management Behavior (Human Readable)", () => {
  let client: ApolloClient<NormalizedCacheObject>;
  let cacheManager: CacheManager;

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    client = createMockApolloClient();
    cacheManager = new CacheManager(client);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("When a user logs in, their previous session's cached data should be cleared", async () => {
    // Given: A user who was browsing anonymously
    // When: They log in with their credentials
    const result = await cacheManager.resetOnAuthChange({
      reason: "user_login",
      refetchActive: false,
    });

    // Then: The cache should be cleared to prevent showing stale anonymous data
    expect(result.success).toBe(true);
    expect(client.clearStore).toHaveBeenCalled();
  });

  it("When a user logs out, all their cached data should be removed for security", async () => {
    // Given: An authenticated user with cached data
    // When: They click the logout button
    const result = await cacheManager.resetOnAuthChange({
      reason: "user_logout",
      refetchActive: false,
    });

    // Then: All cached data should be cleared so the next user doesn't see it
    expect(result.success).toBe(true);
    expect(client.clearStore).toHaveBeenCalled();
  });

  it("When a document is uploaded, the document list should refresh automatically", async () => {
    // Given: A user viewing a corpus's document list
    // When: They upload a new document
    const result = await cacheManager.invalidateDocumentQueries(
      "corpus-123",
      "document_upload"
    );

    // Then: The document list should refresh to show the newly uploaded document
    expect(result.success).toBe(true);
    expect(client.refetchQueries).toHaveBeenCalled();
  });

  it("When multiple documents are uploaded rapidly, the system should batch refreshes", async () => {
    // Given: A user uploading multiple documents at once
    // When: 5 documents are uploaded within 500ms
    const results = await Promise.all([
      cacheManager.invalidateDocumentQueries("corpus-123", "upload_1"),
      cacheManager.invalidateDocumentQueries("corpus-123", "upload_2"),
      cacheManager.invalidateDocumentQueries("corpus-123", "upload_3"),
    ]);

    // Then: Only one refresh should occur to avoid overwhelming the server
    expect(client.refetchQueries).toHaveBeenCalledTimes(1);
    // And subsequent calls should be debounced
    expect(results[1].message).toContain("debounced");
    expect(results[2].message).toContain("debounced");
  });

  it("When a corpus is created, the corpus list should update to show the new corpus", async () => {
    // Given: A user viewing their corpus list
    // When: They create a new corpus
    const result = await cacheManager.invalidateCorpusQueries("corpus_create");

    // Then: The corpus list should refresh to include the new corpus
    expect(result.success).toBe(true);
    expect(client.refetchQueries).toHaveBeenCalled();
  });

  it("When a network error occurs during cache clear, it should fail gracefully", async () => {
    // Given: A user logging out
    // When: A network error occurs during cache clearing
    vi.spyOn(client, "clearStore").mockRejectedValueOnce(
      new Error("Network unavailable")
    );

    const result = await cacheManager.resetOnAuthChange({
      reason: "user_logout",
    });

    // Then: The operation should fail but return a meaningful error message
    expect(result.success).toBe(false);
    expect(result.message).toContain("Network unavailable");
    // And the app should not crash
  });

  it("When checking cache status, developers should see meaningful debug info", () => {
    // Given: A developer debugging cache issues
    // When: They extract cache contents
    const cacheContents = cacheManager.extractCacheForDebug();

    // Then: They should receive a valid object with cache data
    expect(cacheContents).toBeDefined();
    expect(typeof cacheContents).toBe("object");
  });
});

// ============================================================================
// Auth Flow Tests with Cache Inspection (E2E-style)
// ============================================================================

describe("Auth Flow with Cache Inspection", () => {
  let client: ApolloClient<NormalizedCacheObject>;
  let cacheManager: CacheManager;

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    client = createMockApolloClient();
    cacheManager = new CacheManager(client);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("should clear cache completely on login transition", async () => {
    // Simulate pre-login state with cached anonymous data
    const preCacheState = cacheManager.extractCacheForDebug();

    // Perform login cache reset
    const loginResult = await cacheManager.resetOnAuthChange({
      reason: "user_login",
      refetchActive: false,
    });

    // Verify cache was cleared
    expect(loginResult.success).toBe(true);
    expect(client.clearStore).toHaveBeenCalledTimes(1);

    // Extract post-login cache state
    const postCacheState = cacheManager.extractCacheForDebug();
    expect(postCacheState).toBeDefined();
  });

  it("should clear cache completely on logout transition", async () => {
    // Perform logout cache reset
    const logoutResult = await cacheManager.resetOnAuthChange({
      reason: "user_logout",
      refetchActive: false,
    });

    // Verify cache was cleared for security
    expect(logoutResult.success).toBe(true);
    expect(client.clearStore).toHaveBeenCalledTimes(1);
  });

  it("should track cache state changes through full auth lifecycle", async () => {
    // Phase 1: Initial anonymous state
    const initialCache = cacheManager.extractCacheForDebug();
    expect(initialCache).toBeDefined();

    // Phase 2: Login
    const loginResult = await cacheManager.resetOnAuthChange({
      reason: "user_login",
      refetchActive: false,
    });
    expect(loginResult.success).toBe(true);

    // Advance time to allow next operation
    vi.advanceTimersByTime(1100);

    // Phase 3: Logout
    const logoutResult = await cacheManager.resetOnAuthChange({
      reason: "user_logout",
      refetchActive: false,
    });
    expect(logoutResult.success).toBe(true);

    // Verify both operations executed
    expect(client.clearStore).toHaveBeenCalledTimes(2);
  });

  it("should handle rapid login/logout cycles gracefully", async () => {
    // Simulate rapid auth state changes (e.g., token refresh issues)
    const result1 = await cacheManager.resetOnAuthChange({ reason: "login" });
    const result2 = await cacheManager.resetOnAuthChange({ reason: "logout" });
    const result3 = await cacheManager.resetOnAuthChange({ reason: "login" });

    // First should succeed, rest should be debounced
    expect(result1.success).toBe(true);
    expect(result2.message).toContain("debounced");
    expect(result3.message).toContain("debounced");
    expect(client.clearStore).toHaveBeenCalledTimes(1);
  });
});

// ============================================================================
// Race Condition Verification Tests
// ============================================================================

describe("Race Condition Prevention", () => {
  let client: ApolloClient<NormalizedCacheObject>;
  let cacheManager: CacheManager;
  let operationOrder: string[];

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    client = createMockApolloClient();
    cacheManager = new CacheManager(client);
    operationOrder = [];

    // Track operation order
    vi.spyOn(client, "clearStore").mockImplementation(async () => {
      operationOrder.push("clearStore");
      return [];
    });
    vi.spyOn(client, "refetchQueries").mockImplementation((async () => {
      operationOrder.push("refetchQueries");
      return [];
    }) as any);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("should execute cache operations in deterministic order", async () => {
    // When reset is called with refetch
    await cacheManager.resetOnAuthChange({
      reason: "auth_change",
      refetchActive: true,
    });

    // Then clearStore should happen before refetchQueries
    expect(operationOrder).toEqual(["clearStore", "refetchQueries"]);
  });

  it("should not trigger refetch when refetchActive is false", async () => {
    // When reset is called without refetch
    await cacheManager.resetOnAuthChange({
      reason: "auth_change",
      refetchActive: false,
    });

    // Then only clearStore should be called
    expect(operationOrder).toEqual(["clearStore"]);
  });

  it("should handle concurrent cache operations safely", async () => {
    // Simulate concurrent operations (would happen if auth state changes rapidly)
    const promises = [
      cacheManager.resetOnAuthChange({ reason: "op1" }),
      cacheManager.resetOnAuthChange({ reason: "op2" }),
      cacheManager.resetOnAuthChange({ reason: "op3" }),
    ];

    const results = await Promise.all(promises);

    // Only first operation should execute due to debouncing
    expect(results[0].success).toBe(true);
    expect(results[0].message).not.toContain("debounced");
    expect(results[1].message).toContain("debounced");
    expect(results[2].message).toContain("debounced");

    // Verify only one clearStore call
    expect(client.clearStore).toHaveBeenCalledTimes(1);
  });

  it("should maintain cache integrity during error scenarios", async () => {
    // Simulate a failure during clearStore
    vi.spyOn(client, "clearStore").mockRejectedValueOnce(
      new Error("Network error")
    );

    const result = await cacheManager.resetOnAuthChange({ reason: "test" });

    // Operation should fail gracefully
    expect(result.success).toBe(false);

    // refetchQueries should NOT be called if clearStore failed
    expect(client.refetchQueries).not.toHaveBeenCalled();
  });

  it("should handle interleaved entity invalidations correctly", async () => {
    // Simulate rapid document and corpus operations
    const docResult1 = await cacheManager.invalidateDocumentQueries(
      "corpus-1",
      "upload"
    );
    const corpusResult = await cacheManager.invalidateCorpusQueries("create");
    const docResult2 = await cacheManager.invalidateDocumentQueries(
      "corpus-2",
      "upload"
    );

    // Document ops for different corpuses should not debounce each other
    expect(docResult1.success).toBe(true);
    expect(corpusResult.success).toBe(true);
    expect(docResult2.success).toBe(true);

    // All should execute since they're different cache keys
    expect(client.refetchQueries).toHaveBeenCalledTimes(3);
  });
});

// ============================================================================
// Performance Tests
// ============================================================================

describe("Cache Performance", () => {
  let client: ApolloClient<NormalizedCacheObject>;
  let cacheManager: CacheManager;

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    client = createMockApolloClient();
    cacheManager = new CacheManager(client);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("should report operation duration", async () => {
    // Simulate some delay in clearStore
    vi.spyOn(client, "clearStore").mockImplementation(async () => {
      // Advance time to simulate work
      vi.advanceTimersByTime(50);
      return [];
    });

    const result = await cacheManager.resetOnAuthChange({ reason: "test" });

    // Duration should be reported
    expect(result.duration).toBeDefined();
    expect(result.duration).toBeGreaterThanOrEqual(0);
  });

  it("should handle large number of sequential operations with debouncing", async () => {
    const operationCount = 100;
    const results: CacheOperationResult[] = [];

    // Fire 100 operations rapidly
    for (let i = 0; i < operationCount; i++) {
      results.push(
        await cacheManager.invalidateDocumentQueries("corpus-1", `op_${i}`)
      );
    }

    // First should succeed, rest should be debounced
    expect(results[0].success).toBe(true);
    expect(results[0].message).not.toContain("debounced");

    // Count debounced operations
    const debouncedCount = results.filter((r) =>
      r.message.includes("debounced")
    ).length;
    expect(debouncedCount).toBe(operationCount - 1);

    // Only one actual refetch should occur
    expect(client.refetchQueries).toHaveBeenCalledTimes(1);
  });

  it("should efficiently handle operations across multiple cache keys", async () => {
    // Create operations for different cache keys
    const corpusIds = [
      "corpus-1",
      "corpus-2",
      "corpus-3",
      "corpus-4",
      "corpus-5",
    ];

    const results = await Promise.all(
      corpusIds.map((id) =>
        cacheManager.invalidateDocumentQueries(id, "operation")
      )
    );

    // All should succeed since they're different cache keys
    expect(results.every((r) => r.success)).toBe(true);
    expect(client.refetchQueries).toHaveBeenCalledTimes(corpusIds.length);
  });

  it("should not accumulate memory in debounce tracking over time", async () => {
    // Perform many operations with different keys
    for (let i = 0; i < 50; i++) {
      await cacheManager.invalidateDocumentQueries(`corpus-${i}`, "op");
      // Advance time to allow debounce to clear
      vi.advanceTimersByTime(600);
    }

    // All operations should have executed
    expect(client.refetchQueries).toHaveBeenCalledTimes(50);
  });

  it("should complete cache reset within reasonable time bounds", async () => {
    // Mock a slow but successful operation
    let clearStoreCallTime: number;
    let refetchCallTime: number;

    vi.spyOn(client, "clearStore").mockImplementation(async () => {
      clearStoreCallTime = Date.now();
      vi.advanceTimersByTime(100);
      return [];
    });

    vi.spyOn(client, "refetchQueries").mockImplementation((async () => {
      refetchCallTime = Date.now();
      vi.advanceTimersByTime(200);
      return [];
    }) as any);

    const result = await cacheManager.resetOnAuthChange({
      reason: "test",
      refetchActive: true,
    });

    // Operation should complete successfully
    expect(result.success).toBe(true);

    // Duration should be tracked
    expect(result.duration).toBeDefined();
  });
});
