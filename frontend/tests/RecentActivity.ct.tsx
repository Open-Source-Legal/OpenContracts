import React from "react";
import { test, expect } from "@playwright/experimental-ct-react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { gql } from "@apollo/client";
import { RecentActivity } from "../src/components/profile/RecentActivity";
import { docScreenshot } from "./utils/docScreenshot";

const GET_RECENT_ACTIVITY = gql`
  query GetRecentActivity($userId: ID!) {
    userMessages(creatorId: $userId, first: 5, msgType: "HUMAN") {
      id
      content
      created
      conversation {
        id
        title
      }
    }
  }
`;

const mockMessages = [
  {
    id: "msg-1",
    content: "This is a test message about contract review",
    created: new Date(Date.now() - 3600000).toISOString(),
    conversation: { id: "conv-1", title: "Contract Review Thread" },
  },
  {
    id: "msg-2",
    content: "Another message discussing document annotations",
    created: new Date(Date.now() - 7200000).toISOString(),
    conversation: { id: "conv-2", title: "Annotation Discussion" },
  },
];

test.describe("RecentActivity", () => {
  test("renders loading state with spinner", async ({ mount, page }) => {
    const mocks: MockedResponse[] = [
      {
        request: {
          query: GET_RECENT_ACTIVITY,
          variables: { userId: "user-1" },
        },
        delay: 5000,
        result: {
          data: { userMessages: mockMessages },
        },
      },
    ];

    const component = await mount(
      <MockedProvider mocks={mocks} addTypename={false}>
        <RecentActivity userId="user-1" />
      </MockedProvider>
    );

    // Should show spinner while loading
    await expect(
      page.locator('[class*="spinner"], [role="status"]')
    ).toBeVisible({
      timeout: 5000,
    });

    await docScreenshot(page, "profile--recent-activity--loading", {
      element: component,
    });

    await component.unmount();
  });

  test("renders activity list with messages", async ({ mount, page }) => {
    const mocks: MockedResponse[] = [
      {
        request: {
          query: GET_RECENT_ACTIVITY,
          variables: { userId: "user-1" },
        },
        result: {
          data: { userMessages: mockMessages },
        },
      },
    ];

    const component = await mount(
      <MockedProvider mocks={mocks} addTypename={false}>
        <RecentActivity userId="user-1" />
      </MockedProvider>
    );

    // Wait for data to load
    await expect(page.locator("text=Contract Review Thread")).toBeVisible({
      timeout: 10000,
    });

    // Check both messages render
    await expect(page.locator("text=Contract Review Thread")).toBeVisible();
    await expect(page.locator("text=Annotation Discussion")).toBeVisible();
    await expect(
      page.locator("text=This is a test message about contract review")
    ).toBeVisible();

    await docScreenshot(page, "profile--recent-activity--with-data", {
      element: component,
    });

    await component.unmount();
  });

  test("renders empty state when no messages", async ({ mount, page }) => {
    const mocks: MockedResponse[] = [
      {
        request: {
          query: GET_RECENT_ACTIVITY,
          variables: { userId: "user-1" },
        },
        result: {
          data: { userMessages: [] },
        },
      },
    ];

    const component = await mount(
      <MockedProvider mocks={mocks} addTypename={false}>
        <RecentActivity userId="user-1" />
      </MockedProvider>
    );

    await expect(
      page.locator("text=No recent activity to display")
    ).toBeVisible({ timeout: 10000 });

    await docScreenshot(page, "profile--recent-activity--empty", {
      element: component,
    });

    await component.unmount();
  });

  test("renders error state on query failure", async ({ mount, page }) => {
    const mocks: MockedResponse[] = [
      {
        request: {
          query: GET_RECENT_ACTIVITY,
          variables: { userId: "user-1" },
        },
        error: new Error("Network error"),
      },
    ];

    const component = await mount(
      <MockedProvider mocks={mocks} addTypename={false}>
        <RecentActivity userId="user-1" />
      </MockedProvider>
    );

    await expect(page.locator("text=Error loading activity")).toBeVisible({
      timeout: 10000,
    });

    await docScreenshot(page, "profile--recent-activity--error", {
      element: component,
    });

    await component.unmount();
  });
});
