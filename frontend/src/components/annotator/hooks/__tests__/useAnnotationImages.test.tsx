/**
 * Regression net for `useAnnotationImages` — covers the empty-vs-error
 * distinction added for issue #1560 so a successful response with no
 * thumbnails (or an unauthorized 401/404/429 from the IDOR-safe REST view)
 * surfaces as "no thumbnail available" rather than the alarming "Failed"
 * card the original hook produced.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "../../../../test-utils/renderHook";

import { useAnnotationImages } from "../useAnnotationImages";

// Make sure the in-memory imageCache is fresh between tests; the hook keys
// it by numeric annotation id so we use distinct ids per test.
let nextNumericId = 1000;
function nextRelayId(): { relay: string; numeric: number } {
  const numeric = nextNumericId++;
  // base64("AnnotationType:<id>") matches the production global-id format.
  const relay = btoa(`AnnotationType:${numeric}`);
  return { relay, numeric };
}

vi.mock("@apollo/client", async () => {
  const actual = await vi.importActual<typeof import("@apollo/client")>(
    "@apollo/client"
  );
  return {
    ...actual,
    // Sidestep the reactive-var subscription — the hook only reads it.
    useReactiveVar: () => "",
  };
});

const flush = async () => {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
};

describe("useAnnotationImages", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    // jsdom has no fetch by default; install a per-test mock.
    (globalThis as unknown as { fetch: typeof fetch }).fetch =
      fetchMock as unknown as typeof fetch;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("does not fetch when the annotation has no IMAGE modality", async () => {
    const { relay } = nextRelayId();
    const { result } = renderHook(() => useAnnotationImages(relay, ["TEXT"]));

    expect(fetchMock).not.toHaveBeenCalled();
    expect(result.current).toEqual({
      images: null,
      loading: false,
      error: false,
      hasFetchedEmpty: false,
    });
  });

  it("treats a successful empty response as hasFetchedEmpty (not an error)", async () => {
    const { relay, numeric } = nextRelayId();
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        annotation_id: String(numeric),
        images: [],
        count: 0,
      }),
    });

    const { result } = renderHook(() => useAnnotationImages(relay, ["IMAGE"]));
    await flush();

    expect(result.current.error).toBe(false);
    expect(result.current.hasFetchedEmpty).toBe(true);
    expect(result.current.images).toEqual([]);
  });

  it("treats 401 as no-thumbnail (anonymous browse) rather than error", async () => {
    // Browse Annotations may run before the JWT is in the reactive var; the
    // REST endpoint then returns 401. The old hook flagged this as `error`
    // and rendered "Failed" on every image card (issue #1560).
    const { relay } = nextRelayId();
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 401,
      json: async () => ({}),
    });

    const { result } = renderHook(() => useAnnotationImages(relay, ["IMAGE"]));
    await flush();

    expect(result.current.error).toBe(false);
    expect(result.current.hasFetchedEmpty).toBe(true);
    expect(result.current.images).toEqual([]);
  });

  it("does not cache a 401 response so a later fetch can succeed", async () => {
    // Cache-poisoning regression guard: a 401 (no JWT yet) followed by a
    // 200 (token resolved) must hit the network twice for the same id.
    const { relay, numeric } = nextRelayId();

    fetchMock
      .mockResolvedValueOnce({ ok: false, status: 401, json: async () => ({}) })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          annotation_id: String(numeric),
          images: [
            {
              base64_data: "AAA",
              format: "jpeg",
              data_url: "data:image/jpeg;base64,AAA",
              page_index: 0,
              token_index: 1,
            },
          ],
          count: 1,
        }),
      });

    const first = renderHook(() => useAnnotationImages(relay, ["IMAGE"]));
    await flush();
    expect(first.result.current.hasFetchedEmpty).toBe(true);

    // Mounting a fresh hook instance with the same id must re-fetch (the
    // 401 response was *not* memoized as "permanently empty").
    const second = renderHook(() => useAnnotationImages(relay, ["IMAGE"]));
    await flush();

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(second.result.current.images).toHaveLength(1);
    expect(second.result.current.hasFetchedEmpty).toBe(false);
  });

  it("caches a 404 response so subsequent renders skip the network", async () => {
    // The mirror of the 401 test: 404 means "no thumbnail row exists" and
    // is permanent, so the second mount must NOT re-fetch.
    const { relay } = nextRelayId();
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 404,
      json: async () => ({}),
    });

    renderHook(() => useAnnotationImages(relay, ["IMAGE"]));
    await flush();

    renderHook(() => useAnnotationImages(relay, ["IMAGE"]));
    await flush();

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("treats 404 the same as an empty response", async () => {
    const { relay } = nextRelayId();
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 404,
      json: async () => ({}),
    });

    const { result } = renderHook(() => useAnnotationImages(relay, ["IMAGE"]));
    await flush();

    expect(result.current.error).toBe(false);
    expect(result.current.hasFetchedEmpty).toBe(true);
  });

  it("flags genuine 5xx failures as error", async () => {
    const { relay } = nextRelayId();
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => ({}),
    });

    const { result } = renderHook(() => useAnnotationImages(relay, ["IMAGE"]));
    await flush();

    expect(result.current.error).toBe(true);
    expect(result.current.hasFetchedEmpty).toBe(false);
    expect(result.current.images).toBeNull();
  });

  it("returns the images and clears hasFetchedEmpty on a populated response", async () => {
    const { relay, numeric } = nextRelayId();
    const image = {
      base64_data: "AAA",
      format: "jpeg",
      data_url: "data:image/jpeg;base64,AAA",
      page_index: 0,
      token_index: 1,
    };
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        annotation_id: String(numeric),
        images: [image],
        count: 1,
      }),
    });

    const { result } = renderHook(() => useAnnotationImages(relay, ["IMAGE"]));
    await flush();

    expect(result.current.error).toBe(false);
    expect(result.current.hasFetchedEmpty).toBe(false);
    expect(result.current.images).toEqual([image]);
  });
});
