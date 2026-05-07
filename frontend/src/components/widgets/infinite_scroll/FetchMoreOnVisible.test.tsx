import React from "react";
import { render, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FetchMoreOnVisible } from "./FetchMoreOnVisible";

type MockUseInViewState = {
  inView: boolean;
  vertical: "up" | "down" | undefined;
  entry: object | undefined;
};

let mockUseInViewState: MockUseInViewState = {
  inView: false,
  vertical: undefined,
  entry: undefined,
};

vi.mock("react-cool-inview", () => ({
  useInView: () => ({
    observe: vi.fn(),
    inView: mockUseInViewState.inView,
    scrollDirection: { vertical: mockUseInViewState.vertical },
    entry: mockUseInViewState.entry,
  }),
}));

const setMockState = (state: Partial<MockUseInViewState>) => {
  mockUseInViewState = { ...mockUseInViewState, ...state };
};

describe("FetchMoreOnVisible", () => {
  afterEach(() => {
    cleanup();
    setMockState({ inView: false, vertical: undefined, entry: undefined });
  });

  it("does not call any fetcher when not inView", () => {
    setMockState({ inView: false });
    const fetchNextPage = vi.fn();
    const fetchPreviousPage = vi.fn();

    render(
      <FetchMoreOnVisible
        fetchNextPage={fetchNextPage}
        fetchPreviousPage={fetchPreviousPage}
      />
    );

    expect(fetchNextPage).not.toHaveBeenCalled();
    expect(fetchPreviousPage).not.toHaveBeenCalled();
  });

  it("calls fetchNextPage when scrolling 'up' and in view", () => {
    setMockState({
      inView: true,
      vertical: "up",
      entry: { isIntersecting: true },
    });
    const fetchNextPage = vi.fn();
    const fetchPreviousPage = vi.fn();

    render(
      <FetchMoreOnVisible
        fetchNextPage={fetchNextPage}
        fetchPreviousPage={fetchPreviousPage}
      />
    );

    expect(fetchNextPage).toHaveBeenCalledTimes(1);
    expect(fetchPreviousPage).not.toHaveBeenCalled();
  });

  it("calls fetchPreviousPage when scrolling 'down' and in view", () => {
    setMockState({
      inView: true,
      vertical: "down",
      entry: { isIntersecting: true },
    });
    const fetchNextPage = vi.fn();
    const fetchPreviousPage = vi.fn();

    render(
      <FetchMoreOnVisible
        fetchNextPage={fetchNextPage}
        fetchPreviousPage={fetchPreviousPage}
      />
    );

    expect(fetchPreviousPage).toHaveBeenCalledTimes(1);
    expect(fetchNextPage).not.toHaveBeenCalled();
  });

  it("does not call fetchNextPage on 'up' if it is undefined", () => {
    setMockState({
      inView: true,
      vertical: "up",
      entry: { isIntersecting: true },
    });
    const fetchPreviousPage = vi.fn();

    render(<FetchMoreOnVisible fetchPreviousPage={fetchPreviousPage} />);

    expect(fetchPreviousPage).not.toHaveBeenCalled();
  });

  it("does not call fetchPreviousPage on 'down' if it is undefined", () => {
    setMockState({
      inView: true,
      vertical: "down",
      entry: { isIntersecting: true },
    });
    const fetchNextPage = vi.fn();

    render(<FetchMoreOnVisible fetchNextPage={fetchNextPage} />);

    expect(fetchNextPage).not.toHaveBeenCalled();
  });

  it("calls fetchNextPage with fetchWithoutMotion when no scroll direction", () => {
    setMockState({
      inView: true,
      vertical: undefined,
      entry: { isIntersecting: true },
    });
    const fetchNextPage = vi.fn();
    const fetchPreviousPage = vi.fn();

    render(
      <FetchMoreOnVisible
        fetchNextPage={fetchNextPage}
        fetchPreviousPage={fetchPreviousPage}
        fetchWithoutMotion
      />
    );

    expect(fetchNextPage).toHaveBeenCalledTimes(1);
    expect(fetchPreviousPage).not.toHaveBeenCalled();
  });

  it("falls back to fetchPreviousPage with fetchWithoutMotion when fetchNextPage missing", () => {
    setMockState({
      inView: true,
      vertical: undefined,
      entry: { isIntersecting: true },
    });
    const fetchPreviousPage = vi.fn();

    render(
      <FetchMoreOnVisible
        fetchPreviousPage={fetchPreviousPage}
        fetchWithoutMotion
      />
    );

    expect(fetchPreviousPage).toHaveBeenCalledTimes(1);
  });

  it("does nothing without fetchWithoutMotion when no scroll direction", () => {
    setMockState({
      inView: true,
      vertical: undefined,
      entry: { isIntersecting: true },
    });
    const fetchNextPage = vi.fn();
    const fetchPreviousPage = vi.fn();

    render(
      <FetchMoreOnVisible
        fetchNextPage={fetchNextPage}
        fetchPreviousPage={fetchPreviousPage}
      />
    );

    expect(fetchNextPage).not.toHaveBeenCalled();
    expect(fetchPreviousPage).not.toHaveBeenCalled();
  });

  it("uses the latest fetchNextPage callback even after re-render (no stale closure)", () => {
    setMockState({ inView: false });
    const initialFetch = vi.fn();
    const updatedFetch = vi.fn();

    const { rerender } = render(
      <FetchMoreOnVisible fetchNextPage={initialFetch} />
    );

    rerender(<FetchMoreOnVisible fetchNextPage={updatedFetch} />);

    setMockState({
      inView: true,
      vertical: "up",
      entry: { isIntersecting: true },
    });
    rerender(<FetchMoreOnVisible fetchNextPage={updatedFetch} />);

    expect(initialFetch).not.toHaveBeenCalled();
    expect(updatedFetch).toHaveBeenCalledTimes(1);
  });

  it("renders the sentinel div with the FetchMoreOnVisible class", () => {
    const { container } = render(<FetchMoreOnVisible />);
    const sentinel = container.querySelector(".FetchMoreOnVisible");
    expect(sentinel).not.toBeNull();
    expect((sentinel as HTMLDivElement).style.height).toBe("1px");
  });

  it("merges custom style with the default height", () => {
    const { container } = render(
      <FetchMoreOnVisible style={{ background: "red", height: "2px" }} />
    );
    const sentinel = container.querySelector(
      ".FetchMoreOnVisible"
    ) as HTMLDivElement;
    expect(sentinel.style.background).toBe("red");
    expect(sentinel.style.height).toBe("2px");
  });
});
