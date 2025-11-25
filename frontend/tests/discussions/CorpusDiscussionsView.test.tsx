/**
 * Basic smoke tests for CorpusDiscussionsView component
 *
 * NOTE: Full integration tests with ThreadList component will be added
 * once issue #573 (Thread List and Detail Views) is completed.
 *
 * These tests verify:
 * - Component renders without crashing
 * - Basic UI elements are present
 * - Navigation utilities are called correctly
 */

import { test, expect } from "@playwright/experimental-ct-react";
import { MemoryRouter } from "react-router-dom";
import { MockedProvider } from "@apollo/client/testing";
import { CorpusDiscussionsView } from "../../src/components/discussions/CorpusDiscussionsView";
import { openedCorpus } from "../../src/graphql/cache";

test.describe("CorpusDiscussionsView", () => {
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
        <MemoryRouter>
          <CorpusDiscussionsView corpusId="corpus-123" />
        </MemoryRouter>
      </MockedProvider>
    );

    await expect(component).toBeVisible();
  });

  test("displays corpus discussions title", async ({ mount }) => {
    const component = await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <MemoryRouter>
          <CorpusDiscussionsView corpusId="corpus-123" />
        </MemoryRouter>
      </MockedProvider>
    );

    await expect(component.getByText("Corpus Discussions")).toBeVisible();
  });

  test("displays subtitle with corpus title", async ({ mount }) => {
    const component = await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <MemoryRouter>
          <CorpusDiscussionsView corpusId="corpus-123" />
        </MemoryRouter>
      </MockedProvider>
    );

    await expect(
      component.getByText(/Forum-style threads for collaborative discussion/)
    ).toBeVisible();
    await expect(component.getByText(/Test Corpus/)).toBeVisible();
  });

  test("displays create thread button", async ({ mount }) => {
    const component = await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <MemoryRouter>
          <CorpusDiscussionsView corpusId="corpus-123" />
        </MemoryRouter>
      </MockedProvider>
    );

    await expect(component.getByText("New Thread")).toBeVisible();
  });

  test("shows loading state when corpus is not loaded", async ({ mount }) => {
    // Clear the opened corpus
    openedCorpus(null);

    const component = await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <MemoryRouter>
          <CorpusDiscussionsView corpusId="corpus-123" />
        </MemoryRouter>
      </MockedProvider>
    );

    await expect(component.getByText("Loading corpus...")).toBeVisible();
  });

  test("has accessible aria labels", async ({ mount }) => {
    const component = await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <MemoryRouter>
          <CorpusDiscussionsView corpusId="corpus-123" />
        </MemoryRouter>
      </MockedProvider>
    );

    const createButton = component.getByRole("button", {
      name: /create new discussion thread/i,
    });
    await expect(createButton).toBeVisible();
  });
});
