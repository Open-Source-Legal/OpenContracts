// Playwright Component Test for User Profile Page (Issue #611)
import React from "react";
import { test, expect } from "./utils/coverage";
import { MockedProvider } from "@apollo/client/testing";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { UserProfileRoute } from "../src/components/routes/UserProfileRoute";
import { UserProfile } from "../src/views/UserProfile";
import { GET_USER, GET_USER_BADGES } from "../src/graphql/queries";
import { docScreenshot, releaseScreenshot } from "./utils/docScreenshot";

// Mock user data
const mockPublicUser = {
  id: "VXNlclR5cGU6MQ==",
  username: "publicuser",
  slug: "publicuser-123",
  name: "Public User",
  firstName: "Public",
  lastName: "User",
  email: "public@example.com",
  isProfilePublic: true,
  reputationGlobal: 150,
  totalMessages: 42,
  totalThreadsCreated: 5,
  totalAnnotationsCreated: 28,
  totalDocumentsUploaded: 10,
};

test.describe("UserProfileRoute - Hook Ordering Regression (Issue #1295)", () => {
  test("mounts with slug under a Routes tree that also defines /profile (no 'Rendered more hooks' crash)", async ({
    mount,
    page,
  }) => {
    // This test exercises the scenario that surfaced the original bug: both
    // the redirect route (/profile, no slug) and the render route
    // (/users/:slug) live in the same <Routes> tree. When useQuery was below
    // the `!slug` early return, React could (depending on fiber reuse)
    // compare hook call counts across the two renders and throw
    // "Rendered more hooks than during the previous render". With the fix,
    // useQuery is called unconditionally and skip: !slug gates the network
    // request, so the component renders without crashing on either path.
    //
    // NOTE: This is a narrow regression guard rather than a full reproduction
    // of the original crash. Reproducing the exact crash in-process requires
    // keeping the same fiber across /profile -> /users/:slug, which React
    // Router <Routes> doesn't do (it unmounts the old element when the
    // matched path changes). The positive assertions below (loading display
    // for the slug path, absence of hook-count errors) prove the hook
    // ordering is stable — exactly what the fix guarantees statically.
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });

    // Delay the mock so the render parks on the loading state, giving us
    // positive visible evidence (not just the absence of a crash) that
    // useQuery ran under skip:false on the slug path.
    const mocks = [
      {
        request: {
          query: GET_USER,
          variables: { slug: "publicuser-123" },
        },
        delay: 5000,
        result: {
          data: {
            userBySlug: mockPublicUser,
          },
        },
      },
    ];

    const component = await mount(
      <MockedProvider mocks={mocks} addTypename={false}>
        <MemoryRouter initialEntries={["/users/publicuser-123"]}>
          <Routes>
            <Route path="/profile" element={<UserProfileRoute />} />
            <Route path="/users/:slug" element={<UserProfileRoute />} />
          </Routes>
        </MemoryRouter>
      </MockedProvider>
    );

    // Wait for positive DOM evidence that the slug render reached the
    // useQuery call (skip:false branch) instead of a silent bailout.
    await expect(page.locator("text=Loading profile...")).toBeVisible({
      timeout: 10000,
    });

    const hookErrors = consoleErrors.filter((e) =>
      e.includes("Rendered more hooks than during the previous render")
    );
    expect(hookErrors).toEqual([]);

    await component.unmount();
  });
});

test.describe("UserProfile View - Loading and Error States", () => {
  test("should show loading state while fetching user data", async ({
    mount,
    page,
  }) => {
    const mocks = [
      {
        request: {
          query: GET_USER,
          variables: { slug: "publicuser-123" },
        },
        delay: 2000, // Simulate slow network
        result: {
          data: {
            userBySlug: mockPublicUser,
          },
        },
      },
    ];

    const component = await mount(
      <MockedProvider mocks={mocks} addTypename={false}>
        <MemoryRouter initialEntries={["/users/publicuser-123"]}>
          <Routes>
            <Route path="/users/:slug" element={<UserProfileRoute />} />
          </Routes>
        </MemoryRouter>
      </MockedProvider>
    );

    // Check loading spinner is visible
    await expect(page.locator("text=Loading profile...")).toBeVisible();

    await component.unmount();
  });

  test("should show error message when user not found", async ({
    mount,
    page,
  }) => {
    const mocks = [
      {
        request: {
          query: GET_USER,
          variables: { slug: "nonexistent-user" },
        },
        result: {
          data: {
            userBySlug: null,
          },
        },
      },
    ];

    const component = await mount(
      <MockedProvider mocks={mocks} addTypename={false}>
        <MemoryRouter initialEntries={["/users/nonexistent-user"]}>
          <Routes>
            <Route path="/users/:slug" element={<UserProfileRoute />} />
          </Routes>
        </MemoryRouter>
      </MockedProvider>
    );

    // Wait for query to complete
    await page.waitForTimeout(1000);

    // Check error message is displayed
    await expect(page.locator("text=User not found")).toBeVisible();

    await component.unmount();
  });
});

test.describe("UserProfile View - Rendered Profile", () => {
  test("should render public user profile", async ({ mount, page }) => {
    const badgesMock = {
      request: {
        query: GET_USER_BADGES,
        variables: {
          userId: "VXNlclR5cGU6MQ==",
          limit: 100,
        },
      },
      result: {
        data: {
          userBadges: {
            edges: [
              {
                node: {
                  id: "UB1",
                  awardedAt: "2025-01-15T10:00:00Z",
                  user: {
                    id: "VXNlclR5cGU6MQ==",
                    username: "publicuser",
                    email: "public@example.com",
                  },
                  badge: {
                    id: "B1",
                    name: "First Annotation",
                    description: "Created your first annotation",
                    icon: "tag",
                    color: "#10B981",
                    badgeType: "AUTOMATIC",
                  },
                  awardedBy: null,
                  corpus: null,
                },
              },
            ],
            pageInfo: {
              hasNextPage: false,
              hasPreviousPage: false,
              startCursor: null,
              endCursor: null,
            },
          },
        },
      },
    };

    const component = await mount(
      <MockedProvider mocks={[badgesMock]} addTypename={false}>
        <MemoryRouter initialEntries={["/users/publicuser-123"]}>
          <UserProfile user={mockPublicUser} isOwnProfile={false} />
        </MemoryRouter>
      </MockedProvider>
    );

    // Wait for profile to render with user info
    await expect(page.locator("text=Public User")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.locator("text=@publicuser")).toBeVisible();

    // Stats should be visible
    await expect(page.locator("text=150")).toBeVisible(); // reputation

    await docScreenshot(page, "users--profile--public");
    await releaseScreenshot(page, "v3.0.0.b3", "user-profile");

    await component.unmount();
  });
});
