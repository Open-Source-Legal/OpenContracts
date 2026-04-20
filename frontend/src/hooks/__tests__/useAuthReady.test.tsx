import { describe, it, expect, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react-hooks";
import { useAuthReady } from "../useAuthReady";
import { authStatusVar } from "../../graphql/cache";

describe("useAuthReady", () => {
  afterEach(() => {
    authStatusVar("LOADING");
  });

  it("returns false while auth status is LOADING", () => {
    authStatusVar("LOADING");
    const { result } = renderHook(() => useAuthReady());
    expect(result.current).toBe(false);
  });

  it("returns true once status is AUTHENTICATED", () => {
    authStatusVar("LOADING");
    const { result } = renderHook(() => useAuthReady());

    act(() => {
      authStatusVar("AUTHENTICATED");
    });

    expect(result.current).toBe(true);
  });

  it("returns true once status is ANONYMOUS", () => {
    authStatusVar("LOADING");
    const { result } = renderHook(() => useAuthReady());

    act(() => {
      authStatusVar("ANONYMOUS");
    });

    expect(result.current).toBe(true);
  });
});
