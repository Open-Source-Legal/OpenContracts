import { renderHook } from "../../../../../test-utils/renderHook";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

import { useDocumentMarkdown } from "../useDocumentMarkdown";

const flushAsync = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

describe("useDocumentMarkdown", () => {
  beforeEach(() => {
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns null content while no md file is provided", () => {
    const { result } = renderHook(() => useDocumentMarkdown(undefined));
    expect(result.current.markdownContent).toBeNull();
    expect(result.current.markdownError).toBe(false);
  });

  it("loads and exposes the markdown body from a successful fetch", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("# heading\n\nbody", {
        status: 200,
        headers: { "content-type": "text/markdown" },
      })
    );

    const { result, waitFor } = renderHook(() =>
      useDocumentMarkdown("https://example.test/summary.md")
    );

    await waitFor(() => result.current.markdownContent !== null);

    expect(fetchSpy).toHaveBeenCalledWith("https://example.test/summary.md");
    expect(result.current.markdownContent).toBe("# heading\n\nbody");
    expect(result.current.markdownError).toBe(false);
  });

  it("flips markdownError when the response is not ok", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("not found", { status: 404 })
    );

    const { result, waitFor } = renderHook(() =>
      useDocumentMarkdown("https://example.test/missing.md")
    );

    await waitFor(() => result.current.markdownError === true);

    expect(result.current.markdownContent).toBeNull();
    expect(result.current.markdownError).toBe(true);
  });

  it("flips markdownError when the fetch promise rejects", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("offline"));

    const { result, waitFor } = renderHook(() =>
      useDocumentMarkdown("https://example.test/network-fail.md")
    );

    await waitFor(() => result.current.markdownError === true);

    expect(result.current.markdownContent).toBeNull();
    expect(result.current.markdownError).toBe(true);
  });

  it("clears the content when the file URL is removed", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("hello", { status: 200 })
    );

    const { result, rerender, waitFor } = renderHook(
      ({ url }) => useDocumentMarkdown(url),
      { initialProps: { url: "https://example.test/a.md" as string | null } }
    );

    await waitFor(() => result.current.markdownContent === "hello");

    rerender({ url: null });
    expect(result.current.markdownContent).toBeNull();
  });

  it("ignores a stale fetch resolution after the URL changed mid-flight", async () => {
    let resolveFirst!: (response: Response) => void;
    const firstResponse = new Promise<Response>((resolve) => {
      resolveFirst = resolve;
    });

    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockImplementationOnce(() => firstResponse)
      .mockResolvedValueOnce(new Response("second", { status: 200 }));

    const { result, rerender, waitFor } = renderHook(
      ({ url }: { url: string }) => useDocumentMarkdown(url),
      { initialProps: { url: "https://example.test/first.md" } }
    );

    rerender({ url: "https://example.test/second.md" });

    // Resolve the *first* fetch after the URL has already been rotated.
    resolveFirst(new Response("first-stale", { status: 200 }));
    await flushAsync();

    await waitFor(() => result.current.markdownContent === "second");

    expect(result.current.markdownContent).toBe("second");
    expect(fetchSpy).toHaveBeenCalledTimes(2);
  });
});
