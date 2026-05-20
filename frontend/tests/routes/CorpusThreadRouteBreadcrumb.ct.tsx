import { test, expect } from "../utils/coverage";
import { CorpusThreadRouteHarness } from "./utils/CorpusThreadRouteHarness";
import { ThreadTestWrapper } from "../threads/utils/ThreadTestWrapper";
import { createMockThread } from "../threads/utils/mockThreadData";
import { GET_THREAD_DETAIL } from "../../src/graphql/queries";
import { openedCorpus, openedThread } from "../../src/graphql/cache";
import { docScreenshot } from "../utils/docScreenshot";

/**
 * Regression coverage for the mobile breadcrumb-overflow fix (PR #1709):
 * a long corpus title must truncate to a single-line pill rather than
 * reflowing the breadcrumb into 2-3 stacked lines on narrow viewports.
 */
test.describe("CorpusThreadRoute mobile breadcrumb", () => {
  const longCorpusTitle =
    "Quarterly Compliance Review — Cross-Border Data Transfer & " +
    "Retention Obligations Working Group";

  test.afterEach(() => {
    openedThread(null);
    openedCorpus(null);
  });

  test("truncates long corpus title to a single-line pill", async ({
    mount,
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });

    const mocks = [
      {
        request: {
          query: GET_THREAD_DETAIL,
          variables: { conversationId: "thread-1" },
        },
        result: {
          data: {
            conversation: createMockThread({ id: "thread-1", allMessages: [] }),
          },
        },
      },
    ];

    const component = await mount(
      <ThreadTestWrapper mocks={mocks}>
        <CorpusThreadRouteHarness corpusTitle={longCorpusTitle} />
      </ThreadTestWrapper>
    );

    const corpusLink = component.getByTitle(longCorpusTitle);
    await expect(corpusLink).toBeVisible({ timeout: 5000 });

    // The breadcrumb pill must stay a single line, not wrap to 2-3 lines.
    const box = await corpusLink.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.height).toBeLessThanOrEqual(40);

    // The label must actually be clamped (its text overflows its box).
    const label = corpusLink.locator("span");
    const { scrollWidth, clientWidth } = await label.evaluate((el) => ({
      scrollWidth: el.scrollWidth,
      clientWidth: el.clientWidth,
    }));
    expect(scrollWidth).toBeGreaterThan(clientWidth);

    await docScreenshot(
      page,
      "threads--corpus-thread-route--mobile-breadcrumb"
    );
  });
});
