/**
 * Additional Playwright Component Tests for ModerationDashboard.
 *
 * Supplements ModerationDashboard.ct.tsx with coverage for the mutation
 * success path, filter interactions, pagination, loading/error states,
 * and the System (no moderator) branch.
 *
 * Related to issue #1286 — coverage target ≥60%.
 */

import React from "react";
import { test, expect } from "./utils/coverage";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { MemoryRouter } from "react-router-dom";
import { ModerationDashboard } from "../src/components/moderation/ModerationDashboard";
import {
  GET_MODERATION_ACTIONS,
  GET_MODERATION_METRICS,
} from "../src/graphql/queries";
import { ROLLBACK_MODERATION_ACTION } from "../src/graphql/mutations";

const CORPUS_ID = "Q29ycHVzVHlwZToxMjM=";

// ──────────────────────────────────────────────────────────────────────────────
// MOCK DATA
// ──────────────────────────────────────────────────────────────────────────────

const manualAction = {
  id: "TW9kZXJhdGlvbkFjdGlvblR5cGU6MQ==",
  actionType: "LOCK_THREAD",
  reason: "Spam content detected",
  created: new Date().toISOString(),
  canRollback: true,
  isAutomated: false,
  corpusId: CORPUS_ID,
  conversation: {
    id: "Q29udmVyc2F0aW9uVHlwZTox",
    title: "Spam Thread",
  },
  message: null,
  moderator: {
    id: "VXNlclR5cGU6MQ==",
    username: "alice_mod",
  },
};

const systemAction = {
  id: "TW9kZXJhdGlvbkFjdGlvblR5cGU6Mg==",
  actionType: "DELETE_MESSAGE",
  reason: null, // exercises the "No reason provided" branch
  created: new Date(Date.now() - 3600000).toISOString(),
  canRollback: true,
  isAutomated: true,
  corpusId: CORPUS_ID,
  conversation: {
    id: "Q29udmVyc2F0aW9uVHlwZToy",
    title: "Auto Mod Thread",
  },
  message: {
    id: "TWVzc2FnZVR5cGU6MQ==",
    content: "This message was flagged by an automated moderation rule.",
  },
  moderator: null, // exercises the "System" branch
};

const baseActionsData = (opts?: {
  hasNextPage?: boolean;
  edges?: { cursor: string; node: typeof manualAction }[];
}) => ({
  moderationActions: {
    pageInfo: {
      hasNextPage: opts?.hasNextPage ?? false,
      hasPreviousPage: false,
      startCursor: null,
      endCursor: opts?.hasNextPage ? "cursor-1" : null,
    },
    edges:
      opts?.edges ??
      ([
        { cursor: manualAction.id, node: manualAction },
        { cursor: systemAction.id, node: systemAction as any },
      ] as any),
  },
});

const metricsData = {
  moderationMetrics: {
    totalActions: 15,
    automatedActions: 8,
    manualActions: 7,
    actionsByType: {},
    hourlyActionRate: 2.5,
    isAboveThreshold: false,
    thresholdExceededTypes: [],
    timeRangeHours: 24,
    startTime: new Date(Date.now() - 86400000).toISOString(),
    endTime: new Date().toISOString(),
  },
};

// ──────────────────────────────────────────────────────────────────────────────
// MOCK FACTORIES
// ──────────────────────────────────────────────────────────────────────────────

const actionsMock = (
  variables: Record<string, any>,
  data: any = baseActionsData()
): MockedResponse => ({
  request: { query: GET_MODERATION_ACTIONS, variables },
  result: { data },
});

const metricsMock = (
  variables: Record<string, any>,
  data: any = metricsData
): MockedResponse => ({
  request: { query: GET_MODERATION_METRICS, variables },
  result: { data },
});

const rollbackMock = (
  actionId: string,
  reason: string | undefined,
  success = true
): MockedResponse => ({
  request: {
    query: ROLLBACK_MODERATION_ACTION,
    variables: { actionId, reason },
  },
  result: {
    data: {
      rollbackModerationAction: {
        ok: success,
        message: success ? "Rolled back" : "Rollback failed",
        rollbackAction: null,
      },
    },
  },
});

const defaultActionsVars = { corpusId: CORPUS_ID, first: 10 };
const defaultMetricsVars = { corpusId: CORPUS_ID, timeRangeHours: 24 };

/**
 * Produce both the initial fetch + refetch copies for cache-and-network
 * fetch policy. Cache-and-network can trigger a background refetch on mount.
 */
const baselineMocks = (): MockedResponse[] => [
  actionsMock(defaultActionsVars),
  metricsMock(defaultMetricsVars),
  actionsMock(defaultActionsVars),
  metricsMock(defaultMetricsVars),
];

const mountDashboard = (mount: any, mocks: MockedResponse[]) =>
  mount(
    <MemoryRouter>
      <MockedProvider mocks={mocks} addTypename={false}>
        <ModerationDashboard
          corpusId={CORPUS_ID}
          corpusTitle="Coverage Corpus"
        />
      </MockedProvider>
    </MemoryRouter>
  );

// ──────────────────────────────────────────────────────────────────────────────
// TESTS
// ──────────────────────────────────────────────────────────────────────────────

test.describe("ModerationDashboard – coverage", () => {
  test(
    "submits rollback mutation with entered reason",
    { timeout: 25000 },
    async ({ mount, page }) => {
      const mocks: MockedResponse[] = [
        ...baselineMocks(),
        rollbackMock(manualAction.id, "Was a false positive"),
        // Refetch after successful rollback
        actionsMock(defaultActionsVars),
        metricsMock(defaultMetricsVars),
      ];

      await mountDashboard(mount, mocks);

      await expect(page.getByRole("table")).toBeVisible({ timeout: 15000 });
      await page
        .getByRole("button", { name: /Rollback/i })
        .first()
        .click();

      await expect(page.getByText("Confirm Rollback")).toBeVisible();
      await page
        .getByPlaceholder("Enter a reason for this rollback...")
        .fill("Was a false positive");

      // Use the primary action inside the modal footer.
      await page
        .getByRole("button", { name: /^Rollback$/ })
        .last()
        .click();

      // Modal should close on successful mutation completion.
      await expect(page.getByText("Confirm Rollback")).not.toBeVisible({
        timeout: 10000,
      });
    }
  );

  test(
    "renders System label when moderator is absent and 'No reason provided' fallback",
    { timeout: 20000 },
    async ({ mount, page }) => {
      await mountDashboard(mount, baselineMocks());

      await expect(page.getByRole("table")).toBeVisible({ timeout: 15000 });
      await expect(page.getByText("Auto Mod Thread")).toBeVisible();
      await expect(page.getByText(/System/).first()).toBeVisible();
      await expect(page.getByText("No reason provided")).toBeVisible();
    }
  );

  test(
    "action type filter triggers a refetch with actionTypes",
    { timeout: 25000 },
    async ({ mount, page }) => {
      const filteredData = baseActionsData({
        edges: [{ cursor: manualAction.id, node: manualAction }],
      });

      const mocks: MockedResponse[] = [
        ...baselineMocks(),
        actionsMock(
          { ...defaultActionsVars, actionTypes: ["lock_thread"] },
          filteredData
        ),
      ];

      await mountDashboard(mount, mocks);
      await expect(page.getByRole("table")).toBeVisible({ timeout: 15000 });

      // Find the Action Type dropdown (first, non-time dropdown).
      const actionTypeDropdown = page
        .locator(".oc-dropdown")
        .filter({ hasText: /All Actions/i })
        .first();
      await actionTypeDropdown.click();
      await page.getByText("Lock Thread", { exact: true }).first().click();

      // The spam thread (a LOCK_THREAD action) remains; the auto-mod thread
      // (DELETE_MESSAGE) no longer shows.
      await expect(page.getByText("Spam Thread")).toBeVisible({
        timeout: 10000,
      });
      await expect(page.getByText("Auto Mod Thread")).not.toBeVisible();
    }
  );

  test(
    "automated-only toggle refetches with automatedOnly=true",
    { timeout: 25000 },
    async ({ mount, page }) => {
      const automatedOnlyData = baseActionsData({
        edges: [{ cursor: systemAction.id, node: systemAction as any }],
      });

      const mocks: MockedResponse[] = [
        ...baselineMocks(),
        actionsMock(
          { ...defaultActionsVars, automatedOnly: true },
          automatedOnlyData
        ),
      ];

      await mountDashboard(mount, mocks);
      await expect(page.getByRole("table")).toBeVisible({ timeout: 15000 });

      await page.getByRole("checkbox").check();

      await expect(page.getByText("Auto Mod Thread")).toBeVisible({
        timeout: 10000,
      });
      await expect(page.getByText("Spam Thread")).not.toBeVisible();
    }
  );

  test(
    "time range change refetches metrics with new timeRangeHours",
    { timeout: 25000 },
    async ({ mount, page }) => {
      const newMetrics = {
        moderationMetrics: {
          ...metricsData.moderationMetrics,
          totalActions: 42,
          timeRangeHours: 168,
        },
      };

      const mocks: MockedResponse[] = [
        ...baselineMocks(),
        metricsMock({ corpusId: CORPUS_ID, timeRangeHours: 168 }, newMetrics),
      ];

      await mountDashboard(mount, mocks);
      await expect(page.getByText("Moderation Metrics")).toBeVisible({
        timeout: 15000,
      });

      // Open the 24-hours dropdown and pick 7 days.
      const timeDropdown = page
        .locator(".oc-dropdown")
        .filter({ hasText: "Last 24 hours" })
        .first();
      await timeDropdown.click();
      await page.getByText("Last 7 days").first().click();

      // 42 appears in the total-actions StatBlock after the refetch resolves.
      await expect(
        page.locator(".oc-stat-block").filter({ hasText: "42" })
      ).toBeVisible({
        timeout: 10000,
      });
    }
  );

  test(
    "Load More button calls fetchMore and appends the next page",
    { timeout: 25000 },
    async ({ mount, page }) => {
      const extraAction = {
        ...manualAction,
        id: "TW9kZXJhdGlvbkFjdGlvblR5cGU6MTA=",
        conversation: {
          id: "Q29udmVyc2F0aW9uVHlwZToxMA==",
          title: "Second Page Thread",
        },
        reason: "Second page action",
      };

      const firstPage = baseActionsData({
        hasNextPage: true,
        edges: [{ cursor: manualAction.id, node: manualAction }],
      });

      const secondPage = {
        moderationActions: {
          pageInfo: {
            hasNextPage: false,
            hasPreviousPage: true,
            startCursor: null,
            endCursor: null,
          },
          edges: [{ cursor: extraAction.id, node: extraAction }],
        },
      };

      const mocks: MockedResponse[] = [
        actionsMock(defaultActionsVars, firstPage),
        metricsMock(defaultMetricsVars),
        actionsMock(defaultActionsVars, firstPage),
        metricsMock(defaultMetricsVars),
        actionsMock({ ...defaultActionsVars, after: "cursor-1" }, secondPage),
      ];

      await mountDashboard(mount, mocks);
      await expect(page.getByText("Spam Thread")).toBeVisible({
        timeout: 15000,
      });

      const loadMore = page.getByRole("button", { name: /Load More/i });
      await expect(loadMore).toBeVisible();
      await loadMore.click();

      await expect(page.getByText("Second Page Thread")).toBeVisible({
        timeout: 10000,
      });
    }
  );

  test(
    "shows error state when actions query fails",
    { timeout: 20000 },
    async ({ mount, page }) => {
      const mocks: MockedResponse[] = [
        {
          request: {
            query: GET_MODERATION_ACTIONS,
            variables: defaultActionsVars,
          },
          error: new Error("network exploded"),
        },
        metricsMock(defaultMetricsVars),
      ];

      await mountDashboard(mount, mocks);

      await expect(page.getByText(/Error loading actions/i)).toBeVisible({
        timeout: 15000,
      });
    }
  );

  test(
    "shows metrics error state separately",
    { timeout: 20000 },
    async ({ mount, page }) => {
      const mocks: MockedResponse[] = [
        actionsMock(defaultActionsVars),
        {
          request: {
            query: GET_MODERATION_METRICS,
            variables: defaultMetricsVars,
          },
          error: new Error("metrics down"),
        },
      ];

      await mountDashboard(mount, mocks);

      await expect(page.getByText(/Error loading metrics/i)).toBeVisible({
        timeout: 15000,
      });
    }
  );

  test(
    "cancel button on rollback modal closes without firing mutation",
    { timeout: 20000 },
    async ({ mount, page }) => {
      await mountDashboard(mount, baselineMocks());

      await expect(page.getByRole("table")).toBeVisible({ timeout: 15000 });
      await page
        .getByRole("button", { name: /Rollback/i })
        .first()
        .click();

      await expect(page.getByText("Confirm Rollback")).toBeVisible();
      await page.getByRole("button", { name: /^Cancel$/ }).click();
      await expect(page.getByText("Confirm Rollback")).not.toBeVisible();
    }
  );
});
