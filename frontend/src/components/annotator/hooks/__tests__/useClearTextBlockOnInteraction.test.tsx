import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook } from "@testing-library/react-hooks";
import { MemoryRouter } from "react-router-dom";
import * as React from "react";
import type { ReactNode } from "react";

// Mock the cache module to avoid pulling in Apollo's full dependency tree
const mockHighlightedTextBlock = vi.fn();
vi.mock("../../../../graphql/cache", () => ({
  highlightedTextBlock: (...args: unknown[]) =>
    mockHighlightedTextBlock(...args),
}));

// Mock the navigation utility
const mockUpdateTextBlockParam = vi.fn();
vi.mock("../../../../utils/navigationUtils", () => ({
  updateTextBlockParam: (...args: unknown[]) =>
    mockUpdateTextBlockParam(...args),
}));

// Import AFTER mocks are set up
import { useClearTextBlockOnInteraction } from "../useClearTextBlockOnInteraction";

function wrapper({ children }: { children: ReactNode }) {
  return (
    <MemoryRouter initialEntries={["/?tb=s100-200"]}>{children}</MemoryRouter>
  );
}

describe("useClearTextBlockOnInteraction", () => {
  beforeEach(() => {
    mockUpdateTextBlockParam.mockClear();
    mockHighlightedTextBlock.mockReset();
  });

  it("should clear text block when annotations are selected and highlight is active", () => {
    mockHighlightedTextBlock.mockReturnValue("s100-200");

    renderHook(() => useClearTextBlockOnInteraction(["annotation-1"], null), {
      wrapper,
    });

    expect(mockUpdateTextBlockParam).toHaveBeenCalledWith(
      expect.objectContaining({ search: expect.any(String) }),
      expect.any(Function),
      null
    );
  });

  it("should clear text block when a chat message is selected and highlight is active", () => {
    mockHighlightedTextBlock.mockReturnValue("p0:45-65");

    renderHook(() => useClearTextBlockOnInteraction([], "msg-123"), {
      wrapper,
    });

    expect(mockUpdateTextBlockParam).toHaveBeenCalledWith(
      expect.objectContaining({ search: expect.any(String) }),
      expect.any(Function),
      null
    );
  });

  it("should not clear when highlightedTextBlock is falsy", () => {
    mockHighlightedTextBlock.mockReturnValue(null);

    renderHook(() => useClearTextBlockOnInteraction(["annotation-1"], null), {
      wrapper,
    });

    expect(mockUpdateTextBlockParam).not.toHaveBeenCalled();
  });

  it("should not clear when both selections are empty", () => {
    mockHighlightedTextBlock.mockReturnValue("s100-200");

    renderHook(() => useClearTextBlockOnInteraction([], null), {
      wrapper,
    });

    expect(mockUpdateTextBlockParam).not.toHaveBeenCalled();
  });
});
