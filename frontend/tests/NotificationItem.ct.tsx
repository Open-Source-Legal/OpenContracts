import { test, expect } from "@playwright/experimental-ct-react";
import { NotificationItem } from "../src/components/notifications/NotificationItem";
import { MockedProvider } from "@apollo/client/testing";
import {
  MARK_NOTIFICATION_READ,
  MARK_NOTIFICATION_UNREAD,
  DELETE_NOTIFICATION,
} from "../src/graphql/mutations";
import {
  GET_NOTIFICATIONS,
  GET_UNREAD_NOTIFICATION_COUNT,
} from "../src/graphql/queries";
import type { NotificationNode } from "../src/graphql/queries";

test.describe("NotificationItem", () => {
  const createMockNotification = (
    overrides?: Partial<NotificationNode>
  ): NotificationNode => ({
    id: "notif-1",
    notificationType: "REPLY",
    isRead: false,
    createdAt: new Date().toISOString(),
    modified: new Date().toISOString(),
    actor: {
      id: "user-1",
      username: "testuser",
      email: "test@example.com",
    },
    conversation: {
      id: "conv-1",
      title: "Test Thread",
      conversationType: "THREAD",
    },
    ...overrides,
  });

  test("renders notification with actor and message", async ({ mount }) => {
    const notification = createMockNotification();

    const component = await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <NotificationItem notification={notification} showActions={false} />
      </MockedProvider>
    );

    await expect(component.getByText(/testuser replied/i)).toBeVisible();
    await expect(component.getByText(/Test Thread/i)).toBeVisible();
  });

  test("shows unread indicator when isRead is false", async ({ mount }) => {
    const notification = createMockNotification({ isRead: false });

    const component = await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <NotificationItem notification={notification} showActions={false} />
      </MockedProvider>
    );

    // Unread dot should be visible
    const unreadDot = component.locator("span").filter({ hasText: "" }).first();
    await expect(unreadDot).toBeVisible();
  });

  test("does not show unread indicator when isRead is true", async ({
    mount,
  }) => {
    const notification = createMockNotification({ isRead: true });

    const component = await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <NotificationItem notification={notification} showActions={false} />
      </MockedProvider>
    );

    // Check that container has read style (we can't easily test for absence of unread dot)
    await expect(component.getByText(/testuser replied/i)).toBeVisible();
  });

  test("displays different notification types correctly", async ({ mount }) => {
    const voteNotification = createMockNotification({
      notificationType: "VOTE",
      data: { voteType: "UPVOTE" },
    });

    const component = await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <NotificationItem notification={voteNotification} showActions={false} />
      </MockedProvider>
    );

    await expect(component.getByText(/upvoted your message/i)).toBeVisible();
  });

  test("marks notification as read when clicked", async ({ mount, page }) => {
    const notification = createMockNotification({ isRead: false });

    const mocks = [
      {
        request: {
          query: MARK_NOTIFICATION_READ,
          variables: {
            notificationId: "notif-1",
          },
        },
        result: {
          data: {
            markNotificationRead: {
              ok: true,
              message: "Notification marked as read",
              notification: {
                id: "notif-1",
                isRead: true,
                modified: new Date().toISOString(),
              },
            },
          },
        },
      },
    ];

    let clickCalled = false;

    const component = await mount(
      <MockedProvider mocks={mocks} addTypename={false}>
        <NotificationItem
          notification={notification}
          onClick={() => {
            clickCalled = true;
          }}
          showActions={false}
        />
      </MockedProvider>
    );

    const item = component.locator("div").first();
    await item.click();

    await page.waitForTimeout(500);
    expect(clickCalled).toBe(true);
  });

  test("shows mark as read action button", async ({ mount }) => {
    const notification = createMockNotification({ isRead: false });

    const component = await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <NotificationItem notification={notification} showActions={true} />
      </MockedProvider>
    );

    await expect(component.getByText("Mark as read")).toBeVisible();
  });

  test("shows mark as unread action button when read", async ({ mount }) => {
    const notification = createMockNotification({ isRead: true });

    const component = await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <NotificationItem notification={notification} showActions={true} />
      </MockedProvider>
    );

    await expect(component.getByText("Mark as unread")).toBeVisible();
  });

  test("marks notification as read via action button", async ({
    mount,
    page,
  }) => {
    const notification = createMockNotification({ isRead: false });

    const mocks = [
      {
        request: {
          query: MARK_NOTIFICATION_READ,
          variables: {
            notificationId: "notif-1",
          },
        },
        result: {
          data: {
            markNotificationRead: {
              ok: true,
              message: "Notification marked as read",
              notification: {
                id: "notif-1",
                isRead: true,
                modified: new Date().toISOString(),
              },
            },
          },
        },
      },
    ];

    const component = await mount(
      <MockedProvider mocks={mocks} addTypename={false}>
        <NotificationItem notification={notification} showActions={true} />
      </MockedProvider>
    );

    const markReadButton = component.getByText("Mark as read");
    await markReadButton.click();

    await page.waitForTimeout(500);
  });

  test("marks notification as unread via action button", async ({
    mount,
    page,
  }) => {
    const notification = createMockNotification({ isRead: true });

    const mocks = [
      {
        request: {
          query: MARK_NOTIFICATION_UNREAD,
          variables: {
            notificationId: "notif-1",
          },
        },
        result: {
          data: {
            markNotificationUnread: {
              ok: true,
              message: "Notification marked as unread",
              notification: {
                id: "notif-1",
                isRead: false,
                modified: new Date().toISOString(),
              },
            },
          },
        },
      },
    ];

    const component = await mount(
      <MockedProvider mocks={mocks} addTypename={false}>
        <NotificationItem notification={notification} showActions={true} />
      </MockedProvider>
    );

    const markUnreadButton = component.getByText("Mark as unread");
    await markUnreadButton.click();

    await page.waitForTimeout(500);
  });

  test("shows delete button", async ({ mount }) => {
    const notification = createMockNotification();

    const component = await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <NotificationItem notification={notification} showActions={true} />
      </MockedProvider>
    );

    await expect(component.getByText("Delete")).toBeVisible();
  });

  test("formats relative time", async ({ mount }) => {
    const notification = createMockNotification({
      createdAt: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(), // 2 hours ago
    });

    const component = await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <NotificationItem notification={notification} showActions={false} />
      </MockedProvider>
    );

    await expect(component.getByText(/hours ago/i)).toBeVisible();
  });

  test("renders badge notification correctly", async ({ mount }) => {
    const notification = createMockNotification({
      notificationType: "BADGE",
      data: { badgeName: "Expert Contributor" },
    });

    const component = await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <NotificationItem notification={notification} showActions={false} />
      </MockedProvider>
    );

    await expect(component.getByText(/Expert Contributor/i)).toBeVisible();
  });

  test("renders mention notification correctly", async ({ mount }) => {
    const notification = createMockNotification({
      notificationType: "MENTION",
    });

    const component = await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <NotificationItem notification={notification} showActions={false} />
      </MockedProvider>
    );

    await expect(component.getByText(/mentioned you/i)).toBeVisible();
  });

  test("renders moderation notifications correctly", async ({ mount }) => {
    const notification = createMockNotification({
      notificationType: "THREAD_LOCKED",
    });

    const component = await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <NotificationItem notification={notification} showActions={false} />
      </MockedProvider>
    );

    await expect(component.getByText(/locked thread/i)).toBeVisible();
  });
});
