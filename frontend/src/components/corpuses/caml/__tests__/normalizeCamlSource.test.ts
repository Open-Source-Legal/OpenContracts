import { describe, it, expect } from "vitest";
import { parseCaml } from "@os-legal/caml";
import { normalizeCamlSource, parseCamlArticle } from "../normalizeCamlSource";

/**
 * Helper: list block types per chapter, so assertions read as a structural
 * snapshot rather than poking at deep object shapes.
 */
function blockTypesByChapter(source: string): string[][] {
  return parseCaml(source).chapters.map((c) => c.blocks.map((b) => b.type));
}

const FRONTMATTER = [
  "---",
  'version: "1.0"',
  "hero:",
  '  title: ["Fort Worth"]',
  "---",
  "",
].join("\n");

describe("normalizeCamlSource", () => {
  it("returns source unchanged when there is no depth-4 fence (fast path)", () => {
    const src =
      FRONTMATTER +
      [
        "::: chapter {#intro}",
        "## Intro",
        "Just prose, no blocks.",
        ":::",
        "",
      ].join("\n");
    expect(normalizeCamlSource(src)).toBe(src);
  });

  it("leaves correctly-nested blocks untouched", () => {
    const src =
      FRONTMATTER +
      [
        "::: chapter {theme: dark}",
        "## Major Projects",
        "",
        ":::: cards {columns: 2}",
        "- **Infrastructure** | Major | #0f766e",
        "  Body text.",
        "::::",
        "",
        ":::",
        "",
      ].join("\n");
    expect(normalizeCamlSource(src)).toBe(src);
  });

  it("does not touch YAML frontmatter even when the body needs wrapping", () => {
    const src =
      FRONTMATTER +
      [":::: corpus-stats", "- documents | Documents", "::::", ""].join("\n");
    const normalized = normalizeCamlSource(src);
    expect(normalized.startsWith(FRONTMATTER.trimEnd())).toBe(true);
    expect(parseCaml(normalized).frontmatter.hero).toBeTruthy();
  });

  it("is idempotent", () => {
    const src =
      FRONTMATTER +
      [
        ":::: corpus-stats",
        "- documents | Documents",
        "- annotations | Annotations",
        "::::",
        "",
      ].join("\n");
    const once = normalizeCamlSource(src);
    const twice = normalizeCamlSource(once);
    expect(twice).toBe(once);
  });
});

describe("parseCamlArticle — repairs mis-nested blocks the raw parser leaks", () => {
  it("recovers a top-level corpus-stats block (the canonical leak)", () => {
    const src =
      FRONTMATTER +
      [
        ":::: corpus-stats",
        "- documents | Documents",
        "- annotations | Annotations",
        "::::",
        "",
      ].join("\n");

    // Raw parser leaks the block body (incl. literal ::::) as prose.
    const rawBlocks = blockTypesByChapter(src);
    expect(rawBlocks).toEqual([["prose"]]);
    const leakedProse = parseCaml(src).chapters[0].blocks[0];
    expect(leakedProse.type).toBe("prose");
    expect((leakedProse as { content: string }).content).toContain("::::");

    // parseCamlArticle wraps it so the block is recognised.
    const doc = parseCamlArticle(src);
    const block = doc.chapters[0].blocks[0];
    expect(block.type).toBe("corpus-stats");
    expect((block as { items: unknown[] }).items).toHaveLength(2);
  });

  it("recovers the screenshot scenario: dark cards chapter then a stray corpus-stats", () => {
    const src =
      FRONTMATTER +
      [
        "::: chapter {theme: dark}",
        "## Major Projects",
        "",
        ":::: cards {columns: 2}",
        "- **Infrastructure** | Major | #0f766e",
        "  Body.",
        "::::",
        "",
        ":::",
        "",
        "::: chapter {#documentation}",
        "## Documentation",
        "Closing prose.",
        ":::",
        "",
        ":::: corpus-stats",
        "- documents | Documents",
        "- annotations | Annotations",
        "::::",
        "",
      ].join("\n");

    const doc = parseCamlArticle(src);
    const types = doc.chapters.map((c) => c.blocks.map((b) => b.type));
    expect(types).toEqual([["cards"], ["prose"], ["corpus-stats"]]);
  });

  it("adopts a run of stray blocks with prose between them into one chapter", () => {
    const src =
      FRONTMATTER +
      [
        ":::: pills",
        "- 247 | **Docs** | Q4",
        "::::",
        "",
        "Mid prose between blocks.",
        "",
        ":::: cta",
        "- [View](#x) {primary}",
        "::::",
        "",
      ].join("\n");

    const doc = parseCamlArticle(src);
    expect(doc.chapters).toHaveLength(1);
    expect(doc.chapters[0].blocks.map((b) => b.type)).toEqual([
      "pills",
      "prose",
      "cta",
    ]);
  });

  it("recovers a stray tabs block that itself nests depth-5 fences", () => {
    const src =
      FRONTMATTER +
      [
        ":::: tabs",
        '::::: tab {label: "US", color: #0f766e}',
        "#### United States",
        "Federal regulations analyzed.",
        ":::::",
        "::::",
        "",
      ].join("\n");

    const doc = parseCamlArticle(src);
    expect(doc.chapters[0].blocks.map((b) => b.type)).toEqual(["tabs"]);
  });
});
