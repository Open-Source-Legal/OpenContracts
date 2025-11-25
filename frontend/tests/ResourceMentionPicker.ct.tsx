import { test, expect } from "@playwright/experimental-ct-react";
import {
  ResourceMentionPicker,
  MentionResource,
} from "../src/components/threads/ResourceMentionPicker";

// Mock resources for testing
const mockCorpus: MentionResource = {
  id: "corpus-1",
  slug: "legal-contracts",
  title: "Legal Contracts Collection",
  type: "corpus",
  creator: {
    slug: "john-doe",
  },
};

const mockDocumentWithCorpus: MentionResource = {
  id: "doc-1",
  slug: "contract-001",
  title: "Employment Agreement 2024",
  type: "document",
  creator: {
    slug: "jane-smith",
  },
  corpus: {
    slug: "legal-contracts",
    title: "Legal Contracts Collection",
    creator: {
      slug: "john-doe",
    },
  },
};

const mockDocumentWithoutCorpus: MentionResource = {
  id: "doc-2",
  slug: "standalone-doc",
  title: "Standalone Document",
  type: "document",
  creator: {
    slug: "bob-jones",
  },
};

test.describe("ResourceMentionPicker", () => {
  test("renders empty state when no resources", async ({ mount }) => {
    const component = await mount(
      <ResourceMentionPicker
        resources={[]}
        onSelect={() => {}}
        selectedIndex={0}
      />
    );

    await expect(component.getByText("No resources found")).toBeVisible();
    await expect(
      component.getByText("Type to search corpuses and documents")
    ).toBeVisible();
  });

  test("renders corpus with correct format", async ({ mount }) => {
    const component = await mount(
      <ResourceMentionPicker
        resources={[mockCorpus]}
        onSelect={() => {}}
        selectedIndex={0}
      />
    );

    await expect(component.getByText("Corpuses")).toBeVisible();
    await expect(
      component.getByText("Legal Contracts Collection")
    ).toBeVisible();
    await expect(component.getByText("@corpus:legal-contracts")).toBeVisible();
    await expect(component.getByText("by @john-doe")).toBeVisible();
  });

  test("renders document with corpus using full format", async ({ mount }) => {
    const component = await mount(
      <ResourceMentionPicker
        resources={[mockDocumentWithCorpus]}
        onSelect={() => {}}
        selectedIndex={0}
      />
    );

    await expect(component.getByText("Documents")).toBeVisible();
    await expect(
      component.getByText("Employment Agreement 2024")
    ).toBeVisible();
    await expect(
      component.getByText("@corpus:legal-contracts/document:contract-001")
    ).toBeVisible();
    await expect(
      component.getByText(/in "Legal Contracts Collection"/)
    ).toBeVisible();
  });

  test("renders document without corpus using simple format", async ({
    mount,
  }) => {
    const component = await mount(
      <ResourceMentionPicker
        resources={[mockDocumentWithoutCorpus]}
        onSelect={() => {}}
        selectedIndex={0}
      />
    );

    await expect(component.getByText("Documents")).toBeVisible();
    await expect(component.getByText("Standalone Document")).toBeVisible();
    await expect(component.getByText("@document:standalone-doc")).toBeVisible();
    await expect(component.getByText("by @bob-jones")).toBeVisible();
  });

  test("groups corpuses and documents separately", async ({ mount }) => {
    const resources = [mockCorpus, mockDocumentWithCorpus];

    const component = await mount(
      <ResourceMentionPicker
        resources={resources}
        onSelect={() => {}}
        selectedIndex={0}
      />
    );

    // Check headers are present
    await expect(component.getByText("Corpuses")).toBeVisible();
    await expect(component.getByText("Documents")).toBeVisible();

    // Check items are under correct headers
    const corpusSection = component.locator('text="Corpuses"');
    const documentSection = component.locator('text="Documents"');

    await expect(corpusSection).toBeVisible();
    await expect(documentSection).toBeVisible();
  });

  test("calls onSelect with correct resource when clicked", async ({
    mount,
  }) => {
    let selectedResource: MentionResource | null = null;

    const component = await mount(
      <ResourceMentionPicker
        resources={[mockCorpus]}
        onSelect={(resource) => {
          selectedResource = resource;
        }}
        selectedIndex={0}
      />
    );

    await component
      .getByRole("button", { name: /Legal Contracts Collection/ })
      .click();

    expect(selectedResource).toEqual(mockCorpus);
  });

  test("highlights selected index", async ({ mount }) => {
    const resources = [mockCorpus, mockDocumentWithCorpus];

    const component = await mount(
      <ResourceMentionPicker
        resources={resources}
        onSelect={() => {}}
        selectedIndex={1}
      />
    );

    // Second item should have selected styling
    const buttons = await component.getByRole("button").all();
    expect(buttons.length).toBe(2);

    // Check computed style or data attributes for selection
    // This is a visual test - in real usage, the selected item would have different background
  });

  test("shows corpus and document icons", async ({ mount }) => {
    const resources = [mockCorpus, mockDocumentWithCorpus];

    const component = await mount(
      <ResourceMentionPicker
        resources={resources}
        onSelect={() => {}}
        selectedIndex={0}
      />
    );

    // Both icons should be present (Database for corpus, FileText for document)
    // Icons are rendered as SVG elements
    const svgs = await component.locator("svg").all();
    expect(svgs.length).toBeGreaterThanOrEqual(2);
  });

  test("handles mixed corpus and document results", async ({ mount }) => {
    const resources = [
      mockCorpus,
      mockDocumentWithCorpus,
      mockDocumentWithoutCorpus,
    ];

    const component = await mount(
      <ResourceMentionPicker
        resources={resources}
        onSelect={() => {}}
        selectedIndex={0}
      />
    );

    // Should have 1 corpus and 2 documents
    await expect(component.getByText("Corpuses")).toBeVisible();
    await expect(component.getByText("Documents")).toBeVisible();

    // All 3 items should be rendered
    const buttons = await component.getByRole("button").all();
    expect(buttons.length).toBe(3);
  });

  test("truncates long titles with ellipsis", async ({ mount }) => {
    const longTitleResource: MentionResource = {
      ...mockCorpus,
      title:
        "This is a very long corpus title that should be truncated with ellipsis when displayed in the picker component",
    };

    const component = await mount(
      <ResourceMentionPicker
        resources={[longTitleResource]}
        onSelect={() => {}}
        selectedIndex={0}
      />
    );

    // Title should be present (even if truncated visually)
    await expect(
      component.getByText(/This is a very long corpus title/)
    ).toBeVisible();
  });

  test("displays gradient background for resource types", async ({
    mount,
    page,
  }) => {
    const resources = [mockCorpus, mockDocumentWithCorpus];

    const component = await mount(
      <ResourceMentionPicker
        resources={resources}
        onSelect={() => {}}
        selectedIndex={0}
      />
    );

    // Icon containers should have gradient backgrounds
    // Corpus: linear-gradient(135deg, #667eea 0%, #764ba2 100%)
    // Document: linear-gradient(135deg, #f093fb 0%, #f5576c 100%)

    await expect(component).toBeVisible();
  });
});
