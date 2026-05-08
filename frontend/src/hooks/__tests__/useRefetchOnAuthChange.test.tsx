/**
 * useRefetchOnAuthChange Hook Tests
 *
 * Verifies that the hook registers an onClearStore callback that
 * refetches all active queries after any Apollo cache clear,
 * skipping the refetch when there is no auth token (logout).
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook } from "../../test-utils/renderHook";
import { ApolloClient, InMemoryCache, ApolloProvider } from "@apollo/client";
import React from "react";
import { useRefetchOnAuthChange } from "../useRefetchOnAuthChange";
import { authToken } from "../../graphql/cache";

// ============================================================================
// Test Setup
// ============================================================================

function createMockApolloClient() {
  const cache = new InMemoryCache();

  const client = new ApolloClient({
    cache,
  });

  vi.spyOn(client, "refetchQueries").mockResolvedValue([]);

  return client;
}

function createWrapper(client: ApolloClient<any>) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <ApolloProvider client={client}>{children}</ApolloProvider>;
  };
}

// ============================================================================
// Tests
// ============================================================================

describe("useRefetchOnAuthChange", () => {
  let client: ApolloClient<any>;

  beforeEach(() => {
    vi.clearAllMocks();
    client = createMockApolloClient();
    // Default to authenticated state
    authToken("test-token");
  });

  afterEach(() => {
    vi.restoreAllMocks();
    // Reset to default
    authToken("");
  });

  it("should refetch active queries after clearStore when authenticated", async () => {
    renderHook(() => useRefetchOnAuthChange(), {
      wrapper: createWrapper(client),
    });

    // Trigger a cache clear (simulates login)
    await client.clearStore();

    expect(client.refetchQueries).toHaveBeenCalledWith({
      include: "active",
    });
  });

  it("should not refetch before clearStore is called", () => {
    renderHook(() => useRefetchOnAuthChange(), {
      wrapper: createWrapper(client),
    });

    expect(client.refetchQueries).not.toHaveBeenCalled();
  });

  it("should unsubscribe on unmount", async () => {
    const { unmount } = renderHook(() => useRefetchOnAuthChange(), {
      wrapper: createWrapper(client),
    });

    unmount();

    // Clear store after unmount — callback should not fire
    await client.clearStore();

    expect(client.refetchQueries).not.toHaveBeenCalled();
  });

  it("should skip refetch when auth token is empty (logout)", async () => {
    renderHook(() => useRefetchOnAuthChange(), {
      wrapper: createWrapper(client),
    });

    // Simulate logout: clear auth state before cache clear
    authToken("");

    await client.clearStore();

    expect(client.refetchQueries).not.toHaveBeenCalled();
  });

  it("should refetch for each clearStore call when called in quick succession", async () => {
    renderHook(() => useRefetchOnAuthChange(), {
      wrapper: createWrapper(client),
    });

    // Fire two clearStore calls back-to-back — the hook has no internal
    // debounce so both should trigger refetchQueries.
    await client.clearStore();
    await client.clearStore();

    expect(client.refetchQueries).toHaveBeenCalledTimes(2);
  });

  it("should not propagate refetchQueries errors", async () => {
    vi.spyOn(client, "refetchQueries").mockRejectedValue(
      new Error("Network error")
    );
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

    renderHook(() => useRefetchOnAuthChange(), {
      wrapper: createWrapper(client),
    });

    // Should not throw despite refetchQueries rejecting
    await client.clearStore();

    expect(warnSpy).toHaveBeenCalledWith(
      "[useRefetchOnAuthChange] refetchQueries failed:",
      expect.any(Error)
    );
  });
});
