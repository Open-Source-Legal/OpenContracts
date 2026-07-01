import { describe, expect, it } from "vitest";

import {
  formatCanonicalLawKey,
  formatCompactMoney,
  parseIsoDateMs,
} from "./formatters";

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

describe("formatCompactMoney", () => {
  it("drops the decimal at or above $10M", () => {
    expect(formatCompactMoney(10_000_000)).toBe("$10M");
    expect(formatCompactMoney(15_000_000)).toBe("$15M");
    expect(formatCompactMoney(123_400_000)).toBe("$123M");
  });

  it("keeps one decimal between $1M and $10M", () => {
    expect(formatCompactMoney(1_000_000)).toBe("$1.0M");
    expect(formatCompactMoney(1_500_000)).toBe("$1.5M");
    expect(formatCompactMoney(2_300_000)).toBe("$2.3M");
  });

  it("rounds thousands to whole $K", () => {
    expect(formatCompactMoney(1_000)).toBe("$1K");
    expect(formatCompactMoney(250_000)).toBe("$250K");
    expect(formatCompactMoney(1_500)).toBe("$2K"); // rounds half up
  });

  it("renders sub-thousand amounts as whole dollars", () => {
    expect(formatCompactMoney(0)).toBe("$0");
    expect(formatCompactMoney(900)).toBe("$900");
    expect(formatCompactMoney(999)).toBe("$999");
    expect(formatCompactMoney(12.4)).toBe("$12");
  });
});

describe("parseIsoDateMs", () => {
  it("returns null for empty/nullish input", () => {
    expect(parseIsoDateMs(null)).toBeNull();
    expect(parseIsoDateMs(undefined)).toBeNull();
    expect(parseIsoDateMs("")).toBeNull();
  });

  it("parses a leading ISO date to UTC-midnight epoch ms", () => {
    expect(parseIsoDateMs("2021-03-15")).toBe(Date.UTC(2021, 2, 15));
  });

  it("tolerates surrounding whitespace and trailing time components", () => {
    expect(parseIsoDateMs("  2021-03-15  ")).toBe(Date.UTC(2021, 2, 15));
    expect(parseIsoDateMs("2021-03-15T12:34:56Z")).toBe(Date.UTC(2021, 2, 15));
  });

  it("returns null when there is no parseable leading ISO date", () => {
    expect(parseIsoDateMs("not-a-date")).toBeNull();
    expect(parseIsoDateMs("2021/03/15")).toBeNull();
    expect(parseIsoDateMs("March 15, 2021")).toBeNull();
  });

  it("returns null for a shaped-but-invalid date (NaN guard)", () => {
    expect(parseIsoDateMs("2021-13-45")).toBeNull();
  });
});
