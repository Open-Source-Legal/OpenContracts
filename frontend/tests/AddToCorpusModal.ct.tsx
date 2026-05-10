// Playwright Component Test for AddToCorpusModal
// Tests the modal for adding documents to a corpus with search and multi-step flow.
import React from "react";
import { test, expect } from "./utils/coverage";
import { MockedProvider } from "@apollo/client/testing";
import { gql } from "@apollo/client";
import { AddToCorpusModal } from "../src/components/modals/AddToCorpusModal";
import { docScreenshot } from "./utils/docScreenshot";

const DOCUMENT_ID = "RG9jdW1lbnRUeXBlOjE=";

// The AddToCorpusModal defines its own inline query (GET_EDITABLE_CORPUSES).
// We need to match it exactly for the MockedProvider.
const GET_EDITABLE_CORPUSES = gql`
  query GetEditableCorpuses($textSearch: String) {
    corpuses(textSearch: $textSearch, first: 10) {
      pageInfo {
        hasNextPage
        hasPreviousPage
        startCursor
        endCursor
      }
      edges {
        node {
          id
          icon
          title
          creator {
            id
            email
          }
          description
          documentCount
          labelSet {
            id
            title
          }
          myPermissions
        }
      }
    }
  }
`;

const mockCorpuses = [
  {
    id: "Q29ycHVzVHlwZTox",
    icon: "folder",
    title: "Contract Analysis",
    creator: {
      id: "VXNlclR5cGU6MQ==",
      slug: "admin",
      email: "admin@example.com",
    },
    description: "A corpus for analyzing contracts",
    documentCount: 15,
    labelSet: { id: "TGFiZWxTZXRUeXBlOjE=", title: "Legal Terms" },
    myPermissions: ["read_corpus", "update_corpus"],
  },
  {
    id: "Q29ycHVzVHlwZToy",
    icon: null,
    title: "NDA Collection",
    creator: {
      id: "VXNlclR5cGU6Mg==",
      slug: "regular-user",
      email: "user@example.com",
    },
    description: "Collection of non-disclosure agreements",
    documentCount: 8,
    labelSet: null,
    myPermissions: ["read_corpus", "update_corpus"],
  },
];

// Query with empty search term (initial load).
// The modal's ``useEffect(() => refetch(), [open, refetch])`` re-fires
// whenever Apollo's ``useQuery`` returns a new ``refetch`` reference, and
// ``notifyOnNetworkStatusChange: true`` causes that on every network state
// change. Combined with React 18's double-render in the CT harness, the
// modal can issue many ``GetEditableCorpuses`` requests per mount.
// ``result`` as a callback + ``maxUsageCount: Number.POSITIVE_INFINITY`` is
// the Apollo-recommended way to make a mock re-supply itself indefinitely
// instead of being consumed once and triggering "No more mocked responses".
const getCorpusesMock = {
  request: {
    query: GET_EDITABLE_CORPUSES,
    variables: { textSearch: "" },
  },
  result: {
    data: {
      corpuses: {
        pageInfo: {
          hasNextPage: false,
          hasPreviousPage: false,
          startCursor: null,
          endCursor: null,
        },
        edges: mockCorpuses.map((corpus) => ({ node: corpus })),
      },
    },
  },
  maxUsageCount: Number.POSITIVE_INFINITY,
};

// Empty results mock
const getCorpusesEmptyMock = {
  request: {
    query: GET_EDITABLE_CORPUSES,
    variables: { textSearch: "" },
  },
  result: {
    data: {
      corpuses: {
        pageInfo: {
          hasNextPage: false,
          hasPreviousPage: false,
          startCursor: null,
          endCursor: null,
        },
        edges: [],
      },
    },
  },
  maxUsageCount: Number.POSITIVE_INFINITY,
};

test.describe("AddToCorpusModal - Rendering", () => {
  test("should render modal with search and corpus list", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider mocks={[getCorpusesMock]} addTypename={false}>
        <AddToCorpusModal
          documentId={DOCUMENT_ID}
          open={true}
          onClose={() => {}}
          onSuccess={() => {}}
        />
      </MockedProvider>
    );

    // Header should display the title
    await expect(page.locator("text=Add to Corpus")).toBeVisible();

    // Search input should be present
    await expect(
      page.locator('input[placeholder="Search corpuses..."]')
    ).toBeVisible();

    // Instruction text should be visible
    await expect(
      page.locator(
        "text=Select a corpus to enable collaborative features like annotations"
      )
    ).toBeVisible();

    // Cancel button should be present
    await expect(page.locator('[data-testid="cancel-button"]')).toBeVisible();

    // Wait for corpuses to load
    await page.waitForTimeout(500);

    // Corpus items should be visible
    await expect(page.locator("text=Contract Analysis")).toBeVisible();
    await expect(page.locator("text=NDA Collection")).toBeVisible();

    await docScreenshot(page, "corpus--add-to-corpus-modal--initial");

    await component.unmount();
  });

  test("should not render when open is false", async ({ mount, page }) => {
    const component = await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <AddToCorpusModal
          documentId={DOCUMENT_ID}
          open={false}
          onClose={() => {}}
          onSuccess={() => {}}
        />
      </MockedProvider>
    );

    await expect(page.locator("text=Add to Corpus")).not.toBeVisible();

    await component.unmount();
  });
});

test.describe("AddToCorpusModal - Behavior", () => {
  test("should show Next button after selecting a corpus in multi-step mode", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider mocks={[getCorpusesMock]} addTypename={false}>
        <AddToCorpusModal
          documentId={DOCUMENT_ID}
          open={true}
          onClose={() => {}}
          onSuccess={() => {}}
          multiStep={true}
        />
      </MockedProvider>
    );

    // Wait for corpuses to load
    await page.waitForTimeout(500);

    // Next button should not be visible before selection
    await expect(page.locator('[data-testid="next-button"]')).not.toBeVisible();

    // Click on the first corpus card
    await page.locator('[data-testid="corpus-item-Q29ycHVzVHlwZTox"]').click();

    // Next button should now appear
    await expect(page.locator('[data-testid="next-button"]')).toBeVisible();

    await component.unmount();
  });

  test("should call onClose when Cancel is clicked", async ({
    mount,
    page,
  }) => {
    let closeCalled = false;

    const component = await mount(
      <MockedProvider mocks={[getCorpusesMock]} addTypename={false}>
        <AddToCorpusModal
          documentId={DOCUMENT_ID}
          open={true}
          onClose={() => {
            closeCalled = true;
          }}
          onSuccess={() => {}}
        />
      </MockedProvider>
    );

    await page.locator('[data-testid="cancel-button"]').click();
    expect(closeCalled).toBe(true);

    await component.unmount();
  });

  test("should show empty state when no corpuses with edit permission exist", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider mocks={[getCorpusesEmptyMock]} addTypename={false}>
        <AddToCorpusModal
          documentId={DOCUMENT_ID}
          open={true}
          onClose={() => {}}
          onSuccess={() => {}}
        />
      </MockedProvider>
    );

    // Wait for data to load
    await page.waitForTimeout(500);

    // Empty state message should be visible
    await expect(page.locator("text=No corpuses available")).toBeVisible();

    await component.unmount();
  });
});
