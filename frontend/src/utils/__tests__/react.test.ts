import { describe, it, expect } from "vitest";
import React from "react";
import { hasRenderableNode } from "../react";

describe("hasRenderableNode", () => {
  it("returns false for null and undefined", () => {
    expect(hasRenderableNode(null)).toBe(false);
    expect(hasRenderableNode(undefined)).toBe(false);
  });

  it("returns false for boolean values (React renders nothing for them)", () => {
    expect(hasRenderableNode(true)).toBe(false);
    expect(hasRenderableNode(false)).toBe(false);
  });

  it("returns false for an empty React fragment", () => {
    expect(hasRenderableNode(React.createElement(React.Fragment))).toBe(false);
  });

  it("returns false for a fragment whose only children are null/false", () => {
    const node = React.createElement(
      React.Fragment,
      null,
      null,
      false,
      undefined
    );
    expect(hasRenderableNode(node)).toBe(false);
  });

  it("returns false for an array of empty values", () => {
    expect(hasRenderableNode([null, undefined, false, true])).toBe(false);
  });

  it("returns true for a non-empty React element", () => {
    expect(hasRenderableNode(React.createElement("span", null, "hi"))).toBe(
      true
    );
  });

  it("returns true for a fragment containing renderable children", () => {
    const node = React.createElement(
      React.Fragment,
      null,
      React.createElement("span", null, "child")
    );
    expect(hasRenderableNode(node)).toBe(true);
  });

  it("returns true when at least one item in an array is renderable", () => {
    expect(
      hasRenderableNode([null, React.createElement("span", null, "ok"), false])
    ).toBe(true);
  });

  it("returns true for primitive string and number children that React renders as text", () => {
    expect(hasRenderableNode("hello")).toBe(true);
    expect(hasRenderableNode(0)).toBe(true);
    expect(hasRenderableNode(42)).toBe(true);
  });
});
