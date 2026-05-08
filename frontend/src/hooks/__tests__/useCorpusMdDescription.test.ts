/**
 * Tests for useCorpusMdDescription hook.
 *
 * Covers: no-URL case, successful fetch, failed fetch, cleanup on unmount,
 * and module-level request deduplication cache.
 */

import { renderHook, act } from "../../test-utils/renderHook";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  useCorpusMdDescription,
  _inflightRequests,
} from "../useCorpusMdDescription";

/** Flush microtask queue so cached / rejected promises settle. */
const flushPromises = () => act(() => new Promise((r) => setTimeout(r, 0)));

function mockFetch(impl: (...args: unknown[]) => unknown) {
  const fn = vi.fn(impl);
  globalThis.fetch = fn as unknown as typeof fetch;
  return fn;
}

describe("useCorpusMdDescription", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.clearAllMocks();
    _inflightRequests.clear();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("returns null when URL is null", () => {
    const { result } = renderHook(() => useCorpusMdDescription(null));
    expect(result.current).toBeNull();
  });

  it("returns null when URL is undefined", () => {
    const { result } = renderHook(() => useCorpusMdDescription(undefined));
    expect(result.current).toBeNull();
  });

  it("fetches and returns markdown content on success", async () => {
    const md = "# Hello\nSome **bold** text";
    const fn = mockFetch(() =>
      Promise.resolve(new Response(md, { status: 200, statusText: "OK" }))
    );

    const { result, waitForNextUpdate } = renderHook(() =>
      useCorpusMdDescription("https://example.com/desc.md")
    );

    expect(result.current).toBeNull();
    await waitForNextUpdate();
    expect(result.current).toBe(md);
    expect(fn).toHaveBeenCalledWith("https://example.com/desc.md");
  });

  it("returns null on fetch error", async () => {
    mockFetch(() => Promise.reject(new Error("Network error")));
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    const { result } = renderHook(() =>
      useCorpusMdDescription("https://example.com/fail.md")
    );

    // Error path sets content to null (same as initial) — no re-render,
    // so we flush microtasks and verify the result stays null.
    await flushPromises();
    expect(result.current).toBeNull();
    expect(consoleSpy).toHaveBeenCalled();
    consoleSpy.mockRestore();
  });

  it("returns null on HTTP error response", async () => {
    mockFetch(() =>
      Promise.resolve(
        new Response("", { status: 404, statusText: "Not Found" })
      )
    );
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    const { result } = renderHook(() =>
      useCorpusMdDescription("https://example.com/missing.md")
    );

    await flushPromises();
    expect(result.current).toBeNull();
    consoleSpy.mockRestore();
  });

  it("does not update state after unmount", async () => {
    let resolvePromise: (value: Response) => void;
    mockFetch(
      () =>
        new Promise<Response>((resolve) => {
          resolvePromise = resolve;
        })
    );

    const { result, unmount } = renderHook(() =>
      useCorpusMdDescription("https://example.com/slow.md")
    );

    unmount();

    // Resolve after unmount — should not throw or update
    await act(async () => {
      resolvePromise!(
        new Response("late content", { status: 200, statusText: "OK" })
      );
    });

    expect(result.current).toBeNull();
  });

  it("deduplicates concurrent fetches to the same URL", async () => {
    const md = "# Shared";
    const fn = mockFetch(() =>
      Promise.resolve(new Response(md, { status: 200, statusText: "OK" }))
    );

    const url = "https://example.com/shared.md";
    const { result: r1 } = renderHook(() => useCorpusMdDescription(url));
    const { result: r2 } = renderHook(() => useCorpusMdDescription(url));

    await flushPromises();

    expect(r1.current).toBe(md);
    expect(r2.current).toBe(md);
    // fetch should have been called only once for the same URL
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it("resets content when URL changes to null", async () => {
    const md = "# Content";
    mockFetch(() =>
      Promise.resolve(new Response(md, { status: 200, statusText: "OK" }))
    );

    const { result, waitForNextUpdate, rerender } = renderHook(
      ({ url }: { url: string | null }) => useCorpusMdDescription(url),
      { initialProps: { url: "https://example.com/desc.md" as string | null } }
    );

    await waitForNextUpdate();
    expect(result.current).toBe(md);

    rerender({ url: null });
    expect(result.current).toBeNull();
  });
});
