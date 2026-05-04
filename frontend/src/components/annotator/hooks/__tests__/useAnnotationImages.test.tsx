/**
 * useAnnotationImages auth-header tests.
 *
 * The hook fetches annotation image bytes from a REST endpoint and was
 * recently switched from the legacy `JWT <token>` Authorization scheme
 * to the canonical `Bearer <token>` scheme used everywhere else in the
 * stack. These tests pin that contract by inspecting the exact headers
 * passed to `fetch` and by exercising the `no-token` and `non-IMAGE
 * modality` branches so the hook stays well-covered.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook } from "@testing-library/react-hooks";

import { useAnnotationImages } from "../useAnnotationImages";
import { authToken } from "../../../../graphql/cache";
import { toGlobalId } from "../../../../utils/idValidation";

// Build a unique global id per test run so each call bypasses the
// module-level image cache without us having to reach into it.
let nextNumericId = 1000;
const freshAnnotationId = (): { numericId: number; globalId: string } => {
  const numericId = nextNumericId++;
  return {
    numericId,
    globalId: toGlobalId("AnnotationType", numericId),
  };
};

const flushMicrotasks = () => new Promise((r) => setTimeout(r, 0));

describe("useAnnotationImages", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    (global as unknown as { fetch: typeof fetchMock }).fetch = fetchMock;
    authToken("");
  });

  afterEach(() => {
    vi.restoreAllMocks();
    authToken("");
  });

  it("sends Bearer Authorization header when an auth token is set", async () => {
    const { numericId, globalId } = freshAnnotationId();
    const responsePayload = {
      annotation_id: globalId,
      images: [
        {
          base64_data: "AAAA",
          format: "png",
          data_url: "data:image/png;base64,AAAA",
          page_index: 0,
          token_index: 0,
        },
      ],
      count: 1,
    };
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => responsePayload,
    });

    authToken("test-jwt-123");

    const { result, waitFor } = renderHook(() =>
      useAnnotationImages(globalId, ["IMAGE"])
    );

    await waitFor(() => result.current.images !== null);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [calledUrl, calledOpts] = fetchMock.mock.calls[0];
    expect(calledUrl).toBe(`/api/annotations/${numericId}/images/`);
    expect(calledOpts.headers).toMatchObject({
      "Content-Type": "application/json",
      Authorization: "Bearer test-jwt-123",
    });
    expect(result.current.error).toBe(false);
    expect(result.current.loading).toBe(false);
    expect(result.current.images).toHaveLength(1);
  });

  it("omits Authorization header when no auth token is set", async () => {
    const { globalId } = freshAnnotationId();
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ annotation_id: globalId, images: [], count: 0 }),
    });

    authToken("");

    const { result, waitFor } = renderHook(() =>
      useAnnotationImages(globalId, ["IMAGE"])
    );

    await waitFor(() => result.current.images !== null);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, calledOpts] = fetchMock.mock.calls[0];
    expect(calledOpts.headers).not.toHaveProperty("Authorization");
  });

  it("does not call fetch when annotation has no IMAGE modality", async () => {
    const { globalId } = freshAnnotationId();
    authToken("ignored-token");

    const { result } = renderHook(() =>
      useAnnotationImages(globalId, ["TEXT"])
    );

    await flushMicrotasks();

    expect(fetchMock).not.toHaveBeenCalled();
    expect(result.current.images).toBeNull();
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBe(false);
  });

  it("flags error state when the fetch response is not ok", async () => {
    const { globalId } = freshAnnotationId();
    fetchMock.mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({}),
    });

    // Silence expected console.error from the hook's catch branch.
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    authToken("token-x");

    const { result, waitFor } = renderHook(() =>
      useAnnotationImages(globalId, ["IMAGE"])
    );

    await waitFor(() => result.current.error === true);

    expect(result.current.images).toBeNull();
    expect(result.current.loading).toBe(false);
    errSpy.mockRestore();
  });
});
