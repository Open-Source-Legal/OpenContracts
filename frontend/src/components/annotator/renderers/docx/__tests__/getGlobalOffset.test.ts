import { describe, it, expect } from "vitest";
import {
  getGlobalOffsetFromDomPosition,
  mapNormOffsetToReal,
  pickClosestOccurrence,
} from "../docxOffsetUtils";

describe("getGlobalOffsetFromDomPosition", () => {
  it("computes offset for a simple flat text container", () => {
    const container = document.createElement("div");
    container.innerHTML = "Hello World";

    const textNode = container.childNodes[0];
    expect(getGlobalOffsetFromDomPosition(container, textNode, 6)).toBe(6);
  });

  it("computes offset across multiple paragraphs", () => {
    const container = document.createElement("div");
    // Simulates WASM output: document text split across <p> tags
    container.innerHTML = "<p>Hello World.</p><p>This is paragraph two.</p>";

    const p2TextNode = container.querySelectorAll("p")[1].childNodes[0];
    // "Hello World." is 12 chars, then "This" starts at offset 12 in DOM
    expect(getGlobalOffsetFromDomPosition(container, p2TextNode, 0)).toBe(12);
    expect(getGlobalOffsetFromDomPosition(container, p2TextNode, 5)).toBe(17);
  });

  it("skips annotation label text nodes", () => {
    const container = document.createElement("div");
    container.innerHTML =
      "<p>Hello " +
      '<span data-annotation-id="ann-1">' +
      '<span class="oc-annot-label">Label</span>' +
      "World" +
      "</span>" +
      ".</p>" +
      "<p>Second paragraph.</p>";

    // The "Label" text (5 chars) should be skipped.
    // Document text in DOM (excluding labels): "Hello World.Second paragraph."
    // "World" starts at offset 6 in the filtered text.
    const annotSpan = container.querySelector('[data-annotation-id="ann-1"]')!;
    // "World" is the second child of annotSpan (after the label span)
    const worldTextNode = annotSpan.childNodes[1]; // text node "World"
    expect(worldTextNode.textContent).toBe("World");
    expect(getGlobalOffsetFromDomPosition(container, worldTextNode, 0)).toBe(6);

    // "Second paragraph." starts at offset 12 (6 + "World." = 12)
    const p2TextNode = container.querySelectorAll("p")[1].childNodes[0];
    expect(getGlobalOffsetFromDomPosition(container, p2TextNode, 0)).toBe(12);
  });

  it("returns null for nodes not in the container", () => {
    const container = document.createElement("div");
    container.innerHTML = "<p>Hello</p>";

    const outsideNode = document.createTextNode("outside");
    expect(
      getGlobalOffsetFromDomPosition(container, outsideNode, 0)
    ).toBeNull();
  });

  it("returns null for null node", () => {
    const container = document.createElement("div");
    expect(getGlobalOffsetFromDomPosition(container, null, 0)).toBeNull();
  });

  it("handles element node pointing to a text child", () => {
    const container = document.createElement("div");
    container.innerHTML = "<p>First</p><p>Second</p>";

    // When the node is a <p> element and offset points to its text child,
    // the function resolves to the text node within.
    const p1 = container.querySelectorAll("p")[0];
    // offset 0 on an element = its first child (the text node "First")
    expect(getGlobalOffsetFromDomPosition(container, p1, 0)).toBe(0);
  });
});

describe("pickClosestOccurrence (disambiguation)", () => {
  it("picks the only occurrence when there is one", () => {
    const occurrences = [{ start: 13, end: 17 }];
    expect(pickClosestOccurrence(occurrences, 13)).toEqual({
      start: 13,
      end: 17,
    });
  });

  it("picks the closest occurrence from multiple", () => {
    // "This" appears at offset 13 and 57 in docText
    const occurrences = [
      { start: 13, end: 17 },
      { start: 57, end: 61 },
    ];

    // DOM offset ≈ 55 (slightly off from 57 due to missing newlines)
    // |55 - 13| = 42, |55 - 57| = 2 → picks second occurrence
    expect(pickClosestOccurrence(occurrences, 55)).toEqual({
      start: 57,
      end: 61,
    });
  });

  it("picks the first occurrence when DOM offset is near it", () => {
    const occurrences = [
      { start: 13, end: 17 },
      { start: 57, end: 61 },
    ];

    // DOM offset ≈ 12 → picks first occurrence
    expect(pickClosestOccurrence(occurrences, 12)).toEqual({
      start: 13,
      end: 17,
    });
  });

  it("handles three occurrences and picks the middle one", () => {
    const occurrences = [
      { start: 10, end: 14 },
      { start: 50, end: 54 },
      { start: 100, end: 104 },
    ];

    // DOM offset ≈ 48 → picks second occurrence
    expect(pickClosestOccurrence(occurrences, 48)).toEqual({
      start: 50,
      end: 54,
    });
  });

  it("simulates real contract scenario with 'Party' appearing 5 times", () => {
    const occurrences = [
      { start: 42, end: 47 },
      { start: 156, end: 161 },
      { start: 312, end: 317 },
      { start: 498, end: 503 },
      { start: 721, end: 726 },
    ];

    // User selects the 4th "Party" — DOM offset ≈ 490
    expect(pickClosestOccurrence(occurrences, 490)).toEqual({
      start: 498,
      end: 503,
    });
  });
});

describe("mapNormOffsetToReal", () => {
  it("returns the same offset when text has no extra whitespace", () => {
    const text = "Hello World";
    // Normalized: "Hello World" (identical)
    expect(mapNormOffsetToReal(text, 0)).toBe(0);
    expect(mapNormOffsetToReal(text, 5)).toBe(5);
    expect(mapNormOffsetToReal(text, 11)).toBe(11);
  });

  it("maps across newline boundaries (docText paragraphs)", () => {
    // docText uses newlines between paragraphs; normalized uses single spaces
    const text = "Hello\n\nWorld";
    // Normalized: "Hello World" (12→11 chars)
    // normOffset 0 ("H") → real 0
    expect(mapNormOffsetToReal(text, 0)).toBe(0);
    // normOffset 5 (" ") → real 5, but the whitespace run "\n\n" is at 5-6
    // After consuming it, realPos = 7 ("W")
    // Actually normOffset 6 ("W") → real 7
    expect(mapNormOffsetToReal(text, 6)).toBe(7);
    // normOffset 11 (end of "World") → real 12
    expect(mapNormOffsetToReal(text, 11)).toBe(12);
  });

  it("maps across multiple whitespace runs", () => {
    const text = "A  B\n\nC   D";
    // Normalized: "A B C D" (7 chars)
    // A=0, " "=1(real:1-2), B=2(real:3), " "=3(real:4-5), C=4(real:6),
    // " "=5(real:7-9), D=6(real:10)
    expect(mapNormOffsetToReal(text, 0)).toBe(0); // "A"
    expect(mapNormOffsetToReal(text, 2)).toBe(3); // "B"
    expect(mapNormOffsetToReal(text, 4)).toBe(6); // "C"
    expect(mapNormOffsetToReal(text, 6)).toBe(10); // "D"
    expect(mapNormOffsetToReal(text, 7)).toBe(11); // end
  });

  it("handles leading whitespace", () => {
    const text = "  Hello";
    // Normalized: " Hello" (6 chars)
    // normOffset 1 ("H") → realPos skips "  " (2 chars) → real 2
    expect(mapNormOffsetToReal(text, 1)).toBe(2);
  });

  it("handles empty text", () => {
    expect(mapNormOffsetToReal("", 0)).toBe(0);
  });

  it("clamps when normOffset exceeds normalized length", () => {
    const text = "AB";
    // normOffset 10 — should stop at end of text
    expect(mapNormOffsetToReal(text, 10)).toBe(2);
  });
});
