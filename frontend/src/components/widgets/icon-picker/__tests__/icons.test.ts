/**
 * Unit tests for the Lucide icon catalog (icons.ts).
 *
 * The catalog is pure data — a curated list of Lucide icon names with labels
 * and categories, plus derived lookup helpers (set of names, find-by-name map).
 *
 * These tests verify:
 *   - Every entry has a valid name, label, and category.
 *   - Names are unique and conform to the kebab-case convention.
 *   - Every declared category contains at least one icon.
 *   - The derived `LUCIDE_ICON_NAMES` set and `findIconEntry` map stay in sync
 *     with the source `LUCIDE_ICONS` array (guards against accidental drift).
 */
import { describe, it, expect } from "vitest";
import {
  LUCIDE_ICONS,
  LUCIDE_ICON_NAMES,
  ICON_CATEGORIES,
  findIconEntry,
  type IconCategory,
  type IconEntry,
} from "../icons";

// Every category declared in ICON_CATEGORIES must be one of the string-literal
// members of the IconCategory union. Collect them as the source of truth.
const VALID_CATEGORY_IDS: Set<IconCategory> = new Set(
  ICON_CATEGORIES.map((c) => c.id)
);

describe("icons catalog — shape", () => {
  it("exposes a non-empty array of icon entries", () => {
    expect(Array.isArray(LUCIDE_ICONS)).toBe(true);
    expect(LUCIDE_ICONS.length).toBeGreaterThan(0);
  });

  it("exposes ICON_CATEGORIES as a non-empty list of {id,label} records", () => {
    expect(Array.isArray(ICON_CATEGORIES)).toBe(true);
    expect(ICON_CATEGORIES.length).toBeGreaterThan(0);

    for (const cat of ICON_CATEGORIES) {
      expect(typeof cat.id).toBe("string");
      expect(cat.id.length).toBeGreaterThan(0);
      expect(typeof cat.label).toBe("string");
      expect(cat.label.length).toBeGreaterThan(0);
    }
  });

  it("has unique category ids", () => {
    const ids = ICON_CATEGORIES.map((c) => c.id);
    expect(new Set(ids).size).toBe(ids.length);
  });
});

describe("icons catalog — per-entry integrity", () => {
  // Parametrized per-entry check gives us one failed test per bad entry
  // instead of a single opaque catch-all, making regressions easy to debug.
  it.each(LUCIDE_ICONS)(
    "entry $name has valid name/label/category",
    (entry: IconEntry) => {
      // name: non-empty kebab-case string (letters, digits, single hyphens)
      expect(typeof entry.name).toBe("string");
      expect(entry.name.length).toBeGreaterThan(0);
      expect(entry.name).toMatch(/^[a-z0-9]+(?:-[a-z0-9]+)*$/);

      // label: non-empty, no leading/trailing whitespace
      expect(typeof entry.label).toBe("string");
      expect(entry.label.length).toBeGreaterThan(0);
      expect(entry.label).toBe(entry.label.trim());

      // category: must be one of the declared IconCategory members
      expect(VALID_CATEGORY_IDS.has(entry.category)).toBe(true);
    }
  );

  it("has no duplicate icon names", () => {
    const names = LUCIDE_ICONS.map((i) => i.name);
    const seen = new Set<string>();
    const duplicates: string[] = [];

    for (const name of names) {
      if (seen.has(name)) duplicates.push(name);
      seen.add(name);
    }

    expect(duplicates).toEqual([]);
    expect(seen.size).toBe(names.length);
  });

  it("every declared category contains at least one icon", () => {
    const usedCategories = new Set(LUCIDE_ICONS.map((i) => i.category));
    for (const { id } of ICON_CATEGORIES) {
      expect(usedCategories.has(id)).toBe(true);
    }
  });
});

describe("icons catalog — derived lookups", () => {
  it("LUCIDE_ICON_NAMES mirrors the catalog exactly", () => {
    expect(LUCIDE_ICON_NAMES.size).toBe(LUCIDE_ICONS.length);
    for (const entry of LUCIDE_ICONS) {
      expect(LUCIDE_ICON_NAMES.has(entry.name)).toBe(true);
    }
  });

  it("findIconEntry returns the matching entry for every catalog name", () => {
    for (const entry of LUCIDE_ICONS) {
      const found = findIconEntry(entry.name);
      expect(found).toBeDefined();
      // The map should return the same reference that lives in the array
      expect(found).toBe(entry);
    }
  });

  it("findIconEntry returns undefined for names not in the catalog", () => {
    expect(findIconEntry("this-icon-does-not-exist")).toBeUndefined();
    expect(findIconEntry("")).toBeUndefined();
    // Looks plausible but isn't part of the curated list
    expect(findIconEntry("definitely-not-an-icon-xyz-123")).toBeUndefined();
  });
});

describe("icons catalog — snapshot guard", () => {
  /**
   * Catch accidental catalog shrinkage. The catalog is curated and can grow
   * over time, but should never suddenly lose a large chunk of entries.
   * Uses a loose floor rather than an exact count so adding icons does not
   * break the test.
   */
  it("has at least 300 curated icons", () => {
    expect(LUCIDE_ICONS.length).toBeGreaterThanOrEqual(300);
  });
});
