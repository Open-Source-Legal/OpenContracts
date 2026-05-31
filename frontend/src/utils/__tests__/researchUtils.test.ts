import { describe, it, expect } from "vitest";
import {
  getResearchStatus,
  isTerminalResearchStatus,
  formatResearchDuration,
  formatResearchDate,
} from "../researchUtils";
import { JobStatus } from "../../types/graphql-api";
import {
  RESEARCH_STATUS,
  RESEARCH_STATUS_COLORS,
} from "../../assets/configurations/constants";

describe("getResearchStatus()", () => {
  it("maps each JobStatus to its label + chip color", () => {
    expect(getResearchStatus(JobStatus.Queued)).toEqual({
      label: RESEARCH_STATUS.QUEUED,
      color: RESEARCH_STATUS_COLORS[RESEARCH_STATUS.QUEUED],
    });
    expect(getResearchStatus(JobStatus.Running)).toEqual({
      label: RESEARCH_STATUS.RUNNING,
      color: RESEARCH_STATUS_COLORS[RESEARCH_STATUS.RUNNING],
    });
    expect(getResearchStatus(JobStatus.Completed).color).toBe("success");
    expect(getResearchStatus(JobStatus.Failed).color).toBe("error");
    expect(getResearchStatus(JobStatus.Cancelled).color).toBe("warning");
  });

  it("surfaces the transient CREATED state as Queued", () => {
    expect(getResearchStatus(JobStatus.Created)).toEqual({
      label: RESEARCH_STATUS.QUEUED,
      color: RESEARCH_STATUS_COLORS[RESEARCH_STATUS.QUEUED],
    });
  });

  it("falls back to QUEUED for unknown/empty status", () => {
    expect(getResearchStatus(undefined).label).toBe(RESEARCH_STATUS.QUEUED);
    expect(getResearchStatus("WAT").label).toBe(RESEARCH_STATUS.QUEUED);
  });
});

describe("isTerminalResearchStatus()", () => {
  it("is true for terminal states", () => {
    expect(isTerminalResearchStatus(JobStatus.Completed)).toBe(true);
    expect(isTerminalResearchStatus(JobStatus.Failed)).toBe(true);
    expect(isTerminalResearchStatus(JobStatus.Cancelled)).toBe(true);
  });

  it("is false for active states", () => {
    // CREATED is the transient pre-queue state — non-terminal, so polling
    // must continue (regression guard: it was missing from the frontend enum
    // and wrongly fell through to the terminal branch).
    expect(isTerminalResearchStatus(JobStatus.Created)).toBe(false);
    expect(isTerminalResearchStatus(JobStatus.Queued)).toBe(false);
    expect(isTerminalResearchStatus(JobStatus.Running)).toBe(false);
    expect(isTerminalResearchStatus(undefined)).toBe(false);
    expect(isTerminalResearchStatus(null)).toBe(false);
  });

  it("treats an unrecognized status as terminal (so polling stops)", () => {
    // A future backend state the frontend doesn't know about must not keep the
    // detail view polling forever; only Queued/Running/not-set are non-terminal.
    expect(isTerminalResearchStatus("SOME_FUTURE_STATE")).toBe(true);
  });
});

describe("formatResearchDuration()", () => {
  it("formats minutes + seconds", () => {
    expect(formatResearchDuration(125)).toBe("2m 5s");
  });

  it("formats sub-minute durations", () => {
    expect(formatResearchDuration(42)).toBe("42s");
  });

  it("returns null for null/NaN", () => {
    expect(formatResearchDuration(null)).toBeNull();
    expect(formatResearchDuration(undefined)).toBeNull();
    expect(formatResearchDuration(Number.NaN)).toBeNull();
  });
});

describe("formatResearchDate()", () => {
  it("formats an ISO date to a human-readable string", () => {
    // Use a fixed date; assert the year and month token are present
    const out = formatResearchDate("2026-01-15T12:00:00Z");
    expect(out).toContain("2026");
    expect(out).toMatch(/Jan/);
  });
});
