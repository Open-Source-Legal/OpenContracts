import { describe, expect, it } from "vitest";

import { formatCanonicalLawKey } from "./formatters";

describe("formatCanonicalLawKey", () => {
  it("upper-cases acronym authorities", () => {
    expect(formatCanonicalLawKey("dgcl:203")).toBe("DGCL § 203");
    expect(formatCanonicalLawKey("irc:368")).toBe("IRC § 368");
  });

  it("title-cases hyphenated authority words", () => {
    expect(formatCanonicalLawKey("securities-act:4(a)(2)")).toBe(
      "Securities Act § 4(a)(2)"
    );
    expect(formatCanonicalLawKey("exchange-act:16")).toBe("Exchange Act § 16");
  });

  it("mixes acronym and title-cased words", () => {
    expect(formatCanonicalLawKey("sec-rule:10b-5")).toBe("SEC Rule § 10b-5");
  });

  it("renders a bare authority prefix without a section marker", () => {
    expect(formatCanonicalLawKey("dgcl")).toBe("DGCL");
    expect(formatCanonicalLawKey("securities-act")).toBe("Securities Act");
  });
});
