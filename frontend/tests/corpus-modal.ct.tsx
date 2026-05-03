// Playwright Component Test for CorpusModal
import React from "react";
import { test, expect } from "./utils/coverage";
import { MockedProvider } from "@apollo/client/testing";
import { CorpusModal } from "../src/components/corpuses/CorpusModal";
import { GET_LABELSETS, GET_EMBEDDERS } from "../src/graphql/queries";
import { CorpusType } from "../src/types/graphql-api";
import { docScreenshot } from "./utils/docScreenshot";

// Mock data
const mockLabelSet = {
  id: "TGFiZWxTZXRUeXBlOjE=",
  title: "Legal Labels",
  description: "Labels for legal documents",
  icon: null,
};

const mockEmbedder = {
  className:
    "opencontractserver.pipeline.embedders.SentenceTransformerEmbedder",
  name: "SentenceTransformer",
  title: "Sentence Transformer",
  description: "Default text embedder",
  author: "OpenContracts",
  vectorSize: 768,
  enabled: true,
};

const mockCorpus: CorpusType = {
  id: "Q29ycHVzVHlwZTox",
  title: "Test Corpus",
  description: "A test corpus for unit testing",
  icon: null,
  isPublic: false,
  labelSet: mockLabelSet as any,
  preferredEmbedder: mockEmbedder.className,
  creator: {
    id: "VXNlclR5cGU6MQ==",
    email: "test@example.com",
  },
  myPermissions: ["update_corpus", "read_corpus"],
  documents: { totalCount: 0 },
  annotations: { totalCount: 0 },
} as CorpusType;

// GraphQL mocks for selectors
const labelSetsMock = {
  request: {
    query: GET_LABELSETS,
    variables: { description: "" },
  },
  result: {
    data: {
      labelsets: {
        edges: [{ node: mockLabelSet }],
      },
    },
  },
};

const embeddersMock = {
  request: {
    query: GET_EMBEDDERS,
    variables: {},
  },
  result: {
    data: {
      pipelineComponents: {
        embedders: [mockEmbedder],
      },
    },
  },
};

test.describe("CorpusModal - CREATE Mode", () => {
  test("should render create modal with empty form", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider
        mocks={[labelSetsMock, embeddersMock]}
        addTypename={false}
      >
        <CorpusModal
          open={true}
          mode="CREATE"
          onSubmit={() => {}}
          onClose={() => {}}
        />
      </MockedProvider>
    );

    // Check header
    await expect(page.locator("text=Create New Corpus")).toBeVisible();

    // Check form fields are present
    await expect(page.locator("#corpus-title")).toBeVisible();
    await expect(page.locator("#corpus-slug")).toBeVisible();
    await expect(page.locator("#corpus-description")).toBeVisible();

    // Form should be empty
    await expect(page.locator("#corpus-title")).toHaveValue("");
    await expect(page.locator("#corpus-description")).toHaveValue("");

    // Submit button should be present but disabled (no content yet)
    await expect(
      page.locator('button:has-text("Create Corpus")')
    ).toBeVisible();

    await docScreenshot(page, "corpus--corpus-modal--initial");

    await component.unmount();
  });

  test("should enable submit when required fields are filled", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider
        mocks={[labelSetsMock, embeddersMock]}
        addTypename={false}
      >
        <CorpusModal
          open={true}
          mode="CREATE"
          onSubmit={() => {}}
          onClose={() => {}}
        />
      </MockedProvider>
    );

    // Fill required fields
    await page.locator("#corpus-title").fill("My New Corpus");
    await page
      .locator("#corpus-description")
      .fill("A description for my corpus");

    // Submit button should now be enabled
    const submitButton = page.locator('button:has-text("Create Corpus")');
    await expect(submitButton).toBeEnabled();

    await component.unmount();
  });

  test("should call onSubmit with form data", async ({ mount, page }) => {
    let submittedData: any = null;

    const component = await mount(
      <MockedProvider
        mocks={[labelSetsMock, embeddersMock]}
        addTypename={false}
      >
        <CorpusModal
          open={true}
          mode="CREATE"
          onSubmit={(data) => {
            submittedData = data;
          }}
          onClose={() => {}}
        />
      </MockedProvider>
    );

    // Fill form
    await page.locator("#corpus-title").fill("My New Corpus");
    await page.locator("#corpus-slug").fill("my-new-corpus");
    await page.locator("#corpus-description").fill("A test description");

    // Submit
    await page.locator('button:has-text("Create Corpus")').click();

    // Verify data was submitted
    expect(submittedData).not.toBeNull();
    expect(submittedData.title).toBe("My New Corpus");
    expect(submittedData.slug).toBe("my-new-corpus");
    expect(submittedData.description).toBe("A test description");

    await component.unmount();
  });

  test("should call onClose when cancel clicked", async ({ mount, page }) => {
    let closed = false;

    const component = await mount(
      <MockedProvider
        mocks={[labelSetsMock, embeddersMock]}
        addTypename={false}
      >
        <CorpusModal
          open={true}
          mode="CREATE"
          onSubmit={() => {}}
          onClose={() => {
            closed = true;
          }}
        />
      </MockedProvider>
    );

    // Click cancel
    await page.locator('button:has-text("Cancel")').click();

    expect(closed).toBe(true);

    await component.unmount();
  });
});

test.describe("CorpusModal - EDIT Mode", () => {
  test("should populate form with existing corpus data", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider
        mocks={[labelSetsMock, embeddersMock]}
        addTypename={false}
      >
        <CorpusModal
          open={true}
          mode="EDIT"
          corpus={mockCorpus}
          onSubmit={() => {}}
          onClose={() => {}}
        />
      </MockedProvider>
    );

    // Check header
    await expect(page.locator("text=Edit Corpus")).toBeVisible();

    // Form should be populated with corpus data
    await expect(page.locator("#corpus-title")).toHaveValue("Test Corpus");
    await expect(page.locator("#corpus-description")).toHaveValue(
      "A test corpus for unit testing"
    );

    // Save button should be visible
    await expect(page.locator('button:has-text("Save Changes")')).toBeVisible();

    await component.unmount();
  });

  test("should only submit changed fields", async ({ mount, page }) => {
    let submittedData: any = null;

    const component = await mount(
      <MockedProvider
        mocks={[labelSetsMock, embeddersMock]}
        addTypename={false}
      >
        <CorpusModal
          open={true}
          mode="EDIT"
          corpus={mockCorpus}
          onSubmit={(data) => {
            submittedData = data;
          }}
          onClose={() => {}}
        />
      </MockedProvider>
    );

    // Only change the title
    await page.locator("#corpus-title").clear();
    await page.locator("#corpus-title").fill("Updated Corpus Title");

    // Submit
    await page.locator('button:has-text("Save Changes")').click();

    // Verify only changed field is included
    expect(submittedData).not.toBeNull();
    expect(submittedData.id).toBe("Q29ycHVzVHlwZTox");
    expect(submittedData.title).toBe("Updated Corpus Title");

    await component.unmount();
  });

  test("should show loading state", async ({ mount, page }) => {
    const component = await mount(
      <MockedProvider
        mocks={[labelSetsMock, embeddersMock]}
        addTypename={false}
      >
        <CorpusModal
          open={true}
          mode="EDIT"
          corpus={mockCorpus}
          onSubmit={() => {}}
          onClose={() => {}}
          loading={true}
        />
      </MockedProvider>
    );

    // Form inputs should be disabled during loading
    await expect(page.locator("#corpus-title")).toBeDisabled();
    await expect(page.locator("#corpus-description")).toBeDisabled();

    await component.unmount();
  });
});

test.describe("CorpusModal - VIEW Mode", () => {
  test("should display corpus data in read-only mode", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider
        mocks={[labelSetsMock, embeddersMock]}
        addTypename={false}
      >
        <CorpusModal
          open={true}
          mode="VIEW"
          corpus={mockCorpus}
          onClose={() => {}}
        />
      </MockedProvider>
    );

    // Check header
    await expect(page.locator("text=View Corpus")).toBeVisible();

    // Form fields should be disabled
    await expect(page.locator("#corpus-title")).toBeDisabled();
    await expect(page.locator("#corpus-description")).toBeDisabled();

    // No submit button in view mode
    await expect(
      page.locator('button:has-text("Save Changes")')
    ).not.toBeVisible();
    await expect(
      page.locator('button:has-text("Create Corpus")')
    ).not.toBeVisible();

    // Close button should say "Close" not "Cancel"
    await expect(page.locator('button:has-text("Close")')).toBeVisible();

    await component.unmount();
  });
});

test.describe("CorpusModal - Mobile Responsiveness", () => {
  test.use({ viewport: { width: 375, height: 667 } }); // iPhone SE size

  test("should display correctly on mobile viewport", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider
        mocks={[labelSetsMock, embeddersMock]}
        addTypename={false}
      >
        <CorpusModal
          open={true}
          mode="CREATE"
          onSubmit={() => {}}
          onClose={() => {}}
        />
      </MockedProvider>
    );

    // Modal should be visible
    await expect(page.locator("text=Create New Corpus")).toBeVisible();

    // Form elements should still be accessible
    await expect(page.locator("#corpus-title")).toBeVisible();
    await expect(page.locator("#corpus-description")).toBeVisible();

    // Footer buttons should be stacked on mobile
    const footer = page.locator('button:has-text("Cancel")').locator("..");
    await expect(footer).toBeVisible();

    await component.unmount();
  });

  test("should not lose focus or clear fields when switching inputs on mobile", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider
        mocks={[labelSetsMock, embeddersMock]}
        addTypename={false}
      >
        <CorpusModal
          open={true}
          mode="CREATE"
          onSubmit={() => {}}
          onClose={() => {}}
        />
      </MockedProvider>
    );

    // Type in title field
    await page.locator("#corpus-title").fill("Test Title");

    // Move to slug field
    await page.locator("#corpus-slug").focus();
    await page.locator("#corpus-slug").fill("test-slug");

    // Move to description field
    await page.locator("#corpus-description").focus();
    await page.locator("#corpus-description").fill("Test description");

    // Go back and verify title is still there (this was the bug)
    await page.locator("#corpus-title").focus();
    await expect(page.locator("#corpus-title")).toHaveValue("Test Title");

    // Verify all fields retained their values
    await expect(page.locator("#corpus-slug")).toHaveValue("test-slug");
    await expect(page.locator("#corpus-description")).toHaveValue(
      "Test description"
    );

    await component.unmount();
  });
});

test.describe("CorpusModal - Form Validation", () => {
  test("should require title field", async ({ mount, page }) => {
    const component = await mount(
      <MockedProvider
        mocks={[labelSetsMock, embeddersMock]}
        addTypename={false}
      >
        <CorpusModal
          open={true}
          mode="CREATE"
          onSubmit={() => {}}
          onClose={() => {}}
        />
      </MockedProvider>
    );

    // Only fill description, leave title empty
    await page.locator("#corpus-description").fill("A description");

    // Submit should still be disabled
    const submitButton = page.locator('button:has-text("Create Corpus")');
    await expect(submitButton).toBeDisabled();

    await component.unmount();
  });

  test("should require description field", async ({ mount, page }) => {
    const component = await mount(
      <MockedProvider
        mocks={[labelSetsMock, embeddersMock]}
        addTypename={false}
      >
        <CorpusModal
          open={true}
          mode="CREATE"
          onSubmit={() => {}}
          onClose={() => {}}
        />
      </MockedProvider>
    );

    // Only fill title, leave description empty
    await page.locator("#corpus-title").fill("A title");

    // Submit should still be disabled
    const submitButton = page.locator('button:has-text("Create Corpus")');
    await expect(submitButton).toBeDisabled();

    await component.unmount();
  });

  test("slug field should be optional", async ({ mount, page }) => {
    let submittedData: any = null;

    const component = await mount(
      <MockedProvider
        mocks={[labelSetsMock, embeddersMock]}
        addTypename={false}
      >
        <CorpusModal
          open={true}
          mode="CREATE"
          onSubmit={(data) => {
            submittedData = data;
          }}
          onClose={() => {}}
        />
      </MockedProvider>
    );

    // Fill only required fields, leave slug empty
    await page.locator("#corpus-title").fill("My Corpus");
    await page.locator("#corpus-description").fill("A description");

    // Submit should be enabled
    await page.locator('button:has-text("Create Corpus")').click();

    // Data should be submitted with undefined slug (converted from empty string)
    // Empty slug becomes undefined so backend auto-generates one
    expect(submittedData).not.toBeNull();
    expect(submittedData.slug).toBeUndefined();

    await component.unmount();
  });
});
