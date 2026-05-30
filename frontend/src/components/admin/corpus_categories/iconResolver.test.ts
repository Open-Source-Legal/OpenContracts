import { describe, expect, it } from "vitest";
import { FileText, Gavel, Scroll, Tag } from "lucide-react";
import { resolveLucideIcon } from "./iconResolver";

describe("resolveLucideIcon", () => {
  it("falls back to Tag for empty / nullish names", () => {
    expect(resolveLucideIcon("")).toBe(Tag);
    expect(resolveLucideIcon(null)).toBe(Tag);
    expect(resolveLucideIcon(undefined)).toBe(Tag);
  });

  it("resolves kebab-case names to the matching Lucide component", () => {
    expect(resolveLucideIcon("file-text")).toBe(FileText);
    expect(resolveLucideIcon("scroll")).toBe(Scroll);
    expect(resolveLucideIcon("gavel")).toBe(Gavel);
  });

  it("resolves snake_case names as well", () => {
    expect(resolveLucideIcon("file_text")).toBe(FileText);
  });

  it("falls back to Tag for unknown icon names", () => {
    expect(resolveLucideIcon("definitely-not-a-real-icon")).toBe(Tag);
  });
});
