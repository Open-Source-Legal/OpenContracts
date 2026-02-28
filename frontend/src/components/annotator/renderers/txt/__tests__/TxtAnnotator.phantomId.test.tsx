/**
 * Tests for TxtAnnotator annotation DOM ref registration logic.
 *
 * Verifies that onAnnotationRefChange correctly registers and unregisters
 * annotation DOM elements, and that annotations filtered by visibleLabels
 * are never registered (preventing "ghost" IDs in the tracking set).
 */
import React from "react";
import { render, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";

import TxtAnnotator from "../TxtAnnotator";
import { ServerSpanAnnotation } from "../../../types/annotations";
import { PermissionTypes } from "../../../../types";
import { LabelType } from "../../../../../types/graphql-api";

// ---------- Helpers ----------

const mockLabel = {
  id: "label-1",
  text: "TestLabel",
  color: "#3B82F6",
  icon: "tag" as any,
  description: "Test label",
  labelType: LabelType.SpanLabel,
};

const hiddenLabel = {
  id: "label-2",
  text: "HiddenLabel",
  color: "#EF4444",
  icon: "tag" as any,
  description: "Hidden label",
  labelType: LabelType.SpanLabel,
};

function makeAnnotation(
  id: string,
  start: number,
  end: number,
  label = mockLabel
): ServerSpanAnnotation {
  return new ServerSpanAnnotation(
    0,
    label,
    "text",
    false,
    { start, end },
    [PermissionTypes.CAN_READ],
    false,
    false,
    false,
    id
  );
}

// Stable empty arrays to avoid infinite re-render from default parameter allocation
const EMPTY_SEARCH_RESULTS: any[] = [];
const EMPTY_CHAT_SOURCES: any[] = [];

const defaultProps = {
  searchResults: EMPTY_SEARCH_RESULTS,
  getSpan: vi.fn(),
  visibleLabels: null,
  availableLabels: [],
  selectedLabelTypeId: null,
  read_only: true,
  allowInput: false,
  zoom_level: 1,
  createAnnotation: vi.fn(),
  updateAnnotation: vi.fn(),
  deleteAnnotation: vi.fn(),
  selectedAnnotations: [] as string[],
  setSelectedAnnotations: vi.fn(),
  showStructuralAnnotations: true,
  chatSources: EMPTY_CHAT_SOURCES,
};

// ---------- Tests ----------

describe("TxtAnnotator annotation ref registration", () => {
  let onAnnotationRefChange: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    onAnnotationRefChange = vi.fn();
  });

  it("registers refs for annotations with matching DOM spans", async () => {
    const text = "Hello world";
    const annotation = makeAnnotation("ann-1", 0, 5); // covers "Hello"

    render(
      <MemoryRouter>
        <TxtAnnotator
          {...defaultProps}
          text={text}
          annotations={[annotation]}
          onAnnotationRefChange={onAnnotationRefChange}
        />
      </MemoryRouter>
    );

    await waitFor(() => {
      const registerCalls = onAnnotationRefChange.mock.calls.filter(
        ([id, el]: any[]) => id === "ann-1" && el !== null
      );
      expect(registerCalls.length).toBeGreaterThanOrEqual(1);
    });
  });

  it("does NOT register refs for annotations with hidden labels", async () => {
    const text = "Hello world";
    const visibleAnnotation = makeAnnotation("visible-1", 0, 5);
    const hiddenAnn = makeAnnotation("hidden-1", 6, 11, hiddenLabel);

    render(
      <MemoryRouter>
        <TxtAnnotator
          {...defaultProps}
          text={text}
          annotations={[visibleAnnotation, hiddenAnn]}
          visibleLabels={[mockLabel]}
          onAnnotationRefChange={onAnnotationRefChange}
        />
      </MemoryRouter>
    );

    await waitFor(() => {
      const visibleCalls = onAnnotationRefChange.mock.calls.filter(
        ([id, el]: any[]) => id === "visible-1" && el !== null
      );
      expect(visibleCalls.length).toBeGreaterThanOrEqual(1);
    });

    const hiddenCalls = onAnnotationRefChange.mock.calls.filter(
      ([id, el]: any[]) => id === "hidden-1" && el !== null
    );
    expect(hiddenCalls).toHaveLength(0);
  });

  it("unregisters refs when annotations are removed", async () => {
    const text = "Hello world";
    const annotation = makeAnnotation("ann-1", 0, 5);

    const { rerender } = render(
      <MemoryRouter>
        <TxtAnnotator
          {...defaultProps}
          text={text}
          annotations={[annotation]}
          onAnnotationRefChange={onAnnotationRefChange}
        />
      </MemoryRouter>
    );

    await waitFor(() => {
      const initialRegister = onAnnotationRefChange.mock.calls.filter(
        ([id, el]: any[]) => id === "ann-1" && el !== null
      );
      expect(initialRegister.length).toBeGreaterThanOrEqual(1);
    });

    onAnnotationRefChange.mockClear();

    rerender(
      <MemoryRouter>
        <TxtAnnotator
          {...defaultProps}
          text={text}
          annotations={[]}
          onAnnotationRefChange={onAnnotationRefChange}
        />
      </MemoryRouter>
    );

    await waitFor(() => {
      const unregisterCalls = onAnnotationRefChange.mock.calls.filter(
        ([id, el]: any[]) => id === "ann-1" && el === null
      );
      expect(unregisterCalls.length).toBeGreaterThanOrEqual(1);
    });
  });

  it("unregisters refs when label becomes hidden", async () => {
    const text = "Hello world";
    const annotation = makeAnnotation("ann-1", 0, 5);

    const { rerender } = render(
      <MemoryRouter>
        <TxtAnnotator
          {...defaultProps}
          text={text}
          annotations={[annotation]}
          visibleLabels={null}
          onAnnotationRefChange={onAnnotationRefChange}
        />
      </MemoryRouter>
    );

    await waitFor(() => {
      const registerCalls = onAnnotationRefChange.mock.calls.filter(
        ([id, el]: any[]) => id === "ann-1" && el !== null
      );
      expect(registerCalls.length).toBeGreaterThanOrEqual(1);
    });

    onAnnotationRefChange.mockClear();

    // Hide the label by setting visibleLabels to an empty list
    rerender(
      <MemoryRouter>
        <TxtAnnotator
          {...defaultProps}
          text={text}
          annotations={[annotation]}
          visibleLabels={[]}
          onAnnotationRefChange={onAnnotationRefChange}
        />
      </MemoryRouter>
    );

    await waitFor(() => {
      const unregisterCalls = onAnnotationRefChange.mock.calls.filter(
        ([id, el]: any[]) => id === "ann-1" && el === null
      );
      expect(unregisterCalls.length).toBeGreaterThanOrEqual(1);
    });
  });
});
