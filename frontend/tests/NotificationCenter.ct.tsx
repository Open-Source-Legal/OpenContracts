import { test, expect } from "@playwright/experimental-ct-react";
import { NotificationCenter } from "../src/components/notifications/NotificationCenter";
import { MockedProvider } from "@apollo/client/testing";
import { MemoryRouter } from "react-router-dom";
import {
  GET_NOTIFICATIONS,
  GET_UNREAD_NOTIFICATION_COUNT,
} from "../src/graphql/queries";
import { MARK_ALL_NOTIFICATIONS_READ } from "../src/graphql/mutations";

test.describe("NotificationCenter", () => {
  test("renders notification center title", async ({ mount, page }) => {
    const mocks = [
      {
        request: {
          query: GET_NOTIFICATIONS,
          variables: {
            limit: 50,
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
          <NotificationCenter />
        </MockedProvider>
      </MemoryRouter>
    );

    await expect(
      page.getByRole("heading", { name: "Notifications", exact: true }).first()
    ).toBeVisible();
  });

  test("shows filter buttons", async ({ mount, page }) => {
    const mocks = [
      {
        request: {
          query: GET_NOTIFICATIONS,
          variables: {
            limit: 50,
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
          <NotificationCenter />
        </MockedProvider>
      </MemoryRouter>
    );

    await expect(
      page.getByRole("button", { name: "All", exact: true })
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Unread", exact: true })
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Read", exact: true })
    ).toBeVisible();
  });

  test("shows mark all as read button", async ({ mount, page }) => {
    const mocks = [
      {
        request: {
          query: GET_NOTIFICATIONS,
          variables: {
            limit: 50,
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
          <NotificationCenter />
        </MockedProvider>
      </MemoryRouter>
    );

    await expect(
      page.getByRole("button", { name: /Mark all as read/i })
    ).toBeVisible();
  });

  test("shows empty state when no notifications", async ({ mount, page }) => {
    const mocks = [
      {
        request: {
          query: GET_NOTIFICATIONS,
          variables: {
            limit: 50,
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
          <NotificationCenter />
        </MockedProvider>
      </MemoryRouter>
    );

    await page.waitForTimeout(500);
    await expect(page.getByText("No notifications yet")).toBeVisible();
  });

  test("renders notification list", async ({ mount, page }) => {
    const mocks = [
      {
        request: {
          query: GET_NOTIFICATIONS,
          variables: {
            limit: 50,
          },
        },
        result: {
          data: {
            notifications: {
              edges: [
                {
                  node: {
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
                  },
                },
              ],
              pageInfo: {
                hasNextPage: false,
                hasPreviousPage: false,
                startCursor: "",
                endCursor: "",
              },
              totalCount: 1,
            },
          },
        },
      },
    ];

    const component = await mount(
      <MemoryRouter>
        <MockedProvider mocks={mocks} addTypename={false}>
          <NotificationCenter />
        </MockedProvider>
      </MemoryRouter>
    );

    await page.waitForTimeout(500);
    await expect(page.getByText(/testuser replied/i)).toBeVisible();
  });

  test("filters notifications by unread", async ({ mount, page }) => {
    const allMock = {
      request: {
        query: GET_NOTIFICATIONS,
        variables: {
          limit: 50,
        },
      },
      result: {
        data: {
          notifications: {
            edges: [
              {
                node: {
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
                },
              },
            ],
            pageInfo: {
              hasNextPage: false,
              hasPreviousPage: false,
              startCursor: "",
              endCursor: "",
            },
            totalCount: 1,
          },
        },
      },
    };

    const unreadMock = {
      request: {
        query: GET_NOTIFICATIONS,
        variables: {
          limit: 50,
          isRead: false,
        },
      },
      result: {
        data: {
          notifications: {
            edges: [
              {
                node: {
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
                },
              },
            ],
            pageInfo: {
              hasNextPage: false,
              hasPreviousPage: false,
              startCursor: "",
              endCursor: "",
            },
            totalCount: 1,
          },
        },
      },
    };

    const component = await mount(
      <MemoryRouter>
        <MockedProvider mocks={[allMock, unreadMock]} addTypename={false}>
          <NotificationCenter />
        </MockedProvider>
      </MemoryRouter>
    );

    await page.waitForTimeout(500);

    const unreadButton = page.getByRole("button", { name: "Unread" });
    await unreadButton.click();

    await page.waitForTimeout(500);
    await expect(page.getByText(/testuser replied/i)).toBeVisible();
  });

  test("marks all as read", async ({ mount, page }) => {
    const mocks = [
      {
        request: {
          query: GET_NOTIFICATIONS,
          variables: {
            limit: 50,
          },
        },
        result: {
          data: {
            notifications: {
              edges: [
                {
                  node: {
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
                  },
                },
              ],
              pageInfo: {
                hasNextPage: false,
                hasPreviousPage: false,
                startCursor: "",
                endCursor: "",
              },
              totalCount: 1,
            },
          },
        },
      },
      {
        request: {
          query: MARK_ALL_NOTIFICATIONS_READ,
        },
        result: {
          data: {
            markAllNotificationsRead: {
              ok: true,
              message: "Marked 1 notification(s) as read",
              count: 1,
            },
          },
        },
      },
    ];

    const component = await mount(
      <MemoryRouter>
        <MockedProvider mocks={mocks} addTypename={false}>
          <NotificationCenter />
        </MockedProvider>
      </MemoryRouter>
    );

    await page.waitForTimeout(500);

    const markAllButton = page.getByRole("button", {
      name: /Mark all as read/i,
    });
    await markAllButton.click();

    await page.waitForTimeout(500);
  });

  test("disables mark all as read when no unread", async ({ mount, page }) => {
    const mocks = [
      {
        request: {
          query: GET_NOTIFICATIONS,
          variables: {
            limit: 50,
          },
        },
        result: {
          data: {
            notifications: {
              edges: [
                {
                  node: {
                    id: "notif-1",
                    notificationType: "REPLY",
                    isRead: true,
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
                  },
                },
              ],
              pageInfo: {
                hasNextPage: false,
                hasPreviousPage: false,
                startCursor: "",
                endCursor: "",
              },
              totalCount: 1,
            },
          },
        },
      },
    ];

    const component = await mount(
      <MemoryRouter>
        <MockedProvider mocks={mocks} addTypename={false}>
          <NotificationCenter />
        </MockedProvider>
      </MemoryRouter>
    );

    await page.waitForTimeout(500);

    const markAllButton = page.getByRole("button", {
      name: /Mark all as read/i,
    });
    await expect(markAllButton).toBeDisabled();
  });

  test("shows load more button when hasNextPage", async ({ mount, page }) => {
    const mocks = [
      {
        request: {
          query: GET_NOTIFICATIONS,
          variables: {
            limit: 50,
          },
        },
        result: {
          data: {
            notifications: {
              edges: [
                {
                  node: {
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
                  },
                },
              ],
              pageInfo: {
                hasNextPage: true,
                hasPreviousPage: false,
                startCursor: "",
                endCursor: "cursor-1",
              },
              totalCount: 100,
            },
          },
        },
      },
    ];

    const component = await mount(
      <MemoryRouter>
        <MockedProvider mocks={mocks} addTypename={false}>
          <NotificationCenter />
        </MockedProvider>
      </MemoryRouter>
    );

    await page.waitForTimeout(500);
    await expect(
      page.getByRole("button", { name: /Load more/i })
    ).toBeVisible();
  });
});
