/**
 * Playwright component test for StartResearchModal — the explicit (non-chat)
 * deep-research kickoff modal opened from the corpus Research tab.
 *
 * Smoke-level: mounts the modal open and asserts its header + the title/prompt
 * inputs render, and that the optional title input carries the
 * MAX_RESEARCH_TITLE_CHARS cap (mirrors the backend 255-char model column so the
 * UI rejects over-long titles before the round-trip rather than letting the DB
 * silently truncate). Submission is not exercised here.
 */
import { test, expect } from "./utils/coverage";
import { docScreenshot } from "./utils/docScreenshot";
import { MAX_RESEARCH_TITLE_CHARS } from "../src/assets/configurations/constants";
// Component import isolated (Playwright CT split-import rule, CLAUDE.md #16).
import { StartResearchModalTestWrapper } from "./StartResearchModalTestWrapper";

test.describe("StartResearchModal", () => {
  test("renders the kickoff form and caps the title at MAX_RESEARCH_TITLE_CHARS", async ({
    mount,
    page,
  }) => {
    await mount(<StartResearchModalTestWrapper />);

    await expect(page.getByText("Start deep research")).toBeVisible({
      timeout: 15000,
    });

    const titleInput = page.getByPlaceholder("e.g. Indemnification exposure");
    await expect(titleInput).toBeVisible();
    await expect(titleInput).toHaveAttribute(
      "maxlength",
      String(MAX_RESEARCH_TITLE_CHARS)
    );

    await expect(
      page.getByPlaceholder(/Describe the question to research/)
    ).toBeVisible();

    await docScreenshot(page, "research--start-research-modal--open");
  });
});
