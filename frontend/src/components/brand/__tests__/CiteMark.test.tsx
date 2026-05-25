import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";

import { CiteMark } from "../CiteMark";

describe("CiteMark", () => {
  it("renders an SVG with the default 24px size and accessible role", () => {
    const { container } = render(<CiteMark />);
    const svg = container.querySelector("svg");
    expect(svg).not.toBeNull();
    expect(svg).toHaveAttribute("role", "img");
    expect(svg).toHaveAttribute("aria-label", "cite mark");
    expect(svg).toHaveAttribute("width", "24");
    expect(svg).toHaveAttribute("height", "24");
    expect(svg).toHaveAttribute("viewBox", "0 0 64 64");
  });

  it("honors a custom size and propagates it to width/height", () => {
    const { container } = render(<CiteMark size={48} />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("width", "48");
    expect(svg).toHaveAttribute("height", "48");
  });

  it("forwards bracketColor and nodeColor to the underlying shapes", () => {
    const { container } = render(
      <CiteMark bracketColor="#FF0000" nodeColor="#00FF00" />
    );
    const lines = container.querySelectorAll("line");
    expect(lines.length).toBeGreaterThan(0);
    lines.forEach((line) => {
      expect(line).toHaveAttribute("stroke", "#FF0000");
    });
    const circle = container.querySelector("circle");
    expect(circle).toHaveAttribute("fill", "#00FF00");
  });

  it("accepts a custom strokeWidth override regardless of size", () => {
    const { container } = render(<CiteMark size={32} strokeWidth={5} />);
    const line = container.querySelector("line");
    expect(line).toHaveAttribute("stroke-width", "5");
  });

  // The strokeFor helper has four size bands; pick a size in each band so
  // each early-return path is exercised exactly once.
  it.each([
    [16, "1.2"],
    [32, "1.8"],
    [48, "2.4"],
    [64, "3"],
  ])(
    "derives stroke width %s for size %s when no override",
    (size, expected) => {
      const { container } = render(<CiteMark size={size} />);
      const line = container.querySelector("line");
      expect(line).toHaveAttribute("stroke-width", expected);
    }
  );

  it("propagates className, style, and ariaLabel onto the root SVG", () => {
    const { container } = render(
      <CiteMark
        className="custom-mark"
        style={{ opacity: 0.5 }}
        ariaLabel="brand glyph"
      />
    );
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("aria-label", "brand glyph");
    expect(svg).toHaveAttribute("role", "img");
    expect(svg).not.toHaveAttribute("aria-hidden");
    expect(svg).toHaveClass("custom-mark");
    expect(svg).toHaveStyle({ opacity: "0.5" });
  });

  // Decorative callers (GetStarted, CallToAction, About eyebrow, etc.) pass
  // `ariaLabel=""` to opt out of the `role="img"` slot — the mark is
  // alongside its own text, so an announced "image" label is redundant noise
  // for screen-reader users.
  it("renders as aria-hidden when ariaLabel is the empty string", () => {
    const { container } = render(<CiteMark ariaLabel="" />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("aria-hidden", "true");
    expect(svg).not.toHaveAttribute("role");
    expect(svg).not.toHaveAttribute("aria-label");
  });
});
