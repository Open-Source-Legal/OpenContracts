import { test, expect } from "@playwright/experimental-ct-react";
import { BrowserRouter } from "react-router-dom";
import {
  MentionChip,
  MentionedResource,
  parseMentionsInContent,
} from "../src/components/threads/MentionChip";

// Mock resources
const mockCorpusResource: MentionedResource = {
  type: "CORPUS",
  id: "corpus-1",
  slug: "legal-contracts",
  title: "Legal Contracts Collection",
  url: "/c/john-doe/legal-contracts",
};

const mockDocumentResource: MentionedResource = {
  type: "DOCUMENT",
  id: "doc-1",
  slug: "contract-001",
  title: "Employment Agreement 2024",
  url: "/c/john-doe/legal-contracts/d/contract-001",
  corpus: {
    slug: "legal-contracts",
    title: "Legal Contracts Collection",
  },
};

const mockStandaloneDocResource: MentionedResource = {
  type: "DOCUMENT",
  id: "doc-2",
  slug: "standalone-doc",
  title: "Standalone Document",
  url: "/d/bob-jones/standalone-doc",
};

test.describe("MentionChip", () => {
  test("renders corpus mention chip with database icon", async ({ mount }) => {
    const component = await mount(
      <BrowserRouter>
        <MentionChip resource={mockCorpusResource} />
      </BrowserRouter>
    );

    await expect(
      component.getByText("Legal Contracts Collection")
    ).toBeVisible();

    // Check for database icon (SVG)
    const svg = await component.locator("svg").first();
    await expect(svg).toBeVisible();
  });

  test("renders document mention chip with file icon", async ({ mount }) => {
    const component = await mount(
      <BrowserRouter>
        <MentionChip resource={mockDocumentResource} />
      </BrowserRouter>
    );

    await expect(
      component.getByText("Employment Agreement 2024")
    ).toBeVisible();

    // Check for file icon (SVG)
    const svg = await component.locator("svg").first();
    await expect(svg).toBeVisible();
  });

  test("displays external link icon", async ({ mount }) => {
    const component = await mount(
      <BrowserRouter>
        <MentionChip resource={mockCorpusResource} />
      </BrowserRouter>
    );

    // Should have at least 2 SVG icons (type icon + external link icon)
    const svgs = await component.locator("svg").all();
    expect(svgs.length).toBeGreaterThanOrEqual(2);
  });
});

// Note: parseMentionsInContent tests are done via unit tests
// Playwright component testing doesn't support dynamically created components well
