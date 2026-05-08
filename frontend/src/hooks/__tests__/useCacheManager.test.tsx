/**
 * useCacheManager Hook Tests
 *
 * Tests for the React hook that provides access to cache management operations.
 *
 * Related to Issue #694 - Apollo Cache Stale Data Problem
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "../../test-utils/renderHook";
import { ApolloClient, InMemoryCache, ApolloProvider } from "@apollo/client";
import React from "react";
import { useCacheManager } from "../useCacheManager";

// ============================================================================
// Test Setup
// ============================================================================

/**
 * Creates a mock Apollo Client for testing.
 */
function createMockApolloClient() {
  const cache = new InMemoryCache();

  const client = new ApolloClient({
    cache,
    // No link - we're testing cache operations only
  });

  // Mock the methods we'll be testing
  vi.spyOn(client, "clearStore").mockResolvedValue([]);
  vi.spyOn(client, "refetchQueries").mockResolvedValue([]);

  return client;
}

/**
 * Wrapper component that provides Apollo Client context.
 */
function createWrapper(client: ApolloClient<any>) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <ApolloProvider client={client}>{children}</ApolloProvider>;
  };
}

// ============================================================================
// Hook Tests
// ============================================================================

describe("useCacheManager", () => {
  let client: ApolloClient<any>;

  beforeEach(() => {
    vi.clearAllMocks();
    client = createMockApolloClient();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("Hook Initialization", () => {
    it("should return all expected methods", () => {
      // Arrange
      const wrapper = createWrapper(client);

      // Act
      const { result } = renderHook(() => useCacheManager(), { wrapper });

      // Assert
      expect(result.current).toHaveProperty("resetOnAuthChange");
      expect(result.current).toHaveProperty("refreshActiveQueries");
      expect(result.current).toHaveProperty("invalidateEntityQueries");
      expect(result.current).toHaveProperty("invalidateDocumentQueries");
      expect(result.current).toHaveProperty("invalidateCorpusQueries");
      expect(result.current).toHaveProperty("logCacheSize");
    });

    it("should return stable function references", () => {
      // Arrange
      const wrapper = createWrapper(client);

      // Act
      const { result, rerender } = renderHook(() => useCacheManager(), {
        wrapper,
      });
      const firstRender = { ...result.current };
      rerender();
      const secondRender = result.current;

      // Assert - Functions should be memoized
      expect(firstRender.resetOnAuthChange).toBe(
        secondRender.resetOnAuthChange
      );
      expect(firstRender.refreshActiveQueries).toBe(
        secondRender.refreshActiveQueries
      );
      expect(firstRender.invalidateEntityQueries).toBe(
        secondRender.invalidateEntityQueries
      );
    });
  });

  describe("resetOnAuthChange", () => {
    it("should clear the Apollo cache", async () => {
      // Arrange
      const wrapper = createWrapper(client);
      const { result } = renderHook(() => useCacheManager(), { wrapper });

      // Act
      await act(async () => {
        await result.current.resetOnAuthChange({ reason: "test_login" });
      });

      // Assert
      expect(client.clearStore).toHaveBeenCalled();
    });

    it("should refetch active queries when refetchActive is true", async () => {
      // Arrange
      const wrapper = createWrapper(client);
      const { result } = renderHook(() => useCacheManager(), { wrapper });

      // Act
      await act(async () => {
        await result.current.resetOnAuthChange({
          reason: "test",
          refetchActive: true,
        });
      });

      // Assert
      expect(client.refetchQueries).toHaveBeenCalledWith({ include: "active" });
    });

    it("should not refetch active queries by default", async () => {
      // Arrange
      const wrapper = createWrapper(client);
      const { result } = renderHook(() => useCacheManager(), { wrapper });

      // Act
      await act(async () => {
        await result.current.resetOnAuthChange({ reason: "test" });
      });

      // Assert
      expect(client.refetchQueries).not.toHaveBeenCalled();
    });

    it("should skip refetch when refetchActive is false", async () => {
      // Arrange
      const wrapper = createWrapper(client);
      const { result } = renderHook(() => useCacheManager(), { wrapper });

      // Act
      await act(async () => {
        await result.current.resetOnAuthChange({
          reason: "test",
          refetchActive: false,
        });
      });

      // Assert
      expect(client.clearStore).toHaveBeenCalled();
      expect(client.refetchQueries).not.toHaveBeenCalled();
    });

    it("should return success result", async () => {
      // Arrange
      const wrapper = createWrapper(client);
      const { result } = renderHook(() => useCacheManager(), { wrapper });

      // Act
      let operationResult;
      await act(async () => {
        operationResult = await result.current.resetOnAuthChange({
          reason: "test",
        });
      });

      // Assert
      expect(operationResult).toHaveProperty("success", true);
      expect(operationResult).toHaveProperty("message");
      expect(operationResult).toHaveProperty("duration");
    });
  });

  describe("refreshActiveQueries", () => {
    it("should refetch active queries without clearing cache", async () => {
      // Arrange
      const wrapper = createWrapper(client);
      const { result } = renderHook(() => useCacheManager(), { wrapper });

      // Act
      await act(async () => {
        await result.current.refreshActiveQueries("manual_refresh");
      });

      // Assert
      expect(client.refetchQueries).toHaveBeenCalledWith({ include: "active" });
      expect(client.clearStore).not.toHaveBeenCalled();
    });
  });

  describe("invalidateEntityQueries", () => {
    it("should refetch queries for document entity type", async () => {
      // Arrange
      const wrapper = createWrapper(client);
      const { result } = renderHook(() => useCacheManager(), { wrapper });

      // Act
      await act(async () => {
        await result.current.invalidateEntityQueries({
          entityType: "document",
          corpusId: "corpus-1",
          reason: "upload",
        });
      });

      // Assert
      expect(client.refetchQueries).toHaveBeenCalled();
    });

    it("should refetch queries for corpus entity type", async () => {
      // Arrange
      const wrapper = createWrapper(client);
      const { result } = renderHook(() => useCacheManager(), { wrapper });

      // Act
      await act(async () => {
        await result.current.invalidateEntityQueries({
          entityType: "corpus",
          reason: "create",
        });
      });

      // Assert
      expect(client.refetchQueries).toHaveBeenCalled();
    });
  });

  describe("invalidateDocumentQueries", () => {
    it("should invalidate document-related queries", async () => {
      // Arrange
      const wrapper = createWrapper(client);
      const { result } = renderHook(() => useCacheManager(), { wrapper });

      // Act
      let operationResult;
      await act(async () => {
        operationResult = await result.current.invalidateDocumentQueries(
          "corpus-1",
          "document_upload"
        );
      });

      // Assert
      expect(operationResult).toHaveProperty("success", true);
      expect(client.refetchQueries).toHaveBeenCalled();
    });

    it("should work without corpusId", async () => {
      // Arrange
      const wrapper = createWrapper(client);
      const { result } = renderHook(() => useCacheManager(), { wrapper });

      // Act
      let operationResult;
      await act(async () => {
        operationResult = await result.current.invalidateDocumentQueries(
          undefined,
          "global_document_change"
        );
      });

      // Assert
      expect(operationResult).toHaveProperty("success", true);
    });
  });

  describe("invalidateCorpusQueries", () => {
    it("should invalidate corpus-related queries", async () => {
      // Arrange
      const wrapper = createWrapper(client);
      const { result } = renderHook(() => useCacheManager(), { wrapper });

      // Act
      let operationResult;
      await act(async () => {
        operationResult = await result.current.invalidateCorpusQueries(
          "corpus_delete"
        );
      });

      // Assert
      expect(operationResult).toHaveProperty("success", true);
      expect(client.refetchQueries).toHaveBeenCalled();
    });
  });

  describe("logCacheSize", () => {
    it("should not throw when called", async () => {
      // Arrange
      const wrapper = createWrapper(client);
      const { result } = renderHook(() => useCacheManager(), { wrapper });

      // Act & Assert
      expect(() => result.current.logCacheSize()).not.toThrow();
    });
  });
});

// ============================================================================
// Integration Tests with Component Lifecycle
// ============================================================================

describe("useCacheManager Component Lifecycle", () => {
  let client: ApolloClient<any>;

  beforeEach(() => {
    vi.clearAllMocks();
    client = createMockApolloClient();
  });

  it("should handle component unmount gracefully", async () => {
    // Arrange
    const wrapper = createWrapper(client);
    const { result, unmount } = renderHook(() => useCacheManager(), {
      wrapper,
    });

    // Act - Start an operation then unmount
    let operationResult: unknown;
    await act(async () => {
      operationResult = await result.current.resetOnAuthChange({
        reason: "test",
      });
    });

    // Unmount during operation
    unmount();

    // Assert - Should not throw
    expect(operationResult).toBeDefined();
  });

  it("should work with multiple hook instances", async () => {
    // Arrange
    const wrapper = createWrapper(client);
    const { result: result1 } = renderHook(() => useCacheManager(), {
      wrapper,
    });
    const { result: result2 } = renderHook(() => useCacheManager(), {
      wrapper,
    });

    // Act - Use both instances
    await act(async () => {
      await result1.current.resetOnAuthChange({ reason: "instance_1" });
    });

    // Small delay to avoid debounce
    await new Promise((resolve) => setTimeout(resolve, 1100));

    await act(async () => {
      await result2.current.resetOnAuthChange({ reason: "instance_2" });
    });

    // Assert - Both should work independently
    // Note: Due to debouncing, the second call might be debounced if called too quickly
    expect(client.clearStore).toHaveBeenCalled();
  });
});

// ============================================================================
// Human-Readable Scenario Tests
// ============================================================================

describe("useCacheManager Usage Scenarios", () => {
  let client: ApolloClient<any>;

  beforeEach(() => {
    vi.clearAllMocks();
    client = createMockApolloClient();
  });

  it("Logout button component should be able to clear cache before logout", async () => {
    // Scenario: A logout button component needs to clear the cache
    // when the user clicks logout

    const wrapper = createWrapper(client);
    const { result } = renderHook(() => useCacheManager(), { wrapper });

    // Simulate logout button click
    await act(async () => {
      const response = await result.current.resetOnAuthChange({
        reason: "user_logout",
        refetchActive: false, // No need to refetch - user is logging out
      });
      expect(response.success).toBe(true);
    });

    // Cache should be cleared
    expect(client.clearStore).toHaveBeenCalled();
  });

  it("Document upload modal should refresh document list after upload", async () => {
    // Scenario: After a document is uploaded, the document list
    // should refresh to show the new document

    const wrapper = createWrapper(client);
    const { result } = renderHook(() => useCacheManager(), { wrapper });

    // Simulate document upload completion
    await act(async () => {
      const response = await result.current.invalidateDocumentQueries(
        "corpus-123",
        "document_upload_complete"
      );
      expect(response.success).toBe(true);
    });

    // Document queries should be refetched
    expect(client.refetchQueries).toHaveBeenCalled();
  });

  it("Corpus creation form should refresh corpus list after creation", async () => {
    // Scenario: After a corpus is created, the corpus list
    // should refresh to show the new corpus

    const wrapper = createWrapper(client);
    const { result } = renderHook(() => useCacheManager(), { wrapper });

    // Simulate corpus creation completion
    await act(async () => {
      const response = await result.current.invalidateCorpusQueries(
        "corpus_creation_complete"
      );
      expect(response.success).toBe(true);
    });

    // Corpus queries should be refetched
    expect(client.refetchQueries).toHaveBeenCalled();
  });

  it("Manual refresh button should refresh all active data", async () => {
    // Scenario: A user clicks a "Refresh Data" button to manually
    // refresh all displayed data

    const wrapper = createWrapper(client);
    const { result } = renderHook(() => useCacheManager(), { wrapper });

    // Simulate refresh button click
    await act(async () => {
      const response = await result.current.refreshActiveQueries(
        "manual_user_refresh"
      );
      expect(response.success).toBe(true);
    });

    // Active queries should be refetched
    expect(client.refetchQueries).toHaveBeenCalledWith({ include: "active" });
    // But cache should not be cleared (just refresh, not reset)
    expect(client.clearStore).not.toHaveBeenCalled();
  });
});
