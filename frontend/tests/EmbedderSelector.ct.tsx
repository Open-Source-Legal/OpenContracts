import { test, expect } from "./utils/coverage";
import { docScreenshot } from "./utils/docScreenshot";
import { EmbedderSelectorTestWrapper } from "./EmbedderSelectorTestWrapper";
import { GET_EMBEDDERS } from "../src/graphql/queries";

const embeddersMock = {
  request: { query: GET_EMBEDDERS },
  result: {
    data: {
      pipelineComponents: {
        embedders: [
          {
            name: "default_embedder",
            moduleName: "opencontractserver.pipeline.embedders.DefaultEmbedder",
            title: "Default Embedder",
            description: "Standard text embedding model",
            author: "OpenContracts",
            componentType: "embedder",
            inputSchema: null,
            vectorSize: 384,
            className: "DefaultEmbedder",
            enabled: true,
          },
          {
            name: "large_embedder",
            moduleName: "opencontractserver.pipeline.embedders.LargeEmbedder",
            title: "Large Embedder",
            description: "High-dimensional embedding model",
            author: "OpenContracts",
            componentType: "embedder",
            inputSchema: null,
            vectorSize: 1024,
            className: "LargeEmbedder",
            enabled: true,
          },
        ],
      },
    },
  },
};

// Duplicate mock for refetches
const embeddersMockRefetch = { ...embeddersMock };

test.describe("EmbedderSelector", () => {
  test("renders with placeholder when no embedder selected", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <EmbedderSelectorTestWrapper
        mocks={[embeddersMock, embeddersMockRefetch]}
      />
    );

    // Should show the header
    await expect(component.getByText("Preferred Embedder:")).toBeVisible();

    // Wait for data to load - placeholder should show
    await expect(component.locator(".oc-dropdown__placeholder")).toBeVisible({
      timeout: 5000,
    });
    await expect(component.locator(".oc-dropdown__placeholder")).toHaveText(
      "Choose a preferred embedder"
    );

    await docScreenshot(page, "widgets--embedder-selector--default");

    await component.unmount();
  });

  test("renders with selected embedder value", async ({ mount, page }) => {
    const component = await mount(
      <EmbedderSelectorTestWrapper
        preferredEmbedder="DefaultEmbedder"
        mocks={[embeddersMock, embeddersMockRefetch]}
      />
    );

    // Wait for loading to finish and the selected value to appear
    await expect(component.locator(".oc-dropdown__value")).toBeVisible({
      timeout: 5000,
    });
    await expect(component.locator(".oc-dropdown__value")).toHaveText(
      "Default Embedder"
    );

    await docScreenshot(page, "widgets--embedder-selector--with-selection");

    await component.unmount();
  });

  test("shows loading state", async ({ mount, page }) => {
    // Use a mock with a delay to observe loading state
    const delayedMock = {
      ...embeddersMock,
      delay: 30000, // long delay so we can see loading
    };

    const component = await mount(
      <EmbedderSelectorTestWrapper mocks={[delayedMock]} />
    );

    // The placeholder should indicate loading
    await expect(component.locator(".oc-dropdown__placeholder")).toHaveText(
      "Loading embedders...",
      { timeout: 5000 }
    );

    await component.unmount();
  });

  test("dropdown shows embedder options with descriptions", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <EmbedderSelectorTestWrapper
        mocks={[embeddersMock, embeddersMockRefetch]}
      />
    );

    // Wait for data to load
    await expect(component.locator(".oc-dropdown__placeholder")).toHaveText(
      "Choose a preferred embedder",
      { timeout: 5000 }
    );

    // Open the dropdown
    await component.locator(".oc-dropdown__trigger").click();

    // Menu should be visible (may be in portal)
    const menu = page.locator(".oc-dropdown__menu");
    await expect(menu).toBeVisible();

    // Should show both embedder options
    const options = menu.locator(".oc-dropdown__option");
    await expect(options).toHaveCount(2);

    await expect(options.filter({ hasText: "Default Embedder" })).toHaveCount(
      1
    );
    await expect(options.filter({ hasText: "Large Embedder" })).toHaveCount(1);

    await component.unmount();
  });

  test("filters out embedders disabled in pipeline settings", async ({
    mount,
    page,
  }) => {
    const mixedMock = {
      request: { query: GET_EMBEDDERS },
      result: {
        data: {
          pipelineComponents: {
            embedders: [
              {
                name: "default_embedder",
                moduleName:
                  "opencontractserver.pipeline.embedders.DefaultEmbedder",
                title: "Default Embedder",
                description: "Standard text embedding model",
                author: "OpenContracts",
                componentType: "embedder",
                inputSchema: null,
                vectorSize: 384,
                className: "DefaultEmbedder",
                enabled: true,
              },
              {
                name: "disabled_embedder",
                moduleName:
                  "opencontractserver.pipeline.embedders.DisabledEmbedder",
                title: "Disabled Embedder",
                description: "Should not appear in the dropdown",
                author: "OpenContracts",
                componentType: "embedder",
                inputSchema: null,
                vectorSize: 768,
                className: "DisabledEmbedder",
                enabled: false,
              },
            ],
          },
        },
      },
    };

    const component = await mount(
      <EmbedderSelectorTestWrapper mocks={[mixedMock, { ...mixedMock }]} />
    );

    await expect(component.locator(".oc-dropdown__placeholder")).toHaveText(
      "Choose a preferred embedder",
      { timeout: 5000 }
    );

    await component.locator(".oc-dropdown__trigger").click();

    const menu = page.locator(".oc-dropdown__menu");
    await expect(menu).toBeVisible();

    const options = menu.locator(".oc-dropdown__option");
    await expect(options).toHaveCount(1);
    await expect(options.filter({ hasText: "Default Embedder" })).toHaveCount(
      1
    );
    await expect(options.filter({ hasText: "Disabled Embedder" })).toHaveCount(
      0
    );

    await component.unmount();
  });
});
