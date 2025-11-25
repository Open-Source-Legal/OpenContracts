import { test, expect } from "@playwright/experimental-ct-react";
import { NotificationBell } from "../src/components/notifications/NotificationBell";
import { MockedProvider } from "@apollo/client/testing";
import { MemoryRouter } from "react-router-dom";
import { GET_UNREAD_NOTIFICATION_COUNT } from "../src/graphql/queries";

test.describe("NotificationBell", () => {
  test("renders bell icon", async ({ mount, page }) => {
    const mocks = [
      {
        request: {
          query: GET_UNREAD_NOTIFICATION_COUNT,
        },
        result: {
          data: {
            unreadNotificationCount: 0,
          },
        },
      },
    ];

    const component = await mount(
      <MemoryRouter>
        <MockedProvider mocks={mocks} addTypename={false}>
          <NotificationBell pollInterval={0} />
        </MockedProvider>
      </MemoryRouter>
    );

    await expect(page.getByLabel(/Notifications/i)).toBeVisible();
  });

  test("shows unread count badge when > 0", async ({ mount, page }) => {
    const mocks = [
      {
        request: {
          query: GET_UNREAD_NOTIFICATION_COUNT,
        },
        result: {
          data: {
            unreadNotificationCount: 5,
          },
        },
      },
    ];

    const component = await mount(
      <MemoryRouter>
        <MockedProvider mocks={mocks} addTypename={false}>
          <NotificationBell pollInterval={0} />
        </MockedProvider>
      </MemoryRouter>
    );

    await page.waitForTimeout(500);
    await expect(page.getByText("5")).toBeVisible();
  });

  test("shows 99+ for counts over 99", async ({ mount, page }) => {
    const mocks = [
      {
        request: {
          query: GET_UNREAD_NOTIFICATION_COUNT,
        },
        result: {
          data: {
            unreadNotificationCount: 150,
          },
        },
      },
    ];

    const component = await mount(
      <MemoryRouter>
        <MockedProvider mocks={mocks} addTypename={false}>
          <NotificationBell pollInterval={0} />
        </MockedProvider>
      </MemoryRouter>
    );

    await page.waitForTimeout(500);
    await expect(page.getByText("99+")).toBeVisible();
  });

  test("does not show badge when count is 0", async ({ mount, page }) => {
    const mocks = [
      {
        request: {
          query: GET_UNREAD_NOTIFICATION_COUNT,
        },
        result: {
          data: {
            unreadNotificationCount: 0,
          },
        },
      },
    ];

    const component = await mount(
      <MemoryRouter>
        <MockedProvider mocks={mocks} addTypename={false}>
          <NotificationBell pollInterval={0} />
        </MockedProvider>
      </MemoryRouter>
    );

    await page.waitForTimeout(500);
    const bell = page.getByLabel(/Notifications/i);
    await expect(bell).toBeVisible();
    // Badge should not be present
    await expect(
      page.locator("span").filter({ hasText: /^\d+$/ })
    ).not.toBeVisible();
  });

  test("calls onViewAll when clicked in fullPageMode", async ({
    mount,
    page,
  }) => {
    const mocks = [
      {
        request: {
          query: GET_UNREAD_NOTIFICATION_COUNT,
        },
        result: {
          data: {
            unreadNotificationCount: 3,
          },
        },
      },
    ];

    let viewAllCalled = false;

    const component = await mount(
      <MemoryRouter>
        <MockedProvider mocks={mocks} addTypename={false}>
          <NotificationBell
            fullPageMode={true}
            onViewAll={() => {
              viewAllCalled = true;
            }}
            pollInterval={0}
          />
        </MockedProvider>
      </MemoryRouter>
    );

    await page.waitForTimeout(500);

    const bell = page.getByLabel(/Notifications/i);
    await bell.click();

    await page.waitForTimeout(100);
    expect(viewAllCalled).toBe(true);
  });

  test("opens dropdown when clicked (not in fullPageMode)", async ({
    mount,
    page,
  }) => {
    const mocks = [
      {
        request: {
          query: GET_UNREAD_NOTIFICATION_COUNT,
        },
        result: {
          data: {
            unreadNotificationCount: 3,
          },
        },
      },
      {
        request: {
          query: require("../src/graphql/queries").GET_NOTIFICATIONS,
          variables: {
            limit: 10,
          },
        },
        result: {
          data: {
            notifications: {
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
    ];

    const component = await mount(
      <MemoryRouter>
        <MockedProvider mocks={mocks} addTypename={false}>
          <NotificationBell fullPageMode={false} pollInterval={0} />
        </MockedProvider>
      </MemoryRouter>
    );

    await page.waitForTimeout(500);

    const bell = page.getByLabel(/Notifications/i);
    await bell.click();

    await page.waitForTimeout(1000);
    // Dropdown should be visible with "Notifications" title
    await expect(
      page.getByRole("heading", { name: /Notifications/i }).first()
    ).toBeVisible({ timeout: 10000 });
  });

  test("closes dropdown when clicking outside", async ({ mount, page }) => {
    const mocks = [
      {
        request: {
          query: GET_UNREAD_NOTIFICATION_COUNT,
        },
        result: {
          data: {
            unreadNotificationCount: 3,
          },
        },
      },
      {
        request: {
          query: require("../src/graphql/queries").GET_NOTIFICATIONS,
          variables: {
            limit: 10,
          },
        },
        result: {
          data: {
            notifications: {
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
    ];

    const component = await mount(
      <MemoryRouter>
        <MockedProvider mocks={mocks} addTypename={false}>
          <NotificationBell fullPageMode={false} pollInterval={0} />
        </MockedProvider>
      </MemoryRouter>
    );

    await page.waitForTimeout(500);

    // Open dropdown
    const bell = page.getByLabel(/Notifications/i);
    await bell.click();

    await page.waitForTimeout(1000);
    await expect(
      page.getByRole("heading", { name: /Notifications/i }).first()
    ).toBeVisible({ timeout: 10000 });

    // Click outside
    await page.mouse.click(10, 10);

    await page.waitForTimeout(300);
    await expect(
      page.getByRole("heading", { name: /Notifications/i })
    ).not.toBeVisible();
  });
});
