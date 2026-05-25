import { test, expect } from "../utils/coverage";
import {
  GET_THREAD_DETAIL,
  GET_USER_BADGES,
  GET_CONVERSATIONS,
} from "../../src/graphql/queries";
import { createMockThread, createMockMessage } from "./utils/mockThreadData";
import { docScreenshot } from "../utils/docScreenshot";

// Component imports — kept in standalone statements so Playwright CT's
// babel rewrite recognises them as JSX components (CLAUDE.md pitfall #16).
import { MemoryRouter } from "react-router-dom";
import { MockedProvider } from "@apollo/client/testing";
import { Provider as JotaiProvider } from "jotai";
import { SidebarLayoutHarness } from "./ThreadDetailSidebarLayoutHarness";
import { BadgeClipHarness } from "./BadgeClipHarness";

/**
 * Visual coverage for the sidebar discussion view:
 *  - The reworked thread-detail header (badge / title / context / meta on
 *    their own rows instead of one cramped wrap row).
 *  - The portalled badge tooltip, which previously was clipped by the
 *    sidebar's `overflow: hidden` ancestor chain.
 */
test.describe("DocumentDiscussionsContent — sidebar thread detail", () => {
  const documentTitle =
    "SPACE EXPLORATION TECHNOLOGIES CORP S-1 (2026-05-20) - primary document";

  const mockThreadDetail = createMockThread({
    id: "thread-1",
    title: "Overhyped?",
    description: undefined as unknown as string,
    chatWithDocument: {
      id: "doc-1",
      title: documentTitle,
    } as any,
    allMessages: [
      createMockMessage({
        id: "msg-1",
        content: "What do y'all think?",
        creator: {
          id: "user-1",
          username: "majesticGrasshopper",
          email: "mg@example.com",
          slug: "majesticgrasshopper",
          name: "Majestic Grasshopper",
          firstName: "Majestic",
          lastName: "Grasshopper",
          phone: null,
          isUsageCapped: false,
        },
      }),
    ],
  });

  const mocks = [
    {
      request: {
        query: GET_THREAD_DETAIL,
        variables: { conversationId: "thread-1" },
      },
      result: { data: { conversation: mockThreadDetail } },
    },
    // ThreadList briefly mounts before our useEffect promotes us into
    // thread-detail mode; satisfy its query with an empty list.
    {
      request: {
        query: GET_CONVERSATIONS,
        variables: {
          documentId: "doc-1",
          conversationType: "THREAD",
          limit: 20,
        },
      },
      result: {
        data: {
          conversations: {
            edges: [],
            pageInfo: {
              hasNextPage: false,
              hasPreviousPage: false,
              startCursor: "",
              endCursor: "",
            },
            totalCount: 0,
          },
        },
      },
    },
    {
      request: {
        query: GET_USER_BADGES,
        variables: { corpusId: "corpus-1", limit: 5 },
      },
      result: {
        data: {
          userBadges: {
            edges: [
              {
                node: {
                  id: "ub-1",
                  awardedAt: "2026-05-22T10:00:00Z",
                  user: {
                    id: "user-1",
                    username: "majesticGrasshopper",
                    email: "mg@example.com",
                  },
                  badge: {
                    id: "badge-1",
                    name: "Conversationalist",
                    description:
                      "Awarded for sparking lively threads in this corpus.",
                    icon: "MessageCircle",
                    color: "#2563eb",
                    badgeType: "GLOBAL",
                  },
                  awardedBy: null,
                  corpus: null,
                },
              },
            ],
            pageInfo: {
              hasNextPage: false,
              hasPreviousPage: false,
              startCursor: "",
              endCursor: "",
            },
          },
        },
      },
    },
  ];

  test("renders the reworked header layout", async ({ mount, page }) => {
    await page.setViewportSize({ width: 420, height: 800 });

    await mount(
      <MemoryRouter initialEntries={["/?thread=thread-1"]}>
        <MockedProvider mocks={mocks} addTypename={false}>
          <JotaiProvider>
            <SidebarLayoutHarness />
          </JotaiProvider>
        </MockedProvider>
      </MemoryRouter>
    );

    await expect(page.getByText("Overhyped?")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(documentTitle)).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText("What do y'all think?")).toBeVisible({
      timeout: 5_000,
    });

    await docScreenshot(page, "discussions--sidebar-thread-detail--layout");
  });

  test("badge tooltip escapes overflow: hidden ancestors", async ({
    mount,
    page,
  }) => {
    await page.setViewportSize({ width: 420, height: 600 });

    // Mount the badge in a deliberately constrained, overflow-hidden frame
    // that mirrors the sidebar's clipping chain. Pre-fix, the popover was
    // clipped by these ancestors. Post-fix, it's portalled to document.body.
    await mount(<BadgeClipHarness />);

    const badge = page.getByText("Conversationalist", { exact: false });
    await expect(badge).toBeVisible();

    await badge.hover();

    const tooltipText = page.getByText("Awarded for sparking lively threads", {
      exact: false,
    });
    await expect(tooltipText).toBeVisible({ timeout: 3_000 });

    // The tooltip must live OUTSIDE the clipping frame's DOM subtree —
    // a nonzero bounding box alone could pass even if the tooltip were
    // still inside the clip frame and merely positioned somewhere in
    // its scroll buffer.  Assert structurally: the tooltip's nearest
    // ancestor ``[data-testid='clip-frame']`` is ``null``.
    const escapedClip = await tooltipText.evaluate(
      (el) => el.closest("[data-testid='clip-frame']") === null
    );
    expect(escapedClip).toBe(true);

    // Also sanity-check the tooltip rendered with nonzero size (catches
    // a regression where the portal mounts but the popup is collapsed).
    const tooltipBox = await tooltipText.boundingBox();
    expect(tooltipBox).toBeTruthy();
    if (tooltipBox) {
      expect(tooltipBox.width).toBeGreaterThan(0);
      expect(tooltipBox.height).toBeGreaterThan(0);
    }

    await docScreenshot(
      page,
      "discussions--sidebar-thread-detail--tooltip-portal"
    );
  });
});
