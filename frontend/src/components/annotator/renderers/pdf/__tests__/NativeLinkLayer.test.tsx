/**
 * Unit coverage for NativeLinkLayer — verifies that PDF.js link annotations
 * are surfaced as real <a> elements positioned by the page's viewport, and
 * that unsafe URLs are filtered out before they reach the DOM.
 */
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import type { PDFPageProxy } from "pdfjs-dist/types/src/display/api";

import { NativeLinkLayer } from "../NativeLinkLayer";

const makePage = (
  annotations: Array<{
    id: string;
    subtype?: string;
    url?: string;
    rect?: number[];
  }>
): PDFPageProxy => {
  return {
    getAnnotations: vi.fn().mockResolvedValue(annotations),
    // Mock honours the `scale` arg so the test for scaled positioning can
    // verify that NativeLinkLayer actually forwards the prop into
    // ``getViewport({ scale })``.
    getViewport: vi.fn(({ scale = 1 }: { scale?: number } = {}) => ({
      convertToViewportRectangle: (rect: number[]) =>
        rect.map((value) => value * scale),
    })),
  } as unknown as PDFPageProxy;
};

describe("NativeLinkLayer", () => {
  it("renders an <a> for each safe Link annotation", async () => {
    const page = makePage([
      {
        id: "ann-1",
        subtype: "Link",
        url: "https://example.com",
        rect: [10, 20, 110, 40],
      },
      {
        id: "ann-2",
        subtype: "Link",
        url: "mailto:test@example.com",
        rect: [0, 0, 50, 50],
      },
    ]);

    render(<NativeLinkLayer page={page} scale={1} />);

    await waitFor(() => {
      expect(screen.getAllByRole("link")).toHaveLength(2);
    });

    const links = screen.getAllByRole("link");
    expect(links[0]).toHaveAttribute("href", "https://example.com");
    expect(links[0]).toHaveAttribute("target", "_blank");
    expect(links[0]).toHaveAttribute("rel", "noopener noreferrer");
    expect(links[1]).toHaveAttribute("href", "mailto:test@example.com");
  });

  it("filters out unsafe protocols", async () => {
    const page = makePage([
      {
        id: "ann-1",
        subtype: "Link",
        url: "javascript:alert(1)",
        rect: [0, 0, 10, 10],
      },
      {
        id: "ann-2",
        subtype: "Link",
        url: "file:///etc/passwd",
        rect: [0, 0, 10, 10],
      },
      {
        id: "ann-3",
        subtype: "Link",
        url: "https://safe.example",
        rect: [0, 0, 10, 10],
      },
    ]);

    render(<NativeLinkLayer page={page} scale={1} />);

    await waitFor(() => {
      expect(screen.getAllByRole("link")).toHaveLength(1);
    });
    expect(screen.getByRole("link")).toHaveAttribute(
      "href",
      "https://safe.example"
    );
  });

  it("ignores non-Link annotations and Links without a URL", async () => {
    const page = makePage([
      { id: "w", subtype: "Widget", rect: [0, 0, 10, 10] },
      { id: "l-no-url", subtype: "Link", rect: [0, 0, 10, 10] },
      {
        id: "l-ok",
        subtype: "Link",
        url: "https://example.com",
        rect: [0, 0, 10, 10],
      },
    ]);

    render(<NativeLinkLayer page={page} scale={1} />);

    await waitFor(() => {
      expect(screen.getAllByRole("link")).toHaveLength(1);
    });
  });

  it("renders nothing when there are no link annotations", async () => {
    const page = makePage([]);
    const { container } = render(<NativeLinkLayer page={page} scale={1} />);

    // Resolve the promise chain so the empty-state branch runs.
    await waitFor(() => {
      expect(page.getAnnotations).toHaveBeenCalled();
    });
    expect(container.querySelector("a")).toBeNull();
  });

  it("positions links using the scaled viewport rectangle", async () => {
    const page = makePage([
      {
        id: "ann-1",
        subtype: "Link",
        url: "https://example.com",
        rect: [10, 20, 110, 40],
      },
    ]);

    render(<NativeLinkLayer page={page} scale={2} />);

    const link = await waitFor(() => screen.getByRole("link"));
    // Mock viewport multiplies by the passed scale; layer uses min/abs.
    expect(link).toHaveStyle({
      left: "20px",
      top: "40px",
      width: "200px",
      height: "40px",
    });
    // Scale prop must actually flow into the PDF.js viewport call —
    // otherwise the overlay would render at the wrong zoom level.
    expect(page.getViewport).toHaveBeenCalledWith({ scale: 2 });
  });

  it("exposes an aria-label for screen readers", async () => {
    const page = makePage([
      {
        id: "ann-1",
        subtype: "Link",
        url: "https://example.com",
        rect: [10, 20, 110, 40],
      },
    ]);

    render(<NativeLinkLayer page={page} scale={1} />);

    await waitFor(() => {
      expect(
        screen.getByRole("link", { name: "https://example.com" })
      ).toBeInTheDocument();
    });
  });
});
