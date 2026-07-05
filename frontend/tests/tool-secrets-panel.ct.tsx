// Playwright Component Test for the Agent Tools / Tool Secrets panel
// (issue #2117). Covers the not-configured empty state, saving a new
// configuration, and deleting an existing one after confirmation.
import React from "react";
import type { Page } from "@playwright/test";
import { test, expect } from "./utils/coverage";
import { SystemSettingsWrapper } from "./AdminComponentsTestWrapper";
import {
  GET_PIPELINE_SETTINGS,
  GET_PIPELINE_COMPONENTS,
  GET_SUPPORTED_MIME_TYPES,
  UPDATE_TOOL_SECRETS,
  DELETE_TOOL_SECRETS,
} from "../src/components/admin/system_settings/graphql";

// ---------------------------------------------------------------------------
// Minimal shared fixtures — SystemSettings needs all three queries to resolve
// before it renders past the loading state, but the tool secrets panel
// itself only cares about `toolsWithSecrets`.
// ---------------------------------------------------------------------------
const mockSettingsBase = {
  preferredParsers: {},
  preferredEmbedders: {},
  preferredThumbnailers: {},
  preferredEnrichers: {},
  componentSettings: {},
  defaultEmbedder: null,
  defaultFileConverter: null,
  defaultLlm: null,
  defaultReranker: null,
  toolsWithSecrets: [] as string[],
  enabledComponents: [],
  modified: "2024-01-15T10:30:00Z",
  modifiedBy: { id: "VXNlclR5cGU6MQ==", username: "admin" },
};

const mockComponents = {
  parsers: [],
  embedders: [],
  thumbnailers: [],
  llmProviders: [],
  fileConverters: [],
  rerankers: [],
  enrichers: [],
};

const mimeTypesMock = {
  request: { query: GET_SUPPORTED_MIME_TYPES },
  result: { data: { supportedMimeTypes: [] } },
};

const componentsMock = {
  request: { query: GET_PIPELINE_COMPONENTS },
  result: { data: { pipelineComponents: mockComponents } },
};

const settingsMock = (toolsWithSecrets: string[]) => ({
  request: { query: GET_PIPELINE_SETTINGS },
  result: {
    data: { pipelineSettings: { ...mockSettingsBase, toolsWithSecrets } },
  },
});

const waitForLoad = async (page: Page) => {
  await expect(
    page.locator("h1:has-text('Pipeline Configuration')")
  ).toBeVisible({ timeout: 5000 });
};

test.describe("ToolSecretsPanel", () => {
  test("shows 'Not configured' when the web search tool has no secrets", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <SystemSettingsWrapper
        mocks={[settingsMock([]), componentsMock, mimeTypesMock]}
      />
    );
    await waitForLoad(page);

    const panel = page.locator('[data-testid="tool-secrets-panel"]');
    await expect(panel).toBeVisible();
    await expect(panel.locator("text=Not configured")).toBeVisible();
    // No delete button until something is configured.
    await expect(
      panel.locator("button:has-text('Remove Configuration')")
    ).toHaveCount(0);

    await component.unmount();
  });

  test("filling in provider + API key and saving calls updateToolSecrets with the correct variables", async ({
    mount,
    page,
  }) => {
    const saveMock = {
      request: {
        query: UPDATE_TOOL_SECRETS,
        variables: {
          toolKey: "tool:web_search",
          secrets: { api_key: "brave-secret-key" },
          settings: { provider: "brave" },
          merge: true,
        },
      },
      result: {
        data: {
          updateToolSecrets: {
            ok: true,
            message: "Tool settings updated for 'tool:web_search'.",
            toolsWithSecrets: ["tool:web_search"],
          },
        },
      },
    };
    const refetch = settingsMock(["tool:web_search"]);

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[
          settingsMock([]),
          componentsMock,
          mimeTypesMock,
          saveMock,
          refetch,
        ]}
      />
    );
    await waitForLoad(page);

    const panel = page.locator('[data-testid="tool-secrets-panel"]');

    // Provider defaults to "brave" (first option), so no need to change it —
    // but exercise the select to prove it's wired, then set it back.
    const providerSelect = panel.locator("#tool-secrets-provider");
    await expect(providerSelect).toHaveValue("brave");

    await panel.locator("#tool-secrets-api-key").fill("brave-secret-key");
    await panel.locator("button:has-text('Save')").click();

    await expect(
      page.locator("text=Web search tool configured successfully")
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });

  test("delete button calls deleteToolSecrets after confirmation", async ({
    mount,
    page,
  }) => {
    const deleteMock = {
      request: {
        query: DELETE_TOOL_SECRETS,
        variables: { toolKey: "tool:web_search" },
      },
      result: {
        data: {
          deleteToolSecrets: {
            ok: true,
            message: "Tool settings deleted for 'tool:web_search'.",
            toolsWithSecrets: [],
          },
        },
      },
    };
    const refetch = settingsMock([]);

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[
          settingsMock(["tool:web_search"]),
          componentsMock,
          mimeTypesMock,
          deleteMock,
          refetch,
        ]}
      />
    );
    await waitForLoad(page);

    const panel = page.locator('[data-testid="tool-secrets-panel"]');
    await expect(panel.locator("text=Configured").first()).toBeVisible();

    await panel.locator("button:has-text('Remove Configuration')").click();

    // Confirmation banner appears; the destructive action requires a second click.
    await expect(
      panel.locator("text=Are you sure you want to remove")
    ).toBeVisible();
    await panel.locator("button:has-text('Confirm Delete')").click();

    await expect(
      page.locator("text=Web search tool configuration removed")
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });

  test("save failure (ok=false) surfaces the server-provided message", async ({
    mount,
    page,
  }) => {
    const saveMock = {
      request: {
        query: UPDATE_TOOL_SECRETS,
        variables: {
          toolKey: "tool:web_search",
          secrets: { api_key: "brave-secret-key" },
          settings: { provider: "brave" },
          merge: true,
        },
      },
      result: {
        data: {
          updateToolSecrets: {
            ok: false,
            message: "Invalid API key format.",
            toolsWithSecrets: [],
          },
        },
      },
    };

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[settingsMock([]), componentsMock, mimeTypesMock, saveMock]}
      />
    );
    await waitForLoad(page);

    const panel = page.locator('[data-testid="tool-secrets-panel"]');
    await panel.locator("#tool-secrets-api-key").fill("brave-secret-key");
    await panel.locator("button:has-text('Save')").click();

    await expect(page.locator("text=Invalid API key format.")).toBeVisible({
      timeout: 5000,
    });

    await component.unmount();
  });

  test("save failure without a server message falls back to a generic message", async ({
    mount,
    page,
  }) => {
    const saveMock = {
      request: {
        query: UPDATE_TOOL_SECRETS,
        variables: {
          toolKey: "tool:web_search",
          secrets: { api_key: "brave-secret-key" },
          settings: { provider: "brave" },
          merge: true,
        },
      },
      result: {
        data: {
          updateToolSecrets: { ok: false, message: null, toolsWithSecrets: [] },
        },
      },
    };

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[settingsMock([]), componentsMock, mimeTypesMock, saveMock]}
      />
    );
    await waitForLoad(page);

    const panel = page.locator('[data-testid="tool-secrets-panel"]');
    await panel.locator("#tool-secrets-api-key").fill("brave-secret-key");
    await panel.locator("button:has-text('Save')").click();

    await expect(
      page.locator("text=Failed to update tool secrets")
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });

  test("network error while saving surfaces the error message", async ({
    mount,
    page,
  }) => {
    const saveMock = {
      request: {
        query: UPDATE_TOOL_SECRETS,
        variables: {
          toolKey: "tool:web_search",
          secrets: { api_key: "brave-secret-key" },
          settings: { provider: "brave" },
          merge: true,
        },
      },
      error: new Error("backend unavailable"),
    };

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[settingsMock([]), componentsMock, mimeTypesMock, saveMock]}
      />
    );
    await waitForLoad(page);

    const panel = page.locator('[data-testid="tool-secrets-panel"]');
    await panel.locator("#tool-secrets-api-key").fill("brave-secret-key");
    await panel.locator("button:has-text('Save')").click();

    await expect(
      page.locator("text=/Error updating tool secrets:/")
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });

  test("delete failure (ok=false) surfaces the server-provided message", async ({
    mount,
    page,
  }) => {
    const deleteMock = {
      request: {
        query: DELETE_TOOL_SECRETS,
        variables: { toolKey: "tool:web_search" },
      },
      result: {
        data: {
          deleteToolSecrets: {
            ok: false,
            message: "Cannot remove: tool is in use.",
            toolsWithSecrets: ["tool:web_search"],
          },
        },
      },
    };

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[
          settingsMock(["tool:web_search"]),
          componentsMock,
          mimeTypesMock,
          deleteMock,
        ]}
      />
    );
    await waitForLoad(page);

    const panel = page.locator('[data-testid="tool-secrets-panel"]');
    await panel.locator("button:has-text('Remove Configuration')").click();
    await panel.locator("button:has-text('Confirm Delete')").click();

    await expect(
      page.locator("text=Cannot remove: tool is in use.")
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });

  test("delete failure without a server message falls back to a generic message", async ({
    mount,
    page,
  }) => {
    const deleteMock = {
      request: {
        query: DELETE_TOOL_SECRETS,
        variables: { toolKey: "tool:web_search" },
      },
      result: {
        data: {
          deleteToolSecrets: {
            ok: false,
            message: null,
            toolsWithSecrets: ["tool:web_search"],
          },
        },
      },
    };

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[
          settingsMock(["tool:web_search"]),
          componentsMock,
          mimeTypesMock,
          deleteMock,
        ]}
      />
    );
    await waitForLoad(page);

    const panel = page.locator('[data-testid="tool-secrets-panel"]');
    await panel.locator("button:has-text('Remove Configuration')").click();
    await panel.locator("button:has-text('Confirm Delete')").click();

    await expect(
      page.locator("text=Failed to delete tool secrets")
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });

  test("network error while deleting surfaces the error message", async ({
    mount,
    page,
  }) => {
    const deleteMock = {
      request: {
        query: DELETE_TOOL_SECRETS,
        variables: { toolKey: "tool:web_search" },
      },
      error: new Error("backend unavailable"),
    };

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[
          settingsMock(["tool:web_search"]),
          componentsMock,
          mimeTypesMock,
          deleteMock,
        ]}
      />
    );
    await waitForLoad(page);

    const panel = page.locator('[data-testid="tool-secrets-panel"]');
    await panel.locator("button:has-text('Remove Configuration')").click();
    await panel.locator("button:has-text('Confirm Delete')").click();

    await expect(
      page.locator("text=/Error deleting tool secrets:/")
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });

  test("Cancel dismisses the delete confirmation banner without deleting", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <SystemSettingsWrapper
        mocks={[
          settingsMock(["tool:web_search"]),
          componentsMock,
          mimeTypesMock,
        ]}
      />
    );
    await waitForLoad(page);

    const panel = page.locator('[data-testid="tool-secrets-panel"]');
    await panel.locator("button:has-text('Remove Configuration')").click();
    await expect(
      panel.locator("text=Are you sure you want to remove")
    ).toBeVisible();

    await panel.locator("button:has-text('Cancel')").click();

    await expect(
      panel.locator("text=Are you sure you want to remove")
    ).toHaveCount(0);
    await expect(
      panel.locator("button:has-text('Remove Configuration')")
    ).toBeVisible();

    await component.unmount();
  });

  test("changing the provider select saves the newly-selected provider", async ({
    mount,
    page,
  }) => {
    const saveMock = {
      request: {
        query: UPDATE_TOOL_SECRETS,
        variables: {
          toolKey: "tool:web_search",
          secrets: { api_key: "tavily-secret-key" },
          settings: { provider: "tavily" },
          merge: true,
        },
      },
      result: {
        data: {
          updateToolSecrets: {
            ok: true,
            message: "Tool settings updated for 'tool:web_search'.",
            toolsWithSecrets: ["tool:web_search"],
          },
        },
      },
    };

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[settingsMock([]), componentsMock, mimeTypesMock, saveMock]}
      />
    );
    await waitForLoad(page);

    const panel = page.locator('[data-testid="tool-secrets-panel"]');
    await panel.locator("#tool-secrets-provider").selectOption("tavily");
    await expect(panel.locator("#tool-secrets-provider")).toHaveValue("tavily");

    await panel.locator("#tool-secrets-api-key").fill("tavily-secret-key");
    await panel.locator("button:has-text('Save')").click();

    await expect(
      page.locator("text=Web search tool configured successfully")
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });

  test("saving with a blank API key sends secrets: null (keeps the existing value)", async ({
    mount,
    page,
  }) => {
    const saveMock = {
      request: {
        query: UPDATE_TOOL_SECRETS,
        variables: {
          toolKey: "tool:web_search",
          secrets: null,
          settings: { provider: "brave" },
          merge: true,
        },
      },
      result: {
        data: {
          updateToolSecrets: {
            ok: true,
            message: "Tool settings updated for 'tool:web_search'.",
            toolsWithSecrets: ["tool:web_search"],
          },
        },
      },
    };

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[
          settingsMock(["tool:web_search"]),
          componentsMock,
          mimeTypesMock,
          saveMock,
        ]}
      />
    );
    await waitForLoad(page);

    const panel = page.locator('[data-testid="tool-secrets-panel"]');
    // API key field is left blank — saving should still fire, sending
    // secrets: null so the provider setting updates without clobbering the
    // already-configured key.
    await panel.locator("button:has-text('Save')").click();

    await expect(
      page.locator("text=Web search tool configured successfully")
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });
});
