import { describe, it, expect } from "vitest";
import { renderHook } from "../../test-utils/renderHook";
import { useFeatureAvailability } from "../useFeatureAvailability";

describe("useFeatureAvailability", () => {
  it("reports features that require a corpus as unavailable without one", () => {
    const { result } = renderHook(() => useFeatureAvailability());
    expect(result.current.hasCorpus).toBe(false);
    expect(result.current.isFeatureAvailable("CHAT")).toBe(false);
    expect(result.current.isFeatureAvailable("ANNOTATIONS")).toBe(false);
  });

  it("treats corpus-free features as available without a corpus", () => {
    const { result } = renderHook(() => useFeatureAvailability());
    expect(result.current.isFeatureAvailable("NOTES")).toBe(true);
    expect(result.current.isFeatureAvailable("SEARCH")).toBe(true);
  });

  it("marks corpus-gated features available when corpus is present", () => {
    const { result } = renderHook(() => useFeatureAvailability("corpus-1"));
    expect(result.current.hasCorpus).toBe(true);
    expect(result.current.isFeatureAvailable("CHAT")).toBe(true);
    expect(result.current.isFeatureAvailable("ANNOTATIONS")).toBe(true);
  });

  it("getFeatureStatus returns message when feature is unavailable", () => {
    const { result } = renderHook(() => useFeatureAvailability());
    const status = result.current.getFeatureStatus("CHAT");
    expect(status.available).toBe(false);
    expect(status.message).toBe("Add to corpus to enable AI chat");
  });

  it("getFeatureStatus omits message when feature is available", () => {
    const { result } = renderHook(() => useFeatureAvailability("c1"));
    const status = result.current.getFeatureStatus("CHAT");
    expect(status.available).toBe(true);
    expect(status.message).toBeUndefined();
  });

  it("memoizes the returned object when corpusId is stable", () => {
    const { result, rerender } = renderHook(
      ({ cid }) => useFeatureAvailability(cid),
      { initialProps: { cid: "c1" } }
    );
    const first = result.current;
    rerender({ cid: "c1" });
    expect(result.current).toBe(first);
  });

  it("returns a new object when corpusId changes", () => {
    const { result, rerender } = renderHook(
      ({ cid }) => useFeatureAvailability(cid),
      { initialProps: { cid: "c1" as string | undefined } }
    );
    const first = result.current;
    rerender({ cid: "c2" });
    expect(result.current).not.toBe(first);
    expect(result.current.hasCorpus).toBe(true);

    rerender({ cid: undefined });
    expect(result.current.hasCorpus).toBe(false);
  });
});
