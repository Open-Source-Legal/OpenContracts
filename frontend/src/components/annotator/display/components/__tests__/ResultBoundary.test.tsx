/**
 * Unit tests for ResultBoundary's translucent fill.
 *
 * Pins the boundary's translucent fill opacity — rendered independently of
 * the ``showBoundingBox`` toggle so multi-line search results don't stripe
 * white between text rows. The box-shadow halo stays gated by
 * ``showBoundingBox``.
 */
import React from "react";
import { render } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

import { ResultBoundary } from "../ResultBoundary";
import {
  BOUNDARY_OPACITY_SELECTED,
  BOUNDARY_OPACITY_UNSELECTED,
} from "../../../../../assets/configurations/constants";

vi.mock("../../../hooks/useAnnotationRefs", () => ({
  useAnnotationRefs: () => ({
    registerRef: vi.fn(),
    unregisterRef: vi.fn(),
  }),
}));

const bounds = { left: 0, top: 0, right: 100, bottom: 50 };

describe("ResultBoundary translucent fill", () => {
  // #0066cc → rgb(0, 102, 204); the fill is rgba(r, g, b, opacity).
  it("renders the unselected fill even when showBoundingBox is false", () => {
    const { container } = render(
      <ResultBoundary
        id="fill1"
        hidden={false}
        selected={false}
        color="#0066cc"
        bounds={bounds}
        showBoundingBox={false}
      />
    );
    const span = container.querySelector("span") as HTMLElement;
    expect(span.style.background).toBe(
      `rgba(0, 102, 204, ${BOUNDARY_OPACITY_UNSELECTED})`
    );
  });

  it("forces a fully transparent fill when hidden, regardless of showBoundingBox", () => {
    const { container } = render(
      <ResultBoundary
        id="fill2"
        hidden
        selected={false}
        color="#0066cc"
        bounds={bounds}
        showBoundingBox
      />
    );
    const span = container.querySelector("span") as HTMLElement;
    expect(span.style.background).toBe("rgba(0, 102, 204, 0)");
  });

  it("renders the stronger selected fill when selected and showBoundingBox is false", () => {
    const { container } = render(
      <ResultBoundary
        id="fill3"
        hidden={false}
        selected
        color="#0066cc"
        bounds={bounds}
        showBoundingBox={false}
      />
    );
    const span = container.querySelector("span") as HTMLElement;
    expect(span.style.background).toBe(
      `rgba(0, 102, 204, ${BOUNDARY_OPACITY_SELECTED})`
    );
  });
});

describe("ResultBoundary box-shadow halo", () => {
  it("omits the box-shadow halo when showBoundingBox is false", () => {
    const { container } = render(
      <ResultBoundary
        id="halo1"
        hidden={false}
        selected={false}
        color="#0066cc"
        bounds={bounds}
        showBoundingBox={false}
      />
    );
    const span = container.querySelector("span") as HTMLElement;
    expect(span.style.boxShadow).toBe("none");
  });

  it("renders the box-shadow halo when showBoundingBox is true", () => {
    const { container } = render(
      <ResultBoundary
        id="halo2"
        hidden={false}
        selected={false}
        color="#0066cc"
        bounds={bounds}
        showBoundingBox
      />
    );
    const span = container.querySelector("span") as HTMLElement;
    expect(span.style.boxShadow).not.toBe("none");
    expect(span.style.boxShadow).not.toBe("");
  });
});
