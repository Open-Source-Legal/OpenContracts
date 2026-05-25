import { describe, expect, it } from "vitest";

import defaultContent from "../default.json";
import publicRecordContent from "../publicRecord.json";
import { DEFAULT_LANDING_VARIANT, LANDING_VARIANTS } from "../index";
import type { LandingContent } from "../types";

const isLandingContent = (value: unknown): value is LandingContent => {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    "hero" in v &&
    "stats" in v &&
    "getStarted" in v &&
    "callToAction" in v &&
    "about" in v
  );
};

describe("landingContent variants", () => {
  it("registers default and public-record variants", () => {
    expect(Object.keys(LANDING_VARIANTS).sort()).toEqual(
      ["default", "public-record"].sort()
    );
    expect(DEFAULT_LANDING_VARIANT).toBe("default");
  });

  it("the bundled default variant matches the type contract", () => {
    expect(isLandingContent(defaultContent)).toBe(true);
  });

  it("the bundled public-record variant matches the type contract", () => {
    expect(isLandingContent(publicRecordContent)).toBe(true);
  });

  it("default + public-record diverge on hero copy", () => {
    // If these ever match it means a copy-paste regression that
    // collapsed the variants — the whole point of the registry is
    // that they say *different* things to *different* audiences.
    expect(defaultContent.hero.accent).not.toBe(
      publicRecordContent.hero.accent
    );
    expect(defaultContent.about.title).not.toBe(
      publicRecordContent.about.title
    );
  });

  it("every variant references stable GraphQL stat keys", () => {
    const allowed = new Set([
      "totalUsers",
      "totalAnnotations",
      "totalThreads",
      "activeUsersThisWeek",
    ]);
    for (const variantKey of Object.keys(LANDING_VARIANTS)) {
      const variant = LANDING_VARIANTS[variantKey];
      for (const stat of variant.stats) {
        expect(
          allowed.has(stat.key),
          `unknown stat key ${stat.key} in ${variantKey}`
        ).toBe(true);
      }
    }
  });

  it("every variant has at least one About section with paragraphs", () => {
    for (const variantKey of Object.keys(LANDING_VARIANTS)) {
      const variant = LANDING_VARIANTS[variantKey];
      expect(variant.about.sections.length).toBeGreaterThan(0);
      for (const section of variant.about.sections) {
        expect(section.paragraphs.length).toBeGreaterThan(0);
      }
    }
  });
});
