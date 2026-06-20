/**
 * Unit tests for useEnrichmentJobs' WebSocket → refetch wiring.
 *
 * Addresses review item T-1 (PR 2008): no test exercised the
 * ANALYSIS_COMPLETE → refetch() path. useQuery and useNotificationWebSocket
 * are mocked so we can capture the notification callback the hook registers and
 * drive it directly — asserting that:
 *   - an analysis notification whose corpus_id matches triggers a refetch,
 *   - an analysis notification with NO corpus_id refetches as a safe fallback,
 *   - an analysis notification for a DIFFERENT corpus is ignored,
 *   - a non-analysis notification type is ignored,
 *   - an undecodable corpus id leaves corpusPk null (the decode catch branch).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

// Capture the onNotificationCreated callback the hook registers.
let capturedCallback: ((n: unknown) => void) | undefined;
vi.mock("../../../../hooks/useNotificationWebSocket", () => ({
  useNotificationWebSocket: (opts: {
    onNotificationCreated?: (n: unknown) => void;
  }) => {
    capturedCallback = opts.onNotificationCreated;
    return {};
  },
}));

// Stub useQuery so the hook gets a controllable refetch spy (no real network).
const refetchMock = vi.fn();
vi.mock("@apollo/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@apollo/client")>();
  return {
    ...actual,
    useQuery: () => ({
      data: { analyses: { edges: [] } },
      loading: false,
      error: undefined,
      refetch: refetchMock,
    }),
  };
});

import { renderHook } from "../../../../test-utils/renderHook";
import { useEnrichmentJobs } from "../useEnrichmentJobs";

// "Q29ycHVzVHlwZTo0Mg==" decodes to "CorpusType:42" → numeric pk 42.
const CORPUS_GID = "Q29ycHVzVHlwZTo0Mg==";

function emit(notification: unknown) {
  if (!capturedCallback) throw new Error("callback was never registered");
  capturedCallback(notification);
}

describe("useEnrichmentJobs notification handling", () => {
  beforeEach(() => {
    refetchMock.mockClear();
    capturedCallback = undefined;
  });

  it("refetches on an ANALYSIS_COMPLETE for this corpus", () => {
    const { unmount } = renderHook(() => useEnrichmentJobs(CORPUS_GID));
    emit({ notificationType: "ANALYSIS_COMPLETE", data: { corpus_id: 42 } });
    expect(refetchMock).toHaveBeenCalledTimes(1);
    unmount();
  });

  it("refetches as a fallback when the notification carries no corpus_id", () => {
    const { unmount } = renderHook(() => useEnrichmentJobs(CORPUS_GID));
    emit({ notificationType: "ANALYSIS_RUNNING", data: {} });
    expect(refetchMock).toHaveBeenCalledTimes(1);
    unmount();
  });

  it("ignores an analysis notification for a different corpus", () => {
    const { unmount } = renderHook(() => useEnrichmentJobs(CORPUS_GID));
    emit({ notificationType: "ANALYSIS_FAILED", data: { corpus_id: 99 } });
    expect(refetchMock).not.toHaveBeenCalled();
    unmount();
  });

  it("ignores notification types outside the analysis set", () => {
    const { unmount } = renderHook(() => useEnrichmentJobs(CORPUS_GID));
    emit({ notificationType: "DOCUMENT_PROCESSED", data: { corpus_id: 42 } });
    expect(refetchMock).not.toHaveBeenCalled();
    unmount();
  });

  it("treats an undecodable corpus id as no corpus (decode catch)", () => {
    // A non-base64 id makes getNumericIdFromGlobalId throw → corpusPk null, so
    // an analysis notification for a real corpus does NOT match and is skipped.
    const { unmount } = renderHook(() => useEnrichmentJobs("@@not-a-gid@@"));
    emit({ notificationType: "ANALYSIS_COMPLETE", data: { corpus_id: 42 } });
    expect(refetchMock).not.toHaveBeenCalled();
    unmount();
  });
});
