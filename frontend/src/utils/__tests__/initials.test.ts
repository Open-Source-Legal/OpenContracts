import { describe, it, expect } from "vitest";

import { initialsFor } from "../initials";

describe("initialsFor", () => {
  it("uses the first letters of the first two words", () => {
    expect(initialsFor("Alice Anderson")).toBe("AA");
  });

  it("caps at two initials even for long names", () => {
    expect(initialsFor("alice anderson smith")).toBe("AA");
  });

  it("returns a single initial for one-word names", () => {
    expect(initialsFor("alice")).toBe("A");
  });

  it("returns ? for empty input", () => {
    expect(initialsFor("")).toBe("?");
  });

  it("returns ? for whitespace-only input", () => {
    expect(initialsFor("   ")).toBe("?");
  });

  it("collapses consecutive whitespace", () => {
    expect(initialsFor("alice    anderson")).toBe("AA");
  });

  it("uppercases lowercase initials", () => {
    expect(initialsFor("alice anderson")).toBe("AA");
  });

  it("handles unicode word characters", () => {
    expect(initialsFor("élise renard")).toBe("ÉR");
  });
});
