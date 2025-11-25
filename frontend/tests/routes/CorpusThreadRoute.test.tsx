/**
 * Basic smoke tests for CorpusThreadRoute component
 *
 * NOTE: Full integration tests with ThreadDetail component will be added
 * once issue #573 (Thread List and Detail Views) is completed.
 *
 * These tests verify:
 * - Component renders without crashing
 * - Route parameters are extracted correctly
 * - Back button navigation works
 */

import { test, expect } from "@playwright/experimental-ct-react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { MockedProvider } from "@apollo/client/testing";
import { CorpusThreadRoute } from "../../src/components/routes/CorpusThreadRoute";
import { openedCorpus } from "../../src/graphql/cache";

test.describe("CorpusThreadRoute", () => {
  test.beforeEach(() => {
    // Set up mock corpus in reactive var
    openedCorpus({
      id: "corpus-123",
      title: "Test Corpus",
      slug: "test-corpus",
      creator: {
        id: "user-1",
        username: "testuser",
        slug: "testuser",
      },
    } as any);
  });

  test.afterEach(() => {
    // Clean up
    openedCorpus(null);
  });

  test("renders without crashing", async ({ mount }) => {
    const component = await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <MemoryRouter
          initialEntries={["/c/testuser/test-corpus/discussions/thread-123"]}
        >
          <Routes>
            <Route
              path="/c/:userIdent/:corpusIdent/discussions/:threadId"
              element={<CorpusThreadRoute />}
            />
          </Routes>
        </MemoryRouter>
      </MockedProvider>
    );

    await expect(component).toBeVisible();
  });

  test("displays back button with correct text", async ({ mount }) => {
    const component = await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <MemoryRouter
          initialEntries={["/c/testuser/test-corpus/discussions/thread-123"]}
        >
          <Routes>
            <Route
              path="/c/:userIdent/:corpusIdent/discussions/:threadId"
              element={<CorpusThreadRoute />}
            />
          </Routes>
        </MemoryRouter>
      </MockedProvider>
    );

    await expect(component.getByText("Back to Discussions")).toBeVisible();
  });

  test("displays thread ID in placeholder", async ({ mount }) => {
    const component = await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <MemoryRouter
          initialEntries={["/c/testuser/test-corpus/discussions/thread-123"]}
        >
          <Routes>
            <Route
              path="/c/:userIdent/:corpusIdent/discussions/:threadId"
              element={<CorpusThreadRoute />}
            />
          </Routes>
        </MemoryRouter>
      </MockedProvider>
    );

    await expect(component.getByText(/thread-123/i)).toBeVisible();
  });

  test("displays corpus title in placeholder when available", async ({
    mount,
  }) => {
    const component = await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <MemoryRouter
          initialEntries={["/c/testuser/test-corpus/discussions/thread-123"]}
        >
          <Routes>
            <Route
              path="/c/:userIdent/:corpusIdent/discussions/:threadId"
              element={<CorpusThreadRoute />}
            />
          </Routes>
        </MemoryRouter>
      </MockedProvider>
    );

    await expect(component.getByText(/Test Corpus/)).toBeVisible();
  });

  test("displays error when thread ID is missing", async ({ mount }) => {
    const component = await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <MemoryRouter initialEntries={["/c/testuser/test-corpus/discussions/"]}>
          <Routes>
            <Route
              path="/c/:userIdent/:corpusIdent/discussions/:threadId?"
              element={<CorpusThreadRoute />}
            />
          </Routes>
        </MemoryRouter>
      </MockedProvider>
    );

    await expect(component.getByText("Thread ID not found")).toBeVisible();
  });

  test("back button has accessible aria label", async ({ mount }) => {
    const component = await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <MemoryRouter
          initialEntries={["/c/testuser/test-corpus/discussions/thread-123"]}
        >
          <Routes>
            <Route
              path="/c/:userIdent/:corpusIdent/discussions/:threadId"
              element={<CorpusThreadRoute />}
            />
          </Routes>
        </MemoryRouter>
      </MockedProvider>
    );

    const backButton = component.getByRole("button", {
      name: /back to discussions/i,
    });
    await expect(backButton).toBeVisible();
  });
});
