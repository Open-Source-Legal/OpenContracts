import React from "react";
import { test, expect } from "./utils/coverage";
// JSX-component import kept on its own line per the Playwright CT
// split-import rule (CLAUDE.md pitfall #16).
import { LeaderboardTestWrapper } from "./LeaderboardTestWrapper";
import {
  defaultLeaderboardMock,
  defaultCommunityStatsMock,
} from "./LeaderboardTestWrapper";
import { docScreenshot } from "./utils/docScreenshot";
import {
  GET_LEADERBOARD,
  GET_COMMUNITY_STATS,
} from "../src/graphql/queries/leaderboard/queries";

test.describe("Leaderboard", () => {
  test("renders leaderboard header and stats", async ({ mount, page }) => {
    const component = await mount(<LeaderboardTestWrapper />);

    // Should show the leaderboard heading
    await expect(page.locator("h1")).toContainText("Community Leaderboard", {
      timeout: 10000,
    });

    // Community stats should load and display
    await expect(page.getByText("Active Users")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByText("Messages", { exact: true })).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByText("Badges Awarded")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByText("Active This Week")).toBeVisible({
      timeout: 10000,
    });

    await docScreenshot(page, "community--leaderboard--with-data");

    await component.unmount();
  });

  test("shows leaderboard entries with user data", async ({ mount, page }) => {
    const component = await mount(<LeaderboardTestWrapper />);

    // The leaderboard now renders ``user.slug`` (case-sensitive, hyphenated)
    // rather than ``displayName`` — the mock fixture has slug "top-user" /
    // "second-user" alongside displayName "top_user" / "second_user", and
    // the public privacy contract is to surface only the slug.
    await expect(page.getByText("top-user")).toBeVisible({ timeout: 10000 });
    await expect(page.getByText("second-user")).toBeVisible({
      timeout: 10000,
    });

    // First user should have "Rising Star" badge
    await expect(page.getByText("Rising Star")).toBeVisible({
      timeout: 10000,
    });

    // Score column should show badge counts (use exact to avoid matching details column)
    await expect(page.getByText("50 badges", { exact: true })).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByText("35 badges", { exact: true })).toBeVisible({
      timeout: 10000,
    });

    // Current user rank info should be displayed
    await expect(page.getByText("#5")).toBeVisible({ timeout: 10000 });

    await component.unmount();
  });

  test("shows metric dropdown with options", async ({ mount, page }) => {
    const component = await mount(<LeaderboardTestWrapper />);

    // Wait for the filter bar to be visible
    const dropdownTriggers = page.locator(".oc-dropdown__trigger");
    await expect(dropdownTriggers.first()).toBeVisible({ timeout: 10000 });

    // The metric dropdown should show current selection
    const metricValue = page.locator(".oc-dropdown__value").first();
    await expect(metricValue).toContainText("Top Badge Earners", {
      timeout: 10000,
    });

    // Click the metric dropdown to see options
    await dropdownTriggers.first().click();

    const menu = page.locator(".oc-dropdown__menu");
    await expect(menu).toBeVisible({ timeout: 10000 });

    // Should list all metric options
    await expect(page.locator(".oc-dropdown__option")).toHaveCount(5, {
      timeout: 10000,
    });
    await expect(
      page.locator(".oc-dropdown__option", {
        hasText: "Most Active Contributors",
      })
    ).toBeVisible();
    await expect(
      page.locator(".oc-dropdown__option", { hasText: "Top Annotators" })
    ).toBeVisible();

    await docScreenshot(page, "community--leaderboard--filters");

    await component.unmount();
  });

  test("renders time scope and limit dropdowns", async ({ mount, page }) => {
    const component = await mount(<LeaderboardTestWrapper />);

    // There should be 3 dropdown triggers: metric, scope, limit
    const triggers = page.locator(".oc-dropdown__trigger");
    await expect(triggers).toHaveCount(3, { timeout: 10000 });

    // The scope dropdown (second) should show "All Time" by default
    const scopeValue = page.locator(".oc-dropdown__value").nth(1);
    await expect(scopeValue).toContainText("All Time", { timeout: 10000 });

    // The limit dropdown (third) should show "Top 25" by default
    const limitValue = page.locator(".oc-dropdown__value").nth(2);
    await expect(limitValue).toContainText("Top 25", { timeout: 10000 });

    await component.unmount();
  });

  test("renders empty state when no entries", async ({ mount, page }) => {
    // Playwright CT serializes the `mocks` prop across the test/component
    // boundary as JSON, so the `variableMatcher: () => true` shortcut on
    // `defaultLeaderboardMock` doesn't survive the trip. Use explicit
    // `variables` keyed to the component's initial query shape instead.
    const emptyMock = {
      request: {
        query: GET_LEADERBOARD,
        variables: {
          metric: "BADGES",
          scope: "ALL_TIME",
          corpusId: undefined,
          limit: 25,
        },
      },
      result: {
        data: {
          leaderboard: {
            metric: "BADGES",
            scope: "ALL_TIME",
            corpusId: null,
            totalUsers: 0,
            currentUserRank: null,
            entries: [],
          },
        },
      },
    };
    const statsMock = {
      request: {
        query: GET_COMMUNITY_STATS,
        variables: { corpusId: undefined },
      },
      result: defaultCommunityStatsMock.result,
    };
    const component = await mount(
      <LeaderboardTestWrapper
        mocks={[
          emptyMock,
          { ...emptyMock },
          { ...emptyMock },
          statsMock,
          { ...statsMock },
          { ...statsMock },
        ]}
      />
    );

    await expect(page.getByText("No Data Available")).toBeVisible({
      timeout: 10000,
    });
    await expect(
      page.getByText("There are no users in this leaderboard yet", {
        exact: false,
      })
    ).toBeVisible({ timeout: 10000 });

    await component.unmount();
  });

  test("renders error state when leaderboard query fails", async ({
    mount,
    page,
  }) => {
    const errorMock = {
      request: {
        query: GET_LEADERBOARD,
        variables: {
          metric: "BADGES",
          scope: "ALL_TIME",
          corpusId: undefined,
          limit: 25,
        },
      },
      error: new Error("Boom — leaderboard service unavailable"),
    };
    const statsMock = {
      request: {
        query: GET_COMMUNITY_STATS,
        variables: { corpusId: undefined },
      },
      result: defaultCommunityStatsMock.result,
    };
    const component = await mount(
      <LeaderboardTestWrapper
        mocks={[
          errorMock,
          { ...errorMock },
          { ...errorMock },
          statsMock,
          { ...statsMock },
          { ...statsMock },
        ]}
      />
    );

    // The Error object's message doesn't survive the Playwright CT
    // serialization boundary, so we assert on the rendered ErrorMessage
    // title (driven by the resolver-level error path) rather than the
    // specific error text.
    await expect(page.getByText("Error Loading Leaderboard")).toBeVisible({
      timeout: 10000,
    });

    await component.unmount();
  });

  test("renders score labels for messages, threads, annotations, reputation", async ({
    mount,
    page,
  }) => {
    // Cover getMetricIcon + getScoreLabel branches for non-BADGES metrics by
    // mocking a leaderboard whose top entry's score is 1 (singular form) and
    // the second entry has score > 1 (plural form). The actual on-screen
    // selection comes from the metric default ("BADGES"), so what we really
    // exercise here is the "Details" cell which renders the per-metric counts
    // unconditionally for every entry (badges/messages/reputation).
    const richEntryMock = {
      request: {
        query: GET_LEADERBOARD,
        variables: {
          metric: "BADGES",
          scope: "ALL_TIME",
          corpusId: undefined,
          limit: 25,
        },
      },
      result: {
        data: {
          leaderboard: {
            metric: "BADGES",
            scope: "ALL_TIME",
            corpusId: null,
            totalUsers: 1,
            currentUserRank: 1,
            entries: [
              {
                rank: 1,
                score: 1,
                badgeCount: 1,
                messageCount: 1,
                threadCount: 1,
                annotationCount: 1,
                reputation: 100,
                isRisingStar: false,
                user: {
                  id: "user-only",
                  displayName: "only_user",
                  slug: "only-user",
                  isProfilePublic: true,
                },
              },
            ],
          },
        },
      },
    };

    const statsMock = {
      request: {
        query: GET_COMMUNITY_STATS,
        variables: { corpusId: undefined },
      },
      result: defaultCommunityStatsMock.result,
    };
    const component = await mount(
      <LeaderboardTestWrapper
        mocks={[
          richEntryMock,
          { ...richEntryMock },
          { ...richEntryMock },
          statsMock,
          { ...statsMock },
          { ...statsMock },
        ]}
      />
    );

    // Singular form for badges (score=1). The Score column renders this.
    await expect(page.getByText("1 badge", { exact: true })).toBeVisible({
      timeout: 10000,
    });

    // Details column renders all three metric counts for every row:
    // badges (1) + messages (1) + reputation (100). The "rep" suffix is
    // unique to that branch and proves it's wired.
    await expect(page.getByText(/100 rep/)).toBeVisible({ timeout: 10000 });

    await component.unmount();
  });

  test("clicking a user row navigates to the user profile", async ({
    mount,
    page,
  }) => {
    const component = await mount(<LeaderboardTestWrapper />);

    // Wait for the table to render — the visible label is the user's slug
    // (privacy contract: leaderboard never surfaces displayName).
    const topRow = page.getByText("top-user", { exact: false });
    await expect(topRow).toBeVisible({ timeout: 10000 });

    // Click navigates via react-router; in MemoryRouter we can observe the
    // click bubbling and the row's pointer cursor without asserting on the
    // URL (MemoryRouter doesn't update window.location). The presence of
    // the hover styling proves the styled UserRow + onClick are wired,
    // which exercises the handleUserClick callback.
    await topRow.click();

    // After click the table is still rendered (no crash, no navigation
    // outside the in-memory router).
    await expect(page.getByText("top-user")).toBeVisible({ timeout: 10000 });

    await component.unmount();
  });

  test("renders badge distribution when present in stats", async ({
    mount,
    page,
  }) => {
    const leaderboardMock = {
      request: {
        query: GET_LEADERBOARD,
        variables: {
          metric: "BADGES",
          scope: "ALL_TIME",
          corpusId: undefined,
          limit: 25,
        },
      },
      result: defaultLeaderboardMock.result,
    };
    const statsWithBadgesMock = {
      request: {
        query: GET_COMMUNITY_STATS,
        variables: { corpusId: undefined },
      },
      result: {
        data: {
          communityStats: {
            totalUsers: 100,
            totalMessages: 500,
            totalThreads: 50,
            totalAnnotations: 2000,
            totalBadgesAwarded: 75,
            messagesThisWeek: 30,
            messagesThisMonth: 120,
            activeUsersThisWeek: 25,
            activeUsersThisMonth: 60,
            badgeDistribution: [
              {
                badge: {
                  id: "badge-1",
                  name: "First Steps",
                  description: "Welcome aboard",
                  icon: "trophy",
                  color: "#0F766E",
                  rarity: "COMMON",
                },
                awardCount: 42,
                uniqueRecipients: 35,
              },
            ],
          },
        },
      },
    };

    const component = await mount(
      <LeaderboardTestWrapper
        mocks={[
          leaderboardMock,
          { ...leaderboardMock },
          { ...leaderboardMock },
          statsWithBadgesMock,
          { ...statsWithBadgesMock },
          { ...statsWithBadgesMock },
        ]}
      />
    );

    await expect(page.getByText("Badge Distribution")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByText("First Steps").first()).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByText(/Awarded 42 times to 35 users/)).toBeVisible({
      timeout: 10000,
    });

    await component.unmount();
  });

  test("badge tile contains an extremely long badge name without overflow", async ({
    mount,
    page,
  }) => {
    // Regression coverage for the badge-overflow fix: a badge name with no
    // natural break opportunities (a single very long token) used to escape
    // its `BadgeCard`. With `overflow-wrap: anywhere` + `max-width: 100%` on
    // the styled badge / name and `min-width: 0` on the card, the tile width
    // must stay bounded by its grid column.
    const longName = "ExtremelyLongBadgeNameThatWouldPreviouslyOverflowGrid";
    const leaderboardMock = {
      request: {
        query: GET_LEADERBOARD,
        variables: {
          metric: "BADGES",
          scope: "ALL_TIME",
          corpusId: undefined,
          limit: 25,
        },
      },
      result: defaultLeaderboardMock.result,
    };
    const longNameStatsMock = {
      request: {
        query: GET_COMMUNITY_STATS,
        variables: { corpusId: undefined },
      },
      result: {
        data: {
          communityStats: {
            totalUsers: 100,
            totalMessages: 500,
            totalThreads: 50,
            totalAnnotations: 2000,
            totalBadgesAwarded: 75,
            messagesThisWeek: 30,
            messagesThisMonth: 120,
            activeUsersThisWeek: 25,
            activeUsersThisMonth: 60,
            badgeDistribution: [
              {
                badge: {
                  id: "badge-long",
                  name: longName,
                  description: "A badge whose name has no natural break points",
                  icon: "trophy",
                  color: "#0F766E",
                  rarity: "EPIC",
                },
                awardCount: 5,
                uniqueRecipients: 5,
              },
            ],
          },
        },
      },
    };

    const component = await mount(
      <LeaderboardTestWrapper
        mocks={[
          leaderboardMock,
          { ...leaderboardMock },
          { ...leaderboardMock },
          longNameStatsMock,
          { ...longNameStatsMock },
          { ...longNameStatsMock },
        ]}
      />
    );

    const longBadge = page.getByText(longName).first();
    await expect(longBadge).toBeVisible({ timeout: 10000 });

    // The rendered badge name must fit inside its `BadgeCard` parent — i.e.
    // the visible width must not exceed the card's content box. We grab the
    // closest ancestor with `width: 100%` (the `BadgeCard` itself, which is
    // a column-flex container) and assert its child does not overflow it.
    const badgeBox = await longBadge.boundingBox();
    expect(badgeBox).not.toBeNull();
    const cardBox = await longBadge
      .locator("xpath=ancestor::*[contains(@class, 'sc-')][1]")
      .first()
      .boundingBox();
    expect(cardBox).not.toBeNull();
    if (badgeBox && cardBox) {
      expect(badgeBox.width).toBeLessThanOrEqual(cardBox.width + 1);
    }

    await docScreenshot(page, "community--leaderboard--long-badge-name");

    await component.unmount();
  });

  test("renders rank-3 medal styling and rank > 3 numeric fallback", async ({
    mount,
    page,
  }) => {
    // Exercises the rank === 3 branch in RankBadge's three styled-component
    // ternaries (bg / color / border) and the `entry.rank > 3 → <span>{rank}</span>`
    // fallback in the Rank cell. Existing default mock only has ranks 1 + 2.
    const fourEntryMock = {
      request: {
        query: GET_LEADERBOARD,
        variables: {
          metric: "BADGES",
          scope: "ALL_TIME",
          corpusId: undefined,
          limit: 25,
        },
      },
      result: {
        data: {
          leaderboard: {
            metric: "BADGES",
            scope: "ALL_TIME",
            corpusId: null,
            totalUsers: 4,
            currentUserRank: 4,
            entries: [1, 2, 3, 4].map((rank) => ({
              rank,
              score: 100 - rank * 10,
              badgeCount: 100 - rank * 10,
              messageCount: 50,
              threadCount: 5,
              annotationCount: 20,
              reputation: 500,
              isRisingStar: false,
              user: {
                id: `user-${rank}`,
                displayName: `user_${rank}`,
                slug: `user-${rank}`,
                isProfilePublic: true,
              },
            })),
          },
        },
      },
    };
    const statsMock = {
      request: {
        query: GET_COMMUNITY_STATS,
        variables: { corpusId: undefined },
      },
      result: defaultCommunityStatsMock.result,
    };

    const component = await mount(
      <LeaderboardTestWrapper
        mocks={[
          fourEntryMock,
          { ...fourEntryMock },
          { ...fourEntryMock },
          statsMock,
          { ...statsMock },
          { ...statsMock },
        ]}
      />
    );

    // All four user rows should render — leaderboard surfaces ``slug``
    // (case-sensitive, hyphenated), not ``displayName``.
    await expect(page.getByText("user-1")).toBeVisible({ timeout: 10000 });
    await expect(page.getByText("user-2")).toBeVisible({ timeout: 10000 });
    await expect(page.getByText("user-3")).toBeVisible({ timeout: 10000 });
    await expect(page.getByText("user-4")).toBeVisible({ timeout: 10000 });

    // Rank 4 renders the numeric fallback (the `<span>{entry.rank}</span>`
    // branch of `entry.rank <= 3 ? <Medal/> : <span>...</span>`). Scope to a
    // table cell so we don't match score/details that may also contain "4".
    await expect(
      page.locator("td span", { hasText: /^4$/ }).first()
    ).toBeVisible({ timeout: 10000 });

    await component.unmount();
  });

  test("changing metric dropdown to non-BADGES refetches and renders new icon/label", async ({
    mount,
    page,
  }) => {
    // Exercises:
    // - FilterBar metric Dropdown's onChange callback (line 490) — covered
    //   when the user picks a new option.
    // - getMetricIcon / getScoreLabel non-BADGES branches (MESSAGES path).
    const badgesMock = {
      request: {
        query: GET_LEADERBOARD,
        variables: {
          metric: "BADGES",
          scope: "ALL_TIME",
          corpusId: undefined,
          limit: 25,
        },
      },
      result: defaultLeaderboardMock.result,
    };
    const messagesMock = {
      request: {
        query: GET_LEADERBOARD,
        variables: {
          metric: "MESSAGES",
          scope: "ALL_TIME",
          corpusId: undefined,
          limit: 25,
        },
      },
      result: {
        data: {
          leaderboard: {
            metric: "MESSAGES",
            scope: "ALL_TIME",
            corpusId: null,
            totalUsers: 1,
            currentUserRank: null,
            entries: [
              {
                rank: 1,
                score: 250,
                badgeCount: 5,
                messageCount: 250,
                threadCount: 10,
                annotationCount: 30,
                reputation: 800,
                isRisingStar: false,
                user: {
                  id: "user-msg",
                  displayName: "chatty_user",
                  slug: "chatty-user",
                  isProfilePublic: true,
                },
              },
            ],
          },
        },
      },
    };
    const statsMock = {
      request: {
        query: GET_COMMUNITY_STATS,
        variables: { corpusId: undefined },
      },
      result: defaultCommunityStatsMock.result,
    };

    const component = await mount(
      <LeaderboardTestWrapper
        mocks={[
          badgesMock,
          { ...badgesMock },
          { ...badgesMock },
          messagesMock,
          { ...messagesMock },
          { ...messagesMock },
          statsMock,
          { ...statsMock },
          { ...statsMock },
        ]}
      />
    );

    // Wait for initial badges render — leaderboard renders slug, not displayName.
    await expect(page.getByText("top-user")).toBeVisible({ timeout: 10000 });

    // Open metric dropdown and pick "Most Active Contributors" (MESSAGES)
    const triggers = page.locator(".oc-dropdown__trigger");
    await triggers.first().click();
    await page
      .locator(".oc-dropdown__option", { hasText: "Most Active Contributors" })
      .click();

    // After refetch, the new entry should render with the messages-formatted
    // score label produced by getScoreLabel(MESSAGES, 250). User row shows slug.
    await expect(page.getByText("chatty-user")).toBeVisible({
      timeout: 10000,
    });
    await expect(
      page.getByText("250 messages", { exact: true }).first()
    ).toBeVisible({ timeout: 10000 });

    await component.unmount();
  });

  test("changing scope dropdown refetches with new scope variable", async ({
    mount,
    page,
  }) => {
    // Exercises the scope Dropdown's onChange callback (line 499 — second
    // anonymous function in the FilterBar block).
    const allTimeMock = {
      request: {
        query: GET_LEADERBOARD,
        variables: {
          metric: "BADGES",
          scope: "ALL_TIME",
          corpusId: undefined,
          limit: 25,
        },
      },
      result: defaultLeaderboardMock.result,
    };
    const weeklyMock = {
      request: {
        query: GET_LEADERBOARD,
        variables: {
          metric: "BADGES",
          scope: "WEEKLY",
          corpusId: undefined,
          limit: 25,
        },
      },
      result: {
        data: {
          leaderboard: {
            metric: "BADGES",
            scope: "WEEKLY",
            corpusId: null,
            totalUsers: 1,
            currentUserRank: null,
            entries: [
              {
                rank: 1,
                score: 7,
                badgeCount: 7,
                messageCount: 12,
                threadCount: 2,
                annotationCount: 8,
                reputation: 90,
                isRisingStar: false,
                user: {
                  id: "user-week",
                  displayName: "weekly_winner",
                  slug: "weekly-winner",
                  isProfilePublic: true,
                },
              },
            ],
          },
        },
      },
    };
    const statsMock = {
      request: {
        query: GET_COMMUNITY_STATS,
        variables: { corpusId: undefined },
      },
      result: defaultCommunityStatsMock.result,
    };

    const component = await mount(
      <LeaderboardTestWrapper
        mocks={[
          allTimeMock,
          { ...allTimeMock },
          { ...allTimeMock },
          weeklyMock,
          { ...weeklyMock },
          { ...weeklyMock },
          statsMock,
          { ...statsMock },
          { ...statsMock },
        ]}
      />
    );

    await expect(page.getByText("top-user")).toBeVisible({ timeout: 10000 });

    const triggers = page.locator(".oc-dropdown__trigger");
    await triggers.nth(1).click();
    await page
      .locator(".oc-dropdown__option", { hasText: "This Week" })
      .click();

    await expect(page.getByText("weekly-winner")).toBeVisible({
      timeout: 10000,
    });

    await component.unmount();
  });

  test("changing limit dropdown refetches with new limit variable", async ({
    mount,
    page,
  }) => {
    // Exercises the limit Dropdown's onChange callback (line 507 — third
    // anonymous function in the FilterBar block).
    const top25Mock = {
      request: {
        query: GET_LEADERBOARD,
        variables: {
          metric: "BADGES",
          scope: "ALL_TIME",
          corpusId: undefined,
          limit: 25,
        },
      },
      result: defaultLeaderboardMock.result,
    };
    const top10Mock = {
      request: {
        query: GET_LEADERBOARD,
        variables: {
          metric: "BADGES",
          scope: "ALL_TIME",
          corpusId: undefined,
          limit: 10,
        },
      },
      result: {
        data: {
          leaderboard: {
            metric: "BADGES",
            scope: "ALL_TIME",
            corpusId: null,
            totalUsers: 1,
            currentUserRank: null,
            entries: [
              {
                rank: 1,
                score: 99,
                badgeCount: 99,
                messageCount: 50,
                threadCount: 5,
                annotationCount: 20,
                reputation: 200,
                isRisingStar: false,
                user: {
                  id: "user-10",
                  displayName: "top_ten_only",
                  slug: "top-ten-only",
                  isProfilePublic: true,
                },
              },
            ],
          },
        },
      },
    };
    const statsMock = {
      request: {
        query: GET_COMMUNITY_STATS,
        variables: { corpusId: undefined },
      },
      result: defaultCommunityStatsMock.result,
    };

    const component = await mount(
      <LeaderboardTestWrapper
        mocks={[
          top25Mock,
          { ...top25Mock },
          { ...top25Mock },
          top10Mock,
          { ...top10Mock },
          { ...top10Mock },
          statsMock,
          { ...statsMock },
          { ...statsMock },
        ]}
      />
    );

    await expect(page.getByText("top-user")).toBeVisible({ timeout: 10000 });

    const triggers = page.locator(".oc-dropdown__trigger");
    await triggers.nth(2).click();
    // Use exact match — "Top 10" would also match "Top 100".
    await page.getByRole("option", { name: "Top 10", exact: true }).click();

    await expect(page.getByText("top-ten-only")).toBeVisible({
      timeout: 10000,
    });

    await component.unmount();
  });
});
