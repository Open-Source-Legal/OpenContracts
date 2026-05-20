import { test, expect } from "../utils/coverage";
import { ThreadDetail } from "../../src/components/threads/ThreadDetail";
import { ThreadTestWrapper } from "./utils/ThreadTestWrapper";
import { createMockThread } from "./utils/mockThreadData";
import { GET_THREAD_DETAIL } from "../../src/graphql/queries";
import { docScreenshot } from "../utils/docScreenshot";

/**
 * Regression coverage for the mobile header-overflow fix (PR #1709):
 * on narrow viewports the thread header (title + description) must wrap
 * inside the card rather than bleeding past its edge.
 */
test.describe("ThreadDetail mobile header", () => {
  const longTitle =
    "Quarterly Compliance Review — Cross-Border Data Transfer Obligations";

  test("wraps long title/description without horizontal overflow", async ({
    mount,
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });

    const mockThread = createMockThread({
      id: "thread-1",
      title: longTitle,
      description:
        "A long unbroken subtitle describing the discussion scope that " +
        "previously bled past the card edge on narrow mobile viewports.",
      allMessages: [],
    });

    const mocks = [
      {
        request: {
          query: GET_THREAD_DETAIL,
          variables: { conversationId: "thread-1" },
        },
        result: {
          data: {
            conversation: mockThread,
          },
        },
      },
    ];

    const component = await mount(
      <ThreadTestWrapper mocks={mocks}>
        <ThreadDetail conversationId="thread-1" corpusId="corpus-1" />
      </ThreadTestWrapper>
    );

    await component.waitFor({ timeout: 3000 });

    await expect(component.getByText(longTitle)).toBeVisible({
      timeout: 5000,
    });

    // The header content must wrap inside the card — no horizontal bleed.
    // scrollWidth > clientWidth means children overflow the header's box.
    const header = component.locator("[data-testid='thread-header']");
    const { scrollWidth, clientWidth } = await header.evaluate((el) => ({
      scrollWidth: el.scrollWidth,
      clientWidth: el.clientWidth,
    }));
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth);

    await docScreenshot(page, "threads--thread-detail--mobile-header");
  });
});
