// Playwright Component Test for User Profile Page (Issue #611)
import React from "react";
import { test, expect } from "./utils/coverage";
import { MockedProvider } from "@apollo/client/testing";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { UserProfile } from "../src/views/UserProfile";
import {
  UserProfileRouteLoadingWrapper,
  UserProfileRouteResetWrapper,
  UserProfileRouteSeededWrapper,
} from "./UserProfileRouteTestWrappers";
import { GET_USER_BADGES } from "../src/graphql/queries";
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

test.describe("UserProfileRoute - State-Driven Rendering", () => {
  // UserProfileRoute is a dumb consumer of openedUser / routeLoading /
  // routeError, all owned by CentralRouteManager. The wrappers seed those
  // reactive vars in the browser context — see UserProfileRouteTestWrappers.

  test("renders the loading display when routeLoading is true and no user is resolved", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <MemoryRouter initialEntries={["/users/publicuser-123"]}>
          <Routes>
            <Route
              path="/users/:slug"
              element={<UserProfileRouteLoadingWrapper />}
            />
          </Routes>
        </MemoryRouter>
      </MockedProvider>
    );

    await expect(page.locator("text=Loading profile...")).toBeVisible();

    await component.unmount();
  });

  test("renders the not-found display when no user is resolved", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <MemoryRouter initialEntries={["/users/nonexistent-user"]}>
          <Routes>
            <Route
              path="/users/:slug"
              element={<UserProfileRouteResetWrapper />}
            />
          </Routes>
        </MemoryRouter>
      </MockedProvider>
    );

    await expect(page.locator("text=User Not Found")).toBeVisible();

    await component.unmount();
  });

  test("renders the resolved profile when openedUser is populated", async ({
    mount,
    page,
  }) => {
    const badgesMock = {
      request: {
        query: GET_USER_BADGES,
        variables: { userId: "VXNlclR5cGU6MQ==", limit: 100 },
      },
      result: {
        data: {
          userBadges: {
            edges: [],
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
          <Routes>
            <Route
              path="/users/:slug"
              element={
                <UserProfileRouteSeededWrapper user={mockPublicUser as any} />
              }
            />
          </Routes>
        </MemoryRouter>
      </MockedProvider>
    );

    await expect(page.locator("text=Public User")).toBeVisible({
      timeout: 10000,
    });

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

  test("renders markdown headline, about, and links via SafeMarkdown", async ({
    mount,
    page,
  }) => {
    // Verifies the markdown profile fields added in this PR end up in
    // the DOM. The link href is the SafeMarkdown urlTransform contract:
    // an https:// link is preserved; a javascript: link must be
    // stripped (rendered with empty href, not as an executable target).
    const userWithMarkdown = {
      ...mockPublicUser,
      profileHeadline: "Senior contracts engineer",
      profileAboutMarkdown: "I'm **interested** in dispute resolution.",
      profileLinksMarkdown:
        "- [home](https://example.com)\n" +
        "- [evil](javascript:alert(1))\n" +
        // Protocol-relative URL — browsers resolve "//phishing.example" to
        // the page protocol, so this must be stripped just like javascript:.
        "- [protorel](//phishing.example)\n" +
        // data:text/html bypass — must also be stripped by the allowlist.
        "- [datauri](data:text/html,<script>alert(1)</script>)",
    };

    const badgesMock = {
      request: {
        query: GET_USER_BADGES,
        variables: { userId: userWithMarkdown.id, limit: 100 },
      },
      result: {
        data: {
          userBadges: {
            edges: [],
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
          <UserProfile user={userWithMarkdown} isOwnProfile={false} />
        </MemoryRouter>
      </MockedProvider>
    );

    await expect(page.locator("text=Senior contracts engineer")).toBeVisible();
    await expect(page.locator("text=interested")).toBeVisible();
    await expect(page.locator("text=dispute resolution")).toBeVisible();

    const homeLink = page.locator('a:text-is("home")');
    await expect(homeLink).toBeVisible();
    await expect(homeLink).toHaveAttribute("href", "https://example.com");

    // SafeMarkdown.urlTransform must strip the javascript: URL — the
    // anchor still renders (the markdown still parses) but the href
    // must NOT be the executable javascript: target.
    const evilLink = page.locator('a:text-is("evil")');
    await expect(evilLink).toBeVisible();
    const evilHref = (await evilLink.getAttribute("href")) || "";
    expect(evilHref.toLowerCase()).not.toContain("javascript:");

    // Protocol-relative URLs like //phishing.example resolve to the
    // page's protocol, so a profile author could disguise an external
    // link as an in-app relative path. SafeMarkdown.urlTransform must
    // reject anything starting with "//".
    const protorelLink = page.locator('a:text-is("protorel")');
    await expect(protorelLink).toBeVisible();
    const protorelHref = (await protorelLink.getAttribute("href")) || "";
    expect(protorelHref).not.toContain("//phishing.example");

    // data: URLs must also be stripped — react-markdown's default
    // urlTransform handles this today, but pinning the assertion keeps
    // the contract explicit if the dependency or our allowlist drift.
    const dataLink = page.locator('a:text-is("datauri")');
    await expect(dataLink).toBeVisible();
    const dataHref = (await dataLink.getAttribute("href")) || "";
    expect(dataHref.toLowerCase()).not.toContain("data:");

    await component.unmount();
  });
});
