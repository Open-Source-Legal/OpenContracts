import { describe, it, expect, vi, beforeEach } from "vitest";
import { updateCacheForJobNotification } from "../jobNotificationCacheUpdates";
import { toGlobalId } from "../idValidation";
import type { ApolloCache } from "@apollo/client";

function createMockCache() {
  const modifyCalls: Array<{ id: string; fields: Record<string, unknown> }> =
    [];

  const identify = vi.fn(
    (obj: { __typename: string; id: string }) => `${obj.__typename}:${obj.id}`
  );
  const modify = vi.fn((args: any) => {
    modifyCalls.push({ id: args.id, fields: args.fields });
    return true;
  });

  return {
    cache: { identify, modify } as unknown as ApolloCache<unknown>,
    identify,
    modify,
    modifyCalls,
  };
}

describe("updateCacheForJobNotification", () => {
  let harness: ReturnType<typeof createMockCache>;

  beforeEach(() => {
    harness = createMockCache();
  });

  it("handles DOCUMENT_PROCESSED and flips backendLock to false", () => {
    const handled = updateCacheForJobNotification(
      harness.cache,
      "DOCUMENT_PROCESSED" as any,
      { document_id: 42 }
    );
    expect(handled).toBe(true);
    expect(harness.identify).toHaveBeenCalledWith({
      __typename: "DocumentType",
      id: toGlobalId("DocumentType", 42),
    });
    expect(harness.modifyCalls[0].fields.backendLock).toBeTypeOf("function");
    expect((harness.modifyCalls[0].fields.backendLock as () => unknown)()).toBe(
      false
    );
  });

  it("handles EXTRACT_COMPLETE and sets a finished timestamp", () => {
    const handled = updateCacheForJobNotification(
      harness.cache,
      "EXTRACT_COMPLETE" as any,
      { extract_id: 7 }
    );
    expect(handled).toBe(true);
    const finished = harness.modifyCalls[0].fields.finished as () => string;
    expect(typeof finished()).toBe("string");
    expect(Number.isNaN(Date.parse(finished()))).toBe(false);
  });

  it("handles ANALYSIS_COMPLETE setting status and analysisCompleted", () => {
    const handled = updateCacheForJobNotification(
      harness.cache,
      "ANALYSIS_COMPLETE" as any,
      { analysis_id: 9 }
    );
    expect(handled).toBe(true);
    const fields = harness.modifyCalls[0].fields as Record<
      string,
      () => unknown
    >;
    expect(fields.status()).toBe("COMPLETED");
    expect(typeof fields.analysisCompleted()).toBe("string");
  });

  it("handles ANALYSIS_FAILED setting status=FAILED", () => {
    updateCacheForJobNotification(harness.cache, "ANALYSIS_FAILED" as any, {
      analysis_id: 1,
    });
    const fields = harness.modifyCalls[0].fields as Record<
      string,
      () => unknown
    >;
    expect(fields.status()).toBe("FAILED");
  });

  it("handles EXPORT_COMPLETE clearing backendLock and setting finished", () => {
    updateCacheForJobNotification(harness.cache, "EXPORT_COMPLETE" as any, {
      export_id: 3,
    });
    const fields = harness.modifyCalls[0].fields as Record<
      string,
      () => unknown
    >;
    expect(fields.backendLock()).toBe(false);
    expect(typeof fields.finished()).toBe("string");
  });

  it("returns false when the id is missing", () => {
    expect(
      updateCacheForJobNotification(
        harness.cache,
        "EXTRACT_COMPLETE" as any,
        {}
      )
    ).toBe(false);
    expect(harness.modify).not.toHaveBeenCalled();
  });

  it("returns false for unknown notification types", () => {
    expect(
      updateCacheForJobNotification(harness.cache, "UNKNOWN_TYPE" as any, {
        document_id: 1,
      })
    ).toBe(false);
  });

  it("skips modify when cache cannot identify the object", () => {
    const identify = vi.fn(() => undefined);
    const modify = vi.fn();
    const cache = { identify, modify } as unknown as ApolloCache<unknown>;

    const handled = updateCacheForJobNotification(
      cache,
      "DOCUMENT_PROCESSED" as any,
      { document_id: 100 }
    );
    // The function still returns true because the id was provided, but
    // modify must not have been invoked.
    expect(handled).toBe(true);
    expect(modify).not.toHaveBeenCalled();
  });
});
