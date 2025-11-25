// Playwright Component Test for User Profile Page (Issue #611)
import React from "react";
import { test, expect } from "@playwright/experimental-ct-react";
import { MockedProvider } from "@apollo/client/testing";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { UserProfileRoute } from "../src/components/routes/UserProfileRoute";
import { UserLink } from "../src/components/widgets/UserLink";
import { GET_USER } from "../src/graphql/queries";

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

test.describe("UserLink Component", () => {
  test("should render username as clickable link when slug provided", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MemoryRouter>
        <UserLink username="testuser" slug="testuser-123" />
      </MemoryRouter>
    );

    // Check link is visible with correct text
    const link = page.locator('a:has-text("testuser")');
    await expect(link).toBeVisible();

    // Check link has correct href
    await expect(link).toHaveAttribute("href", "/users/testuser-123");

    await component.unmount();
  });

  test("should render username as plain text when no slug provided", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MemoryRouter>
        <UserLink username="anonuser" />
      </MemoryRouter>
    );

    // Check text is visible but not as a link
    await expect(page.locator("span:has-text('anonuser')")).toBeVisible();
    await expect(page.locator("a:has-text('anonuser')")).not.toBeVisible();

    await component.unmount();
  });

  test("should render username as plain text when disableLink is true", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MemoryRouter>
        <UserLink username="disabled" slug="disabled-123" disableLink={true} />
      </MemoryRouter>
    );

    // Check text is visible but not as a link
    await expect(page.locator("span:has-text('disabled')")).toBeVisible();
    await expect(page.locator("a:has-text('disabled')")).not.toBeVisible();

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
