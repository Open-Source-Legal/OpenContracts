import React from "react";
import { test, expect } from "./utils/coverage";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { MemoryRouter } from "react-router-dom";
import { ModerationDashboard } from "../src/components/moderation/ModerationDashboard";
import {
  GET_MODERATION_ACTIONS,
  GET_MODERATION_METRICS,
} from "../src/graphql/queries";
import { docScreenshot } from "./utils/docScreenshot";

/* -------------------------------------------------------------------------- */
/* Mock Data                                                                   */
/* -------------------------------------------------------------------------- */
const CORPUS_ID = "Q29ycHVzVHlwZToxMjM="; // Base64 encoded CorpusType:123

const mockModerationAction = {
  id: "TW9kZXJhdGlvbkFjdGlvblR5cGU6MQ==",
  actionType: "LOCK_THREAD",
  reason: "Spam content detected",
  created: new Date().toISOString(),
  canRollback: true,
  isAutomated: false,
  corpusId: CORPUS_ID,
  conversation: {
    id: "Q29udmVyc2F0aW9uVHlwZTox",
    title: "Test Thread",
  },
  message: null,
  moderator: {
    id: "VXNlclR5cGU6MQ==",
    slug: "moderator-user",
  },
};

const mockAutomatedAction = {
  id: "TW9kZXJhdGlvbkFjdGlvblR5cGU6Mg==",
  actionType: "DELETE_MESSAGE",
  reason: "Automated moderation",
  created: new Date(Date.now() - 3600000).toISOString(), // 1 hour ago
  canRollback: true,
  isAutomated: true,
  corpusId: CORPUS_ID,
  conversation: {
    id: "Q29udmVyc2F0aW9uVHlwZToy",
    title: "Another Thread",
  },
  message: {
    id: "TWVzc2FnZVR5cGU6MQ==",
    content: "This message was deleted for violating community guidelines...",
  },
  moderator: null,
};

const actionsData = {
  moderationActions: {
    pageInfo: {
      hasNextPage: false,
      hasPreviousPage: false,
      startCursor: null,
      endCursor: null,
    },
    edges: [
      {
        cursor: mockModerationAction.id,
        node: mockModerationAction,
      },
      {
        cursor: mockAutomatedAction.id,
        node: mockAutomatedAction,
      },
    ],
  },
};

const metricsData = {
  moderationMetrics: {
    totalActions: 15,
    automatedActions: 8,
    manualActions: 7,
    actionsByType: {
      lock_thread: 5,
      delete_message: 6,
      pin_thread: 4,
    },
    hourlyActionRate: 2.5,
    isAboveThreshold: false,
    thresholdExceededTypes: [],
    timeRangeHours: 24,
    startTime: new Date(Date.now() - 86400000).toISOString(),
    endTime: new Date().toISOString(),
  },
};

const metricsWithWarningData = {
  moderationMetrics: {
    ...metricsData.moderationMetrics,
    totalActions: 100,
    isAboveThreshold: true,
    thresholdExceededTypes: ["delete_message", "lock_thread"],
  },
};

const emptyActionsData = {
  moderationActions: {
    pageInfo: {
      hasNextPage: false,
      hasPreviousPage: false,
      startCursor: null,
      endCursor: null,
    },
    edges: [],
  },
};

// Helper to create mocks with exact variables the component will use
const createMocks = (
  actionsResult: any,
  metricsResult: any
): MockedResponse[] => [
  // Initial load with default variables
  {
    request: {
      query: GET_MODERATION_ACTIONS,
      variables: {
        corpusId: CORPUS_ID,
        first: 10,
      },
    },
    result: { data: actionsResult },
  },
  // Metrics with default 24 hours
  {
    request: {
      query: GET_MODERATION_METRICS,
      variables: {
        corpusId: CORPUS_ID,
        timeRangeHours: 24,
      },
    },
    result: { data: metricsResult },
  },
  // Additional mocks for refetches with cache-and-network
  {
    request: {
      query: GET_MODERATION_ACTIONS,
      variables: {
        corpusId: CORPUS_ID,
        first: 10,
      },
    },
    result: { data: actionsResult },
  },
  {
    request: {
      query: GET_MODERATION_METRICS,
      variables: {
        corpusId: CORPUS_ID,
        timeRangeHours: 24,
      },
    },
    result: { data: metricsResult },
  },
];

/* -------------------------------------------------------------------------- */
/* Tests                                                                       */
/* -------------------------------------------------------------------------- */

test(
  "renders moderation dashboard with header and sections",
  { timeout: 20000 },
  async ({ mount, page }) => {
    const mocks = createMocks(actionsData, metricsData);

    await mount(
      <MemoryRouter>
        <MockedProvider mocks={mocks} addTypename={false}>
          <ModerationDashboard corpusId={CORPUS_ID} corpusTitle="Test Corpus" />
        </MockedProvider>
      </MemoryRouter>
    );

    // Wait for dashboard to load
    await expect(page.getByText("Moderation Dashboard")).toBeVisible({
      timeout: 15000,
    });
    await expect(page.getByText("Test Corpus")).toBeVisible();

    // Check metrics section
    await expect(page.getByText("Moderation Metrics")).toBeVisible();

    // Check filters section
    await expect(page.getByText("Filters")).toBeVisible();

    // Check actions section
    await expect(page.getByText("Moderation Actions")).toBeVisible();

    await docScreenshot(page, "moderation--dashboard--initial");
  }
);

test(
  "displays metrics correctly",
  { timeout: 20000 },
  async ({ mount, page }) => {
    const mocks = createMocks(actionsData, metricsData);

    await mount(
      <MemoryRouter>
        <MockedProvider mocks={mocks} addTypename={false}>
          <ModerationDashboard corpusId={CORPUS_ID} />
        </MockedProvider>
      </MemoryRouter>
    );

    // Wait for metrics to load
    await expect(page.getByText("Total Actions")).toBeVisible({
      timeout: 15000,
    });

    // Check metric values — StatBlock uses @os-legal/ui with .oc-stat-block class
    const metricsSection = page
      .locator("div")
      .filter({ hasText: "Moderation Metrics" })
      .first();
    await expect(
      metricsSection.locator(".oc-stat-block").filter({ hasText: "15" })
    ).toBeVisible();
    await expect(metricsSection.getByText("Manual")).toBeVisible();
    await expect(metricsSection.getByText("Actions/Hour")).toBeVisible();
  }
);

test(
  "displays warning when threshold exceeded",
  { timeout: 20000 },
  async ({ mount, page }) => {
    const mocks = createMocks(actionsData, metricsWithWarningData);

    await mount(
      <MemoryRouter>
        <MockedProvider mocks={mocks} addTypename={false}>
          <ModerationDashboard corpusId={CORPUS_ID} />
        </MockedProvider>
      </MemoryRouter>
    );

    // Wait for warning message
    await expect(
      page.getByText(/High moderation activity detected/)
    ).toBeVisible({ timeout: 15000 });
    await expect(page.getByText(/delete_message/)).toBeVisible();
    await expect(page.getByText(/lock_thread/)).toBeVisible();
  }
);

test(
  "displays moderation actions in table",
  { timeout: 20000 },
  async ({ mount, page }) => {
    const mocks = createMocks(actionsData, metricsData);

    await mount(
      <MemoryRouter>
        <MockedProvider mocks={mocks} addTypename={false}>
          <ModerationDashboard corpusId={CORPUS_ID} />
        </MockedProvider>
      </MemoryRouter>
    );

    // Wait for table to load with data (wait for table row with action data)
    const table = page.getByRole("table");
    await expect(table).toBeVisible({ timeout: 15000 });

    // Wait for data to load - check for thread title which is unique to table
    await expect(page.getByText("Test Thread")).toBeVisible({ timeout: 15000 });

    // Check table headers using th elements with exact text
    await expect(table.locator("th", { hasText: /^Action$/ })).toBeVisible();
    await expect(table.locator("th", { hasText: /^Target$/ })).toBeVisible();
    await expect(table.locator("th", { hasText: /^Moderator$/ })).toBeVisible();
    await expect(table.locator("th", { hasText: /^Reason$/ })).toBeVisible();

    // Check action data - action badges use data-testid
    await expect(
      table
        .locator('[data-testid="action-badge"]')
        .filter({ hasText: "Lock Thread" })
    ).toBeVisible();
    await expect(
      table
        .locator('[data-testid="action-badge"]')
        .filter({ hasText: "Delete Message" })
    ).toBeVisible();

    // Check thread titles
    await expect(page.getByText("Another Thread")).toBeVisible();

    // Check moderator (slug is rendered cross-user; underscores are not used in slugs)
    await expect(page.getByText("moderator-user")).toBeVisible();

    // Check automated badge (span contains SVG icon + "Auto" text)
    await expect(
      table.locator("span").filter({ hasText: "Auto" }).first()
    ).toBeVisible();
  }
);

test(
  "shows rollback buttons for rollbackable actions",
  { timeout: 20000 },
  async ({ mount, page }) => {
    const mocks = createMocks(actionsData, metricsData);

    await mount(
      <MemoryRouter>
        <MockedProvider mocks={mocks} addTypename={false}>
          <ModerationDashboard corpusId={CORPUS_ID} />
        </MockedProvider>
      </MemoryRouter>
    );

    // Wait for actions to load
    await expect(page.getByRole("table")).toBeVisible({ timeout: 15000 });

    // Should have rollback buttons
    const rollbackButtons = page.getByRole("button", { name: /Rollback/i });
    await expect(rollbackButtons.first()).toBeVisible();
  }
);

test(
  "opens rollback confirmation modal",
  { timeout: 20000 },
  async ({ mount, page }) => {
    const mocks = createMocks(actionsData, metricsData);

    await mount(
      <MemoryRouter>
        <MockedProvider mocks={mocks} addTypename={false}>
          <ModerationDashboard corpusId={CORPUS_ID} />
        </MockedProvider>
      </MemoryRouter>
    );

    // Wait for table and click rollback button
    await expect(page.getByRole("table")).toBeVisible({ timeout: 15000 });
    await page
      .getByRole("button", { name: /Rollback/i })
      .first()
      .click();

    // Modal should open
    await expect(page.getByText("Confirm Rollback")).toBeVisible();
    await expect(
      page.getByText(/Are you sure you want to rollback/)
    ).toBeVisible();
    await expect(
      page.getByPlaceholder("Enter a reason for this rollback...")
    ).toBeVisible();

    // Cancel and close modal
    await page.getByRole("button", { name: "Cancel" }).click();
    await expect(page.getByText("Confirm Rollback")).not.toBeVisible();
  }
);

test(
  "shows empty state when no actions",
  { timeout: 20000 },
  async ({ mount, page }) => {
    const mocks = createMocks(emptyActionsData, metricsData);

    await mount(
      <MemoryRouter>
        <MockedProvider mocks={mocks} addTypename={false}>
          <ModerationDashboard corpusId={CORPUS_ID} />
        </MockedProvider>
      </MemoryRouter>
    );

    await expect(page.getByText("No moderation actions found")).toBeVisible({
      timeout: 15000,
    });
  }
);

test(
  "filter dropdown is visible and interactive",
  { timeout: 20000 },
  async ({ mount, page }) => {
    const mocks = createMocks(actionsData, metricsData);

    await mount(
      <MemoryRouter>
        <MockedProvider mocks={mocks} addTypename={false}>
          <ModerationDashboard corpusId={CORPUS_ID} />
        </MockedProvider>
      </MemoryRouter>
    );

    // Wait for dashboard to load
    await expect(page.getByText("Filters")).toBeVisible({ timeout: 15000 });

    // Check action type dropdown exists
    await expect(page.getByText("Action Type")).toBeVisible();

    // Check automated checkbox exists
    await expect(page.getByText("Automated actions only")).toBeVisible();
  }
);

test(
  "time range dropdown changes selection",
  { timeout: 20000 },
  async ({ mount, page }) => {
    const mocks = createMocks(actionsData, metricsData);

    await mount(
      <MemoryRouter>
        <MockedProvider mocks={mocks} addTypename={false}>
          <ModerationDashboard corpusId={CORPUS_ID} />
        </MockedProvider>
      </MemoryRouter>
    );

    // Wait for dashboard to load
    await expect(page.getByText("Moderation Metrics")).toBeVisible({
      timeout: 15000,
    });

    // Find the time range dropdown and check default
    const dropdown = page
      .locator(".oc-dropdown")
      .filter({ hasText: "Last 24 hours" })
      .first();
    await expect(dropdown).toBeVisible();

    // Click dropdown to open
    await dropdown.click();

    // Should see other options
    await expect(page.getByText("Last hour")).toBeVisible();
    await expect(page.getByText("Last 7 days")).toBeVisible();
    await expect(page.getByText("Last 30 days")).toBeVisible();

    await docScreenshot(page, "moderation--dashboard--time-filter");
  }
);
